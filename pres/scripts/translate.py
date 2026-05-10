#!/usr/bin/env python3
"""
Augment an OCR JSON with Simplified Chinese translations.

Strategy: send the full OCR JSON to claude as slide context, plus a
compact list of `{id, role, text}` elements to translate. Claude
returns `[{id, zh_text}, ...]`. We merge those translations into the
original elements as `zh_text` and `en_text` (en_text == text_logical).

Usage:
    python translate.py extracted.json --out overlay.json

As a module:
    from translate import translate_overlay
    overlay = translate_overlay(ocr_data)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "translate_zh.txt"
DEFAULT_TIMEOUT_SEC = 600


class ClaudeCLIError(RuntimeError):
    """Raised when the claude CLI fails or returns unparseable output."""


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json|JSON)?\s*\n(.*)\n```\s*$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_json_array(text: str) -> str:
    """Find the first balanced JSON array in the text and return it."""
    text = _strip_code_fences(text)
    if text.startswith("["):
        return text
    start = text.find("[")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text


# Pattern matches one `{"id": "...", "zh_text": "..."}` entry, where the
# closing `"}` must be followed by `,` or `]` (top-level comma or array
# close). The lookahead is what makes this robust to unescaped " inside
# the zh_text value: non-greedy `.*?` keeps extending until it finds a
# `"}` that's actually the entry boundary, not just any `"`.
_ENTRY_RE = re.compile(
    r'(\{\s*"id"\s*:\s*"[^"]+"\s*,\s*"zh_text"\s*:\s*")(.*?)("\s*\}\s*(?=[,\]]))',
    re.DOTALL,
)


def _repair_unescaped_quotes(text: str) -> str:
    """
    Best-effort repair for the most common translation-JSON failure: the
    model writing an ASCII " inside a zh_text value (e.g. to wrap a
    program name) without escaping it. We find each entry boundary by
    its trailing `"}` followed by `,` or `]`, then escape any stray "
    inside the value.
    """
    def _fix(m: re.Match) -> str:
        prefix, value, suffix = m.group(1), m.group(2), m.group(3)
        # Protect already-escaped \" so we don't double-escape.
        sentinel = "\x00ESCQ\x00"
        value = value.replace('\\"', sentinel)
        value = value.replace('"', '\\"')
        value = value.replace(sentinel, '\\"')
        return prefix + value + suffix

    return _ENTRY_RE.sub(_fix, text)


def _lenient_extract_pairs(text: str) -> list[dict]:
    """
    Last-resort recovery: walk the entry regex and pull out every
    `{id, zh_text}` we can find, regardless of overall JSON validity.
    """
    pairs: list[dict] = []
    id_re = re.compile(r'"id"\s*:\s*"([^"]+)"')
    for m in _ENTRY_RE.finditer(text):
        prefix = m.group(1)
        value = m.group(2)
        eid_match = id_re.search(prefix)
        if not eid_match:
            continue
        # Convert any embedded \" back to " in the recovered value.
        recovered = value.replace('\\"', '"')
        pairs.append({"id": eid_match.group(1), "zh_text": recovered})
    return pairs


def _run_claude(prompt: str, timeout: int) -> str:
    # --dangerously-skip-permissions matches extract_text.py and avoids
    # the CLI gating any incidental tool use (Read, etc.) in print mode.
    try:
        proc = subprocess.run(
            ["claude", "-p", "--dangerously-skip-permissions", prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ClaudeCLIError(
            "`claude` CLI not found on PATH. Install Claude Code and ensure "
            "`claude` is on your PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ClaudeCLIError(
            f"claude CLI timed out after {timeout}s during translation."
        ) from exc

    if proc.returncode != 0:
        raise ClaudeCLIError(
            f"claude CLI returned code {proc.returncode}.\n"
            f"stderr:\n{proc.stderr.strip()}"
        )
    return proc.stdout


def _build_prompt(ocr_data: dict, prompt_path: Path) -> tuple[str, list[dict]]:
    """
    Build the translation prompt. Returns (prompt_text, elements_to_translate).

    elements_to_translate is the list of compact {id, role, text} dicts in the
    same order as ocr_data["elements"].
    """
    base_prompt = prompt_path.read_text(encoding="utf-8")

    elements_to_translate: list[dict] = []
    for idx, el in enumerate(ocr_data.get("elements", [])):
        eid = el.get("id") or f"text_{idx + 1:03d}"
        role = el.get("role", "other")
        text = el.get("text_logical") or el.get("text_visible") or ""
        elements_to_translate.append({"id": eid, "role": role, "text": text})

    context_json = json.dumps(ocr_data, ensure_ascii=False, indent=2)
    elements_json = json.dumps(elements_to_translate, ensure_ascii=False, indent=2)

    full_prompt = (
        f"{base_prompt}\n\n"
        f"SLIDE_CONTEXT (full OCR output for context only — do not return this):\n"
        f"{context_json}\n\n"
        f"ELEMENTS (translate every entry, preserve order, return only the array):\n"
        f"{elements_json}\n"
    )
    return full_prompt, elements_to_translate


def translate_overlay(
    ocr_data: dict,
    prompt_path: Path = DEFAULT_PROMPT_PATH,
    timeout: int = DEFAULT_TIMEOUT_SEC,
) -> dict:
    """
    Return a new dict (deep copy) with `zh_text` and `en_text` injected
    into each element under `elements`.

    en_text is set from text_logical (falling back to text_visible).
    zh_text is set from the LLM's translation. If translation for an
    element is missing in the response, zh_text falls back to "" so the
    schema stays consistent.
    """
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Translation prompt not found: {prompt_path}")

    prompt, requested = _build_prompt(ocr_data, prompt_path)
    raw = _run_claude(prompt, timeout=timeout)
    cleaned = _extract_json_array(raw)

    translations: list | None = None
    try:
        translations = json.loads(cleaned)
    except json.JSONDecodeError:
        # Most common failure: model put unescaped " inside a zh_text.
        # Try repair, then strict re-parse.
        try:
            repaired = _repair_unescaped_quotes(cleaned)
            translations = json.loads(repaired)
        except json.JSONDecodeError:
            # Last resort: regex-extract whatever {id, zh_text} pairs we can.
            translations = _lenient_extract_pairs(cleaned)
            if not translations:
                raise ClaudeCLIError(
                    f"Failed to parse translation JSON even after repair.\n"
                    f"Raw output (first 1000 chars):\n{raw[:1000]}"
                )

    if not isinstance(translations, list):
        raise ClaudeCLIError("Translation output was not a JSON array.")

    by_id: dict[str, str] = {}
    for entry in translations:
        if not isinstance(entry, dict):
            continue
        eid = entry.get("id")
        zh = entry.get("zh_text", "")
        if isinstance(eid, str):
            by_id[eid] = zh if isinstance(zh, str) else ""

    # Build augmented copy.
    augmented: dict[str, Any] = json.loads(json.dumps(ocr_data, ensure_ascii=False))
    for idx, el in enumerate(augmented.get("elements", [])):
        eid = el.get("id") or f"text_{idx + 1:03d}"
        en = el.get("text_logical") or el.get("text_visible") or ""
        el["en_text"] = en
        el["zh_text"] = by_id.get(eid, "")

    augmented["translation"] = {
        "target_language": "zh-CN",
        "source_count": len(requested),
        "translated_count": sum(1 for v in by_id.values() if v),
    }
    return augmented


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Translate OCR JSON to Simplified Chinese.")
    parser.add_argument("ocr_json", type=Path, help="Path to extracted OCR JSON.")
    parser.add_argument("--out", type=Path, default=None, help="Where to write augmented JSON. Default: stdout.")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH, help="Override translation prompt path.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC, help="Claude CLI timeout in seconds.")
    args = parser.parse_args()

    try:
        ocr_data = json.loads(args.ocr_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR reading {args.ocr_json}: {exc}", file=sys.stderr)
        return 1

    try:
        overlay = translate_overlay(ocr_data, prompt_path=args.prompt, timeout=args.timeout)
    except (ClaudeCLIError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    payload = json.dumps(overlay, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
