"""Guarantee that every prose field in a trader_snapshot is populated
in both English and Simplified Chinese.

The trader-snapshot generator (companies_ai_public) instructs the LLM
to fill paired ``_en`` / ``_zh`` siblings for every prose field, but
"best effort" isn't good enough — a missing translation surfaces as
a null on the iOS / web UI and the user perceives the language toggle
as broken. This module enforces the invariant *after* generation:

1. Walk the snapshot, find every paired ``<base>_en`` / ``<base>_zh``.
2. If exactly one side is filled, translate it into the missing side
   via a single batched Claude Code call.
3. If both sides are empty but the legacy single-language
   ``<base>`` field is filled (back-compat shape from pre-bilingual
   generators), use it as the English-canonical value and translate
   to Chinese.
4. If both sides are empty and no legacy fallback exists, leave it —
   genuinely no data to translate.

The walker is schema-shape-agnostic: it discovers pairs at every depth
by name convention (``foo_en`` + ``foo_zh`` on the same dict). New
bilingual fields added to the schema get covered automatically.

Falls back to the original (still-null) snapshot if the translator
errors. Logs a warning so the gap is observable.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from . import claude_runner
from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

logger = logging.getLogger(__name__)


def ensure_bilingual_completeness(snapshot: dict) -> dict:
    """Fill any missing ``_en`` / ``_zh`` siblings in ``snapshot``.
    Mutates in place; also returns the snapshot for chaining.
    """
    if not isinstance(snapshot, dict):
        return snapshot

    # Pre-bilingual snapshots only have the legacy `<base>` keys —
    # no `_en` / `_zh` siblings exist at all, so the pair iterator
    # below would find nothing. Seed the missing sibling keys as None
    # so the iterator picks them up and the legacy → both-languages
    # promotion path can run.
    _seed_bilingual_keys(snapshot)

    # Collect work in three buckets: en→zh translations, zh→en
    # translations, and arrays (which need their own schema). The
    # `legacy_to_en_then_translate` case is handled here too: if both
    # _en and _zh are empty but the legacy field has content, populate
    # _en from legacy first, then queue an en→zh translation.
    str_en_to_zh: list[tuple[dict, str, str]] = []
    str_zh_to_en: list[tuple[dict, str, str]] = []
    arr_en_to_zh: list[tuple[dict, str, list[str]]] = []
    arr_zh_to_en: list[tuple[dict, str, list[str]]] = []

    for parent, base in _iter_pairs(snapshot):
        en_key = f"{base}_en"
        zh_key = f"{base}_zh"
        en_val = parent.get(en_key)
        zh_val = parent.get(zh_key)

        en_filled = _is_filled(en_val)
        zh_filled = _is_filled(zh_val)

        if en_filled and zh_filled:
            continue
        if not en_filled and not zh_filled:
            # Both empty — last hope is the legacy field.
            legacy = parent.get(base)
            if _is_filled(legacy):
                # Copy legacy to _en (English-canonical) and queue
                # translation to _zh.
                parent[en_key] = legacy
                en_val = legacy
                en_filled = True
            else:
                continue
        # Exactly one side is filled now. Translate to the other.
        if en_filled and not zh_filled:
            if isinstance(en_val, list):
                arr_en_to_zh.append((parent, zh_key, en_val))
            else:
                str_en_to_zh.append((parent, zh_key, en_val))
        elif zh_filled and not en_filled:
            if isinstance(zh_val, list):
                arr_zh_to_en.append((parent, en_key, zh_val))
            else:
                str_zh_to_en.append((parent, en_key, zh_val))

    if not (str_en_to_zh or str_zh_to_en or arr_en_to_zh or arr_zh_to_en):
        return snapshot

    if str_en_to_zh:
        _apply_translations(
            str_en_to_zh,
            _translate_strings(
                [v for _, _, v in str_en_to_zh],
                source="en", target="zh",
            ),
        )
    if str_zh_to_en:
        _apply_translations(
            str_zh_to_en,
            _translate_strings(
                [v for _, _, v in str_zh_to_en],
                source="zh", target="en",
            ),
        )
    if arr_en_to_zh:
        _apply_translations(
            arr_en_to_zh,
            _translate_arrays(
                [v for _, _, v in arr_en_to_zh],
                source="en", target="zh",
            ),
        )
    if arr_zh_to_en:
        _apply_translations(
            arr_zh_to_en,
            _translate_arrays(
                [v for _, _, v in arr_zh_to_en],
                source="zh", target="en",
            ),
        )

    return snapshot


# ---------- internals -------------------------------------------------


# Base-field names that are known to be bilingual anywhere they appear
# in a trader_snapshot. Pre-bilingual snapshots only carry the bare
# `<base>` key; the seeder below creates the `_en` / `_zh` siblings
# as None so the iterator + fill loop can promote and translate.
# Keep this list in sync with the bilingual schema in
# `companies_ai_public.py` and `docs/heat-card-v2.md` §7.
_BILINGUAL_BASES: frozenset[str] = frozenset({
    # Trader snapshot prose fields (non-heat).
    "trend",
    "breakout_signals",
    "analyst_consensus",
    "action",  # recent_rating_changes[*].action
    "from",
    "to",
    "title",
    "summary",
    "headline",
    # Heat card v2 — every section carries some subset.
    "label",
    "note",
    "regime",
    "quality_label",
    "confidence_note",
    "reasons",
    "drivers",
})


def _seed_bilingual_keys(node: Any) -> None:
    """Walk ``node`` recursively. For every dict that carries a key
    matching ``_BILINGUAL_BASES`` (the legacy / canonical single-
    language form), make sure the ``_en`` and ``_zh`` siblings exist —
    create them as None if missing. Idempotent.
    """
    if isinstance(node, dict):
        for base in _BILINGUAL_BASES:
            if base in node:
                node.setdefault(f"{base}_en", None)
                node.setdefault(f"{base}_zh", None)
        for v in node.values():
            _seed_bilingual_keys(v)
    elif isinstance(node, list):
        for v in node:
            _seed_bilingual_keys(v)


def _iter_pairs(node: Any) -> Iterator[tuple[dict, str]]:
    """Yield ``(parent_dict, base_key)`` for every dict that has both
    ``<base>_en`` and ``<base>_zh`` keys. Recurses through dicts +
    lists.
    """
    if isinstance(node, dict):
        en_bases = {k[:-3] for k in node if k.endswith("_en")}
        zh_bases = {k[:-3] for k in node if k.endswith("_zh")}
        for base in en_bases & zh_bases:
            yield node, base
        for v in node.values():
            yield from _iter_pairs(v)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_pairs(v)


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_is_filled(v) for v in value)
    return True


def _apply_translations(
    queue: list[tuple[dict, str, Any]],
    translations: list[Any],
) -> None:
    if len(translations) != len(queue):
        logger.warning(
            "trader_bilingual_fill: got %d translations for %d inputs — "
            "skipping fill to avoid misalignment",
            len(translations), len(queue),
        )
        return
    for (parent, key, _), translated in zip(queue, translations):
        # `None` is the "translator failed for this slot" signal — don't
        # overwrite the existing value (which is already None or the
        # original source). Leaving _zh / _en as None is preferable to
        # poisoning the slot with same-language text.
        if translated is None:
            continue
        parent[key] = translated


# Batch sizes — one item per Claude call. Earlier larger batches
# (6+) hit two failure modes on real data: 180-second timeouts and
# silent JSON truncation mid-Chinese-string. Single-item batches are
# reliable because each call's output is tiny (one short string in a
# `{"translations":["..."]}` envelope). The latency cost is real —
# ~5s × N items — but a half-translated card is worse than a slow
# refresh, and the worker runs in the background.
_STRING_BATCH_SIZE = 1
_ARRAY_BATCH_SIZE = 1


# Translation direction labels used inside the system prompt.
_DIRECTIONS = {
    ("en", "zh"): "English → Simplified Chinese",
    ("zh", "en"): "Simplified Chinese → English",
}


_SYSTEM_PROMPT_BASE = (
    "You translate trader / finance text {direction}. Preserve every "
    "ticker, firm name, product code, and number verbatim. Keep tone "
    "neutral and natural in the target language. Do not add or remove "
    "content. Output the JSON object only.\n\n"
    f"{INVESTMENT_RESEARCH_CHINESE_STYLE}"
)


def _translate_strings(
    values: list[str], *, source: str, target: str,
) -> list[str | None]:
    """Translate every string in ``values`` and return a list of the
    same length. Slots whose translation failed (parse error, length
    mismatch, no Claude CLI) come back as ``None`` so the caller
    leaves the existing value alone instead of poisoning it with
    same-language text.
    """
    if not values:
        return []
    if not claude_runner.is_available():
        logger.warning(
            "trader_bilingual_fill: claude CLI not on PATH — skipping fill"
        )
        return [None] * len(values)

    # Chunk so each Claude call returns a small response. A long
    # single batch can exceed Claude's output buffer and come back
    # truncated, which the JSON parser then rejects — and we'd silently
    # lose every translation. Smaller batches keep failures localized.
    if len(values) > _STRING_BATCH_SIZE:
        out: list[str | None] = []
        for i in range(0, len(values), _STRING_BATCH_SIZE):
            chunk = values[i : i + _STRING_BATCH_SIZE]
            out.extend(_translate_strings(chunk, source=source, target=target))
        return out

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "translations": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "required": ["translations"],
    }
    sys_prompt = _SYSTEM_PROMPT_BASE.format(
        direction=_DIRECTIONS[(source, target)],
    )
    payload = json.dumps({"items": values}, ensure_ascii=False)
    user_prompt = (
        "Translate every string in `items` and return them in the same "
        "order under `translations`. Lengths must match exactly.\n\n"
        f"INPUT:\n{payload}"
    )
    data, err = claude_runner.run_structured_prompt(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        schema=schema,
        name="trader_bilingual_fill_strings",
    )
    if err or not isinstance(data, dict):
        logger.warning(
            "trader_bilingual_fill: string translation %s→%s failed: %s",
            source, target, err,
        )
        return [None] * len(values)
    translations = data.get("translations")
    if not isinstance(translations, list) or len(translations) != len(values):
        logger.warning(
            "trader_bilingual_fill: string translation %s→%s returned "
            "unusable shape (got %d items for %d inputs)",
            source, target,
            len(translations) if isinstance(translations, list) else -1,
            len(values),
        )
        return [None] * len(values)
    return [str(t) if isinstance(t, str) and t.strip() else None
            for t in translations]


def _translate_arrays(
    values: list[list[str]], *, source: str, target: str,
) -> list[list[str] | None]:
    if not values:
        return []
    if not claude_runner.is_available():
        logger.warning(
            "trader_bilingual_fill: claude CLI not on PATH — skipping fill"
        )
        return [None] * len(values)

    if len(values) > _ARRAY_BATCH_SIZE:
        out: list[list[str] | None] = []
        for i in range(0, len(values), _ARRAY_BATCH_SIZE):
            chunk = values[i : i + _ARRAY_BATCH_SIZE]
            out.extend(_translate_arrays(chunk, source=source, target=target))
        return out

    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "required": ["translations"],
    }
    sys_prompt = _SYSTEM_PROMPT_BASE.format(
        direction=_DIRECTIONS[(source, target)],
    )
    payload = json.dumps({"items": values}, ensure_ascii=False)
    user_prompt = (
        "Each item in `items` is an array of strings. Translate every "
        "string in every array and return arrays of the SAME length and "
        "order under `translations`. Outer-array length must equal "
        f"{len(values)}; each inner-array length must equal its input.\n\n"
        f"INPUT:\n{payload}"
    )
    data, err = claude_runner.run_structured_prompt(
        system_prompt=sys_prompt,
        user_prompt=user_prompt,
        schema=schema,
        name="trader_bilingual_fill_arrays",
    )
    if err or not isinstance(data, dict):
        logger.warning(
            "trader_bilingual_fill: array translation %s→%s failed: %s",
            source, target, err,
        )
        return [None] * len(values)
    translations = data.get("translations")
    if not isinstance(translations, list) or len(translations) != len(values):
        return [None] * len(values)
    # Per-item length sanity. Misaligned shapes return None for that
    # slot so the caller leaves the source alone — never poisons a
    # _zh field with same-language text.
    fixed: list[list[str] | None] = []
    for src, dst in zip(values, translations):
        if (isinstance(dst, list)
                and len(dst) == len(src)
                and all(isinstance(x, str) and x.strip() for x in dst)):
            fixed.append([str(t) for t in dst])
        else:
            logger.warning(
                "trader_bilingual_fill: array translation length mismatch "
                "or empty item (%s → %s); leaving source slot None",
                len(src), (len(dst) if isinstance(dst, list) else "n/a"),
            )
            fixed.append(None)
    return fixed
