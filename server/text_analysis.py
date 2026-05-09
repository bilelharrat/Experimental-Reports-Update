"""OpenAI-backed analysis for external text content.

Given a chunk of article / document text, produce:
- a 2–3 sentence summary
- 3–7 key-point bullets
- detected source language (en / zh / other)
- a translation block in the other language (en↔zh) with the same summary +
  key-point shape, plus a full translation of the source text

Returns a dict suitable for storing on an external item. If OPENAI_API_KEY
isn't set or the call fails, returns a stub with `error` populated so the
caller can still persist the item without analysis.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("OPENAI_ANALYSIS_MODEL", "gpt-4.1")

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {
            "type": ["string", "null"],
            "description": "Concise display title in the source language.",
        },
        "summary": {"type": "string", "description": "2-3 sentence summary."},
        "key_points": {
            "type": "array",
            "items": {"type": "string"},
        },
        "language": {
            "type": "string",
            "enum": ["en", "zh", "other"],
            "description": "Detected source language.",
        },
        "translation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["en", "zh"],
                    "description": "Target language. Always opposite of source for en/zh.",
                },
                "title": {"type": ["string", "null"]},
                "summary": {"type": "string"},
                "key_points": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "full_text": {
                    "type": "string",
                    "description": "Full translation of the source content.",
                },
            },
            "required": ["language", "title", "summary", "key_points", "full_text"],
        },
    },
    "required": ["title", "summary", "key_points", "language", "translation"],
}


SYSTEM_PROMPT = (
    "You are an analyst processing news articles and external research for an "
    "investment-research dashboard. Read the source content and return:\n"
    "1. A concise 2–3 sentence summary in the source language.\n"
    "2. 3–7 key-point bullets capturing the most important facts/insights.\n"
    "3. The detected source language (en / zh / other).\n"
    "4. A translation block in the *other* language (English↔Chinese). The "
    "translation includes a translated title, translated summary, translated "
    "key points, and a full translation of the source content. If the source "
    "is neither English nor Chinese, translate to English. The translation "
    "should preserve nuance and technical terminology.\n\n"
    "Bullets should be terse and concrete (numbers, names, dates) — not "
    "marketing fluff. Don't invent details that aren't in the source. If the "
    "content is short, that's fine — return fewer bullets."
)


def _is_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def analyze(text: str, *, hint_title: str | None = None) -> dict:
    """Run analysis on `text`. Returns a dict with `summary`, `key_points`,
    `language`, `translation` (and `title` if the model produced one), or
    `{error: "..."}` on failure / no API key.
    """
    text = (text or "").strip()
    if not text:
        return {"error": "Empty text — nothing to analyze."}
    if not _is_available():
        return {
            "error": "OPENAI_API_KEY not set — analysis skipped.",
        }

    try:
        from openai import OpenAI
    except ImportError:
        return {"error": "openai package not installed."}

    user_prompt_lines = []
    if hint_title:
        user_prompt_lines.append(f"Page title (hint): {hint_title}")
    user_prompt_lines.append("Source content:")
    user_prompt_lines.append("---")
    user_prompt_lines.append(text)
    user_prompt_lines.append("---")
    user_prompt = "\n".join(user_prompt_lines)

    client = OpenAI()
    try:
        response = client.responses.create(
            model=DEFAULT_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "external_analysis",
                    "schema": ANALYSIS_SCHEMA,
                    "strict": True,
                }
            },
        )
    except Exception as exc:  # noqa: BLE001 — surface to caller
        msg = f"OpenAI analysis failed: {type(exc).__name__}: {exc}"
        logger.warning(msg)
        return {"error": msg}

    raw = getattr(response, "output_text", "")
    if not raw:
        return {"error": "OpenAI returned empty output."}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {"error": f"OpenAI returned non-JSON: {exc}"}
    return data
