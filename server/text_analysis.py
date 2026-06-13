"""External-text analysis — via Claude Code CLI.

Given a chunk of article / document text, produce:
- a 2–3 sentence summary
- 3–7 key-point bullets
- detected source language (en / zh / other)
- a translation block in the other language (en↔zh) with the same summary +
  key-point shape, plus a full translation of the source text

Returns a dict suitable for storing on an external item. On failure
returns ``{error: "..."}`` so the caller can still persist the item
without analysis.

All LLM calls go through ``claude_runner.run_structured_prompt`` — the
``claude`` CLI is the only LLM provider this codebase uses.
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from . import claude_runner
from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

logger = logging.getLogger(__name__)


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
        "source_traces": {
            "type": "array",
            "description": (
                "Up to five source-backed traces for important claims. Use the "
                "source locator labels exactly as provided, such as Page 3 or "
                "Slide 2."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": ["string", "null"]},
                    "locator": {"type": "string"},
                    "excerpt": {
                        "type": "string",
                        "description": "Short exact excerpt copied from the source.",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["claim", "locator", "excerpt", "confidence"],
            },
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
    "should preserve nuance and technical terminology.\n"
    "5. A `source_traces` array with up to five important claims grounded in "
    "the source. The source text may be labeled as [Page 3], [Slide 2], "
    "[Slide 2 notes], or [Document]. Use that label as `locator` and quote a "
    "short exact excerpt; do not paraphrase excerpts.\n\n"
    "When translating or summarizing into Chinese, apply this style guide:\n"
    f"{INVESTMENT_RESEARCH_CHINESE_STYLE}\n"
    "Bullets should be terse and concrete (numbers, names, dates) — not "
    "marketing fluff. Don't invent details that aren't in the source. If the "
    "content is short, that's fine — return fewer bullets."
)


def analyze(
    text: str,
    *,
    hint_title: str | None = None,
    progress=None,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Run analysis on `text` via Claude CLI.

    Returns a dict with ``summary``, ``key_points``, ``language``,
    ``translation`` (and ``title`` if the model produced one), or
    ``{error: "..."}`` on failure.
    """
    text = (text or "").strip()
    if not text:
        return {"error": "Empty text — nothing to analyze."}

    user_prompt_lines: list[str] = []
    if hint_title:
        user_prompt_lines.append(f"Page title (hint): {hint_title}")
    user_prompt_lines.append("Source content:")
    user_prompt_lines.append("---")
    user_prompt_lines.append(text)
    user_prompt_lines.append("---")
    user_prompt = "\n".join(user_prompt_lines)

    data, err = claude_runner.run_structured_prompt(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        schema=ANALYSIS_SCHEMA,
        name="external_analysis",
        timeout_sec=240,
        progress=progress,
        cancel_event=cancel_event,
    )
    if err is not None:
        logger.warning("text_analysis failed: %s", err)
        return {"error": err}
    return data
