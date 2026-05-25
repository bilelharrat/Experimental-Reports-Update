"""Add a Simplified-Chinese overlay to the parsed page model.

The art is language-free by construction, so a ZH deck reuses the exact
same images at zero extra image-gen cost — that is the whole point of
the hybrid pipeline. Only the coded overlay copy needs translating.

After ``bilingualize``, each overlay field on a page is a
``{"en": ..., "zh": ...}`` dict, which ``render._t`` already resolves
per locale. Untranslatable / empty fields stay as plain strings (which
``_t`` also accepts), so a translation failure degrades to EN-only
rather than blanking the page.

All LLM work goes through the Claude Code CLI via
``server.claude_runner`` — the project's required LLM runtime.
"""
from __future__ import annotations

import logging

from server import claude_runner
from server.chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

logger = logging.getLogger(__name__)

# Overlay fields the renderer actually paints. `content` is parsed but
# never displayed, so it is intentionally not translated.
_FIELDS = ("kicker", "headline", "dek", "footer")

_SYSTEM_PROMPT = (
    "You translate institutional-finance editorial copy from English to "
    "Simplified Chinese for a polished investment-memo slide deck. "
    "Translate naturally and concisely in a confident analyst register — "
    "this is display copy on a slide, not a literal gloss. Keep every "
    "company / product name (e.g. AlphaSense), ticker, financial acronym "
    "(ARR, IC, S&P 100, IPO), number, currency amount, and symbol "
    "verbatim. Preserve any leading ordinal and separator in a label "
    "exactly (e.g. \"01 · Verdict\" → \"01 · 结论\"). Do not add, drop, "
    "or reorder content. Output the JSON object only.\n\n"
    f"{INVESTMENT_RESEARCH_CHINESE_STYLE}"
)

_SCHEMA = {
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


def bilingualize(pages: list[dict], *, locales: list[str]) -> None:
    """If ``zh`` is among ``locales``, attach a Simplified-Chinese
    translation to every overlay field of every page, in place.

    One batched Claude Code call covers the whole deck (≈4 short
    strings × N pages). On any failure the pages are left as EN-only
    plain strings and a warning is logged — the deck still renders.
    """
    if "zh" not in locales:
        return

    # Flatten every non-empty overlay string into one ordered list so a
    # single call translates the whole deck; remember where each came
    # from so results map back unambiguously.
    slots: list[tuple[dict, str]] = []
    values: list[str] = []
    for p in pages:
        for f in _FIELDS:
            v = p.get(f)
            if isinstance(v, str) and v.strip():
                slots.append((p, f))
                values.append(v)

    if not values:
        return

    if not claude_runner.is_available():
        logger.warning(
            "report_visuals.translate: claude CLI not on PATH — "
            "ZH deck will fall back to English copy"
        )
        return

    import json

    payload = json.dumps({"items": values}, ensure_ascii=False)
    user_prompt = (
        "Translate every string in `items` to Simplified Chinese and "
        "return them in the same order under `translations`. The "
        "`translations` array length MUST equal "
        f"{len(values)}.\n\nINPUT:\n{payload}"
    )
    data, err = claude_runner.run_structured_prompt(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=_SCHEMA,
        name="report_visuals_translate",
    )
    if err or not isinstance(data, dict):
        logger.warning(
            "report_visuals.translate: ZH translation failed (%s) — "
            "falling back to English copy", err,
        )
        return

    out = data.get("translations")
    if not isinstance(out, list) or len(out) != len(values):
        logger.warning(
            "report_visuals.translate: ZH translation returned %s items "
            "for %d inputs — falling back to English copy",
            len(out) if isinstance(out, list) else "non-list", len(values),
        )
        return

    for (page, field), en, zh in zip(slots, values, out):
        zh_clean = zh.strip() if isinstance(zh, str) else ""
        # Per-slot guard: if a single string didn't translate, keep that
        # field EN-only rather than poisoning it with same-language text.
        page[field] = {"en": en, "zh": zh_clean or en}
