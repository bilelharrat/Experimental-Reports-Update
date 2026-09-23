"""Which engine answers Warren, and what happens when that one cannot.

Warren's questions go to the Claude CLI, which spends the Claude Code
subscription. When the subscription is out of usage ("You've hit your weekly
limit · resets 5pm"), the CLI is signed out, or the run fails, Gemini answers
the same question from the same conversation instead. Settings → Warren
reverses the order: Gemini first, Claude only when Gemini fails.

A usage limit also rests Claude for a while, so the next questions go straight
to Gemini instead of each paying for a CLI spawn that is bound to fail. Only a
limit rests it: a sign-in problem is fixed at the keyboard, and the next
question should find the fix.

The fallback is never silent, the same rule as ``ai_engine``: the stored turn
carries ``engine``, ``model`` and, when the first engine failed,
``fallback_reason``, and the Warren panel prints them under the answer.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from . import claude_runner, gemini_runner

logger = logging.getLogger(__name__)

ENGINES = ("claude", "gemini")
DEFAULT_ENGINE = "claude"

# How long a usage limit keeps Claude out of Warren's way: long enough that a
# run of questions does not respawn the CLI for each one, short enough that
# Claude is back soon after the limit lifts.
CLAUDE_REST_S = 15 * 60

# The conversation Gemini is shown: the newest exchanges, within a budget.
HISTORY_EXCHANGES = 12
HISTORY_CHARS = 24_000
# What Claude is told about exchanges Gemini answered while it was out.
CATCH_UP_EXCHANGES = 6
CATCH_UP_CHARS = 8_000
MAX_SOURCES = 5

# Said after a failed turn that carried files, because the usual advice —
# wait for the stand-in — does not apply: Gemini was never asked.
ATTACHED_FILES_NOTE = (
    "Warren needs Claude's eyes for an image or a scan, so this question did "
    "not fall back to Gemini. Ask again in a few minutes, or remove the file."
)

GEMINI_NOTE = (
    "\n\n## Tools in this session\n\n"
    "You cannot open the staged session files here, so the instructions about "
    "the Read tool do not apply. Answer from the workspace context in the "
    "message and, for anything current or outside it, from Google Search. "
    "When a question needs the dossier files, say that you cannot see them "
    "rather than guessing."
)

_rest_lock = threading.Lock()
_rest: dict[str, Any] = {"until": 0.0, "reason": ""}


def chosen() -> str:
    """The engine Warren asks first: the Settings choice, else Claude."""
    from . import product_store

    try:
        stored = product_store.warren_engine()
    except Exception:  # noqa: BLE001 — a settings read must never break an ask
        logger.warning("warren_engine: could not read the setting", exc_info=True)
        stored = None
    return stored if stored in ENGINES else DEFAULT_ENGINE


def claude_resting() -> str | None:
    """Claude's last usage-limit message while it rests, else None."""
    with _rest_lock:
        if time.monotonic() < _rest["until"]:
            return _rest["reason"] or "Claude hit its usage limit"
        return None


def _rest_claude(reason: str) -> None:
    with _rest_lock:
        _rest["until"] = time.monotonic() + CLAUDE_REST_S
        _rest["reason"] = reason


def reset() -> None:
    """Forget a rest. A server restart does the same."""
    with _rest_lock:
        _rest["until"] = 0.0
        _rest["reason"] = ""


def status() -> dict:
    """What Settings shows beside the choice."""
    return {
        "engine": chosen(),
        "gemini_available": gemini_runner.is_available(),
        "gemini_model": gemini_runner.default_model(),
        "claude_available": claude_runner.is_available(),
        "claude_resting": claude_resting(),
    }


# ---- the conversation -------------------------------------------------------


def exchanges(turns: list[dict]) -> list[dict]:
    """Answered questions, oldest first, as ``{question, answer, engine}``.

    A question whose answer failed has no place in the transcript: its
    "answer" is an error message, and keeping the question alone would put
    two questions in a row. So does the question being answered now, which
    is already stored when the worker runs.
    """
    pairs: list[dict] = []
    question: str | None = None
    for turn in turns:
        role = turn.get("role")
        text = str(turn.get("text") or "").strip()
        if role == "user":
            question = text or None
        elif role == "assistant":
            if question and text and not turn.get("error"):
                pairs.append(
                    {
                        "question": question,
                        "answer": text,
                        "engine": turn.get("engine") or "claude",
                    }
                )
            question = None
    return pairs


def _newest(pairs: list[dict], *, count: int, chars: int) -> list[dict]:
    """The newest ``count`` pairs that fit in ``chars``, oldest first."""
    kept: list[dict] = []
    used = 0
    for pair in reversed(pairs[-count:]):
        used += len(pair["question"]) + len(pair["answer"])
        if kept and used > chars:
            break
        kept.append(pair)
    kept.reverse()
    return kept


def catch_up_block(turns: list[dict]) -> str:
    """What Gemini said since Claude last answered, to lead Claude's prompt.

    Claude resumes its own CLI session, which never saw the turns Gemini
    answered while it was out. Without this, a follow-up to one of those
    answers would reach a Claude with no idea what had been said.
    """
    since: list[dict] = []
    for pair in reversed(exchanges(turns)):
        if pair["engine"] == "claude":
            break
        since.append(pair)
    if not since:
        return ""
    since.reverse()
    lines = [
        "## Earlier in this chat",
        "",
        "Gemini answered these while you were unavailable. You have not seen "
        "them; treat them as part of this conversation.",
        "",
    ]
    for pair in _newest(since, count=CATCH_UP_EXCHANGES, chars=CATCH_UP_CHARS):
        lines += [f"Q: {pair['question']}", f"A: {pair['answer']}", ""]
    return "\n".join(lines).rstrip() + "\n\n"


# ---- Gemini's answer ---------------------------------------------------------


def _with_sources(text: str, meta: dict) -> str:
    """The reply, with the pages a grounded answer read linked under it."""
    sources = [
        source
        for source in (meta.get("sources") or [])
        if isinstance(source, dict) and source.get("url")
    ][:MAX_SOURCES]
    if not meta.get("grounded") or not sources:
        return text
    links = " · ".join(
        f"[{source.get('title') or source['url']}]({source['url']})" for source in sources
    )
    return f"{text}\n\nSources: {links}"


def ask_gemini(
    *,
    system_prompt: str,
    turns: list[dict],
    question: str,
    progress,
    cancel_event: threading.Event | None = None,
) -> dict:
    """One Warren answer from Gemini, in ``run_console_ask``'s outcome shape.

    ``turns`` is the session's stored transcript and ``question`` the prompt
    Claude would have been sent, workspace context included. The call does
    not watch ``cancel_event``; a Stop pressed meanwhile discards the reply.
    """
    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "subtype": "error", "text": "",
                "error": "Interrupted (user_cancelled)",
                "interrupt_reason": "user_cancelled"}
    progress.emit("stage", stage="starting", message="Asking Gemini")
    history = [
        (pair["question"], pair["answer"])
        for pair in _newest(exchanges(turns), count=HISTORY_EXCHANGES, chars=HISTORY_CHARS)
    ]
    started = time.monotonic()
    text, meta, error = gemini_runner.run_chat(
        system_prompt=system_prompt + GEMINI_NOTE,
        history=history,
        user_prompt=question,
        name="warren",
    )
    usage = meta.get("usage") or {}
    base = {
        "model": meta.get("model"),
        "usage": usage,
        "cost_usd": meta.get("cost_usd"),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    if cancel_event is not None and cancel_event.is_set():
        return {"ok": False, "subtype": "error", "text": "",
                "error": "Interrupted (user_cancelled)",
                "interrupt_reason": "user_cancelled", **base}
    if error is not None:
        progress.emit("error", error=error)
        return {"ok": False, "subtype": "error", "text": "", "error": error, **base}
    text = _with_sources(str(text), meta)
    progress.emit(
        "done",
        text=text,
        usage=usage,
        cost_usd=meta.get("cost_usd"),
        engine="gemini",
        model=meta.get("model"),
    )
    return {"ok": True, "subtype": "success", "text": text,
            "sources": meta.get("sources") or [], **base}


# ---- choosing and falling back ----------------------------------------------


class _HeldProgress:
    """A progress sink that holds back an engine's terminal ``error``.

    The ask stream ends at the first ``error`` event, so letting the first
    engine's failure through would close it before the second engine
    answered. ``answer`` emits the one terminal event itself. Also notes the
    model a Claude run reports at start-up, which its outcome leaves out.
    """

    def __init__(self, progress):
        self._progress = progress
        self.model: str | None = None

    def emit(self, type_: str, **fields: Any) -> None:
        if type_ == "error":
            return
        if type_ == "claude_action" and fields.get("action") == "init" and fields.get("model"):
            self.model = str(fields["model"])
        self._progress.emit(type_, **fields)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._progress, name)


def _combined_error(failures: list[tuple[str, str]]) -> str:
    """One message naming every engine that failed, each once."""
    reasons: dict[str, str] = {}
    for engine, reason in failures:
        reasons[engine] = reason
    if len(reasons) == 1:
        return next(iter(reasons.values()))
    return " · ".join(f"{engine.capitalize()}: {reason}" for engine, reason in reasons.items())


def answer(
    *,
    run_claude: Callable[[Any], dict],
    run_gemini: Callable[[Any], dict],
    progress,
    require_claude: bool = False,
) -> dict:
    """Answer one Warren question, the second engine standing in for the first.

    ``run_claude`` and ``run_gemini`` take a progress sink and return an
    outcome in ``claude_runner.run_console_ask``'s shape. Returns that shape
    plus ``engine``, ``model`` and, when the first engine failed,
    ``fallback_reason``. A Stop ends the turn wherever it lands; the other
    engine is never asked to answer a question the analyst withdrew.

    ``require_claude`` is for a question carrying files: only Claude opens
    what is staged beside it, so Gemini is not asked. An answer about a
    document it cannot see reads like any other answer, which is the one
    failure worth refusing outright.
    """
    first = chosen()
    order = ["claude", "gemini"] if first == "claude" else ["gemini", "claude"]
    failures: list[tuple[str, str]] = []
    resting = claude_resting()
    if require_claude:
        order = ["claude"]
    elif first == "claude" and resting and gemini_runner.is_available():
        # Straight to Gemini: another CLI spawn would fail the same way.
        order = ["gemini", "claude"]
        failures.append(("claude", resting))

    held = _HeldProgress(progress)
    outcome: dict | None = None
    for engine in order:
        if engine == "gemini" and not gemini_runner.is_available():
            # Unconfigured is only worth reporting when Gemini was the choice;
            # as a stand-in it just means there is none.
            if first == "gemini":
                failures.append(("gemini", "no Gemini API key configured"))
            continue
        if failures:
            progress.emit(
                "claude_action",
                action="fallback",
                engine=engine,
                reason=failures[-1][1][:300],
            )
        run = run_claude if engine == "claude" else run_gemini
        outcome = dict(run(held) or {})
        outcome["engine"] = engine
        if engine == "claude" and held.model and not outcome.get("model"):
            outcome["model"] = held.model
        if outcome.get("ok") or outcome.get("interrupt_reason") == "user_cancelled":
            break
        reason = str(outcome.get("error") or "No answer came back")
        failures.append((engine, reason))
        if engine == "claude" and claude_runner.provider_limit_reason(reason):
            _rest_claude(reason)
            logger.warning(
                "warren_engine: Claude is out of usage (%s); Gemini answers for %d min",
                reason,
                CLAUDE_REST_S // 60,
            )

    if outcome is None:
        outcome = {"ok": False, "subtype": "error", "text": "", "usage": {}, "cost_usd": None}
    if outcome.get("ok"):
        if outcome["engine"] == "claude":
            reset()  # it answered, so whatever limit rested it has lifted
        earlier = [reason for engine, reason in failures if engine != outcome["engine"]]
        if earlier:
            outcome["fallback_reason"] = earlier[0]
        return outcome

    if outcome.get("interrupt_reason") == "user_cancelled":
        error = str(outcome.get("error") or "Interrupted (user_cancelled)")
    else:
        error = _combined_error(failures) if failures else "No answer came back"
        if require_claude:
            error = f"{error} {ATTACHED_FILES_NOTE}"
    outcome["error"] = error
    progress.emit("error", error=error, interrupt_reason=outcome.get("interrupt_reason"))
    return outcome
