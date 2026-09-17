"""Engine selection for the research surfaces that run on Gemini Flash.

Three surfaces — the founder/team dossier, the daily desk note, and the
company news sweep — run on Gemini Flash with Claude as the fallback. This
module owns that policy so the call sites stay about their own domain.

The fallback is deliberately **not** silent: every call returns a ``meta``
dict recording which engine actually produced the answer and, when Gemini
was skipped or failed, why. Call sites persist that onto their payload so a
degraded answer is visible in the UI and in the stored record rather than
looking like a normal Gemini result.

``BSH_AI_ENGINE`` picks the policy:
- ``gemini`` (default) — Gemini first, Claude on failure.
- ``gemini-only`` — Gemini only; a failure is an error, no Claude spend.
- ``claude`` — Claude only, exactly the pre-Gemini behavior.
"""
from __future__ import annotations

import logging
import os

from . import claude_runner, gemini_runner

logger = logging.getLogger(__name__)

POLICIES = ("gemini", "gemini-only", "claude")
DEFAULT_POLICY = "gemini"


def policy() -> str:
    raw = str(os.environ.get("BSH_AI_ENGINE") or "").strip().lower()
    return raw if raw in POLICIES else DEFAULT_POLICY


def available() -> bool:
    """Whether the configured policy has an engine that can actually run.

    Callers that gate a background loop on "is a model installed" must ask
    this rather than `claude_runner.is_available()`: with a Gemini key and
    no Claude CLI the answer is yes, and the pre-Gemini check would have
    silently kept the loop switched off.
    """
    chosen = policy()
    if chosen == "claude":
        return claude_runner.is_available()
    if chosen == "gemini-only":
        return gemini_runner.is_available()
    return gemini_runner.is_available() or claude_runner.is_available()


def _meta(
    engine: str,
    *,
    model: str | None = None,
    sources: list[dict] | None = None,
    queries: list[str] | None = None,
    fallback_reason: str | None = None,
) -> dict:
    return {
        "engine": engine,
        "model": model,
        "sources": sources or [],
        "queries": queries or [],
        # Whether the answer was actually backed by web searches. False for
        # the Claude fallback (it reports none) and for a Gemini answer that
        # skipped the search tool.
        "grounded": False,
        "fallback_reason": fallback_reason,
    }


def structured(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str,
    timeout_sec: int = 180,
    gemini_model: str | None = None,
    thinking_level: str | None = None,
    claude_model: str | None = None,
    claude_effort: str | None = None,
) -> tuple[dict | None, dict, str | None]:
    """Text-in / JSON-out with no web access. Returns ``(data, meta, error)``."""
    chosen = policy()
    gemini_error: str | None = None

    if chosen != "claude":
        if gemini_runner.is_available():
            data, error = gemini_runner.run_structured_prompt(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                name=name,
                timeout_sec=timeout_sec,
                model=gemini_model,
                thinking_level=thinking_level,
            )
            if error is None and isinstance(data, dict):
                return data, _meta(
                    "gemini", model=gemini_model or gemini_runner.default_model()
                ), None
            gemini_error = error or "gemini returned no object"
        else:
            gemini_error = "no Gemini API key configured"
        if chosen == "gemini-only":
            return None, _meta("gemini", fallback_reason=gemini_error), gemini_error
        logger.warning("ai_engine: %s falling back to Claude — %s", name, gemini_error)

    data, error = claude_runner.run_structured_prompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        name=name,
        timeout_sec=timeout_sec,
        model=claude_model,
        effort=claude_effort,
        tools="",
    )
    meta = _meta("claude", model=claude_model, fallback_reason=gemini_error)
    if error is not None or not isinstance(data, dict):
        return None, meta, error or "Empty response"
    return data, meta, None


def grounded(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str,
    gemini_timeout_sec: int = 240,
    claude_timeout_sec: int = 900,
    gemini_model: str | None = None,
    thinking_level: str | None = None,
) -> tuple[dict | None, dict, str | None]:
    """Web-grounded research. Returns ``(data, meta, error)``.

    Gemini grounds with its ``google_search`` tool and reports the source
    URIs it used; the Claude fallback is a WebSearch/WebFetch CLI run, which
    is far slower and reports no machine-readable sources — ``meta["sources"]``
    is empty in that case, and callers should not present it as audited.
    """
    chosen = policy()
    gemini_error: str | None = None

    if chosen != "claude":
        if gemini_runner.is_available():
            data, meta, error = gemini_runner.run_grounded_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                schema=schema,
                name=name,
                timeout_sec=gemini_timeout_sec,
                model=gemini_model,
                thinking_level=thinking_level,
            )
            if error is None and isinstance(data, dict):
                engine_meta = _meta(
                    "gemini",
                    model=meta.get("model"),
                    sources=meta.get("sources"),
                    queries=meta.get("queries"),
                )
                engine_meta["grounded"] = bool(meta.get("grounded"))
                return data, engine_meta, None
            gemini_error = error or "gemini returned no object"
        else:
            gemini_error = "no Gemini API key configured"
        if chosen == "gemini-only":
            return None, _meta("gemini", fallback_reason=gemini_error), gemini_error
        logger.warning(
            "ai_engine: grounded %s falling back to Claude — %s", name, gemini_error
        )

    data, error = claude_runner.run_web_research_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        name=name,
        timeout_sec=claude_timeout_sec,
    )
    meta = _meta("claude", fallback_reason=gemini_error)
    if error is not None or not isinstance(data, dict):
        return None, meta, error or "Empty response"
    return data, meta, None
