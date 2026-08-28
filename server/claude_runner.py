"""Run Claude Code (the `claude` CLI) as a subprocess for LLM jobs.

Why this instead of direct API SDK calls:
- Uses the user's existing Claude Code subscription / token allowance.
- Gives us file-system observability — Claude writes a `progress.md` to the
  job's work directory as it processes each slide, so we have a durable
  trail and can tail it for granular progress.
- The `stream-json` output format yields one event per assistant turn /
  tool call / tool result, which we translate into our existing
  ProgressLog so the SSE feed stays granular (per-slide, per-tool).
- The native `--json-schema` flag validates the final structured summary
  for free; no manual JSON cleanup needed.

Public entry points:
- run_summary()         — bilingual deck summary (PDF/PPTX → JSON).
- run_company_search()  — company deep search using WebSearch/WebFetch.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
import weakref
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import job_progress
from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE
from .risk_workbench import company_risk_context

logger = logging.getLogger(__name__)

# Every claude CLI subprocess is registered here so a server shutdown can
# reap the whole fleet. The CLI runs with start_new_session=True (so a
# cancelled parent doesn't orphan its Bash-tool children), which also means
# nothing kills those sessions automatically when uvicorn exits — without
# this registry a dev restart leaves live `claude` processes burning tokens
# with no consumer. WeakSet: finished/reaped Popen objects drop out on GC.
_LIVE_CLAUDE_PROCS: "weakref.WeakSet[subprocess.Popen]" = weakref.WeakSet()
_LIVE_CLAUDE_PROCS_LOCK = threading.Lock()


def _popen_claude(*args, **kwargs) -> subprocess.Popen:
    """subprocess.Popen + registration in the live-process registry.

    Every claude CLI spawn in this module must go through this helper so
    `terminate_live_claude_procs` can reap it at shutdown.
    """
    proc = subprocess.Popen(*args, **kwargs)
    with _LIVE_CLAUDE_PROCS_LOCK:
        _LIVE_CLAUDE_PROCS.add(proc)
    return proc


def terminate_live_claude_procs() -> int:
    """Terminate every still-running claude subprocess group. Returns the
    number of processes that needed termination. Called from the server's
    shutdown path (and safe to call any time)."""
    with _LIVE_CLAUDE_PROCS_LOCK:
        procs = list(_LIVE_CLAUDE_PROCS)
    killed = 0
    for proc in procs:
        if proc.poll() is None:
            killed += 1
            _terminate_process_group(proc, grace_s=2.0)
    if killed:
        logger.info("shutdown: terminated %d live claude subprocess(es)", killed)
    return killed


atexit.register(terminate_live_claude_procs)


def _terminate_process_group(proc: subprocess.Popen, *, grace_s: float = 2.0) -> None:
    """Terminate a subprocess and its children when we own its session."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except Exception:
        pass
    if proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            return
    try:
        proc.wait(timeout=grace_s)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except Exception:
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            return
    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        pass


def is_available() -> bool:
    """True if `claude` is on PATH."""
    return shutil.which("claude") is not None


def claude_path() -> str | None:
    return shutil.which("claude")


_PROVIDER_LIMIT_MARKERS = (
    "usage limit",
    "rate limit",
    "quota",
    "too many requests",
    "429",
    "limit reached",
    "daily limit",
    "weekly limit",
    "try again later",
    "overloaded",
    "session limit",
    "resets ",
    "reset at",
    "retry after",
)


_TRANSIENT_CLAUDE_ERROR_MARKERS = (
    "socket connection was closed unexpectedly",
    "socket closed",
    "connection reset",
    "connection aborted",
    "connection closed",
    "network error",
    "fetch failed",
    "failed to fetch",
    "econnreset",
    "etimedout",
    "ehostunreach",
    "enetworkdown",
    "enetworkunreach",
    "epipe",
    "tls handshake",
    "stalled after",
    "without output",
)


def provider_limit_reason(
    value: Any, *, include_bare_claude_exit: bool = False
) -> str | None:
    """Return text if it looks like a provider quota / rate-limit failure."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    lowered = text.lower()
    if any(marker in lowered for marker in _PROVIDER_LIMIT_MARKERS):
        return text
    if include_bare_claude_exit and "claude exited 1" in lowered:
        return text
    return None


def transient_claude_error_reason(value: Any) -> str | None:
    """Return text if a Claude CLI failure looks safe to retry once."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if provider_limit_reason(text):
        return None
    lowered = text.lower()
    if any(marker in lowered for marker in _TRANSIENT_CLAUDE_ERROR_MARKERS):
        return text
    return None


def is_transient_claude_error(value: Any) -> bool:
    return transient_claude_error_reason(value) is not None


def _extract_claude_output_message(text: str | None) -> str | None:
    if not text or not text.strip():
        return None
    stripped = text.strip()
    candidates = [stripped, *reversed(stripped.splitlines())]
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            for key in ("error", "message", "result"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return stripped


def _subprocess_output_tail(*parts: str | None, limit: int = 600) -> str:
    messages = []
    seen = set()
    for part in parts:
        message = _extract_claude_output_message(part)
        if message and message not in seen:
            messages.append(message)
            seen.add(message)
    text = "\n".join(messages)
    return text[-limit:] if text else ""


def _claude_exit_error(
    returncode: int | None, *output_parts: str | None, limit: int = 600
) -> str:
    tail = _subprocess_output_tail(*output_parts, limit=limit)
    base = f"claude exited {returncode}"
    return f"{base}: {tail}" if tail else base


def health_check(*, timeout_sec: int = 60) -> dict:
    """Run a tiny one-shot prompt against `claude` and report what happened.

    Returns a dict with `ok` plus diagnostic fields suitable for an HTTP
    health endpoint. Never raises — always returns a structured result.
    """
    import time

    if not is_available():
        return {
            "ok": False,
            "available": False,
            "path": None,
            "error": (
                "`claude` not on PATH. Install with `npm install -g "
                "@anthropic-ai/claude-code` and run `claude` once to log in."
            ),
        }

    path = claude_path()

    # Best-effort version probe.
    version: str | None = None
    try:
        v = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if v.returncode == 0:
            version = v.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        version = f"(version probe failed: {exc})"

    started = time.monotonic()
    try:
        proc = subprocess.run(
            [
                path,
                "-p",
                "Reply with exactly: BSH analyst online.",
                "--output-format",
                "json",
                "--no-session-persistence",
            ],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "error": f"claude timed out after {timeout_sec}s",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "error": f"{type(exc).__name__}: {exc}",
        }

    duration_ms = int((time.monotonic() - started) * 1000)

    parsed_stdout: dict | None = None
    try:
        maybe_data = json.loads(proc.stdout or "{}")
        if isinstance(maybe_data, dict):
            parsed_stdout = maybe_data
    except json.JSONDecodeError:
        parsed_stdout = None

    if proc.returncode != 0:
        error = (
            _extract_claude_output_message(proc.stdout)
            if parsed_stdout and parsed_stdout.get("is_error")
            else None
        ) or _claude_exit_error(proc.returncode, proc.stderr, proc.stdout)
        result = {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "duration_ms": duration_ms,
            "error": error,
            "api_error_status": (
                parsed_stdout.get("api_error_status") if parsed_stdout else None
            ),
        }
        stderr_tail = (proc.stderr or "").strip()
        if stderr_tail:
            result["stderr_tail"] = stderr_tail[-600:]
        return result

    if parsed_stdout is None:
        return {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "duration_ms": duration_ms,
            "error": "claude returned non-JSON output",
            "stdout_preview": (proc.stdout or "")[:300],
        }

    data = parsed_stdout

    if data.get("is_error"):
        return {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "duration_ms": duration_ms,
            "error": (
                data.get("error")
                or data.get("result")
                or "claude returned an error result"
            ),
            "api_error_status": data.get("api_error_status"),
            "subtype": data.get("subtype"),
        }

    return {
        "ok": True,
        "available": True,
        "path": path,
        "version": version,
        "duration_ms": duration_ms,
        "model": data.get("model"),
        "session_id": data.get("session_id"),
        "result": (data.get("result") or "").strip(),
        "cost_usd": data.get("total_cost_usd"),
        "usage": data.get("usage"),
    }


def _drain_stderr(proc: subprocess.Popen, log: list[str]) -> None:
    """Background thread that buffers stderr so a long stderr can't deadlock
    the subprocess."""
    if proc.stderr is None:
        return
    for line in proc.stderr:
        log.append(line)


_SLIDE_LINE_RE = re.compile(
    r"^\s*-\s*slide\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE
)


# Matches an ASCII `"` that's clearly INSIDE a JSON string body — i.e. its
# neighbors are word-like characters, not JSON structural punctuation. A
# valid JSON quote is always adjacent to whitespace, `,`, `:`, `[`, `]`,
# `{`, or `}` on at least one side. If neither neighbor is one of those,
# the quote is almost certainly a stray emphasis quote inside a CJK or
# mixed-script value (e.g. `"iOS/Android"叙事` or `司"战`) that needs
# escaping.
_BAD_QUOTE_RE = re.compile(r'(?<=[^\s,:\[\]{}])"(?=[^\s,:\[\]{}])')


def _parse_json_tolerant(text: str) -> dict | None:
    """`json.loads(text)`, with a single-pass repair for unescaped ASCII
    quotes used as inline emphasis inside string values (most often around
    CJK terms). Returns None if even the repair doesn't parse.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    candidate = _BAD_QUOTE_RE.sub(r'\\"', text)
    if candidate == text:
        return None
    try:
        result = json.loads(candidate)
        logger.warning(
            "claude_runner: salvaged broken JSON by escaping unescaped "
            "emphasis quotes (%d substitutions)",
            (len(candidate) - len(text)),
        )
        return result
    except json.JSONDecodeError:
        return None


def _scan_progress_for_slides(text: str, progress, state: dict) -> None:
    """Scan a chunk of progress.md content for `- Slide N: ...` bullets.

    Emits slide_extracted only for slides we haven't seen this job, advances
    the analyzing-stage counter, and flips to `translating` when the last
    expected slide has been observed.
    """
    seen: set[int] = state.setdefault("slides_seen", set())
    for line in text.splitlines():
        m = _SLIDE_LINE_RE.match(line)
        if not m:
            continue
        try:
            sn = int(m.group(1))
        except ValueError:
            continue
        if sn in seen:
            continue
        seen.add(sn)
        body_text = m.group(2).strip()[:160]
        progress.emit("slide_extracted", slide_no=sn, preview=body_text)

        page_count = state.get("page_count")
        progress.emit(
            "stage",
            stage="analyzing",
            message=(
                f"Analyzing slide {sn} of {page_count}"
                if page_count
                else f"Analyzing slide {sn}"
            ),
            slide_no=sn,
            slide_count=page_count,
        )
        if page_count and len(seen) >= page_count and not state.get("translating_emitted"):
            state["translating_emitted"] = True
            progress.emit(
                "stage",
                stage="translating",
                message="Composing bilingual translation",
            )


def _threads_for_tool_use(name: str, inp: dict, state: dict) -> list[str]:
    """Return composite-job thread labels for this Claude tool_use.

    Driven by `state["thread_map"]` (filename -> label). Memo runs usually
    write expected analysis files through Write/Edit, but Claude can also use
    Bash with shell redirection. Scanning for known artifact filenames keeps
    sub-task progress visible when the tool shape changes.
    """
    thread_map = state.get("thread_map")
    if not thread_map:
        return []

    found: list[str] = []

    def add(label: str | None) -> None:
        if label and label not in found:
            found.append(label)

    fp = str(inp.get("file_path") or "").replace("\\", "/")
    if fp:
        add(thread_map.get(fp.rsplit("/", 1)[-1]))

    haystack_parts: list[str] = []
    for key in ("command", "description", "path", "pattern"):
        value = inp.get(key)
        if isinstance(value, str):
            haystack_parts.append(value)
    if not found:
        try:
            haystack_parts.append(json.dumps(inp, ensure_ascii=False)[:20000])
        except Exception:
            pass
    haystack = "\n".join(haystack_parts).replace("\\", "/")
    for leaf, label in thread_map.items():
        if leaf in haystack:
            add(label)
    return found


def _tool_use_haystack(inp: dict) -> str:
    haystack_parts: list[str] = []
    for key in ("file_path", "command", "description", "path", "pattern"):
        value = inp.get(key)
        if isinstance(value, str):
            haystack_parts.append(value)
    try:
        haystack_parts.append(json.dumps(inp, ensure_ascii=False)[:20000])
    except Exception:
        pass
    return "\n".join(haystack_parts).replace("\\", "/")


def _memo_phase_for_tool_use(inp: dict) -> str | None:
    haystack = _tool_use_haystack(inp)
    if "logs/memo_package.json" in haystack or haystack.endswith("memo_package.json"):
        return _MEMO_PHASE4_THREAD
    if any(leaf in haystack for leaf in _MEMO_SYNTHESIS_FILES):
        return _MEMO_PHASE3_THREAD
    if any(leaf in haystack for leaf in _MEMO_PARALLEL_ANALYSIS_FILES):
        return _MEMO_PHASE2_THREAD
    return None


def _memo_phase_for_text(text: str) -> str | None:
    lowered = text.lower()
    if (
        "all inputs loaded" in lowered
        or "orthogonal analytical" in lowered
        or "parallel analysis" in lowered
        or "parallel passes" in lowered
    ):
        return _MEMO_PHASE2_THREAD
    if "synthesis complete" in lowered or "draft the full bilingual memo" in lowered:
        return _MEMO_PHASE4_THREAD
    return None


def _memo_package_progress_for_text(text: str) -> tuple[str, str] | None:
    lowered = text.lower()
    mentions_memo_package = "memo_package" in lowered or "memo package" in lowered
    if (
        mentions_memo_package
        and (
            "writing" in lowered
            or "write" in lowered
            or "author" in lowered
            or "creating" in lowered
            or "create" in lowered
            or "drafting" in lowered
            or "draft" in lowered
        )
    ):
        return (
            "memo_package_writing",
            "Writing memo package from existing analysis artifacts",
        )
    if (
        mentions_memo_package
        and (
            "validating" in lowered
            or "validation" in lowered
            or "quality check" in lowered
            or "quality checks" in lowered
            or "json now parses" in lowered
        )
    ):
        return (
            "memo_package_validating",
            "Validating memo package before rendering",
        )
    return None


def _emit_memo_package_progress_stage(
    progress,
    state: dict,
    *,
    stage: str,
    message: str,
    thread: str | None,
    **fields,
) -> None:
    emitted = state.setdefault("memo_package_progress_stages", set())
    if stage in emitted:
        return
    emitted.add(stage)
    payload = {"stage": stage, "message": message, **fields}
    if thread:
        payload["thread"] = thread
    progress.emit("stage", **payload)


_MEMO_OUTPUT_CONTENT_LIMIT = 16_000


def _trim_output_content(content: str) -> tuple[str, bool]:
    if len(content) <= _MEMO_OUTPUT_CONTENT_LIMIT:
        return content, False
    return content[:_MEMO_OUTPUT_CONTENT_LIMIT].rstrip(), True


def _memo_output_piece(
    *,
    tool_name: str,
    inp: dict,
    phase_label: str | None,
    thread_labels: list[str],
) -> dict[str, Any] | None:
    if tool_name == "Write":
        path = str(inp.get("file_path") or "")
        content = inp.get("content")
        operation = "write"
    elif tool_name == "Edit":
        path = str(inp.get("file_path") or "")
        content = inp.get("new_string")
        operation = "edit"
    else:
        return None
    if not path or not isinstance(content, str) or not content.strip():
        return None

    normalized_path = path.replace("\\", "/")
    leaf = normalized_path.rsplit("/", 1)[-1]
    known_artifact = (
        leaf in _MEMO_PARALLEL_ANALYSIS_FILES
        or leaf in _MEMO_SYNTHESIS_FILES
        or normalized_path.endswith("logs/memo_package.json")
    )
    if not known_artifact:
        return None

    visible_content, truncated = _trim_output_content(content)
    return {
        "path": path,
        "filename": leaf,
        "operation": operation,
        "phase": phase_label,
        "artifact": thread_labels[0] if thread_labels else phase_label,
        "content": visible_content,
        "content_chars": len(content),
        "truncated": truncated,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _emit_memo_output_piece(
    progress,
    *,
    piece: dict[str, Any] | None,
    thread_labels: list[str],
    phase_label: str | None,
) -> None:
    if not piece:
        return
    labels = thread_labels or ([phase_label] if phase_label else [])
    if not labels:
        return
    for label in labels:
        progress.emit("output_piece", **piece, thread=label)


def _emit_progress_thread_started(progress, state: dict, label: str) -> None:
    threads_started = state.setdefault("threads_started", set())
    if label in threads_started:
        return
    threads_started.add(label)
    progress.emit("thread_started", thread=label, title=label)


def _emit_progress_thread_finished(
    progress,
    state: dict,
    label: str,
    *,
    failed: bool = False,
    error: str | None = None,
) -> None:
    threads_finished = state.setdefault("threads_finished", set())
    if label in threads_finished:
        return
    threads_finished.add(label)
    fields: dict[str, Any] = {"thread": label}
    if error:
        fields["error"] = error
    progress.emit("thread_failed" if failed else "thread_finished", **fields)


def _active_phase_thread(progress, state: dict) -> str | None:
    label = state.get("phase_thread")
    if not label or state.get("phase_thread_closed"):
        return None
    _emit_progress_thread_started(progress, state, str(label))
    state["phase_thread_open"] = True
    return str(label)


def _current_phase_thread(progress, state: dict) -> str | None:
    active = state.get("active_phase_thread")
    if active:
        return str(active)
    return _active_phase_thread(progress, state)


def _close_phase_thread(progress, state: dict, *, failed: bool = False) -> None:
    label = state.get("phase_thread")
    if not label or state.get("phase_thread_closed"):
        return
    if state.get("phase_thread_open") or label in (state.get("threads_started") or ()):
        _emit_progress_thread_finished(progress, state, str(label), failed=failed)
    state["phase_thread_closed"] = True
    state["phase_thread_open"] = False


def _transition_memo_phase(progress, state: dict, next_label: str) -> None:
    current = state.get("active_phase_thread") or (
        state.get("phase_thread") if not state.get("phase_thread_closed") else None
    )
    current_order = _MEMO_PHASE_ORDER.get(str(current), 0)
    next_order = _MEMO_PHASE_ORDER.get(next_label, 0)
    if current == next_label:
        _emit_progress_thread_started(progress, state, next_label)
        state["active_phase_thread"] = next_label
        return
    if current and current_order and next_order and next_order > current_order:
        _emit_progress_thread_finished(progress, state, str(current))
        if current == state.get("phase_thread"):
            state["phase_thread_closed"] = True
            state["phase_thread_open"] = False
    if next_order > current_order + 1:
        for skipped_order in range(current_order + 1, next_order):
            skipped_label = _MEMO_PHASE_BY_ORDER.get(skipped_order)
            if not skipped_label:
                continue
            _emit_progress_thread_started(progress, state, skipped_label)
            _emit_progress_thread_finished(progress, state, skipped_label)
    if next_order >= current_order:
        _emit_progress_thread_started(progress, state, next_label)
        state["active_phase_thread"] = next_label


def emit_memo_phase_planned(progress, *, start_phase: int = 1) -> None:
    for item in _MEMO_PHASE_PLAN:
        if int(item.get("phase_index") or 0) < start_phase:
            continue
        progress.emit("thread_planned", **item)


def _process_event(event: dict, progress, state: dict) -> None:
    """Translate a stream-json event into our ProgressLog vocabulary.

    `state` is per-job mutable scratch — we use it to track the latest tool
    invocation so we can pair tool_result events back to their tool_use, plus
    which slides we've emitted so we can dedup and detect stage transitions.

    If `state["thread_map"]` is set (filename -> pass label), tool events
    that mention those files are tagged with `thread=<label>` so the
    JobLogModal can render them as composite/threaded sub-tasks.
    """
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        phase_thread = _active_phase_thread(progress, state)
        fields = {
            "action": "init",
            "session": event.get("session_id"),
            "model": event.get("model"),
            "cwd": event.get("cwd"),
            "tools": event.get("tools") or [],
        }
        if phase_thread:
            fields["thread"] = phase_thread
        progress.emit(
            "claude_action",
            **fields,
        )
        return
    if etype == "rate_limit_event":
        info = event.get("rate_limit_info") or {}
        phase_thread = _current_phase_thread(progress, state)
        fields = {
            "action": "rate_limit",
            "resets_at": info.get("resetsAt"),
        }
        if phase_thread:
            fields["thread"] = phase_thread
        progress.emit("claude_action", **fields)
        return
    if etype == "assistant":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    if "api error" in text.lower() or transient_claude_error_reason(text):
                        state["last_api_error_text"] = text[:1000]
                    if transient_claude_error_reason(text):
                        state["last_transient_error_text"] = text[:1000]
                    if state.get("resume_packaging"):
                        _transition_memo_phase(progress, state, _MEMO_PHASE4_THREAD)
                    elif state.get("memo_phase_tracking"):
                        phase_label = _memo_phase_for_text(text)
                        if phase_label:
                            _transition_memo_phase(progress, state, phase_label)
                    phase_thread = _current_phase_thread(progress, state)
                    package_progress = _memo_package_progress_for_text(text)
                    if package_progress and (
                        state.get("resume_packaging")
                        or phase_thread == _MEMO_PHASE4_THREAD
                    ):
                        stage, message = package_progress
                        _emit_memo_package_progress_stage(
                            progress,
                            state,
                            stage=stage,
                            message=message,
                            thread=phase_thread,
                        )
                    fields = {"action": "thinking", "text": text[:600]}
                    if phase_thread:
                        fields["thread"] = phase_thread
                    progress.emit(
                        "claude_action", **fields
                    )
            elif btype == "tool_use":
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                tool_id = block.get("id")
                if state.get("resume_packaging"):
                    thread_labels = []
                    phase_label = _MEMO_PHASE4_THREAD
                else:
                    thread_labels = _threads_for_tool_use(name, inp, state)
                    phase_label = (
                        _memo_phase_for_tool_use(inp)
                        if state.get("memo_phase_tracking")
                        else None
                    )
                if phase_label:
                    _transition_memo_phase(progress, state, phase_label)
                elif thread_labels:
                    _close_phase_thread(progress, state)
                if thread_labels or phase_label:
                    effective_thread_labels = []
                    if phase_label:
                        effective_thread_labels.append(phase_label)
                    effective_thread_labels.extend(
                        label for label in thread_labels
                        if label not in effective_thread_labels
                    )
                else:
                    phase_thread = _current_phase_thread(progress, state)
                    effective_thread_labels = [phase_thread] if phase_thread else []
                thread_label = (
                    effective_thread_labels[0] if effective_thread_labels else None
                )
                state["last_tool"] = {
                    "id": tool_id,
                    "name": name,
                    "thread": thread_label,
                    "threads": effective_thread_labels,
                    "artifact_threads": thread_labels,
                }
                # Track all in-flight tools by id so the user-message
                # handler can re-attach thread labels even when many
                # parallel tool calls are pending at once.
                in_flight = state.setdefault("in_flight", {})
                if tool_id:
                    in_flight[tool_id] = {
                        "name": name,
                        "thread": thread_label,
                        "threads": effective_thread_labels,
                        "artifact_threads": thread_labels,
                    }
                for started_label in effective_thread_labels:
                    _emit_progress_thread_started(progress, state, started_label)
                output_piece = (
                    _memo_output_piece(
                        tool_name=name,
                        inp=inp,
                        phase_label=phase_label,
                        thread_labels=thread_labels,
                    )
                    if state.get("memo_phase_tracking")
                    else None
                )
                if output_piece and str(output_piece.get("path") or "").replace(
                    "\\", "/"
                ).endswith("logs/memo_package.json"):
                    _emit_memo_package_progress_stage(
                        progress,
                        state,
                        stage="memo_package_write_started",
                        message="Writing structured memo package",
                        thread=phase_label or thread_label,
                        content_chars=output_piece.get("content_chars"),
                    )
                preview = ""
                if name == "Read":
                    preview = inp.get("file_path") or ""
                    if inp.get("pages"):
                        preview += f"  (pages={inp.get('pages')})"
                    if inp.get("offset") is not None or inp.get("limit") is not None:
                        preview += (
                            f"  (offset={inp.get('offset')}, limit={inp.get('limit')})"
                        )
                elif name == "Write":
                    fp = inp.get("file_path") or ""
                    body = inp.get("content") or ""
                    preview = f"{fp}  ({len(body)} chars)"
                    if fp.endswith("progress.md"):
                        _scan_progress_for_slides(body, progress, state)
                    elif fp.endswith("summary.json"):
                        if not state.get("structuring_emitted"):
                            state["structuring_emitted"] = True
                            progress.emit(
                                "stage",
                                stage="structuring",
                                message="Structuring final output",
                            )
                elif name == "Edit":
                    fp = inp.get("file_path") or ""
                    new_string = inp.get("new_string") or ""
                    old_string = inp.get("old_string") or ""
                    preview = f"{fp}  (+{max(0, len(new_string) - len(old_string))} chars)"
                    if fp.endswith("progress.md"):
                        # New slide bullets only appear in new_string by
                        # definition (old_string is anchor text already in
                        # the file), so scan the diff portion. Cheapest:
                        # scan all of new_string and let dedup handle the rest.
                        _scan_progress_for_slides(new_string, progress, state)
                elif name == "TodoWrite":
                    # Pull out the in_progress todo (or last pending) so the
                    # rail shows what Claude is *currently doing*, not the
                    # raw JSON dump truncated mid-string.
                    todos = inp.get("todos") or []
                    active = next(
                        (t for t in todos if t.get("status") == "in_progress"),
                        None,
                    )
                    if active:
                        preview = (
                            f"→ {active.get('activeForm') or active.get('content') or '?'}"
                        )
                    else:
                        done = sum(1 for t in todos if t.get("status") == "completed")
                        preview = f"updated todos ({done}/{len(todos)} done)"
                elif name == "Bash":
                    cmd = inp.get("command") or ""
                    desc = inp.get("description") or ""
                    preview = cmd if not desc else f"{desc} — {cmd}"
                elif name in ("Grep", "Glob"):
                    pat = inp.get("pattern") or ""
                    pth = inp.get("path") or ""
                    preview = pat + (f"  in {pth}" if pth else "")
                elif name in ("WebSearch", "WebFetch"):
                    preview = (
                        inp.get("query")
                        or inp.get("url")
                        or json.dumps(inp)
                    )
                elif name == "StructuredOutput":
                    if isinstance(inp, dict):
                        state["structured_output"] = inp
                    preview = json.dumps(inp, ensure_ascii=False)
                else:
                    preview = json.dumps(inp, ensure_ascii=False)
                emit_kwargs = {
                    "action": "tool_use",
                    "tool": name,
                    "preview": preview[:500],
                }
                if effective_thread_labels:
                    for label in effective_thread_labels:
                        progress.emit("claude_action", **emit_kwargs, thread=label)
                else:
                    progress.emit("claude_action", **emit_kwargs)
                _emit_memo_output_piece(
                    progress,
                    piece=output_piece,
                    thread_labels=thread_labels,
                    phase_label=phase_label,
                )
        return
    if etype == "user":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_result":
                # Prefer the in-flight map keyed by tool_use_id so parallel
                # calls attribute correctly. Fall back to the last-seen
                # tool for runners that don't track in_flight.
                tu_id = block.get("tool_use_id")
                in_flight = state.get("in_flight") or {}
                meta = in_flight.pop(tu_id, None) if tu_id else None
                if meta is None:
                    meta = state.get("last_tool") or {}
                tool = meta.get("name") or "?"
                thread_labels = list(meta.get("threads") or [])
                thread_label = meta.get("thread")
                if thread_label and thread_label not in thread_labels:
                    thread_labels.insert(0, thread_label)
                content = block.get("content")
                # Content can be a string or a list of blocks
                if isinstance(content, list):
                    text_pieces = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text_pieces.append(c.get("text") or "")
                    content_str = "\n".join(text_pieces)
                else:
                    content_str = content if isinstance(content, str) else ""
                tr_kwargs = {
                    "action": "tool_result",
                    "tool": tool,
                    "is_error": bool(block.get("is_error")),
                    "preview": (content_str or "")[:200],
                }
                if not tr_kwargs["is_error"]:
                    successful_artifacts = state.setdefault(
                        "successful_artifact_threads", set()
                    )
                    successful_artifacts.update(meta.get("artifact_threads") or [])
                if thread_labels:
                    for label in thread_labels:
                        progress.emit("claude_action", **tr_kwargs, thread=label)
                else:
                    progress.emit("claude_action", **tr_kwargs)
        return
    if etype == "result":
        is_error = bool(event.get("is_error"))
        phase_thread = _current_phase_thread(progress, state)
        fields = {
            "action": "result",
            "subtype": event.get("subtype"),
            "is_error": is_error,
            "error": (
                event.get("error")
                or event.get("result")
                if is_error
                else None
            ),
            "api_error_status": event.get("api_error_status"),
            "cost_usd": event.get("total_cost_usd"),
            "duration_ms": event.get("duration_ms"),
            "usage": event.get("usage"),
        }
        if phase_thread:
            fields["thread"] = phase_thread
        progress.emit(
            "claude_action",
            **fields,
        )
        return


SPEED_GRANULAR = "granular"
SPEED_FAST = "fast"
SPEED_AUTO = "auto"


def run_summary(
    *,
    work_dir: Path,
    source_path: Path,
    hint_title: str | None,
    schema: dict,
    quality_bar: str,
    page_count: int | None = None,
    speed: str = SPEED_AUTO,
    progress=None,
    timeout_sec: int = 1200,
) -> dict:
    """Spawn `claude -p` with a deck-summary prompt and return the parsed
    structured result.

    Layout under `work_dir`:
      - <source basename>   (the deck — Read by Claude)
      - progress.md         (Claude writes per-slide observations)
      - summary.json        (mirror of the final output)

    Returns the parsed summary dict on success, or `{error: "..."}` on any
    failure path. Pipeline stages and tool-uses are emitted to `progress`.
    """
    if not is_available():
        return {
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            )
        }
    if not source_path.exists():
        return {"error": f"Source file missing: {source_path.name}"}

    work_dir.mkdir(parents=True, exist_ok=True)

    # Stage the deck inside the work dir so Claude has filesystem access via
    # cwd + --add-dir without us having to allow-list the project root.
    # copy2 preserves mtime, so (size, mtime) equality means "same file";
    # comparing size alone let a same-size edited source reuse a stale copy.
    staged_deck = work_dir / source_path.name
    src_stat = source_path.stat()
    if (
        not staged_deck.exists()
        or (staged_deck.stat().st_size, staged_deck.stat().st_mtime)
        != (src_stat.st_size, src_stat.st_mtime)
    ):
        shutil.copy2(source_path, staged_deck)

    # Don't pre-create progress.md — Claude's tool stack requires that any
    # pre-existing file be Read before Write succeeds, which forced an
    # avoidable read+retry on the very first append. Letting Claude create
    # the file with its first Write skips that trap entirely.
    progress_md = work_dir / "progress.md"
    progress_md.unlink(missing_ok=True)
    summary_json = work_dir / "summary.json"
    summary_json.unlink(missing_ok=True)

    # Auto: fast for big decks (>30 pages), granular for small ones.
    resolved_speed = speed
    if speed == SPEED_AUTO:
        resolved_speed = SPEED_FAST if (page_count or 0) > 30 else SPEED_GRANULAR

    user_prompt = _build_prompt(
        deck_filename=source_path.name,
        hint_title=hint_title or source_path.name,
        page_count=page_count,
        quality_bar=quality_bar,
        speed=resolved_speed,
    )

    cmd = [
        claude_path() or "claude",
        "-p",
        user_prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--tools", "Read,Write,Edit",
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message=(
                "Processing with Claude (fast mode)"
                if resolved_speed == SPEED_FAST
                else "Processing with Claude"
            ),
            work_dir=str(work_dir),
            speed=resolved_speed,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    def _handle_event(event: dict, prog, state: dict) -> None:
        if prog:
            _process_event(event, prog, state)

    state: dict[str, Any] = {"page_count": page_count}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_handle_event,
        timeout_sec=timeout_sec,
        timeout_label="deck summary",
        # Slide-by-slide Reads/Writes produce a steady event stream; 300s of
        # silence means the CLI is genuinely wedged, not just thinking.
        silence_timeout_sec=300.0,
    )
    if stream_error:
        return {"error": stream_error}

    result_event = state.get("result_event")
    if not final_text and result_event:
        final_text = result_event.get("result")
    if not final_text:
        return {"error": "Claude produced no final result"}

    # Try the structured-output JSON first; if Claude wrote summary.json
    # alongside (it may, since the prompt encourages it), prefer that as a
    # tiebreaker since it's already validated by file write.
    parsed: dict | None = None
    for source_text in (
        summary_json.read_text(encoding="utf-8") if summary_json.exists() else None,
        final_text,
    ):
        if not source_text:
            continue
        data = _parse_json_tolerant(source_text)
        if isinstance(data, dict) and "exec_summary" in data:
            parsed = data
            break

    if parsed is None:
        return {
            "error": (
                "Claude returned output that didn't parse as the expected "
                "summary JSON. Check progress.md in the job directory for "
                "what it produced."
            )
        }

    if result_event:
        parsed["claude_cost_usd"] = result_event.get("total_cost_usd")
        parsed["claude_duration_ms"] = result_event.get("duration_ms")
    parsed["mode"] = "claude_code"
    return parsed


def _build_prompt(
    *,
    deck_filename: str,
    hint_title: str,
    page_count: int | None,
    quality_bar: str,
    speed: str = SPEED_GRANULAR,
) -> str:
    page_line = (
        f"The deck has {page_count} pages."
        if page_count
        else "The deck's exact page count is unknown — read until Read returns no more pages."
    )
    last_page = page_count or "N"
    if speed == SPEED_FAST:
        read_loop = f"""\
STAGE 2 — PER-SLIDE ANALYSIS (batched 8-page Reads, but per-slide bullets).
**Batch size = 8 pages max** — larger batches blow up token AND image-count
limits when pages render as images (which is common for picture-heavy
decks). Do NOT batch more than 8 pages per Read call.

  - Read ./{deck_filename} pages="1-8"
  - Read ./{deck_filename} pages="9-16"
  - ... continue in 8-page chunks; the final chunk can be shorter
    (e.g. pages="49-{last_page}") but must NEVER exceed 8 pages.

After EACH Read, append one bullet PER SLIDE in that chunk to
./progress.md (so 8 bullets after the first Read, etc.):

      - Slide 1: <observation>
      - Slide 2: <observation>
      ...

For the very first Read, ./progress.md does not exist — use the Write
tool with a header line plus your 8 bullets. For every subsequent
chunk, use Edit to append. Pick a unique string from the END of the
current file as `old_string`, set `new_string` to that same string +
"\\n- Slide N: …" lines for each new slide.

Each bullet is ONE line, factual, specific. Numbers, names, claims,
dates. Don't invent. If a slide is empty / decorative / a divider, say
so briefly ("- Slide N: section divider, 'Operations'").
"""
    else:
        read_loop = f"""\
STAGE 2 — PER-SLIDE ANALYSIS (one Read per page).
For EACH page from 1 to {last_page}, in order:

  a) Read ./{deck_filename} with `pages` set to a SINGLE page number, e.g.
     pages="1", then pages="2", then pages="3". One page per Read call —
     this is intentional, the operator wants per-page visibility.

  b) After each Read, append exactly one bullet to ./progress.md:
         - Slide N: <one specific observation, 80–160 chars>
     - For page 1, the file does NOT exist yet — use the Write tool.
       Start with a one-line header, then your first bullet:
            # Progress — {deck_filename}

            - Slide 1: <observation>
     - For page 2 and beyond, use the Edit tool. Pick a unique string
       from the END of the current file as `old_string` and set
       `new_string` to that same string + "\\n- Slide N: <observation>".

  c) Move to the next page. Don't skip pages.

The bullet is ONE line, factual, specific. Numbers, names, claims, dates.
Don't invent. If a slide is empty / decorative / a divider, say so briefly
("- Slide N: section divider, 'Operations'").
"""
    begin_line = (
        'Begin Stage 2 now. Read pages="1-8".'
        if speed == SPEED_FAST
        else 'Begin Stage 2 now. Read pages="1".'
    )
    return f"""\
You are analyzing a presentation deck for an investment-research dashboard.

The deck has been staged in your current working directory as: ./{deck_filename}
(Hint: titled "{hint_title}".)
{page_line}

WORKFLOW — exactly four stages. The operator is watching ./progress.md and
the live tool-call feed, so progress visibly.

STAGE 1 — INVENTORY (already done for you).
The local pre-pass already counted the slides, so no work needed here.

{read_loop}
STAGE 3 — TRANSLATE.
Once all {last_page} bullets are in progress.md, compose the bilingual
content. For every English string you'll emit (exec summary, section
titles, section bodies), prepare the matching 简体中文 rendering — natural
language, same facts, same numbers. Apply this Chinese style guide:
{INVESTMENT_RESEARCH_CHINESE_STYLE}

STAGE 4 — STRUCTURE OUTPUT.
Write the final JSON to ./summary.json using the Write tool. The schema
is attached to this run via --json-schema; both `exec_summary.en` /
`exec_summary.zh` and every `sections[*].title.{{en,zh}}` /
`body.{{en,zh}}` must be populated. `slide_refs` are integer 1-indexed
page numbers from the source deck. Then return the SAME JSON as your
final answer so the validator can confirm it.

JSON SAFETY (this is enforced by both you and the validator):
- Inside ANY string value (en OR zh), NEVER write a straight ASCII double
  quote (") unescaped. If you need to emphasize or quote a phrase, use
  single quotes ('iOS/Android of warfare') in English, and full-width
  Chinese quotes 「」 or "" in 简体中文 — never ASCII ".
- Use real newlines as \n inside strings, not literal line breaks.
- Validate the JSON in your head before Writing summary.json.

QUALITY BAR — every word earns its place:
{quality_bar}

{begin_line}
"""


# ---- Company deep search via WebSearch/WebFetch ----


def _process_search_event(event: dict, progress, state: dict) -> None:
    """Translate a stream-json event from a company-search run into
    progress.emit() calls. Mirrors _process_event but tuned for WebSearch
    and WebFetch tool use — so the live UI shows what Claude is actually
    looking up rather than just a spinner.
    """
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        progress.emit(
            "claude_action",
            action="init",
            session=event.get("session_id"),
            model=event.get("model"),
            tools=event.get("tools") or [],
        )
        progress.emit("stage", stage="searching", message="Searching the web")
        return
    if etype == "assistant":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    if "api error" in text.lower() or transient_claude_error_reason(text):
                        state["last_api_error_text"] = text[:1000]
                    if transient_claude_error_reason(text):
                        state["last_transient_error_text"] = text[:1000]
                    progress.emit(
                        "claude_action", action="thinking", text=text[:400]
                    )
            elif btype == "tool_use":
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                state["last_tool"] = {
                    "id": block.get("id"),
                    "name": name,
                }
                if name == "WebSearch":
                    preview = inp.get("query") or ""
                    state["search_count"] = state.get("search_count", 0) + 1
                elif name == "WebFetch":
                    preview = inp.get("url") or ""
                    state["fetch_count"] = state.get("fetch_count", 0) + 1
                elif name == "StructuredOutput":
                    # When `--json-schema` is in effect Claude emits the
                    # final structured payload via this tool call rather
                    # than the assistant `result` text. Capture it so the
                    # outer loop can prefer it as the parse target.
                    if isinstance(inp, dict):
                        state["structured_output"] = inp
                    preview = json.dumps(inp)[:200]
                else:
                    preview = json.dumps(inp)[:200]
                progress.emit(
                    "claude_action",
                    action="tool_use",
                    tool=name,
                    preview=preview[:300],
                )
        return
    if etype == "user":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_result":
                tool = state.get("last_tool", {}).get("name", "?")
                content = block.get("content")
                if isinstance(content, list):
                    text_pieces = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text_pieces.append(c.get("text") or "")
                    content_str = "\n".join(text_pieces)
                else:
                    content_str = content if isinstance(content, str) else ""
                progress.emit(
                    "claude_action",
                    action="tool_result",
                    tool=tool,
                    is_error=bool(block.get("is_error")),
                    preview=(content_str or "")[:200],
                )
        return
    if etype == "result":
        progress.emit(
            "claude_action",
            action="result",
            subtype=event.get("subtype"),
            cost_usd=event.get("total_cost_usd"),
            duration_ms=event.get("duration_ms"),
            usage=event.get("usage"),
        )
        return


def _start_stream_json_reader(proc: subprocess.Popen):
    """Read Claude stream-json stdout on a side thread so callers can enforce
    wall-clock and silence timeouts while waiting for the next line.
    """
    import queue as _queue

    events: _queue.Queue = _queue.Queue()

    def reader() -> None:
        try:
            stdout = proc.stdout
            if stdout is None:
                return
            for line in stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.put(json.loads(line))
                except json.JSONDecodeError:
                    continue
        finally:
            events.put(None)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    return events, thread


def _consume_stream_json_process(
    proc: subprocess.Popen,
    *,
    stderr_log: list[str],
    progress,
    state: dict,
    event_handler,
    timeout_sec: float,
    timeout_label: str,
    silence_timeout_sec: float = 120.0,
    cancel_event: threading.Event | None = None,
    stop_on_result: bool = False,
) -> tuple[str | None, str | None]:
    """Consume Claude stream-json without blocking forever on stdout.

    Returns ``(final_text, error)``. ``final_text`` prefers a captured
    StructuredOutput payload when present, matching the previous parser
    behavior.

    ``stop_on_result=True`` stops consuming at the first ``result`` event
    and reaps a lingering process instead of erroring — for skill runs
    where the CLI can keep the pipe open after its result.
    """
    import queue as _queue

    events, reader = _start_stream_json_reader(proc)
    start = time.monotonic()
    last_event_at = start
    final_text: str | None = None
    interrupted: str | None = None

    while True:
        now = time.monotonic()
        if cancel_event is not None and cancel_event.is_set():
            interrupted = "user_cancelled"
            break
        if now - start > timeout_sec:
            interrupted = f"{timeout_label} timed out after {timeout_sec:g}s"
            break
        if now - last_event_at > silence_timeout_sec:
            interrupted = (
                f"{timeout_label} stalled after {silence_timeout_sec:g}s "
                "without output"
            )
            break
        try:
            event = events.get(timeout=0.25)
        except _queue.Empty:
            if proc.poll() is not None and not reader.is_alive():
                break
            continue

        if event is None:
            break

        last_event_at = time.monotonic()
        try:
            event_handler(event, progress, state)
        except Exception:  # noqa: BLE001
            logger.exception("%s event handling failed", timeout_label)
        if event.get("type") == "result":
            state["result_event"] = event
            structured = state.get("structured_output")
            if isinstance(structured, dict):
                final_text = json.dumps(structured)
            else:
                final_text = event.get("result")
            if stop_on_result:
                break

    if interrupted is not None:
        _terminate_process_group(proc, grace_s=5.0)
        if progress is not None:
            progress.emit(
                "claude_action",
                action="interrupted",
                reason=interrupted,
            )
        return None, interrupted

    if stop_on_result and state.get("result_event") is not None:
        # The CLI can linger after emitting its result; give it a moment
        # then reap the whole group rather than failing a completed run.
        try:
            proc.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.warning(
                "%s subprocess kept running after result; terminating group",
                timeout_label,
            )
            _terminate_process_group(proc, grace_s=2.0)
        return final_text, None

    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc, grace_s=5.0)
        return None, f"{timeout_label} did not exit cleanly"

    if proc.returncode and proc.returncode != 0:
        result_event = state.get("result_event") or {}
        result_text = (
            result_event.get("result")
            if isinstance(result_event.get("result"), str)
            else None
        )
        return None, _claude_exit_error(
            proc.returncode,
            "".join(stderr_log[-20:]),
            state.get("last_transient_error_text"),
            state.get("last_api_error_text"),
            result_text,
        )

    return final_text, None


def run_company_search(
    *,
    query: str,
    schema: dict,
    system_prompt: str,
    max_results: int = 6,
    timeout_sec: int = 600,
    progress=None,
) -> tuple[list[dict] | None, str | None]:
    """Run a deep company search by spawning `claude -p` with WebSearch and
    WebFetch enabled. Returns ``(matches, error)`` mirroring the OpenAI
    helper in companies_ai.py — on success ``error`` is None.

    When ``progress`` is supplied (a ProgressLog), the function streams
    Claude's tool calls (WebSearch queries, WebFetch URLs, thinking text)
    via ``progress.emit("claude_action", ...)`` so the frontend can render
    a live transcript instead of a generic spinner.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not found on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and run `claude` "
            "once to authenticate."
        )

    work_dir = Path("/tmp") / f"bsh_company_search_{abs(hash(query)) % 10**8}"
    work_dir.mkdir(parents=True, exist_ok=True)

    user_prompt = (
        f"{system_prompt}\n\n"
        f"User query: {query}\n\n"
        f"Return up to {max_results} matches. Use the WebSearch tool "
        "aggressively to ground every field. Use WebFetch on official "
        "company pages, recent news articles, and SEC filings to verify "
        "specific numbers and dates before quoting them. Do NOT invent "
        "values — if a field can't be verified, return null for it.\n\n"
        "When you've gathered enough evidence, produce ONE final assistant "
        "message that is the JSON object satisfying the attached schema. "
        "No preamble, no markdown fences — just the JSON."
    )

    use_stream = progress is not None
    cmd = [
        claude_path() or "claude",
        "-p",
        user_prompt,
        "--output-format", "stream-json" if use_stream else "json",
    ]
    if use_stream:
        cmd.append("--verbose")
    cmd += [
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "WebSearch,WebFetch",
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]

    if not use_stream:
        # Single-shot path — no progress, no streaming.
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return None, f"claude search timed out after {timeout_sec}s"
        except FileNotFoundError as exc:
            return None, f"Failed to launch claude: {exc}"

        if proc.returncode != 0:
            return None, _claude_exit_error(
                proc.returncode, proc.stderr, proc.stdout
            )

        try:
            envelope = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            return None, f"claude returned non-JSON envelope: {exc}"
        final_text = (envelope.get("result") or "").strip()
        return _parse_search_result(final_text, max_results)

    # Streaming path — emit progress events as Claude works.
    try:
        proc_stream = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    stderr_log: list[str] = []
    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc_stream, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc_stream,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label="claude search",
    )
    if stream_error:
        return None, stream_error

    return _parse_search_result(final_text, max_results)


def run_public_company_snapshot(
    *,
    company_name: str,
    ticker: str,
    exchange: str | None,
    schema: dict,
    system_prompt: str,
    timeout_sec: int = 600,
    progress=None,
    focus_hint: str | None = None,
) -> tuple[dict | None, str | None]:
    """Spawn ``claude -p`` to produce one public-company trader snapshot.

    Always streams (so the AI rail can tail the run). Returns
    ``(snapshot, error)``; ``snapshot`` is the parsed dict on success.
    Uses the same WebSearch/WebFetch tool surface as the deep-search
    flow but with a snapshot-shaped JSON schema instead of the match-
    list shape.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not found on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and run `claude` "
            "once to authenticate."
        )

    exchange_line = f" on {exchange}" if exchange else ""
    focus_block = f"\n\n{focus_hint.strip()}" if focus_hint else ""
    user_prompt = (
        f"{system_prompt}\n\n"
        f"Target company: {company_name} ({ticker}){exchange_line}.\n\n"
        "Produce the snapshot now. Use WebSearch and WebFetch on Yahoo "
        "Finance, Nasdaq, the SEC, IR pages, and recent news sources. "
        "Output ONE JSON object matching the attached schema."
        f"{focus_block}"
    )

    # Per-snapshot work dir — Claude needs an --add-dir target even
    # though we don't expect any tool writes here. Suffix keeps parallel
    # per-section passes for the same ticker from colliding.
    suffix = ""
    if focus_hint:
        import hashlib

        suffix = "_" + hashlib.sha1(focus_hint.encode()).hexdigest()[:8]
    work_dir = Path("/tmp") / f"bsh_public_snapshot_{ticker.lower()}{suffix}"
    work_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        claude_path() or "claude",
        "-p", user_prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "WebSearch,WebFetch",
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]

    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    stderr_log: list[str] = []
    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label="claude snapshot",
    )
    if stream_error:
        return None, stream_error

    if not final_text:
        return None, "claude returned empty result"

    parsed = _parse_json_tolerant(final_text)
    if not isinstance(parsed, dict):
        # Try to recover from a fenced block.
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, "claude's final answer didn't parse as a JSON object"

    return parsed, None


def run_web_research_json(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str = "web_research",
    timeout_sec: int = 900,
    silence_timeout_sec: int = 120,
    progress=None,
    use_json_schema: bool = True,
) -> tuple[dict | None, str | None]:
    """Run a WebSearch/WebFetch-grounded Claude job and return strict JSON.

    This is the generic sibling of ``run_company_search`` and
    ``run_public_company_snapshot``: callers own the prompt + schema, while
    this helper owns CLI invocation, progress translation, and tolerant JSON
    parsing.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not found on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and run `claude` "
            "once to authenticate."
        )

    import hashlib

    key = hashlib.sha1(f"{name}\n{user_prompt}".encode("utf-8")).hexdigest()[:10]
    work_dir = Path("/tmp") / f"bsh_{name}_{key}"
    work_dir.mkdir(parents=True, exist_ok=True)

    schema_instruction = (
        "attached schema" if use_json_schema else "JSON schema included below"
    )
    schema_block = (
        ""
        if use_json_schema
        else "\n\nJSON schema:\n" + json.dumps(schema, ensure_ascii=False)
    )
    combined_prompt = (
        f"{system_prompt.strip()}\n\n"
        f"{user_prompt.strip()}\n\n"
        "Use WebSearch and WebFetch to verify current facts, prices, dates, "
        "and sources. Do not invent unavailable fields; use null where the "
        f"schema permits it. Output ONE JSON object matching the {schema_instruction}. "
        "No markdown fences, preamble, or commentary."
        f"{schema_block}"
    )

    cmd = [
        claude_path() or "claude",
        "-p", combined_prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "WebSearch,WebFetch",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if use_json_schema:
        cmd += ["--json-schema", json.dumps(schema)]

    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    stderr_log: list[str] = []
    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        silence_timeout_sec=silence_timeout_sec,
        timeout_label="claude web research",
    )
    if stream_error:
        return None, stream_error

    if not final_text:
        return None, "claude returned empty result"

    parsed = _parse_json_tolerant(final_text)
    if not isinstance(parsed, dict):
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, "claude's final answer didn't parse as a JSON object"

    return parsed, None


def _parse_search_result(
    final_text: str | None, max_results: int
) -> tuple[list[dict] | None, str | None]:
    if not final_text:
        return None, "claude returned empty result"
    parsed = _parse_json_tolerant(final_text)
    if parsed is None:
        return None, "claude's final answer didn't parse as JSON"
    if not isinstance(parsed, dict):
        return None, "claude's final answer wasn't a JSON object"
    matches = parsed.get("matches")
    if not isinstance(matches, list):
        return None, "claude's final answer is missing the `matches` array"
    return matches[:max_results], None


# ---- PDF translation (high-fidelity, structured) ----


PDF_TRANSLATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "detected_language": {
            "type": "string",
            "enum": ["en", "zh", "other"],
            "description": "Source language detected from the PDF.",
        },
        "target_language": {
            "type": "string",
            "enum": ["en", "zh"],
            "description": "Target language. Opposite of source for en/zh; en if source is other.",
        },
        "page_count": {"type": "integer"},
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "page": {"type": "integer"},
                    "blocks": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": [
                                        "heading",
                                        "paragraph",
                                        "list_item",
                                        "table_row",
                                        "quote",
                                        "caption",
                                    ],
                                },
                                "level": {
                                    "type": ["integer", "null"],
                                    "description": "1-3 for headings; null otherwise.",
                                },
                                "text": {
                                    "type": "string",
                                    "description": "Translated content. For table_row, this is a fallback display string; the structured cells go in `cells`.",
                                },
                                "cells": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string"},
                                    "description": "For table_row only: one entry per cell. Null otherwise.",
                                },
                            },
                            "required": ["type", "level", "text", "cells"],
                        },
                    },
                },
                "required": ["page", "blocks"],
            },
        },
    },
    "required": ["detected_language", "target_language", "page_count", "pages"],
}


def _process_pdf_translation_event(event: dict, progress, state: dict) -> None:
    """Translate stream-json events into progress.emit() calls for the
    PDF translation pipeline. Tracks per-page translation progress by
    watching Write/Edit calls against translation.json.
    """
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        progress.emit(
            "claude_action",
            action="init",
            session=event.get("session_id"),
            model=event.get("model"),
            tools=event.get("tools") or [],
        )
        progress.emit(
            "stage", stage="reading", message="Reading the PDF"
        )
        return
    if etype == "assistant":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    progress.emit("claude_action", action="thinking", text=text[:400])
            elif btype == "tool_use":
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                state["last_tool"] = {"id": block.get("id"), "name": name}
                preview = ""
                if name == "Read":
                    preview = inp.get("file_path") or ""
                    if inp.get("pages"):
                        preview += f"  (page {inp.get('pages')})"
                        # Track which page Claude is working on for stage updates.
                        try:
                            page_no = int(str(inp.get("pages")).split("-")[0])
                            state["current_page"] = page_no
                            page_count = state.get("page_count")
                            progress.emit(
                                "stage",
                                stage="translating",
                                message=(
                                    f"Translating page {page_no} of {page_count}"
                                    if page_count
                                    else f"Translating page {page_no}"
                                ),
                                page_no=page_no,
                                page_count=page_count,
                            )
                        except ValueError:
                            pass
                elif name in ("Write", "Edit"):
                    fp = inp.get("file_path") or ""
                    body = inp.get("content") or inp.get("new_string") or ""
                    preview = f"{fp}  ({len(body)} chars)"
                    if fp.endswith("translation.json") and not state.get("structuring_emitted"):
                        state["structuring_emitted"] = True
                        progress.emit(
                            "stage",
                            stage="structuring",
                            message="Finalizing translation",
                        )
                elif name == "StructuredOutput":
                    if isinstance(inp, dict):
                        state["structured_output"] = inp
                    preview = json.dumps(inp, ensure_ascii=False)
                else:
                    preview = json.dumps(inp)[:200]
                progress.emit(
                    "claude_action", action="tool_use", tool=name, preview=preview[:300]
                )
        return
    if etype == "user":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_result":
                tool = state.get("last_tool", {}).get("name", "?")
                content = block.get("content")
                if isinstance(content, list):
                    text_pieces = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            text_pieces.append(c.get("text") or "")
                    content_str = "\n".join(text_pieces)
                else:
                    content_str = content if isinstance(content, str) else ""
                progress.emit(
                    "claude_action",
                    action="tool_result",
                    tool=tool,
                    is_error=bool(block.get("is_error")),
                    preview=(content_str or "")[:200],
                )
        return
    if etype == "result":
        progress.emit(
            "claude_action",
            action="result",
            subtype=event.get("subtype"),
            cost_usd=event.get("total_cost_usd"),
            duration_ms=event.get("duration_ms"),
            usage=event.get("usage"),
        )
        return


def run_pdf_translation(
    *,
    pdf_path: Path,
    work_dir: Path,
    page_count: int | None = None,
    app_language: str | None = None,
    progress=None,
    timeout_sec: int = 1800,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Translate a PDF document end-to-end via Claude Code.

    Stages the PDF inside ``work_dir`` so Claude can Read it directly via
    its filesystem tool, instructs Claude to detect the source language,
    translate page-by-page preserving block structure (headings,
    paragraphs, list items, tables), and write the result to
    ``translation.json``. Returns the parsed JSON or ``{error: "..."}``.

    ``app_language`` is a hint about the user's preferred target ("en" or
    "zh"). Claude uses it as the default target unless the source is
    already in that language, in which case it translates to the opposite.
    """
    if not is_available():
        return {
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run `claude` "
                "once to authenticate."
            )
        }
    if not pdf_path.exists():
        return {"error": f"Source PDF missing: {pdf_path.name}"}

    work_dir.mkdir(parents=True, exist_ok=True)

    staged_pdf = work_dir / pdf_path.name
    if not staged_pdf.exists() or staged_pdf.stat().st_size != pdf_path.stat().st_size:
        shutil.copy2(pdf_path, staged_pdf)

    progress_md = work_dir / "progress.md"
    progress_md.unlink(missing_ok=True)
    translation_json = work_dir / "translation.json"
    translation_json.unlink(missing_ok=True)

    user_prompt = _build_pdf_translation_prompt(
        pdf_filename=pdf_path.name,
        page_count=page_count,
        app_language=app_language,
    )

    cmd = [
        claude_path() or "claude",
        "-p",
        user_prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--tools", "Read,Write,Edit",
        "--json-schema", json.dumps(PDF_TRANSLATION_SCHEMA),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Starting Claude Code translator",
            page_count=page_count,
        )

    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"error": f"Failed to launch claude: {exc}"}

    stderr_log: list[str] = []
    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {"page_count": page_count}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_pdf_translation_event,
        timeout_sec=timeout_sec,
        timeout_label="PDF translation",
        silence_timeout_sec=300.0,
        cancel_event=cancel_event,
    )
    if stream_error:
        return {"error": stream_error}

    if proc.returncode and proc.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return {
            "error": (
                f"claude exited {proc.returncode}"
                + (f": {tail[:600]}" if tail else "")
            )
        }

    parsed: dict | None = None
    for source_text in (
        translation_json.read_text(encoding="utf-8") if translation_json.exists() else None,
        final_text,
    ):
        if not source_text:
            continue
        data = _parse_json_tolerant(source_text)
        if isinstance(data, dict) and "pages" in data:
            parsed = data
            break

    if parsed is None:
        return {
            "error": (
                "Claude returned output that didn't parse as the expected "
                "translation JSON. Check translation.json in the work directory."
            )
        }

    result_event = state.get("result_event")
    if result_event:
        parsed["claude_cost_usd"] = result_event.get("total_cost_usd")
        parsed["claude_duration_ms"] = result_event.get("duration_ms")
    return parsed


def _build_pdf_translation_prompt(
    *,
    pdf_filename: str,
    page_count: int | None,
    app_language: str | None,
) -> str:
    page_line = (
        f"The PDF has {page_count} pages."
        if page_count
        else "Page count is unknown — read until Read returns no more pages."
    )
    target_hint = (
        f"The user's preferred target language is {app_language!r}. Use it as "
        "the target UNLESS the source is already in that language, in which "
        "case translate to the opposite (en↔zh). If the source is neither en "
        "nor zh, translate to English."
        if app_language in ("en", "zh")
        else "Auto-detect source language and translate to the opposite (en↔zh). "
        "If the source is neither, translate to English."
    )
    return f"""\
You are translating a PDF document for an investment-research dashboard.

The source PDF has been staged in your current working directory as: ./{pdf_filename}
{page_line}

LANGUAGE POLICY
{target_hint}

WORKFLOW

STAGE 1 — DETECT.
Read ./{pdf_filename} pages="1" to see the first page. Determine the source
language and the target language per the policy above.

STAGE 2 — PER-PAGE TRANSLATION.
For each page from 1 to N:
  a) Read ./{pdf_filename} pages="<N>" (one page per Read call).
  b) Identify the structural blocks on the page. For each block, classify it as:
       - heading (with level 1, 2, or 3)
       - paragraph
       - list_item (bulleted or numbered — strip the bullet/number)
       - table_row (split by columns into the `cells` array)
       - quote
       - caption (image/figure caption)
  c) Translate every block to the target language. Preserve numbers, dates,
     money amounts, URLs, and proper nouns (use widely-recognized target-
     language form for proper nouns ONLY when one exists; otherwise keep the
     original). Don't paraphrase — translate faithfully.
  d) Append a one-line entry to ./progress.md as you finish each page:
       - Page N: <count> blocks translated
     Use Write for the first append (file doesn't exist yet), Edit for the rest.

STAGE 3 — FINALIZE.
Write the complete structured translation to ./translation.json using the
attached --json-schema. Schema:
  - detected_language ("en" | "zh" | "other")
  - target_language ("en" | "zh")
  - page_count (integer)
  - pages: array of {{ page: int, blocks: [block, ...] }}

A block is {{ type, level (or null), text, cells (or null) }}. For table_row,
populate `cells` with the per-column translated strings AND set `text` to
the cells joined by " | " (so plain renderers still show something).

Then return the SAME JSON as your final assistant message so the validator
can confirm it.

QUALITY BAR
- Faithful translation, not paraphrase.
- Preserve every block — don't drop content.
- Headings stay headings; lists stay lists; tables stay structured.
- Numbers, dates, money, URLs, ISO codes, model numbers: unchanged.
- When translating into Chinese, apply this style guide:
{INVESTMENT_RESEARCH_CHINESE_STYLE}

JSON SAFETY
- Inside any string value, never use unescaped ASCII double quotes. For
  emphasis, use single quotes ('like this') in English and 「」 or "" in
  Chinese.
- Use \\n for newlines inside strings; never literal line breaks.
- Validate the JSON in your head before Writing translation.json.

Begin now: Read pages="1".
"""


# --- Investment memo runner ------------------------------------------------

_SKILL_PATH = Path(__file__).resolve().parent / "skills" / "bsh_investment_memo_latestage.md"
_BUFFETT_SKILL_PATH = (
    Path(__file__).resolve().parent / "skills" / "bsh_buffett_investment_memo.md"
)


# Maps the analysis artifacts produced by Serena's memo skill to the
# human-readable "pass" label the JobLogModal renders. When Claude writes
# any of these files, _process_event tags the event with `thread=<label>`
# so the AI-Task modal can group the parallel passes as their own
# collapsible sections instead of one flat firehose.
_MEMO_ANALYSIS_PASSES: dict[str, str] = {
    "pressure_tests.md": "Arithmetic / pressure tests",
    "time_base_checks.md": "Time-base integrity",
    "growth_bridge.md": "Growth bridge",
    "competitive_notes.md": "Competitive compression",
    "disconfirming_evidence.md": "Alternative explanations",
    "adoption_ladder.md": "Adoption ladder",
    "core_franchise_resilience.md": "Core franchise resilience",
    "claim_register.md": "Claim register",
    "distribution_notes.md": "Distribution / GTM",
    "replacement_vs_coexistence.md": "Replacement vs coexistence",
    "scenario_swim_lanes.md": "Scenario swim lanes",
    "downside_scenario.md": "Downside scenario analysis",
    "countercase.md": "Countercase analysis",
    "source_treatment_assumptions.md": "Source treatment and assumptions",
    "risk_sensitivities.md": "Risk and valuation sensitivities",
}

_BUFFETT_ANALYSIS_PASSES: dict[str, str] = {
    "business.md": "The business",
    "economics.md": "Owner's earnings / economics",
    "moat.md": "Durable advantage",
    "management.md": "Management and capital allocation",
    "valuation.md": "Intrinsic value / margin of safety",
    "permanent_loss.md": "Permanent capital loss",
}

_MEMO_PHASE1_THREAD = "Phase 1 - Intake and setup"
_MEMO_PHASE2_THREAD = "Phase 2 - Parallel analysis passes"
_MEMO_PHASE3_THREAD = "Phase 3 - Synthesis and sensitivities"
_MEMO_PHASE4_THREAD = "Phase 4 - Memo package drafting"
MEMO_PHASE5_THREAD = "Phase 5 - Rendering and QA"
MEMO_PHASE6_THREAD = "Phase 6 - Optional internal diligence and previews"

_MEMO_PHASE_PLAN: tuple[dict[str, Any], ...] = (
    {
        "thread": _MEMO_PHASE1_THREAD,
        "title": _MEMO_PHASE1_THREAD,
        "phase_index": 1,
        "estimate_ms": 150_000,
        "description": "Setup usually takes about 2m 30s while sources and run context load.",
    },
    {
        "thread": _MEMO_PHASE2_THREAD,
        "title": _MEMO_PHASE2_THREAD,
        "phase_index": 2,
        "description": "Fan out independent analysis passes and pressure tests.",
    },
    {
        "thread": _MEMO_PHASE3_THREAD,
        "title": _MEMO_PHASE3_THREAD,
        "phase_index": 3,
        "description": (
            "Reconcile claims, scenarios, validation log, and risk sensitivities."
        ),
    },
    {
        "thread": _MEMO_PHASE4_THREAD,
        "title": _MEMO_PHASE4_THREAD,
        "phase_index": 4,
        "description": "Author the bilingual structured memo package for the fixed renderer.",
    },
    {
        "thread": MEMO_PHASE5_THREAD,
        "title": MEMO_PHASE5_THREAD,
        "phase_index": 5,
        "description": "Render DOCX output, run Chinese parity, and run memo quality checks.",
    },
    {
        "thread": MEMO_PHASE6_THREAD,
        "title": MEMO_PHASE6_THREAD,
        "phase_index": 6,
        "description": "Optional internal diligence memo and PDF previews when enabled.",
    },
)

_MEMO_PHASE_ORDER = {
    str(item["thread"]): int(item["phase_index"])
    for item in _MEMO_PHASE_PLAN
}
_MEMO_PHASE_BY_ORDER = {
    int(item["phase_index"]): str(item["thread"])
    for item in _MEMO_PHASE_PLAN
}

_MEMO_PARALLEL_ANALYSIS_FILES = {
    "pressure_tests.md",
    "time_base_checks.md",
    "growth_bridge.md",
    "competitive_notes.md",
    "disconfirming_evidence.md",
    "adoption_ladder.md",
    "core_franchise_resilience.md",
    "distribution_notes.md",
    "replacement_vs_coexistence.md",
}

_MEMO_SYNTHESIS_FILES = {
    "claim_register.md",
    "scenario_swim_lanes.md",
    "downside_scenario.md",
    "countercase.md",
    "source_treatment_assumptions.md",
    "risk_sensitivities.md",
}

MEMO_FAST_PASS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "key_findings": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"},
                    "finding": {"type": "string"},
                    "evidence_class": {"type": "string"},
                    "implication": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "claim",
                    "finding",
                    "evidence_class",
                    "implication",
                    "confidence",
                ],
            },
        },
        "supporting_evidence": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string"},
                    "source_class": {"type": "string"},
                    "detail": {"type": "string"},
                    "as_of": {"type": ["string", "null"]},
                },
                "required": ["source", "source_class", "detail", "as_of"],
            },
        },
        "disconfirming_evidence": {
            "type": "array",
            "maxItems": 6,
            "items": {"type": "string"},
        },
        "remaining_evidence_limits": {
            "type": "array",
            "maxItems": 5,
            "items": {"type": "string"},
        },
        "investment_implications": {
            "type": "array",
            "maxItems": 6,
            "items": {"type": "string"},
        },
    },
    "required": [
        "summary",
        "key_findings",
        "supporting_evidence",
        "disconfirming_evidence",
        "remaining_evidence_limits",
        "investment_implications",
    ],
}

MEMO_FAST_ENGLISH_PACKAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis_artifacts": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "claim_register_md": {"type": "string"},
                "scenario_swim_lanes_md": {"type": "string"},
                "downside_scenario_md": {"type": "string"},
                "countercase_md": {"type": "string"},
                "source_treatment_assumptions_md": {"type": "string"},
                "risk_sensitivities_md": {"type": "string"},
                "content_coverage_md": {"type": "string"},
            },
            "required": [
                "claim_register_md",
                "scenario_swim_lanes_md",
                "downside_scenario_md",
                "countercase_md",
                "source_treatment_assumptions_md",
                "risk_sensitivities_md",
            ],
        },
        "memo_package": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["analysis_artifacts", "memo_package"],
}

MEMO_FAST_BILINGUAL_PACKAGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "memo_package": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["memo_package"],
}

# Canonical renderer section ids, in package order. Mirrors
# memo_docx_renderer.REQUIRED_SECTION_IDS (kept literal here so claude_runner
# stays import-free of the renderer).
MEMO_PACKAGE_SECTION_IDS: tuple[str, ...] = (
    "executive_summary",
    "company_overview",
    "investment_highlights",
    "investment_risk",
    "financial_forecast_valuation",
)

# The "spine-lite" contract: the spine pins ONLY the envelope and the shared
# facts every section must agree on. The seven analysis artifacts moved to a
# dedicated side agent (MEMO_FAST_ENGLISH_ARTIFACTS_SCHEMA below) — writing
# them inside the spine was most of the old spine's ~9-minute runtime. The
# maxLength/maxItems bounds are hard schema limits so the spine physically
# cannot regrow into an essay writer.
MEMO_FAST_ENGLISH_SPINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "package_skeleton": {
            "type": "object",
            "additionalProperties": True,
        },
        "shared_facts": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "recommendation_sentence": {"type": "string", "maxLength": 300},
                "key_metrics": {
                    "type": "array",
                    "maxItems": 12,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string", "maxLength": 80},
                            "value": {"type": "string", "maxLength": 120},
                            "as_of": {"type": "string", "maxLength": 40},
                            "source_ids": {
                                "type": "array",
                                "maxItems": 4,
                                "items": {"type": "string", "maxLength": 8},
                            },
                        },
                        "required": ["name", "value", "as_of"],
                    },
                },
                "scenarios": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "bear": {"type": "string", "maxLength": 240},
                        "base": {"type": "string", "maxLength": 240},
                        "bull": {"type": "string", "maxLength": 240},
                    },
                    "required": ["bear", "base", "bull"],
                },
                "risks": {
                    "type": "array",
                    "minItems": 4,
                    "maxItems": 6,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "summary": {"type": "string", "maxLength": 160},
                            "rating": {
                                "type": "string",
                                "pattern": "^(10|[1-9])/10$",
                            },
                            "likelihood": {
                                "type": "string",
                                "enum": ["High", "Medium", "Low"],
                            },
                        },
                        "required": ["summary", "rating"],
                    },
                },
                "source_topics": {
                    "type": "object",
                    "additionalProperties": {"type": "string", "maxLength": 120},
                },
            },
            "required": [
                "recommendation_sentence",
                "key_metrics",
                "scenarios",
                "risks",
            ],
        },
        "section_notes": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                section_id: {"type": "string", "maxLength": 400}
                for section_id in MEMO_PACKAGE_SECTION_IDS
            },
        },
    },
    "required": ["package_skeleton", "shared_facts"],
}

# The seven private analysis artifacts, authored by a side agent that runs
# concurrently with the section workers (they never read these).
MEMO_FAST_ENGLISH_ARTIFACTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "analysis_artifacts": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "claim_register_md": {"type": "string", "maxLength": 8000},
                "scenario_swim_lanes_md": {"type": "string", "maxLength": 8000},
                "downside_scenario_md": {"type": "string", "maxLength": 8000},
                "countercase_md": {"type": "string", "maxLength": 8000},
                "source_treatment_assumptions_md": {
                    "type": "string",
                    "maxLength": 8000,
                },
                "risk_sensitivities_md": {"type": "string", "maxLength": 8000},
                "content_coverage_md": {"type": "string", "maxLength": 8000},
            },
            "required": [
                "claim_register_md",
                "scenario_swim_lanes_md",
                "downside_scenario_md",
                "countercase_md",
                "source_treatment_assumptions_md",
                "risk_sensitivities_md",
            ],
        },
    },
    "required": ["analysis_artifacts"],
}

_MEMO_ENGLISH_SECTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "section": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["section"],
}

MEMO_PACKAGE_SOURCES_CONTRACT = """\
## Renderer Sources Contract (hard requirement — validated before rendering)

Every entry in the package `sources` list must be an object with exactly
these keys, all non-empty:
- `id`: "S1", "S2", ... in order;
- `title`: {"en": "...", "zh": ""} — human-readable source name;
- `class`: the source class ("company-reported", "investor materials",
  "third-party market data", "BSH primary diligence", "public filings", ...);
- `treatment`: {"en": "...", "zh": ""} — one sentence on how the memo
  weighs and uses this source;
- `as_of`: the data vintage as an ISO date string.

Do NOT reuse the analysis-pass evidence vocabulary (`source`,
`source_class`, `label`, `detail`) for package sources — the renderer
rejects those keys and the run fails.
"""

MEMO_PACKAGE_BLOCK_CONTRACT = """\
## Renderer Block Contract (hard requirement — validated before rendering)

Every block is validated field-by-field. Required fields per block type:
- `heading`: `text` (bilingual object). Optional `level`.
- `paragraph`: `text` (bilingual object).
- `bullets`: `items` — non-empty list of bilingual objects.
- `callout`: `title` (bilingual object) is REQUIRED on every callout, even
  when the callout has a body or items; a callout without a title fails the
  run. Optional `body` (bilingual) and `items` (list of bilingual objects).
- `table`: `headers` and/or `rows` (rows are lists of bilingual cell
  objects); optional `title` (bilingual).

Bilingual object means `{"en": "...", "zh": ""}` in this pass (`zh` filled
later). Plain strings are allowed ONLY for fully language-neutral values
(dates, figures, tickers, proper-noun names). Any plain string containing
ordinary lowercase English words fails validation — when in doubt, use the
bilingual object form.

Before returning, re-check every callout block for a non-empty `title` and
every bullets block for a non-empty `items` list.
"""

HUMAN_EXEC_MEMO_VOICE_CONTRACT = """\
## Human Executive Memo Voice Contract

This is a final-writing override. It supersedes any older skill instruction
that asks for inline source markers, bracketed source traces, scaffolded
taxonomy labels, or prompt-visible headings in final prose. Preserve the full
diligence standard from the skill, but the finished English memo is an
exec-ready LP-facing sell-side investment memo, not a generated research
report, buyer-side diligence memo, or BSH internal allocation note.

Final memo prose must:
- write like a senior investor explaining the investment case under uncertainty;
- convert evidence into judgment;
- avoid process language, methodology narration, task labels, and validation
  scaffolding in the body;
- make statements directly. Do not write about the memo as an object, do not
  narrate what the memo/document/section/analysis does, and do not use
  writer-process language;
- use first-person sponsor voice when stating our view, access, conviction,
  and action: "we believe", "we are being offered", "we recommend", and
  "we are participating through";
- never use detached third-person constructions for the investment call;
  recommendation, access, base case, and action sentences need a first-person
  sponsor subject or a direct investment-case subject;
- state uncertainty directly instead of explaining why certainty is
  unavailable;
- avoid template-visible language, symmetrical model phrasing, and repetitive
  paragraph openings;
- keep analytical artifacts private unless a fact or conclusion belongs in
  the memo;
- use source-class language in Sections I-V, with detailed source IDs only in
  a separate Sources, Source Classes, and Fact Reference Index;
- convert disclosure gaps into risk factors, valuation sensitivities, Fermi
  estimates, or deal-mechanics treatment. This applies to EVERY mention,
  including table cells: never leave a bare "Not disclosed" or "not
  computable" — the same cell (or its row) must state the treatment, e.g.
  "Not disclosed; modeled via customer-count proxy" or "Not disclosed;
  treated as a valuation sensitivity". The quality gate recognizes treatment
  through this vocabulary (any form): model, treat, assume, proxy, estimate,
  conversion, range, scenario, sensitivity, valuation, risk, credit,
  discount, haircut, downside, "we value". Use at least one of these words
  in the same cell or row as every "not disclosed" / "not computable" —
  a terse untreated cell fails the quality gate and costs a retry;
- never bridge clauses with an em dash ANYWHERE in the package — body prose,
  table cells, headings, the company descriptor, and source titles and
  treatments all included. Use a colon, semicolon, or two sentences instead
  ("Information Technology: semiconductors", never "Information Technology —
  semiconductors"). The quality gate blocks em-dash bridging and each miss
  costs a retry;
- express data vintage with absolute dates only: "figures are as of March
  2026", "no disclosure since the January launch window". NEVER anchor
  staleness to the memo itself — phrases like "at the memo date", "as of
  this writing", "four months old at the memo date", or any other
  "the memo ..." construction are banned memo-self-reference and will fail
  the quality gate. If staleness matters, state the as-of date and treat the
  gap as a risk factor or valuation sensitivity.

Sell-side investment memo posture:
- Open from the sponsor thesis, not from a tombstone. Start with why we care
  about the category, why the timing matters, why this company is shaping the
  layer or market that matters, and why the opportunity fits BSH's mandate.
  Then explain the technical proof, commercial proof, and SPV/round mechanics.
- For Wisdom-sponsored opportunities, write in a Wisdom/BSH sponsor register:
  use "BSH invests in..." for mandate-level category statements, and use
  "we are being offered", "we are participating through the SPV", and
  "we recommend participating..." for the transaction and recommendation. Do
  not describe the sponsor or investors from a detached third-person vantage
  point unless identifying a legal counterparty.
- Do not write as if BSH is negotiating control terms in a private-equity
  process or exposing its internal intended position to LPs.
- Do not default to "small/minimum" allocation because revenue, ARR, gross
  margin, lead investor, or detailed SAFE side terms are undisclosed. For
  early-growth or Series A/A2 deep-tech rounds, those gaps are normal unless
  the supplied source package says otherwise. Calibrate expectations to the
  stage, round, sponsor channel, scarcity of allocation, and strength of the
  syndicate.
- If the round is oversubscribed, has top-tier participation, or the available
  economics are attractive versus what others are receiving, reflect that as
  positive evidence for scarcity and urgency. Do not default to a minimum
  participation recommendation unless the facts show conviction is genuinely
  low.
- Treat SPV/SAFE economics as deal mechanics to explain plainly, not as a
  thesis-breaking risk by default. State the economics, valuation support, and
  sensitivity to the final instrument terms without turning the memo into a
  checklist.
- The finished investment memo is an offer memo, not an internal approval note.
  Do not use closing-checklist language, expected-bar labels, funding-gate
  language, or next-step checklists in final prose. Convert those ideas into
  investment thesis, risk factors, valuation
  sensitivities, and deal-mechanics disclosure.
- Do not use funding-gate or checklist phrasing that tells the reader to
  confirm, require, or wait for process items before funding or signing.
  Convert each item into risk or valuation language: "The $500M+ figure blends
  signed contracts and MOUs, so valuation support is strongest where binding
  contract value converts to recognized revenue."
- Do not use confirmation-section headings, expected-bar headings, investment
  condition headings, revisit-condition headings, or next-step checklist
  headings in the finished memo. Those are internal workflow labels. Fold the
  same substance into the investment thesis, risk factors, valuation
  sensitivity, or deal-mechanics disclosure.
- Do not start final memo sentences, bullets, or table cells with imperative
  evidence-request verbs. That is internal-note/checklist voice. The final memo
  should state the disclosed fact, model treatment, and valuation sensitivity
  directly.
- Do not speculate about sponsor, company, investor, or counterparty
  capability to share, provide, produce, or confirm information. State the
  disclosed fact, the risk to the investment case, and the valuation
  sensitivity directly.
- Do not narrate the sponsor memo or source process in final prose. Avoid
  "memo language was", "the sponsor implies", "the sponsor frames", and
  "the sponsor itself flags". State the fact or risk directly, then say how it
  affects the investment case.
- Do not use source-process narration as a substitute for investment judgment.
  Do not narrate what a sponsor note, registry, source packet, or memo artifact
  says. Write the fact in plain form: "The $500M+ figure blends signed
  contracts and MOUs" or "available evidence does not document revenue
  attribution."
- Do not write passive availability language about future process access or
  ease of confirmation. Those are guesses about process, not investment
  judgments.
- Do not use legal-rights shorthand in operating tables. Translate it into
  economic meaning: "The SPV offers limited direct governance and reporting;
  the manager controls investor-level decisions as a single block."
- Do not use buyer-side underwriting vocabulary in final prose or tables.
  Use investment-case language instead: "we give credit to", "our base case
  credits", "the investment case rests on", or "the valuation is supported by."
- Do not use writer-process framing such as "we frame it as", "we frame the
  market", or "the framework". State the investment conclusion directly.
- Do not write imperative diligence commands such as "Require X before
  underwriting". Use investment-case language: "The base case gives credit to
  X", "X supports the valuation", or "X remains the principal risk factor."
- Do not use casual sponsor verbs or exposure-seeking idioms for mandate-level
  statements. Write "BSH invests in..." for the mandate and "we recommend..."
  for the action. Do not use buried or underside metaphors for infrastructure;
  write "control layer for" or "infrastructure layer for".
- Do not overload the opening paragraph with sponsor mission, technical claim,
  investor roster, and founder resume in one block. Open with sponsor thesis
  and company relevance, then move technical proof, backers, and team pedigree
  into the next paragraph or Company Overview.
- Do not use uniqueness claims such as "only scaled platform" unless the source
  package independently supports both uniqueness and scale. Use precise
  capability claims instead.
- Do not use protected or sensitive founder demographic traits, BSH founder
  background preferences, or thesis-fit exception labels as investment
  rationale, investment risk, recommendation logic, source treatment, or final
  memo disclosure. Team discussion belongs in operating history, domain
  expertise, technical authorship, recruiting strength, governance, and
  company-building evidence.

Concrete positive writing patterns:
- Opening: "BSH invests in physical-world infrastructure that makes people
  safer, healthier, and more capable. ZaiNar is compelling because precise
  network-side positioning is becoming a control layer for defense PNT,
  industrial automation, logistics, healthcare, and Physical AI."
- Transaction: "We are being offered SPV exposure to a SAFE expected to convert
  into the A2 at an effective entry near $2.55B after the discount."
- Recommendation: "We recommend participating in the SPV because the entry
  prices scarce technical infrastructure, patent depth, early commercial pull,
  and defense validation before the full revenue curve is visible."
- Risk sensitivity: "The principal sensitivity is the binding-contract share
  inside the $500M+ commercial figure and whether final SAFE mechanics preserve
  the disclosed effective entry."
- Evidence gap: "Revenue is not disclosed; our base case uses binding
  contract value, implementation timing, and conservative conversion ranges
  rather than treating pipeline or MOUs as revenue."
- Risk: "Key risk centers on whether signed commercial interest converts into
  repeatable deployments quickly enough to support a $3.0B valuation."

Rejected language categories:
- detached third-person recommendation or opportunity framing;
- memo/document/process narration;
- analysis-process narration;
- passive sponsor/counterparty capability speculation;
- legal-rights checklist shorthand in operating tables;
- uncertainty apologies instead of direct evidence treatment.

Final memo body and operating tables must not contain:
- bracketed source tokens or file references such as `[S1]`, `[WV]`,
  `[WV SPV memo]`, `[companies.yaml]`, `[internal]`, or similar;
- internal artifact names such as `companies.yaml`, `memo_packet`,
  `source_trace`, `claim_register`, `research_tasks`, `reviewer_prompts`, or
  analysis file names;
- source-process narration about what a memo artifact, registry, source packet,
  sponsor note, or reviewer prompt says;
- scaffold headings or labels from analytical worksheets, evidence-state
  tables, closing checklists, expected-bar lists, investment-condition lists,
  revisit-condition lists, or internal question lists;
- founder demographic preference language, thesis-fit exception labels, or
  internal mandate exceptions as investment rationale or risk factors;
- cute or fuzzy finance metaphors, no-rights legal shorthand, overclaimed
  scarcity phrases, or shorthand that obscures the economic point;
- deal-legal checklist terms such as `MFN`, `down-round protection`,
  `information rights`, `voting rights`, `named lead`, `named institutional
  lead`, or `governance at the LP level`; explain the investor economics in
  plain English instead;
- passive counterparty-capability or availability speculation;
- detached recommendation-label headings; state the investment decision directly
  in a sentence;
- internal question-list labels, confirmation labels, expected-bar labels, or
  internal-audience suffixes;
- internal IC, buyer-side diligence, bank/debt, control-investor, or
  deal-legal checklist shorthand. This is an LP-facing, exec-ready sell-side
  investment memo, not a BSH internal allocation note. Write every deal
  mechanic, governance point, and recommendation as plain narrative prose
  describing what it means economically for investors. Say that a valuation
  rests on or is supported by specific evidence; that a structure offers
  limited governance, reporting, or oversight; and frame the decision as a
  clear recommendation. Use investment-case, participation, valuation-support,
  and risk-sensitivity vocabulary instead of process labels, confirmation
  labels, small-check reflexes, legal-rights labels, or control-rights
  checklist phrasing;
- BSH internal participation-sizing language or internal recommendation
  instructions;
- em dash bridging in English body prose or operating tables;
- meta-language about the memo/document/analysis/framework/section, including
  writer-process phrasing.

Memo spine requirement:
- core_bet: what has to be true for investors to make money;
- entry_tension: what the valuation or instrument already assumes;
- current_proof: what is proven today by source class;
- unproven_but_modelable: what is missing but can be modeled conservatively;
- risk_sensitivity: what weakens valuation support or return potential;
- action: recommendation verdict and investment rationale.

The opening, Investment View, risk section, scenario section, and final
Investment Decision / Closing View must use the same spine. The first two
body paragraphs must state company, transaction, valuation / entry terms,
central price/proof tension, and recommendation verdict. The substantive
ending must state the investment recommendation, risk sensitivities, and
valuation support before any sources or
disclosures. Do not include BSH internal participation sizing in the
LP-facing memo.

Positive examples for early-commercial infrastructure deals:
- "ZaiNar is a scarce technical asset in network-side positioning; the A2
  prices real IP, technical depth, and early commercial pull before the full
  revenue curve is visible."
- "Company-reported contract and MOU figures support commercial momentum; the
  base case credits the binding portion and leaves upside for MOU and
  carrier conversion."
- "Pipeline is not contracted revenue. Use a 5-15% conversion range for
  scenario construction until named site-level commitments are available."
- "An SPV interest depends on the SAFE converting as described; explain the
  economics and valuation sensitivity without turning them into a
  control-rights or confirmation checklist."
- "If the round is meaningfully oversubscribed and BSH has differentiated
  access, we would reflect scarcity and upside in our recommendation,
  not mechanically default to a minimum check."

Banned phrase / rewrite guidance:

| Avoid | Prefer |
|---|---|
| The investment case is not that... | This is not a conventional SaaS case. |
| Detached recommendation framing | We recommend participating... / We do not recommend participating... |
| Detached opportunity framing | We are being offered... |
| Detached base-case framing | Our base case gives credit for... |
| Memo/document/process narration | Remove the frame; make the investment statement. |
| Analysis-process narration | State the conclusion directly. |
| Uncertainty apology | State the disclosed and undisclosed facts directly. |
| Detached decision label | Investment Decision / We recommend... |
| Question-form closing checklist | State the deal economics, risk factor, or valuation sensitivity. |
| Sponsor capability speculation | State the disclosed fact and investment implication directly. |
| Passive availability language | Remove the process guess; state the risk or valuation sensitivity. |
| Funding-gate checklist phrase | State the risk or valuation sensitivity. |
| Imperative evidence-request phrase | State the deal fact, support point, or risk sensitivity directly. |
| Closing checklist headings | Remove the section; fold the substance into recommendation, risk, valuation, or deal mechanics. |
| Signing-process checklist phrase | State the deal fact or valuation sensitivity directly. |
| Open-item process phrase | State what is disclosed, not disclosed, and why it matters. |
| Sponsor-process narration | State the investment fact or risk directly. |
| Source-process narration | available evidence / disclosed materials / omit the process frame |
| Diligence threshold or next-step checklist labels | Fold into recommendation, risk, valuation, or deal-mechanics prose. |
| No voting or information rights | The SPV offers limited direct governance and reporting; the manager controls investor-level decisions. |
| underwrite / underwriting | give credit to / investment case / valuation support |
| Pre-underwriting process language | our base case credits... where source support is strongest |
| the right way to view the underwriting | the investment case rests on... |
| We frame it as... | State the conclusion directly without writer-process narration. |
| Require X before underwriting | X is a valuation-support factor / X remains a risk factor. |
| Internal question-list labels | Remove; use investment thesis, risk, valuation, or deal mechanics. |
| Proving the case | investment case, base case, conviction, support |
| Describing participation | participation, commitment, exposure |
| Unresolved inquiry framing | Risk factors / valuation sensitivities / deal-mechanics disclosure |
| Missing proof | Risk factor / valuation sensitivity / disclosed evidence gap |
| Recommendation labels | We recommend participating / We do not recommend participating |
| Decision discipline | risk sensitivities |
| False precision | State the evidence range without over-modeling it. |
| not treated as ARR | not revenue-recognized |
| commercial momentum is material, but... | The pipeline is large but not contractually binding. |
| The principal risk is that... | Key risk centers on... |
| Soft-instrument metaphor | SPV interest whose economics depend on SAFE conversion. |
| Hard-IP metaphor | patent estate and technical approach that still need claim-scope review. |
| Moat-compression shorthand | upside shifts from product margin to patent leverage and deployment relationships. |

Before DOCX generation, run a final prose QA pass. Remove banned phrases,
meta language, methodology leakage, over-explained risks, template-visible
structure, and unnatural model voice. The output must read like an experienced
investor making a call under uncertainty.
"""

MEMO_CONTENT_PARITY_CONTRACT = """\
## Memo Content Parity Contract

The package must preserve the full institutional memo content standard across
every company, not just the current run. Do not collapse analytical artifacts
into a short executive summary. If a metric is unavailable, include the
component and state the source class, model treatment, and valuation
sensitivity rather than omitting the component.

Source-to-final fidelity is part of this contract. When the source set,
research folder, prior memo versions, Memo Studio packet, or analysis artifacts
contain material investment facts, preserve them in the final package with
source treatment instead of dropping them for brevity. This includes
management-reported commercial velocity signals, transaction-size or growth
expectations, profitability claims, ecosystem/logo rosters, technical
performance claims, standards or commoditization context, third-party industry
validation, resilient-infrastructure market context, and legal/offering
disclosures. Caveated facts should be included as caveated facts, not promoted
to revenue, margin, or valuation proof.

Every successful package must include these reusable component slugs. Put the
slug on the relevant block as `component: "<slug>"`; the renderer validates
these and writes content coverage into `logs/validation.txt`.

- `key_metrics_snapshot`: Executive Summary table.
- `deal_terms`: deal mechanics / headline terms table.
- `board`: Board of Directors table.
- `revenue`: revenue picture table.
- `key_operating_metrics`: key operating metrics table.
- `competitive_analysis`: competitive analysis table.
- `replacement_coexistence`: replacement-vs-coexistence treatment.
- `moat`: moat / defensibility table.
- `risk_register`: per-risk card tables in `investment_risk` (see the Risk
  Register Format Contract).
- `disconfirming_evidence`: bear-case or disconfirming evidence treatment.
- `time_base_integrity`: valuation/date/multiple timing table.
- `growth_bridge`: growth bridge table.
- `scenario_analysis`: bear/base/bull or equivalent scenario table.
- `investment_decision`: final Investment Decision / Closing View.
- `evidence_thresholds`: evidence thresholds that would materially support
  the next valuation step-up, written as valuation sensitivities rather than
  buyer-side gating commands.
- `source_index`: source/fact index through the `sources` list or a sources section.
- `disclosures`: concise legal/offering disclosure language.

If you add any non-core section id, provide a bilingual section `title`; the
renderer only auto-titles known core section ids. Unknown ids without titles
lose visible structure and will fail validation.
"""

MEMO_RISK_REGISTER_CONTRACT = """\
## Risk Register Format Contract (hard requirement — validated before rendering)

The `investment_risk` section presents risks as PER-RISK CARDS, not one wide
risk table. Structure, in order:

1. One short intro paragraph framing where the risk really concentrates.
2. 4-6 risk cards. Each card is exactly two consecutive blocks:
   - a `heading` block (level 3) whose text is
     `{"en": "Risk N: <one-line summary>", "zh": "风险 N：<一句话概括>"}`.
     The one-line summary is a plain, specific sentence a reader understands
     without opening the table — name the actual failure ("The next round may
     price below the December 2024 mark"), never a category label
     ("Financing risk").
   - a `table` block with `component: "risk_register"`,
     `"layout": "key_value"`, `"headers": []`, and EXACTLY these five
     two-cell rows (label cell first, content cell second):
       1. `Risk Type` / `风险类型` — a 1-4 word category such as Commercial,
          Market, Competition, Technology, Financing, Regulatory, or
          Execution. Not a sentence.
       2. `Why it matters` / `为什么重要` — 2-4 plain sentences: what the
          risk is, the evidence behind it, and its effect on valuation
          stated explicitly, with numbers wherever they exist.
       3. `What we watch` / `跟踪信号` — 1-3 concrete, observable signals
          that would confirm or defuse the risk, dated where possible.
       4. `Likelihood` / `可能性` — `"High|Medium|Low: <short reason>"`
          (Chinese `"高|中|低：<简短理由>"`): how likely the risk is to
          materialize inside the 3-5 year underwriting window. Anchors:
          High — more likely than not; Medium — a realistic chance,
          roughly one-in-three; Low — unlikely, but consequential enough
          to track. Ground the reason in evidence, not vibes.
       5. `Risk Rating` / `风险评分` — `"N/10: <short reason>"` with N from
          1-10. This scores impact-weighted importance to the investment
          case, not probability (Likelihood carries that). Anchors: 9-10
          could break the investment case on its own; 7-8 could push the
          outcome below base case; 5-6 meaningful but monitorable; 3-4
          real but limited effect; 1-2 minor.
3. Order the cards by Risk Rating, highest first, so the most important risk
   is the first thing the reader sees.

Card prose style: write like a person, not a report generator. Short
declarative sentences. Never use "furthermore", "moreover", "notably", "it
is important to note", "significant headwinds", or symmetrical templated
phrasing, and never bridge clauses with an em dash — the quality lint
blocks it. Concrete nouns and numbers over abstractions. A reader should
grasp each risk from its heading alone and get the full picture from the
card in under thirty seconds.

Keep the disconfirming-evidence treatment and the downside scenario as
separate blocks after the risk cards, as before.
"""


def _load_skill_text() -> str:
    if not _SKILL_PATH.exists():
        raise RuntimeError(f"Skill file missing: {_SKILL_PATH}")
    return _SKILL_PATH.read_text(encoding="utf-8")


def _load_buffett_skill_text() -> str:
    if not _BUFFETT_SKILL_PATH.exists():
        raise RuntimeError(f"Skill file missing: {_BUFFETT_SKILL_PATH}")
    return _BUFFETT_SKILL_PATH.read_text(encoding="utf-8")


_HORMUZ_SKILL_PATH = (
    Path(__file__).resolve().parent / "skills" / "bsh_hormuz_appendix.md"
)


def _load_hormuz_skill_text() -> str:
    if not _HORMUZ_SKILL_PATH.exists():
        raise RuntimeError(f"Skill file missing: {_HORMUZ_SKILL_PATH}")
    return _HORMUZ_SKILL_PATH.read_text(encoding="utf-8")


def _extract_company_registry_entry_yaml(
    companies_yaml_path: Path,
    company_slug: str,
) -> str | None:
    """Return the selected companies.yaml entry as YAML for prompt embedding."""
    try:
        data = yaml.safe_load(companies_yaml_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("failed to read companies.yaml for %s", company_slug)
        return None
    if isinstance(data, dict) and isinstance(data.get("companies"), list):
        records = data.get("companies") or []
    elif isinstance(data, list):
        records = data
    else:
        return None
    for item in records:
        if isinstance(item, dict) and str(item.get("id") or "") == company_slug:
            return yaml.safe_dump(
                item,
                sort_keys=False,
                allow_unicode=True,
                width=100,
            ).strip()
    return None


def _build_investment_memo_prompt(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    company_registry_entry_yaml: str | None = None,
) -> str:
    """Build the prompt for one Claude subprocess running Serena's skill.

    The prompt is **Serena's skill text verbatim**, with a short
    operational header that:
      - maps the skill's `[BSH Assistant]/` paths onto our `data/` tree,
      - lists the actual inputs (Serena_Background.md + the
        companies.yaml record) — note: no Document Library files,
      - carries non-fatal scope warnings from prep into the analysis,
      - points final memo content at the tracked parameterized renderer,
      - hints that the eight orthogonal analysis passes have no
        inter-dependencies and can run via parallel tool calls in a
        single response.

    Everything else is the skill text.
    """
    skill_text = _load_skill_text()
    rel_run_dir = run_dir.name
    memo_package_path = run_dir / "logs" / "memo_package.json"
    scope_warning_block = ""
    if scope_check and scope_check.get("outcome") == "warn":
        warning_lines = "\n".join(f"- {w}" for w in (warnings or []))
        scope_warning_block = f"""\
## Stage Calibration Context From Prep

The pre-run scope check produced a **non-fatal warning**:

- classification: `{scope_check.get('classification')}`
- reason: {scope_check.get('reason') or '(no reason recorded)'}

{warning_lines if warning_lines else "- No additional warnings recorded."}

Proceed with the memo anyway. Do **not** stop or decline solely because the
company is early-stage or indeterminate. Treat stage fit, source depth,
missing unit economics, and late-stage/pre-IPO comparability as model
treatment, allocation sensitivity, and valuation sensitivity. Preserve the
late-stage analytical standard where possible, but state assumptions as
investment-case treatment rather than apologetic caveats.

"""

    research_block = ""
    if research_dir and research_dir.exists():
        research_block = f"""\
The skill text describes a `[BSH Assistant]/[Company Name]/` folder
that historically held PitchBook PDFs, partner notes, CB Insights
exports, etc. **For this run, that folder maps to this absolute path:**

  `{research_dir}`

Read the raw files in that folder before memo writing. Use the files
themselves, not just quick summaries or index metadata. Continue to
apply source-provenance discipline: company-originated material,
investor/intermediary estimates, independent secondary sources, and
internal analysis must remain clearly separated.

"""
    else:
        research_block = """\
The skill text describes a `[BSH Assistant]/[Company Name]/` folder
that historically held PitchBook PDFs, partner notes, CB Insights
exports, etc. **For this run, that folder is not populated.** Treat
the company folder as empty — proceed without external research
materials, exactly as the skill says to do when the folder is absent.

"""

    analysis_block = ""
    if analysis_session_path and analysis_session_path.exists():
        analysis_block = f"""\
## Serena memo analysis packet

Serena has prepared a pre-memo analysis session for this run. It may still
contain draft, unapproved, or incomplete Memo Studio work. Read this folder
before drafting the memo:

  `{analysis_session_path}`

Start with `memo_packet.md`, then use the YAML artifacts as source material
as needed:
strategic risks, risk priorities, research tasks, thesis spine,
infographic source brief, chart/infographic plans, narrative hooks, and
benchmark dashboard. Treat the thesis spine as draft authorship guidance:
the final memo structure still follows the skill, but
Investment Highlights, Investment Risks, Valuation Sensitivity,
infographic choices, selected operator narrative choices, source-brief
warnings, intro stance, risk-section stance, and conclusion verdict come from
this packet when they are supported by evidence. Treat selected
openings, risk framings, and endings as operator HIL guidance, not copy-paste
text. Do not convert draft status, source-brief unsupported claims, missing
evidence, unresolved readiness blockers, or operator prompts into factual
memo claims.

"""

    if analysis_session_path and analysis_session_path.exists():
        analysis_execution_block = """\
## Approved Memo Studio execution mode

This run has a Serena memo analysis packet. Treat `memo_packet.md` and the
artifact YAML files as the primary synthesis. Do not rerun the eight
orthogonal analysis passes from scratch, do not reread every raw source file by
default, and do not spend the run recreating Memo Studio work that already
exists.

Read the approved packet and artifact files together, then write only the
concise run-folder analysis artifacts needed by the renderer contract and audit
trail. Use raw company research files only when a material final-memo claim
needs support or a packet claim is contradictory. Once the packet is reconciled,
move directly to memo package drafting, translation, and JSON package writing.

"""
    else:
        analysis_execution_block = """\
## Parallel execution of the eight orthogonal passes

The skill's "Non-Linear Analysis Engine" section lists eight orthogonal
analytical passes (Arithmetic / denominators, Deployment / behavior,
Budget / ownership, Rights / licensing / dependency, Replacement vs
coexistence, GTM / operating burden, Time-series change-over-time,
Competitive compression). **These eight passes have no
inter-dependencies and must be issued as parallel tool calls in a
single assistant turn.** Issue all eight Read/Write/Bash calls for the
passes together, let them stream back, then move on to the synthesis
step. Sequential per-pass execution is wasteful — fan them out
concurrently.

The synthesis step (Claim Register reconciliation, Scenario Swim
Lanes, valuation sensitivity, downside scenario, countercase), the memo
drafting step, the translation step, and the package-writing step
remain sequential. Server-side `.docx` rendering happens after Claude exits.

"""

    lessons_block = ""
    if lessons_path and lessons_path.exists():
        lessons_block = f"""\
## Serena memo lessons

Serena has stored lessons from prior completed memo runs for this company:

  `{lessons_path}`

Read this file before drafting. Use these lessons as memo-quality heuristics,
not as facts. Current company evidence, current public data, and the approved
analysis packet override stale or contradictory lessons. Before applying any
lesson, discard or rewrite stale internal labels, third-person recommendation
voice, prompt labels, and process/checklist wording under the current voice
contract.

"""

    registry_entry_block = ""
    if company_registry_entry_yaml:
        registry_entry_block = f"""\
## Resolved company registry entry

The server has already resolved the exact `data/companies.yaml` entry for
`{company_slug}`. Use this embedded YAML as the registry source for Phase 1.
Do not read or grep the full companies.yaml file during Phase 1 unless you need
to audit a contradiction against another source.

```yaml
{company_registry_entry_yaml}
```

"""

    return f"""\
You are running the **bsh-investment-memo-latestage-v1** skill (Serena's
script) for one real run. The skill text is included below as the source
standard, with the current voice and renderer contract taking precedence.

Prompt precedence:
1. The Human Executive Memo Voice Contract below governs all final prose.
2. The fixed DOCX renderer contract governs package shape and bilingual output.
3. Source-boundary rules and `data/uploads/` exclusion govern source use.
4. The remediated final-output requirements below override any older wording
   inside the included skill text.
5. The skill text supplies the diligence standard and section expectations only
   where it does not conflict with the current contract.

## Run-specific operational context

- **Run folder (your CWD):** `{rel_run_dir}` — everything is relative
  to here. The subfolders `analysis/`, `memo/`, `logs/`,
  `logs/previews/`, and `logs/previews_cn/` already exist.
- **Company:** {company_name} (slug `{company_slug}`)
- **Run ID:** {run_id}

{scope_warning_block}\
## Inputs (Serena's "company folder" + Settings)

{research_block}\
{analysis_block}\
{lessons_block}\

Where the skill says `[BSH Assistant]/Settings/Serena_Background.md`,
read this absolute path:

  `{settings_path}`

Where the skill says it needs the company's registry data, read **only
the entry matching the slug `{company_slug}`** from this absolute path:

  `{companies_yaml_path}`

That entry carries: description, sector, status, exchange, industry,
HQ, founded year, website, employee_band, parent_company, key_people,
latest_funding, latest_earnings, total_funding_usd, products,
competitors, recent_news, notable_contracts, notable_acquisitions,
plus a `translation` block with the Chinese equivalents of those
fields. You may not need every field; pull what's relevant for each
section per the skill's structure.

{registry_entry_block}\
The company registry is a top-level YAML list keyed by `id`, not by
`slug`. To find this company, search for the exact line
`- id: {company_slug}` or read the known entry directly. Do not waste a
pass searching for `slug:`.

## DO NOT read from `data/uploads/`

`data/uploads/<slug>/` is the user's Document Library. It belongs to a
**separate feature** (the per-document Sparkle button) and is **not** a
source for the memo. Do not Read, Bash, Glob, or Grep inside that
directory. If you find yourself wanting to reach into it, stop — the
skill is designed to run from the Serena library + companies.yaml
only.

## Fixed DOCX renderer contract

Do **not** write or edit a per-run renderer script. Forbidden files include
`build_memo.py`, `build_memos.py`, `generate_memo.py`, `render_memo.py`,
and JS variants of those names. The server will fail the run if any such
file exists in the run folder.

Instead, write the memo content and structure as data to:

  `{memo_package_path}`

The renderer is fixed product code (`server.memo_docx_renderer`). Your
job is to author a complete `memo_package.json`, not rendering code and
not final `.docx` files. After this Claude subprocess exits, the Python
worker will invoke `server.memo_docx_renderer` directly, render both
DOCX files, write validation logs, write the file inventory, and append
the manifest finalization block. Do not run `python -m
server.memo_docx_renderer` yourself. The package must be JSON with this
shape:

```json
{{
  "schema_version": 1,
  "company": {{
    "name": "Company, Inc.",
    "descriptor": {{"en": "Category", "zh": "类别"}},
    "stage": "Late-stage / pre-IPO",
    "sector": "AI",
    "location": "City, Region",
    "round": "Round / valuation context"
  }},
  "run": {{"run_id": "{run_id}", "as_of": "YYYY-MM-DD"}},
  "sections": [
    {{
      "id": "executive_summary",
      "blocks": [
        {{"type": "heading", "level": 2, "text": {{"en": "Investment Opportunity", "zh": "投资机会"}}}},
        {{"type": "paragraph", "text": {{"en": "Body prose.", "zh": "正文。"}}}},
        {{"type": "bullets", "items": [{{"en": "Bullet.", "zh": "要点。"}}]}},
        {{"type": "callout", "tone": "warning", "title": {{"en": "Valuation Sensitivity", "zh": "估值敏感因素"}}, "items": []}},
        {{"type": "table", "component": "key_metrics_snapshot", "title": {{"en": "Key Metrics Snapshot", "zh": "关键指标快照"}}, "headers": [], "rows": []}}
      ]
    }}
  ],
  "sources": [
    {{
      "id": "S1",
      "title": "Source title",
      "class": {{"en": "Company material", "zh": "公司材料"}},
      "treatment": {{"en": "How used", "zh": "使用方式"}},
      "as_of": "YYYY-MM-DD"
    }}
  ]
}}
```

The abbreviated shape above illustrates block syntax. The final package must
include all required core section ids: `executive_summary`,
`company_overview`, `investment_highlights`, `investment_risk`, and
`financial_forecast_valuation`, each with non-empty blocks. Include a
non-empty `sources` list. Use `paragraph`, `heading`, `bullets`, `callout`,
and `table` blocks. Tables carry headers and rows as arrays; callouts carry
concise title/body/items. The same package drives both EN and ZH
output, so every final user-facing string in blocks, table cells, and source
treatment must be bilingual (`{{"en": "...", "zh": "..."}}`). The ONLY values
that may stay plain strings are fully language-neutral ones: dates
("2026-05"), figures ("~$2.55B", "+180%"), source ids, tickers, and
proper-noun names ("Koch Disruptive Technologies"). The renderer rejects any
plain string containing ordinary lowercase English words — "120+ filed / 90+
issued" or "$10M/site (LOI expected)" MUST be a bilingual object. When in
doubt, use a bilingual object; identical en/zh is always valid.
This applies to descriptive prose inside table cells too: deal
mechanics such as SAFE / discount / cap / conversion terms must be written in
natural Chinese in the `.zh` value (keep the bare term "SAFE", tickers, dates,
and numbers, but translate the surrounding sentence). Never leave a cell's `.zh`
identical to its English when the cell contains prose.

Do not author a `heading` block that restates a numbered top-level section
title. The renderer emits the `I.`–`VI.` section titles automatically from the
section id, so a heading block beginning with a roman numeral (`VI. Sources …`)
or a Chinese numeral (`六、…`) renders a duplicate heading and fails the
Chinese-parity heading-count gate. Sub-headings inside a section must be plain,
unnumbered labels (e.g. "Source Index" / "来源索引", not "VI. Sources …").

The renderer fails closed on shallow package content. A required core section
cannot be only headings, spacers, title-only callouts, title-only tables, or
generic filler such as "More diligence is needed." Use substantive investor
content in every required section. `executive_summary` needs at least two
substantive content blocks. `investment_highlights` and `investment_risk` each
need at least two substantive bullets, or explanatory prose plus a substantive
table/callout. `financial_forecast_valuation` must explicitly address model
treatment, scenario ranges, valuation, revenue, margins, or valuation
sensitivities.

{MEMO_CONTENT_PARITY_CONTRACT}

{MEMO_RISK_REGISTER_CONTRACT}

The Chinese memo must be native professional investment Chinese with
analytical parity to English: same recommendation, confidence level, risks,
valuation posture, evidence, caveats, tables, and risk / valuation sensitivity. Do not
translate prompt scaffolding into visible prose. Avoid terms like `上行状态`,
`现态`, `关键现实检查`, `源追踪`, `备忘录包`, `审阅者提示`, `声明登记`,
`硬 IP 墙`, or `软性工具`; rewrite them as precise investment judgments,
evidence chains, valuation sensitivities, scenario ranges, valuation support,
or specific deal mechanics.

## Phase 1 - intake and setup

The first phase is only for source intake, run-folder orientation, and launch
prep. Keep it short and visible. Do not create a separate task plan or call any
task-management tools. Do not use ToolSearch, TaskCreate, TaskUpdate, TaskList,
TaskOutput, TaskStop, TodoWrite, or Task tools. Use only direct Read, Write,
Edit, Bash, Grep, and Glob calls.

In the first assistant turn after initialization, issue independent intake
calls together: verify the run folder, inspect the research folder, read
Serena_Background.md, read the research index if present, and use the embedded
registry entry above if present. Only locate the exact `- id: {company_slug}`
companies.yaml entry if the embedded entry is absent or contradictory. After
the research directory listing returns, read all relevant raw source files
together in the next assistant turn. Do not walk those files one at a time
unless a specific tool result forces it.

Once the minimum source package is loaded, immediately leave Phase 1 and follow
the execution mode below.

{analysis_execution_block}\

## Output contract — exactly per the skill text

Produce all analytical artifacts the skill specifies, plus
`logs/memo_package.json`. Do not write or edit final `.docx` files; the
server will render them from the package after Claude exits. The expected
server-rendered absolute paths are:

  - `{memo_paths['en']}`
  - `{memo_paths['zh']}`

Do not append the analysis finalization block to `logs/run_manifest.md`;
the server renderer appends it after successful package validation and
DOCX rendering.

{HUMAN_EXEC_MEMO_VOICE_CONTRACT}

==========================================================
SKILL: bsh-investment-memo-latestage-v1 source standard
==========================================================

{skill_text}
"""


def _research_file_listing(research_dir: Path | None) -> str:
    if not research_dir or not research_dir.exists():
        return "- No research directory is populated for this run."
    try:
        files = [
            p.name
            for p in sorted(research_dir.iterdir())
            if p.is_file() and p.name != "index.yaml"
        ][:80]
    except Exception:
        logger.exception("failed to list memo research files: %s", research_dir)
        return "- Research directory exists, but file listing failed."
    return "\n".join(f"- {name}" for name in files) or "- No research files found."


def _analysis_session_file_listing(analysis_session_path: Path | None) -> str:
    if not analysis_session_path or not analysis_session_path.exists():
        return "- No Memo Studio analysis packet is attached."
    try:
        files = [
            str(p.relative_to(analysis_session_path))
            for p in sorted(analysis_session_path.rglob("*"))
            if p.is_file()
        ][:120]
    except Exception:
        logger.exception(
            "failed to list memo analysis session files: %s",
            analysis_session_path,
        )
        return "- Memo Studio packet exists, but file listing failed."
    return "\n".join(f"- {name}" for name in files) or "- Packet folder is empty."


# The memo "package" passes (English synthesis, bilingual/Chinese fill, and
# resume) each hand Claude the whole memo and ask for one large, tool-free
# generation. During that emission Claude Code publishes no intermediate
# stream-json events, so the silence guard's clock advances while the model
# is working fine. The 180s default kills these routinely (it was the single
# most common memo failure on record — "memo Chinese package stalled after
# 180s"). Give them a budget that matches a real long generation, matching
# the precedent already set for PDF translation.
MEMO_PACKAGE_SILENCE_TIMEOUT_SEC = 600


def _memo_role_env(kind: str, role: str) -> str | None:
    """Per-role subprocess override: BSH_MEMO_<kind>_<role>, else BSH_MEMO_<kind>.

    Returns None when neither is set (or both are blank), which leaves the
    spawned `claude` argv byte-identical to the historical behavior — the CLI
    default model/effort applies.
    """
    value = os.environ.get(f"BSH_MEMO_{kind}_{role}") or os.environ.get(
        f"BSH_MEMO_{kind}"
    )
    value = (value or "").strip()
    return value or None


def _memo_role_model(role: str) -> str | None:
    return _memo_role_env("MODEL", role)


def _memo_role_effort(role: str) -> str | None:
    return _memo_role_env("EFFORT", role)


def _run_memo_local_json_artifact(
    *,
    prompt: str,
    schema: dict[str, Any],
    run_dir: Path,
    progress,
    progress_message: str,
    timeout_label: str,
    timeout_sec: int,
    silence_timeout_sec: int = 180,
    add_dirs: list[Path] | None = None,
    allowed_tools: str = "Read,Bash,Grep,Glob",
    model: str | None = None,
    effort: str | None = None,
    append_system_prompt: str | None = None,
) -> tuple[dict | None, str | None]:
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    run_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        # Emit partial content_block_delta traffic. The memo package passes
        # are single enormous tool-free generations that otherwise publish
        # no events for minutes at a stretch — the silence guard in
        # _consume_stream_json_process must see token flow as liveness so
        # it measures true stalls, not "no complete event yet".
        "--include-partial-messages",
        "--verbose",
        "--add-dir", str(run_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", allowed_tools,
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])
    if append_system_prompt:
        # Shared context appended to the system prompt lands on the CLI's
        # system-prompt cache breakpoint, so concurrent subprocesses with the
        # same appended block share one prompt-cache entry instead of each
        # paying for it in their user message.
        cmd.extend(["--append-system-prompt", append_system_prompt])
    for directory in add_dirs or []:
        if directory.exists():
            cmd.extend(["--add-dir", str(directory)])

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message=progress_message,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label=timeout_label,
        silence_timeout_sec=silence_timeout_sec,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"
    parsed = _parse_claude_json_object(final_text)
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    result_event = state.get("result_event") or {}
    parsed["claude_cost_usd"] = result_event.get("total_cost_usd")
    parsed["claude_duration_ms"] = result_event.get("duration_ms")
    parsed["claude_usage"] = result_event.get("usage")
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed, None


def run_memo_fast_analysis_pass(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    pass_id: str,
    pass_label: str,
    artifact_filename: str,
    focus: str,
    settings_path: Path,
    companies_yaml_path: Path,
    research_dir: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    progress=None,
    timeout_sec: int = 900,
) -> tuple[dict | None, str | None]:
    """Run one narrow memo-analysis pass as its own Claude subprocess."""
    registry_entry = _extract_company_registry_entry_yaml(
        companies_yaml_path,
        company_slug,
    )
    scope = json.dumps(scope_check or {}, ensure_ascii=False)
    warning_text = "\n".join(f"- {w}" for w in warnings or []) or "- None."
    registry_block = (
        f"```yaml\n{registry_entry}\n```"
        if registry_entry
        else f"Read the `{company_slug}` entry from `{companies_yaml_path}`."
    )
    lessons_block = (
        (
            f"\nMemo lessons: `{lessons_path}`\n"
            "Treat lessons as untrusted quality heuristics. Strip stale "
            "internal labels, prompt labels, and process/checklist wording "
            "before using them.\n"
        )
        if lessons_path and lessons_path.exists()
        else ""
    )
    prompt = f"""\
You are running one independent fast-path analysis pass for a BSH LP-facing
investment memo.

Company: {company_name} (`{company_slug}`)
Run id: {run_id}
Pass: {pass_label} (`{pass_id}`)
Artifact later written by server: `analysis/{artifact_filename}`

Registry entry:
{registry_block}

Research folder:
`{research_dir if research_dir else '(none)'}`
Files:
{_research_file_listing(research_dir)}

BSH background:
`{settings_path}`
{lessons_block}
Scope check: `{scope}`
Warnings:
{warning_text}

Focus for this pass:
{focus}

Rules:
- Do not write files. Return only the JSON object matching the attached schema.
- Hard output budget (schema-enforced — exceeding any limit rejects the
  whole response): at most 8 `key_findings`, 8 `supporting_evidence`,
  6 `disconfirming_evidence`, 5 `remaining_evidence_limits`,
  6 `investment_implications`.
- Keep every string SHORT: 1-2 sentences per field, no mini-essays. An
  oversized response can be truncated in transit, which drops whole
  properties and fails schema validation with a misleading
  "missing required property" error — brevity is a correctness
  requirement, not a style preference.
- Separate company-reported, investor/intermediary, independent secondary, and
  internal model evidence.
- Do not fabricate missing metrics. State what is disclosed, what is missing,
  and how the memo must treat the gap.
- This is a sell-side LP memo input. Convert evidence into investment judgment,
  but do not draft final memo prose.
"""
    add_dirs = [settings_path.parent, companies_yaml_path.parent]
    if research_dir and research_dir.exists():
        add_dirs.append(research_dir)
    if lessons_path and lessons_path.exists():
        add_dirs.append(lessons_path.parent)
    return _run_memo_local_json_artifact(
        prompt=prompt,
        schema=MEMO_FAST_PASS_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message=f"Running memo pass: {pass_label}",
        timeout_label=f"memo pass {pass_id}",
        timeout_sec=timeout_sec,
        add_dirs=add_dirs,
        model=_memo_role_model("ANALYSIS_PASS"),
        effort=_memo_role_effort("ANALYSIS_PASS"),
    )


def run_memo_fast_english_package(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    progress=None,
    timeout_sec: int = 1200,
    validation_feedback: str | None = None,
) -> tuple[dict | None, str | None]:
    """Synthesize fast-pass artifacts into an English source package."""
    registry_entry = _extract_company_registry_entry_yaml(
        companies_yaml_path,
        company_slug,
    )
    validation_feedback_block = (
        (
            "\n## Previous attempts failed renderer validation\n"
            "Fix EVERY error below while keeping the analytical content. The\n"
            "list is cumulative across attempts: errors from earlier attempts\n"
            "must STAY fixed — do not reintroduce a defect while fixing a new\n"
            "one. Re-verify the full Renderer Block Contract on every block\n"
            "before returning:\n"
            f"{validation_feedback}\n"
        )
        if validation_feedback
        else ""
    )
    registry_block = (
        f"```yaml\n{registry_entry}\n```"
        if registry_entry
        else f"Read the `{company_slug}` entry from `{companies_yaml_path}`."
    )
    analysis_dir = run_dir / "analysis"
    fast_dir = analysis_dir / "fast"
    source_mode = (
        "Use the approved Memo Studio packet as the primary synthesis."
        if analysis_session_path and analysis_session_path.exists()
        else "Use the fast parallel analysis artifacts as the primary synthesis."
    )
    prompt = f"""\
You are drafting the English source package for a BSH LP-facing sell-side
investment memo about {company_name}. This is the fast-path synthesis pass:
{source_mode}

{HUMAN_EXEC_MEMO_VOICE_CONTRACT}

Company registry entry:
{registry_block}

Run context:
- run_id: {run_id}
- run_dir: `{run_dir}`
- English DOCX later rendered by server: `{memo_paths.get('en')}`
- Chinese DOCX later rendered by server: `{memo_paths.get('zh')}`
- scope_check: `{json.dumps(scope_check or {}, ensure_ascii=False)}`
- warnings: `{json.dumps(warnings or [], ensure_ascii=False)}`

Research folder:
`{research_dir if research_dir else '(none)'}`
Files:
{_research_file_listing(research_dir)}

Memo Studio packet:
`{analysis_session_path if analysis_session_path else '(none)'}`
Files:
{_analysis_session_file_listing(analysis_session_path)}

Fast analysis artifacts:
- JSON directory: `{fast_dir}`
- Markdown directory: `{analysis_dir}`

Read the relevant packet/artifact files. Do not rerun the eight analysis
passes. Use `analysis/fast/*.json` as the primary synthesis inputs because
they already contain the structured results from each pass. Read markdown
artifacts only when a JSON artifact is missing, contradictory, or needs a
short source-specific detail; when reading markdown, use targeted reads rather
than loading every full artifact. Use raw company research files only for a
specific source-support check that affects a final package claim.

Produce ONE JSON object with:
1. `analysis_artifacts`: concise markdown strings for claim register,
   scenario swim lanes, downside scenario, countercase, source-treatment log,
   risk and valuation sensitivities, and content coverage against the reusable
   component slugs. Keep each artifact useful but short.
2. `memo_package`: an English source package for the fixed renderer. Every
   user-facing string must be represented as `{{"en": "...", "zh": ""}}`.
   Leave `zh` blank; a separate subprocess will fill Chinese. Do not write
   final DOCX files.

Package requirements:
- `schema_version: 1`
- `company`, `run`, `sections`, and `sources`
- Required section ids: `executive_summary`, `company_overview`,
  `investment_highlights`, `investment_risk`,
  `financial_forecast_valuation`
- Use paragraph, heading, bullets, callout, and table blocks.
- Include at least two substantive Executive Summary blocks.
- Include a non-empty sources list.
- Use first-person sponsor voice: "we recommend participating", "we are being
  offered", and "we are participating through". Never use detached
  recommendation, opportunity, access, or base-case framing.

{MEMO_PACKAGE_SOURCES_CONTRACT}

{MEMO_PACKAGE_BLOCK_CONTRACT}

{MEMO_CONTENT_PARITY_CONTRACT}

{MEMO_RISK_REGISTER_CONTRACT}
{validation_feedback_block}
Return only the JSON matching the attached schema.
"""
    add_dirs = [settings_path.parent, companies_yaml_path.parent, run_dir]
    if research_dir and research_dir.exists():
        add_dirs.append(research_dir)
    if analysis_session_path and analysis_session_path.exists():
        add_dirs.append(analysis_session_path)
    if lessons_path and lessons_path.exists():
        add_dirs.append(lessons_path.parent)
    return _run_memo_local_json_artifact(
        prompt=prompt,
        schema=MEMO_FAST_ENGLISH_PACKAGE_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message="Synthesizing English memo package",
        timeout_label="memo English package",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=add_dirs,
        model=_memo_role_model("ENGLISH"),
        effort=_memo_role_effort("ENGLISH"),
    )


# ---- Parallel English package synthesis ---------------------------------
#
# The monolithic English package call writes ~80K output tokens in one
# 10-17 minute Claude invocation, and a single validation failure regenerates
# all of it. The parallel "spine-lite" path splits phase 3 into:
#   1. a fast spine call — ONLY the package envelope (company / run / the
#      complete sources list) plus a schema-bounded shared-facts pin sheet
#      (recommendation sentence, key metrics, bear/base/bull, the ordered
#      risk list) so parallel sections cannot drift apart;
#   2. five per-section calls plus one analysis-artifacts side agent on a
#      thread pool, all sharing the common context through
#      --append-system-prompt (one prompt-cache entry instead of seven cold
#      contexts);
#   3. on a validation retry, only the sections implicated by the errors are
#      regenerated — the rest of the package is spliced from the previous
#      attempt.
# Any spine/section failure falls back to the monolithic call, so the worst
# case is exactly as slow and as correct as before. Artifacts-agent failure
# only degrades to stub artifacts.

_MEMO_ENGLISH_UNITS_DIRNAME = "english_units"

# Which renderer coverage component belongs to which section, per the skill
# and every accepted package on record. Used to route "missing required memo
# component" validation errors to the owning section, and to tell each
# section worker which component slugs it must produce.
_MEMO_COMPONENT_SECTION: dict[str, str] = {
    "key_metrics_snapshot": "executive_summary",
    "board": "company_overview",
    "revenue": "company_overview",
    "key_operating_metrics": "company_overview",
    "competitive_analysis": "investment_highlights",
    "replacement_coexistence": "investment_highlights",
    "moat": "investment_highlights",
    "risk_register": "investment_risk",
    "disconfirming_evidence": "investment_risk",
    "time_base_integrity": "financial_forecast_valuation",
    "growth_bridge": "financial_forecast_valuation",
    "scenario_analysis": "financial_forecast_valuation",
    "deal_terms": "financial_forecast_valuation",
    "evidence_thresholds": "financial_forecast_valuation",
    "investment_decision": "financial_forecast_valuation",
    "disclosures": "financial_forecast_valuation",
}

_MEMO_SECTION_TITLE_WORDS: dict[str, str] = {
    "executive summary": "executive_summary",
    "company overview": "company_overview",
    "investment highlights": "investment_highlights",
    "investment risk": "investment_risk",
    "financial forecast & valuation": "financial_forecast_valuation",
    "financial forecast and valuation": "financial_forecast_valuation",
}

_MEMO_SECTION_SPECS: dict[str, str] = {
    "executive_summary": """\
Open from the sponsor thesis, not a tombstone. At least two substantive
content blocks. Must include the Key Metrics Snapshot table with
`component: "key_metrics_snapshot"`. State the recommendation exactly as the
spine brief fixes it.""",
    "company_overview": """\
Must include three tables, each carrying its component slug:
`component: "revenue"` (revenue picture), `component: "key_operating_metrics"`
(key operating metrics), and `component: "board"` (Board of Directors with
strategic value).""",
    "investment_highlights": """\
At least two substantive bullets, or explanatory prose plus a substantive
table/callout. Must include tables with `component: "competitive_analysis"`,
`component: "replacement_coexistence"` (replacement vs. coexistence), and
`component: "moat"` (moat / defensibility).""",
    "investment_risk": """\
Present risks as per-risk cards (contract below), every card table carrying
`component: "risk_register"`, plus a disconfirming-evidence treatment block
with `component: "disconfirming_evidence"`. Use exactly the risk list and
ratings the spine brief fixes.""",
    "financial_forecast_valuation": """\
Must reference model treatment, scenario ranges, valuation, revenue, margins,
or valuation sensitivities, and include blocks carrying these component
slugs: `time_base_integrity` (valuation/date/multiple timing table),
`growth_bridge`, `scenario_analysis` (bear/base/bull), `deal_terms`
(headline terms / deal mechanics), `evidence_thresholds` (written as
valuation sensitivities), `investment_decision` (final Investment Decision /
Closing View, first-person sponsor voice), and `disclosures` (concise
legal/offering disclosure language).""",
}


def _memo_english_units_dir(run_dir: Path) -> Path:
    return run_dir / "logs" / _MEMO_ENGLISH_UNITS_DIRNAME


def _render_shared_facts_block(shared_facts: dict) -> str:
    """Deterministic markdown rendering of the spine's shared-facts pin
    sheet. Rendered once per attempt and handed byte-identical to every
    section worker, so the sections cannot disagree on the pinned facts."""
    lines: list[str] = ["## Shared fact sheet (pinned — repeat these exactly)"]
    recommendation = str(shared_facts.get("recommendation_sentence") or "").strip()
    if recommendation:
        lines.append(f"Recommendation sentence: {recommendation}")
    metrics = shared_facts.get("key_metrics")
    if isinstance(metrics, list) and metrics:
        lines.append("Key metrics:")
        for metric in metrics:
            if not isinstance(metric, dict):
                continue
            source_ids = metric.get("source_ids")
            source_note = (
                f"; {', '.join(str(s) for s in source_ids)}"
                if isinstance(source_ids, list) and source_ids
                else ""
            )
            lines.append(
                f"- {metric.get('name')}: {metric.get('value')} "
                f"(as of {metric.get('as_of')}{source_note})"
            )
    scenarios = shared_facts.get("scenarios")
    if isinstance(scenarios, dict):
        lines.append("Scenarios:")
        for key in ("bear", "base", "bull"):
            value = str(scenarios.get(key) or "").strip()
            if value:
                lines.append(f"- {key}: {value}")
    risks = shared_facts.get("risks")
    if isinstance(risks, list) and risks:
        lines.append("Risk list (ordered by rating, highest first):")
        for index, risk in enumerate(risks, start=1):
            if not isinstance(risk, dict):
                continue
            likelihood = str(risk.get("likelihood") or "").strip()
            likelihood_note = f" ({likelihood})" if likelihood else ""
            lines.append(
                f"{index}. {risk.get('summary')} — "
                f"{risk.get('rating')}{likelihood_note}"
            )
    source_topics = shared_facts.get("source_topics")
    if isinstance(source_topics, dict) and source_topics:
        lines.append("Source coverage:")
        for source_id in sorted(source_topics):
            lines.append(f"- {source_id}: {source_topics[source_id]}")
    return "\n".join(lines)


def _memo_english_common_context(
    *,
    company_name: str,
    company_slug: str,
    run_id: str,
    run_dir: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None,
    analysis_session_path: Path | None,
    scope_check: dict | None,
    warnings: list[str] | None,
) -> str:
    """Shared context for the spine, artifacts agent, and section workers.

    Passed to every parallel call as ``--append-system-prompt`` so the block
    lands on the CLI's system-prompt cache breakpoint: the first call writes
    one cache entry and the rest read it, instead of each paying for ~21KB of
    identical context in its user message. Keep it byte-identical across the
    calls of one invocation.
    """
    registry_entry = _extract_company_registry_entry_yaml(
        companies_yaml_path,
        company_slug,
    )
    registry_block = (
        f"```yaml\n{registry_entry}\n```"
        if registry_entry
        else f"Read the `{company_slug}` entry from `{companies_yaml_path}`."
    )
    analysis_dir = run_dir / "analysis"
    fast_dir = analysis_dir / "fast"
    source_mode = (
        "Use the approved Memo Studio packet as the primary synthesis."
        if analysis_session_path and analysis_session_path.exists()
        else "Use the fast parallel analysis artifacts as the primary synthesis."
    )
    return f"""\
This is the fast-path synthesis for a BSH LP-facing sell-side investment
memo about {company_name}. {source_mode}

{HUMAN_EXEC_MEMO_VOICE_CONTRACT}

{MEMO_PACKAGE_BLOCK_CONTRACT}

{MEMO_PACKAGE_SOURCES_CONTRACT}

{MEMO_CONTENT_PARITY_CONTRACT}

Use first-person sponsor voice: "we recommend participating", "we are being
offered", and "we are participating through". Never use detached
recommendation, opportunity, access, or base-case framing.

Company registry entry:
{registry_block}

Run context:
- run_id: {run_id}
- run_dir: `{run_dir}`
- English DOCX later rendered by server: `{memo_paths.get('en')}`
- Chinese DOCX later rendered by server: `{memo_paths.get('zh')}`
- scope_check: `{json.dumps(scope_check or {}, ensure_ascii=False)}`
- warnings: `{json.dumps(warnings or [], ensure_ascii=False)}`

Research folder:
`{research_dir if research_dir else '(none)'}`
Files:
{_research_file_listing(research_dir)}

Memo Studio packet:
`{analysis_session_path if analysis_session_path else '(none)'}`
Files:
{_analysis_session_file_listing(analysis_session_path)}

Fast analysis artifacts:
- JSON directory: `{fast_dir}`
- Markdown directory: `{analysis_dir}`

Read the relevant packet/artifact files. Do not rerun the eight analysis
passes. Use `analysis/fast/*.json` as the primary synthesis inputs because
they already contain the structured results from each pass. Read markdown
artifacts only when a JSON artifact is missing, contradictory, or needs a
short source-specific detail; when reading markdown, use targeted reads
rather than loading every full artifact.

Every user-facing string must be a bilingual object `{{"en": "...", "zh": ""}}`
with `zh` left blank; a separate subprocess fills Chinese. Do not write final
DOCX files, and do not write any files — return only JSON.
"""


def _memo_english_add_dirs(
    *,
    settings_path: Path,
    companies_yaml_path: Path,
    run_dir: Path,
    research_dir: Path | None,
    analysis_session_path: Path | None,
    lessons_path: Path | None,
) -> list[Path]:
    add_dirs = [settings_path.parent, companies_yaml_path.parent, run_dir]
    if research_dir and research_dir.exists():
        add_dirs.append(research_dir)
    if analysis_session_path and analysis_session_path.exists():
        add_dirs.append(analysis_session_path)
    if lessons_path and lessons_path.exists():
        add_dirs.append(lessons_path.parent)
    return add_dirs


def run_memo_fast_english_spine(
    *,
    run_dir: Path,
    company_name: str,
    common_context: str,
    add_dirs: list[Path],
    progress=None,
    timeout_sec: int = 1200,
    validation_feedback: str | None = None,
) -> tuple[dict | None, str | None]:
    """Synthesize the lite spine: package envelope plus the shared-facts pin
    sheet. No analysis artifacts, no memo prose — those belong to the side
    agent and the section workers."""
    feedback_block = (
        (
            "\n## Previous attempts failed renderer validation\n"
            "Fix EVERY error below that concerns the package envelope\n"
            "(company, run, sources) or the shared numbers, and make the\n"
            "shared facts prevent the rest from recurring:\n"
            f"{validation_feedback}\n"
        )
        if validation_feedback
        else ""
    )
    section_list = "\n".join(f"- `{sid}`" for sid in MEMO_PACKAGE_SECTION_IDS)
    prompt = f"""\
You are drafting the SHARED SPINE of the English source package. Five section
workers will author the memo sections in parallel from your output, and a
side agent writes the private analysis artifacts; none of them see each
other. Your job is ONLY the package envelope and the shared facts every
section must agree on — no memo prose, no analysis artifacts.

Produce ONE JSON object with:
1. `package_skeleton`: the package envelope WITHOUT sections:
   - `schema_version: 1`
   - `company`: name, descriptor, sector, stage, round, location
   - `run`: run_id, language, as_of, evidence_cutoff
   - `sources`: the COMPLETE non-empty source list for the whole memo,
     following the sources contract in your instructions. Sections cite
     these by id and cannot add sources, so include every source any
     section will need.
2. `shared_facts`: the compact pin sheet handed to every section worker:
   - `recommendation_sentence`: the exact first-person recommendation
     sentence, verbatim as the executive summary must state it.
   - `key_metrics`: the metric values sections repeat (name, value, as_of,
     supporting source ids).
   - `scenarios`: one line of numbers each for bear, base, and bull.
   - `risks`: the full risk list, ordered by rating highest first — one-line
     summary, `N/10` rating, and High/Medium/Low likelihood per risk.
   - `source_topics`: source id -> one line on what it supports.
3. `section_notes` (optional): at most one or two short sentences per
   section id, only for section-specific pointers the standing section
   requirements do not already cover:
{section_list}

The schema limits are hard: exceeding any maxLength or maxItems rejects the
whole response. Keep every value tight — this is a fact sheet, not a draft.
{feedback_block}
Return only the JSON matching the attached schema.
"""
    return _run_memo_local_json_artifact(
        prompt=prompt,
        schema=MEMO_FAST_ENGLISH_SPINE_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message="Pinning memo spine: envelope and shared facts",
        timeout_label="memo English spine",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=add_dirs,
        model=_memo_role_model("SPINE"),
        effort=_memo_role_effort("SPINE"),
        append_system_prompt=common_context,
    )


def run_memo_fast_english_artifacts(
    *,
    run_dir: Path,
    company_name: str,
    common_context: str,
    add_dirs: list[Path],
    progress=None,
    timeout_sec: int = 1200,
) -> tuple[dict | None, str | None]:
    """Author the seven private analysis artifacts on a side agent.

    Runs concurrently with the section workers; the sections never read
    these. Failures degrade to stub artifacts downstream — this call must
    never sink the whole parallel pass.
    """
    prompt = f"""\
You are writing the PRIVATE analysis artifacts for this memo run — internal
records saved under `analysis/`. The memo sections are written by other
workers and never read these; do not write memo prose or address the LP
reader.

Produce ONE JSON object with `analysis_artifacts` holding concise markdown
strings for: claim register, scenario swim lanes, downside scenario,
countercase, source-treatment and assumptions log, risk and valuation
sensitivities, and content coverage against the reusable component slugs.
Derive them from `analysis/fast/*.json`. The schema length limits are hard;
keep each artifact tight and useful.

Return only the JSON matching the attached schema.
"""
    return _run_memo_local_json_artifact(
        prompt=prompt,
        schema=MEMO_FAST_ENGLISH_ARTIFACTS_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message="Writing private analysis artifacts",
        timeout_label="memo English artifacts",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=add_dirs,
        model=_memo_role_model("ARTIFACTS"),
        effort=_memo_role_effort("ARTIFACTS"),
        append_system_prompt=common_context,
    )


def _memo_artifacts_async_enabled() -> bool:
    return (
        os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") == "1"
        and os.environ.get("BSH_MEMO_ARTIFACTS_ASYNC", "0") == "1"
    )


class AsyncArtifacts:
    """Run the private analysis-artifacts agent detached from the section wave.

    The seven artifacts derive only from ``analysis/fast/*.json`` — never
    from the spine or the sections — yet nothing in the run reads them until
    ``_write_fast_synthesis_artifacts`` fires after package acceptance,
    minutes after the section wave joins. Keeping the agent inside the wave
    made it the pass gate whenever it was the slowest worker (Run B: the
    whole wave waited on its 6.0 m). Detached, it starts as soon as the
    common context exists (overlapping even the spine) and is joined right
    before the artifacts are written to disk.

    The agent is submitted once per run — the artifacts are
    attempt-independent, so retries reuse the same in-flight future.
    Failure semantics are unchanged: a failed or unjoined agent degrades to
    stub artifact files, never sinks the pass.
    """

    def __init__(self, *, run_dir: Path, company_name: str, stream=None):
        from concurrent.futures import ThreadPoolExecutor

        self._run_dir = run_dir
        self._company_name = company_name
        self._stream = stream
        self._pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="memo-artifacts"
        )
        self._lock = threading.Lock()
        self._future = None

    @property
    def started(self) -> bool:
        with self._lock:
            return self._future is not None

    def start(
        self,
        *,
        common_context: str,
        add_dirs: list[Path],
        timeout_sec: int = 1200,
    ) -> None:
        """Submit the artifacts agent (idempotent across attempts)."""
        with self._lock:
            if self._future is not None:
                return
            row_label = "English artifacts"
            if self._stream is not None:
                self._stream.emit(
                    "thread_planned",
                    thread=row_label,
                    title=row_label,
                    phase_index=3.02,
                    parent_thread=_MEMO_PHASE3_THREAD,
                    group="memo_english_unit",
                    estimate_ms=300_000,
                    description=(
                        "Write the seven private analysis artifacts "
                        "(detached from the section wave)"
                    ),
                )
            self._future = self._pool.submit(
                self._run, row_label, common_context, add_dirs, timeout_sec
            )

    def _run(
        self,
        row_label: str,
        common_context: str,
        add_dirs: list[Path],
        timeout_sec: int,
    ) -> tuple[dict | None, str | None]:
        """Worker-thread body: run the agent and emit lifecycle events at
        their true times."""
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic()
        progress = None
        if self._stream is not None:
            self._stream.emit(
                "thread_started", thread=row_label, title=row_label
            )
            self._stream.emit(
                "phase_timing",
                phase="english_artifacts",
                status="started",
                started_at=started_at,
                thread=row_label,
            )
            progress = job_progress.ThreadProgress(self._stream, row_label)
        result, error = run_memo_fast_english_artifacts(
            run_dir=self._run_dir,
            company_name=self._company_name,
            common_context=common_context,
            add_dirs=add_dirs,
            progress=progress,
            timeout_sec=timeout_sec,
        )
        artifacts = (
            result.get("analysis_artifacts")
            if not error and isinstance(result, dict)
            else None
        )
        if isinstance(artifacts, dict):
            # Persist for the selective-retry splice, which reads the cache
            # from disk.
            try:
                artifacts_path = (
                    _memo_english_units_dir(self._run_dir)
                    / "analysis_artifacts.json"
                )
                artifacts_path.parent.mkdir(parents=True, exist_ok=True)
                artifacts_path.write_text(
                    json.dumps(artifacts, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "failed to persist detached analysis artifacts",
                    exc_info=True,
                )
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()
        if self._stream is not None:
            if error is None and isinstance(artifacts, dict):
                self._stream.emit(
                    "thread_finished", thread=row_label, duration_ms=duration_ms
                )
                self._stream.emit(
                    "phase_timing",
                    phase="english_artifacts",
                    status="finished",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row_label,
                    cost_usd=(result or {}).get("claude_cost_usd"),
                    claude_duration_ms=(result or {}).get("claude_duration_ms"),
                    detached=True,
                )
            else:
                self._stream.emit(
                    "thread_failed",
                    thread=row_label,
                    duration_ms=duration_ms,
                    error=str(error or "no artifacts returned")[:500],
                )
                self._stream.emit(
                    "phase_timing",
                    phase="english_artifacts",
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row_label,
                    error=str(error or "no artifacts returned")[:500],
                    detached=True,
                )
        return result, error

    def join(
        self, timeout_sec: float = 900.0
    ) -> tuple[dict | None, str | None]:
        """Wait for the agent; returns the raw run result tuple. Never
        raises — a timeout or crash comes back as an error string, which the
        caller degrades to stub artifacts exactly like an in-wave failure."""
        with self._lock:
            future = self._future
        if future is None:
            return None, "artifacts agent was never started"
        try:
            return future.result(timeout=timeout_sec)
        except Exception as exc:  # noqa: BLE001
            return None, f"artifacts agent did not complete: {exc}"

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)


def _run_english_section(
    *,
    run_dir: Path,
    section_id: str,
    common_context: str,
    shared_facts_block: str,
    spine_path: Path,
    add_dirs: list[Path],
    progress,
    timeout_sec: int,
    section_note: str = "",
    validation_errors: list[str] | None = None,
    previous_section_path: Path | None = None,
) -> tuple[dict | None, str | None]:
    """Author (or repair) ONE package section from the shared spine."""
    spec = _MEMO_SECTION_SPECS.get(section_id, "")
    risk_contract = (
        f"\n{MEMO_RISK_REGISTER_CONTRACT}\n"
        if section_id == "investment_risk"
        else ""
    )
    note_block = (
        f"\n## Spine note for this section\n{section_note}\n" if section_note else ""
    )
    repair_block = ""
    if previous_section_path is not None and validation_errors:
        error_lines = "\n".join(f"- {err}" for err in validation_errors[:20])
        repair_block = f"""
## Repair mode
A previous draft of this section is at `{previous_section_path}`. It failed
renderer validation with the errors below. Return the SAME section with ONLY
these defects fixed — preserve every other block, claim, number, table row,
and source reference exactly as-is:
{error_lines}
"""
    elif validation_errors:
        error_lines = "\n".join(f"- {err}" for err in validation_errors[:20])
        repair_block = f"""
## Previous attempt failed renderer validation
A previous attempt at this section failed validation. Do not repeat these
defects:
{error_lines}
"""
    # Section-specific content stays at the tail so the five section prompts
    # share their whole leading region (the system prompt already carries the
    # common context via --append-system-prompt).
    prompt = f"""\
You are drafting ONE SECTION of the English source package. Sibling workers
draft the other sections in parallel; the shared fact sheet below pins
everything the sections must agree on. Repeat the pinned recommendation,
numbers, and risk list exactly.

{shared_facts_block}

## Shared spine
The package envelope (company, run, complete sources list): `{spine_path}`.
Cite sources by the ids in the spine's `sources` list using source-class
language in prose; do not add, drop, or renumber sources.

## Your section: `{section_id}`
{spec}
{risk_contract}{note_block}{repair_block}
Return only JSON: {{"section": {{"id": "{section_id}", "blocks": [...]}}}}
matching the attached schema.
"""
    result, error = _run_memo_local_json_artifact(
        prompt=prompt,
        schema=_MEMO_ENGLISH_SECTION_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message=f"Drafting section {section_id}",
        timeout_label=f"memo English section ({section_id})",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=add_dirs,
        model=_memo_role_model("SECTION"),
        effort=_memo_role_effort("SECTION"),
        append_system_prompt=common_context,
    )
    if error:
        return None, error
    section = (result or {}).get("section")
    if not isinstance(section, dict):
        return None, f"section {section_id} pass did not return a section object"
    section["id"] = section_id
    return (
        {
            "section": section,
            "claude_cost_usd": result.get("claude_cost_usd"),
            "claude_duration_ms": result.get("claude_duration_ms"),
            "claude_usage": result.get("claude_usage"),
        },
        None,
    )


def _iter_package_strings(value: Any):
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_package_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_package_strings(item)
    elif isinstance(value, str):
        yield value


def _section_for_validation_error(package: dict, error: str) -> str | None:
    """Map one validation error string to the package section that owns it.

    Returns None when the error is not attributable to a single section
    (envelope/sources defects, or text we cannot locate) — the caller then
    falls back to a full regeneration.
    """
    lowered = error.lower()
    sections = package.get("sections") if isinstance(package, dict) else None
    sections = sections if isinstance(sections, list) else []

    match = re.search(r"sections\[(\d+)\]", error)
    if match:
        index = int(match.group(1))
        if 0 <= index < len(sections) and isinstance(sections[index], dict):
            section_id = str(sections[index].get("id") or "")
            if section_id in MEMO_PACKAGE_SECTION_IDS:
                return section_id
        return None

    for section_id in MEMO_PACKAGE_SECTION_IDS:
        if section_id in lowered:
            return section_id

    match = re.search(r"missing required memo component (\w+)", lowered)
    if match:
        return _MEMO_COMPONENT_SECTION.get(match.group(1))

    context_match = re.search(r" at [^():]*\(([^)]+)\)", error)
    if context_match:
        context = context_match.group(1).strip().lower()
        context = re.sub(r"^[ivx]+\.\s*", "", context)
        mapped = _MEMO_SECTION_TITLE_WORDS.get(context)
        if mapped:
            return mapped
        for section in sections:
            if not isinstance(section, dict):
                continue
            section_id = str(section.get("id") or "")
            if section_id not in MEMO_PACKAGE_SECTION_IDS:
                continue
            for block in section.get("blocks") or []:
                if not isinstance(block, dict):
                    continue
                labels = [block.get("text"), block.get("title")]
                for label in labels:
                    en = (
                        str(label.get("en") or "")
                        if isinstance(label, dict)
                        else str(label or "")
                    )
                    if en and context in en.lower():
                        return section_id

    snippet_match = re.search(r'"([^"]{12,})"', error)
    if snippet_match:
        fragments = [
            fragment.strip()
            for fragment in snippet_match.group(1).split("...")
            if len(fragment.strip()) >= 12
        ]
        needle = max(fragments, key=len, default="").lower()
        if needle:
            for section in sections:
                if not isinstance(section, dict):
                    continue
                section_id = str(section.get("id") or "")
                if section_id not in MEMO_PACKAGE_SECTION_IDS:
                    continue
                for text in _iter_package_strings(section):
                    if needle in text.lower():
                        return section_id
    return None


def _map_validation_errors_to_sections(
    package: dict,
    errors: list[str],
) -> dict[str, list[str]] | None:
    """Group validation errors by owning section. Returns None when any error
    cannot be attributed to a single section."""
    mapping: dict[str, list[str]] = {}
    for error in errors:
        section_id = _section_for_validation_error(package, error)
        if section_id is None:
            return None
        mapping.setdefault(section_id, []).append(error)
    return mapping


def run_memo_fast_english_package_parallel(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    progress=None,
    timeout_sec: int = 1200,
    validation_feedback: str | None = None,
    previous_validation_errors: list[str] | None = None,
    previous_package_path: Path | None = None,
    max_workers: int | None = None,
    stream=None,
    attempt: int | None = None,
    on_spine=None,
    on_section=None,
    async_artifacts: AsyncArtifacts | None = None,
) -> tuple[dict | None, str | None]:
    """Spine-lite + parallel per-section synthesis of the English package.

    A fast spine call pins the package envelope (company/run/sources) and a
    compact shared-facts sheet; five section workers then draft the memo
    sections in parallel while a side agent writes the private analysis
    artifacts. All post-spine calls share the common context through
    ``--append-system-prompt`` so they read one prompt-cache entry instead
    of six cold contexts. Same result shape as
    ``run_memo_fast_english_package`` plus ``claude_wall_ms`` (true
    wall-clock of the parallel pass). Falls back to the monolithic call when
    disabled or when the spine/section machinery fails. On a validation
    retry with attributable errors, regenerates only the implicated sections
    and splices the rest from the previous attempt.

    ``stream`` (the run's ProgressLog) adds one lifecycle thread row per
    worker under Phase 3; ``attempt`` suffixes the row labels so retries get
    fresh rows. ``on_spine(spine_payload)`` fires once after the spine is
    validated and written; ``on_section(section_id, section)`` fires in the
    worker thread on each successful section — full pass only, never the
    selective retry. Both hooks are exception-guarded (the Chinese chasing
    seam).

    ``async_artifacts`` (an :class:`AsyncArtifacts` handle) detaches the
    artifacts agent from the section wave: it starts at wrapper entry and
    the caller joins it after acceptance; ``analysis_artifacts`` comes back
    ``None`` in that mode.

    Default OFF behind BSH_MEMO_ENGLISH_PARALLEL — experimental; benchmark
    per docs/memo-benchmarks.md before enabling.
    """
    if os.environ.get("BSH_MEMO_ENGLISH_PARALLEL", "0") != "1":
        return run_memo_fast_english_package(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            settings_path=settings_path,
            companies_yaml_path=companies_yaml_path,
            memo_paths=memo_paths,
            research_dir=research_dir,
            analysis_session_path=analysis_session_path,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            progress=progress,
            timeout_sec=timeout_sec,
            validation_feedback=validation_feedback,
        )

    def _fallback(reason: str) -> tuple[dict | None, str | None]:
        logger.warning(
            "parallel English package falling back to monolithic: %s", reason
        )
        if progress is not None:
            progress.emit(
                "stage",
                stage="memo_fast_english_parallel_fallback",
                message=(
                    f"Parallel English synthesis unavailable ({reason[:500]}); "
                    "running monolithic pass"
                ),
            )
        return run_memo_fast_english_package(
            run_dir=run_dir,
            company_name=company_name,
            company_slug=company_slug,
            run_id=run_id,
            settings_path=settings_path,
            companies_yaml_path=companies_yaml_path,
            memo_paths=memo_paths,
            research_dir=research_dir,
            analysis_session_path=analysis_session_path,
            lessons_path=lessons_path,
            scope_check=scope_check,
            warnings=warnings,
            progress=progress,
            timeout_sec=timeout_sec,
            validation_feedback=validation_feedback,
        )

    wall_start = time.monotonic()
    common_context = _memo_english_common_context(
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        run_dir=run_dir,
        companies_yaml_path=companies_yaml_path,
        memo_paths=memo_paths,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        scope_check=scope_check,
        warnings=warnings,
    )
    add_dirs = _memo_english_add_dirs(
        settings_path=settings_path,
        companies_yaml_path=companies_yaml_path,
        run_dir=run_dir,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
    )
    units_dir = _memo_english_units_dir(run_dir)
    units_dir.mkdir(parents=True, exist_ok=True)
    spine_path = units_dir / "spine.json"
    artifacts_path = units_dir / "analysis_artifacts.json"
    if async_artifacts is not None:
        # Detached mode: the artifacts agent starts now — overlapping the
        # spine and the section wave — and the caller joins it after
        # acceptance. Idempotent, so retry attempts reuse the same run.
        async_artifacts.start(
            common_context=common_context,
            add_dirs=add_dirs,
            timeout_sec=timeout_sec,
        )
    try:
        env_workers = int(
            os.environ.get("BSH_MEMO_ENGLISH_SECTION_WORKERS", "6") or 6
        )
    except ValueError:
        env_workers = 6
    workers = max_workers or env_workers
    # +1: the analysis-artifacts side agent shares the pool with the five
    # section workers.
    workers = max(1, min(workers, len(MEMO_PACKAGE_SECTION_IDS) + 1))
    from concurrent.futures import ThreadPoolExecutor

    attempt_suffix = f" (attempt {attempt})" if attempt and attempt > 1 else ""

    def _row(label: str) -> str:
        # job_progress keeps finished rows finished, so retries need fresh
        # labels.
        return f"{label}{attempt_suffix}"

    def _plan_row(label: str, phase_index: float, description: str) -> None:
        if stream is None:
            return
        stream.emit(
            "thread_planned",
            thread=_row(label),
            title=_row(label),
            phase_index=phase_index,
            parent_thread=_MEMO_PHASE3_THREAD,
            group="memo_english_unit",
            estimate_ms=300_000,
            description=description,
        )

    def _start_row(label: str, phase_name: str):
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic()
        if stream is not None:
            stream.emit("thread_started", thread=_row(label), title=_row(label))
            stream.emit(
                "phase_timing",
                phase=phase_name,
                status="started",
                started_at=started_at,
                thread=_row(label),
                **({"attempt": attempt} if attempt else {}),
            )
        return started_at, started_monotonic

    def _finish_row(
        label: str,
        phase_name: str,
        started,
        *,
        error=None,
        result: dict | None = None,
    ) -> None:
        if stream is None:
            return
        started_at, started_monotonic = started
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()
        extra = {"attempt": attempt} if attempt else {}
        if error is None:
            usage = (result or {}).get("claude_usage")
            cache_read = (
                usage.get("cache_read_input_tokens")
                if isinstance(usage, dict)
                else None
            )
            stream.emit(
                "thread_finished",
                thread=_row(label),
                duration_ms=duration_ms,
            )
            stream.emit(
                "phase_timing",
                phase=phase_name,
                status="finished",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                thread=_row(label),
                cost_usd=(result or {}).get("claude_cost_usd"),
                claude_duration_ms=(result or {}).get("claude_duration_ms"),
                cache_read_input_tokens=cache_read,
                **extra,
            )
        else:
            stream.emit(
                "thread_failed",
                thread=_row(label),
                duration_ms=duration_ms,
                error=str(error)[:500],
            )
            stream.emit(
                "phase_timing",
                phase=phase_name,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                thread=_row(label),
                error=str(error)[:500],
                **extra,
            )

    def _run_sections(
        section_jobs: dict[str, dict],
        *,
        section_hook=None,
        run_artifacts: bool = False,
    ) -> tuple[dict[str, dict], list[str], dict | None, str | None]:
        """Run section workers (plus, optionally, the artifacts side agent)
        concurrently. Each job dict carries the _run_english_section kwargs
        beyond the shared ones. The artifacts agent's failure is returned
        separately — it must never count as a section failure."""
        results: dict[str, dict] = {}
        errors: list[str] = []
        artifacts_result: dict | None = None
        artifacts_error: str | None = None

        def _run_one(section_id: str, job: dict):
            row = f"Section - {section_id}"
            phase_name = f"english_section:{section_id}"
            started = _start_row(row, phase_name)
            result, error = _run_english_section(
                run_dir=run_dir,
                section_id=section_id,
                common_context=common_context,
                spine_path=spine_path,
                add_dirs=add_dirs,
                progress=progress,
                timeout_sec=timeout_sec,
                **job,
            )
            _finish_row(row, phase_name, started, error=error, result=result)
            if error is None and isinstance(result, dict) and section_hook:
                try:
                    section_hook(section_id, result["section"])
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "section hook failed for %s", section_id, exc_info=True
                    )
            return result, error

        def _run_artifacts_agent():
            started = _start_row("English artifacts", "english_artifacts")
            result, error = run_memo_fast_english_artifacts(
                run_dir=run_dir,
                company_name=company_name,
                common_context=common_context,
                add_dirs=add_dirs,
                progress=progress,
                timeout_sec=timeout_sec,
            )
            _finish_row(
                "English artifacts",
                "english_artifacts",
                started,
                error=error,
                result=result,
            )
            return result, error

        job_count = len(section_jobs) + (1 if run_artifacts else 0)
        with ThreadPoolExecutor(
            max_workers=max(1, min(workers, job_count)),
            thread_name_prefix="memo-english",
        ) as pool:
            futures = {
                pool.submit(_run_one, section_id, job): section_id
                for section_id, job in section_jobs.items()
            }
            artifacts_future = (
                pool.submit(_run_artifacts_agent) if run_artifacts else None
            )
            for future, section_id in futures.items():
                try:
                    result, error = future.result()
                except Exception as exc:  # noqa: BLE001
                    result, error = None, f"section {section_id} crashed: {exc}"
                if error or not isinstance(result, dict):
                    errors.append(f"{section_id}: {error or 'no result'}")
                else:
                    results[section_id] = result
            if artifacts_future is not None:
                try:
                    artifacts_result, artifacts_error = artifacts_future.result()
                except Exception as exc:  # noqa: BLE001
                    artifacts_result = None
                    artifacts_error = f"artifacts agent crashed: {exc}"
        return results, errors, artifacts_result, artifacts_error

    def _degraded_artifacts(artifacts_error: str | None) -> dict:
        """Warn and return empty artifacts — downstream writes stub files."""
        logger.warning(
            "analysis-artifacts agent degraded to stubs: %s", artifacts_error
        )
        if progress is not None:
            progress.emit(
                "stage",
                stage="memo_fast_english_artifacts_degraded",
                message=(
                    "Analysis-artifacts agent failed; writing stub artifacts "
                    f"({str(artifacts_error)[:300]})"
                ),
            )
        return {}

    # ---- Selective retry: regenerate only the sections the errors name ----
    if (
        previous_validation_errors
        and previous_package_path is not None
        and previous_package_path.exists()
        and spine_path.exists()
        and (artifacts_path.exists() or async_artifacts is not None)
    ):
        try:
            previous_package = json.loads(
                previous_package_path.read_text(encoding="utf-8")
            )
            spine = json.loads(spine_path.read_text(encoding="utf-8"))
            # In detached mode the artifacts cache may not exist yet (the
            # agent is still running); the caller's join delivers it later.
            artifacts = (
                json.loads(artifacts_path.read_text(encoding="utf-8"))
                if artifacts_path.exists()
                else None
            )
        except Exception:  # noqa: BLE001
            previous_package = None
            spine = None
            artifacts = None
        mapping = (
            _map_validation_errors_to_sections(
                previous_package, list(previous_validation_errors)
            )
            if isinstance(previous_package, dict)
            and isinstance(spine, dict)
            # A cached spine.json from the pre-spine-lite format (no
            # shared_facts) cannot brief the section workers — run the full
            # pass instead of mis-splicing.
            and isinstance(spine.get("shared_facts"), dict)
            else None
        )
        if mapping:
            facts_block = _render_shared_facts_block(spine["shared_facts"])
            section_notes = spine.get("section_notes")
            if not isinstance(section_notes, dict):
                section_notes = {}
            previous_sections = {
                str(section.get("id") or ""): section
                for section in previous_package.get("sections") or []
                if isinstance(section, dict)
            }
            if progress is not None:
                progress.emit(
                    "stage",
                    stage="memo_fast_english_section_retry",
                    message=(
                        "Regenerating only the sections named by validation "
                        f"errors: {', '.join(sorted(mapping))}"
                    ),
                    sections=sorted(mapping),
                )
            section_jobs: dict[str, dict] = {}
            for section_id, section_errors in mapping.items():
                previous_section = previous_sections.get(section_id)
                previous_section_path = None
                if isinstance(previous_section, dict):
                    previous_section_path = (
                        units_dir / f"{section_id}.previous.json"
                    )
                    previous_section_path.write_text(
                        json.dumps(
                            previous_section, ensure_ascii=False, indent=2
                        ),
                        encoding="utf-8",
                    )
                section_jobs[section_id] = {
                    "shared_facts_block": facts_block,
                    "section_note": str(section_notes.get(section_id) or ""),
                    "validation_errors": section_errors,
                    "previous_section_path": previous_section_path,
                }
            cached_artifacts = artifacts if isinstance(artifacts, dict) else {}
            results, errors, artifacts_result, artifacts_error = _run_sections(
                section_jobs,
                run_artifacts=not cached_artifacts and async_artifacts is None,
            )
            if not errors:
                if not cached_artifacts and async_artifacts is None:
                    if isinstance(artifacts_result, dict) and isinstance(
                        artifacts_result.get("analysis_artifacts"), dict
                    ):
                        cached_artifacts = artifacts_result["analysis_artifacts"]
                    else:
                        cached_artifacts = _degraded_artifacts(artifacts_error)
                    artifacts_path.write_text(
                        json.dumps(
                            cached_artifacts, ensure_ascii=False, indent=2
                        ),
                        encoding="utf-8",
                    )
                package = dict(previous_package)
                package["sections"] = [
                    results[section_id]["section"]
                    if section_id in results
                    else previous_sections.get(section_id)
                    for section_id in MEMO_PACKAGE_SECTION_IDS
                    if section_id in results
                    or previous_sections.get(section_id) is not None
                ]
                cost = sum(
                    _to_float(result.get("claude_cost_usd"))
                    for result in results.values()
                ) + _to_float((artifacts_result or {}).get("claude_cost_usd"))
                duration = max(
                    (
                        _to_int(result.get("claude_duration_ms"))
                        for result in results.values()
                    ),
                    default=0,
                )
                return (
                    {
                        # Empty-with-a-detached-agent means "not delivered
                        # yet" (the caller joins); a real degraded {} still
                        # comes back as a dict so stubs get written.
                        "analysis_artifacts": (
                            cached_artifacts
                            if cached_artifacts or async_artifacts is None
                            else None
                        ),
                        "memo_package": package,
                        "claude_cost_usd": round(cost, 6) if cost else None,
                        "claude_duration_ms": duration or None,
                        "claude_usage": None,
                        "claude_wall_ms": int(
                            (time.monotonic() - wall_start) * 1000
                        ),
                    },
                    None,
                )
            logger.warning(
                "selective section retry failed (%s); running full parallel pass",
                "; ".join(errors[:3]),
            )

    # ---- Full parallel pass: spine, then sections + artifacts -------------
    _plan_row(
        "English spine",
        3.01,
        "Pin the package envelope and shared facts",
    )
    spine_row_started = _start_row("English spine", "english_spine")
    spine_result, spine_error = run_memo_fast_english_spine(
        run_dir=run_dir,
        company_name=company_name,
        common_context=common_context,
        add_dirs=add_dirs,
        progress=progress,
        timeout_sec=timeout_sec,
        validation_feedback=validation_feedback,
    )
    _finish_row(
        "English spine",
        "english_spine",
        spine_row_started,
        error=spine_error,
        result=spine_result if isinstance(spine_result, dict) else None,
    )
    if spine_error or not isinstance(spine_result, dict):
        return _fallback(spine_error or "spine pass returned no data")
    skeleton = spine_result.get("package_skeleton")
    shared_facts = spine_result.get("shared_facts")
    section_notes = spine_result.get("section_notes")
    if not isinstance(section_notes, dict):
        section_notes = {}
    if (
        not isinstance(skeleton, dict)
        or not isinstance(skeleton.get("company"), dict)
        or not isinstance(skeleton.get("sources"), list)
        or not skeleton.get("sources")
        or not isinstance(shared_facts, dict)
    ):
        return _fallback("spine returned an unusable skeleton or shared facts")
    spine_payload = {
        "package_skeleton": skeleton,
        "shared_facts": shared_facts,
        "section_notes": section_notes,
    }
    spine_path.write_text(
        json.dumps(spine_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if on_spine is not None:
        try:
            on_spine(spine_payload)
        except Exception:  # noqa: BLE001
            logger.warning("spine hook failed", exc_info=True)
    if async_artifacts is None:
        _plan_row(
            "English artifacts",
            3.02,
            "Write the seven private analysis artifacts",
        )
    for index, section_id in enumerate(MEMO_PACKAGE_SECTION_IDS):
        _plan_row(
            f"Section - {section_id}",
            round(3.03 + index / 100, 4),
            f"Draft the {section_id} section",
        )
    if progress is not None:
        progress.emit(
            "stage",
            stage="memo_fast_english_parallel_dispatch",
            message=(
                f"Drafting {len(MEMO_PACKAGE_SECTION_IDS)} memo sections and "
                f"the analysis artifacts with up to {workers} parallel workers"
            ),
            sections=list(MEMO_PACKAGE_SECTION_IDS),
            worker_count=workers,
        )
    feedback_errors: list[str] | None = None
    if validation_feedback:
        feedback_errors = [
            line[2:].strip() if line.startswith("- ") else line.strip()
            for line in validation_feedback.splitlines()
            if line.strip()
        ]
    facts_block = _render_shared_facts_block(shared_facts)
    section_jobs = {
        section_id: {
            "shared_facts_block": facts_block,
            "section_note": str(section_notes.get(section_id) or ""),
            "validation_errors": feedback_errors,
            "previous_section_path": None,
        }
        for section_id in MEMO_PACKAGE_SECTION_IDS
    }
    results, errors, artifacts_result, artifacts_error = _run_sections(
        section_jobs,
        section_hook=on_section,
        run_artifacts=async_artifacts is None,
    )
    if errors:
        return _fallback("; ".join(errors[:3]))
    if async_artifacts is not None:
        # Detached mode: the caller joins the artifacts agent after
        # acceptance; the agent persists its own cache file.
        artifacts = None
    elif isinstance(artifacts_result, dict) and isinstance(
        artifacts_result.get("analysis_artifacts"), dict
    ):
        artifacts = artifacts_result["analysis_artifacts"]
    else:
        artifacts = _degraded_artifacts(artifacts_error)
    if artifacts is not None:
        artifacts_path.write_text(
            json.dumps(artifacts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    sections = [
        results[section_id]["section"]
        for section_id in MEMO_PACKAGE_SECTION_IDS
    ]
    package = dict(skeleton)
    package.setdefault("schema_version", 1)
    package["sections"] = sections
    cost = (
        _to_float(spine_result.get("claude_cost_usd"))
        + _to_float((artifacts_result or {}).get("claude_cost_usd"))
        + sum(
            _to_float(result.get("claude_cost_usd"))
            for result in results.values()
        )
    )
    worker_durations = [
        _to_int(result.get("claude_duration_ms")) for result in results.values()
    ]
    worker_durations.append(
        _to_int((artifacts_result or {}).get("claude_duration_ms"))
    )
    duration = _to_int(spine_result.get("claude_duration_ms")) + max(
        worker_durations, default=0
    )
    return (
        {
            "analysis_artifacts": artifacts,
            "memo_package": package,
            "claude_cost_usd": round(cost, 6) if cost else None,
            "claude_duration_ms": duration or None,
            "claude_usage": None,
            "claude_wall_ms": int((time.monotonic() - wall_start) * 1000),
        },
        None,
    )


def run_memo_fast_bilingual_package(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    english_package_path: Path,
    progress=None,
    timeout_sec: int = 1200,
) -> tuple[dict | None, str | None]:
    """Fill Chinese strings in the English source package."""
    prompt = f"""\
You are completing the Simplified Chinese version of a BSH LP-facing investment
memo package for {company_name}.

Input English source package:
`{english_package_path}`

Run id: {run_id}

Task:
- Read the English package.
- Return `memo_package` with the same JSON schema, unchanged English values,
  same source list, same recommendation, same numbers, and same table rows.
- Fill every blank `zh` user-facing string with native professional Simplified
  Chinese suitable for institutional investment readers.
- Preserve company names, executive names, tickers, dates, currency amounts,
  percentages, URLs, SAFE, SPV, ARR, NRR, IRR, EBITDA, CAGR, and other standard
  acronyms in Latin form where appropriate.
- Do not soften risks or change the investment recommendation.
- Do not introduce new analysis.
- Do not write files or DOCX outputs. Return only the JSON object matching the
  attached schema.

Chinese style:
- Formal written Chinese, not colloquial.
- Use Chinese punctuation in Chinese sentences.
- Keep a half-width space around Latin acronyms inside Chinese sentences.
- Avoid prompt-scaffold terms such as `上行状态`, `现态`, `关键现实检查`,
  source-trace labels, memo-package labels, reviewer-prompt labels,
  decision-question labels, `硬 IP 墙`, or `软性工具`.
- Use these fixed translations for risk-card row labels: Risk Type →
  风险类型; Why it matters → 为什么重要; What we watch → 跟踪信号;
  Likelihood → 可能性; Risk Rating → 风险评分. A card heading
  "Risk N: <summary>" becomes "风险 N：<一句话概括>". Likelihood values
  High/Medium/Low become 高/中/低 (e.g. `高：<简短理由>`). Keep the
  rating value format `N/10` unchanged.
"""
    return _run_memo_local_json_artifact(
        prompt=prompt,
        schema=MEMO_FAST_BILINGUAL_PACKAGE_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message="Completing Chinese memo package",
        timeout_label="memo Chinese package",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=[run_dir],
        model=_memo_role_model("TRANSLATION"),
        effort=_memo_role_effort("TRANSLATION"),
    )


def run_memo_package_structure_repair(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    package_path: Path,
    validation_errors: list[str],
    progress=None,
    timeout_sec: int = 900,
) -> tuple[dict | None, str | None]:
    """Surgically fix listed validation defects in an existing package.

    Last-resort recovery: instead of regenerating a whole ~$2.5 English
    package because one callout is missing a title, hand the invalid package
    plus the exact validator errors to a short repair pass that must return
    the full package with ONLY those defects fixed.
    """
    error_lines = "\n".join(f"- {err}" for err in validation_errors[:30])
    prompt = f"""\
You are repairing the structure of a BSH LP-facing investment memo package
for {company_name} (run id: {run_id}).

Input package (fails renderer validation):
`{package_path}`

Renderer validation errors to fix:
{error_lines}

{MEMO_PACKAGE_BLOCK_CONTRACT}

{MEMO_PACKAGE_SOURCES_CONTRACT}

{MEMO_RISK_REGISTER_CONTRACT}

Task:
- Read the package file.
- Return `memo_package`: the SAME package with ONLY the listed defects
  repaired. This is a structural repair, not a rewrite.
- Preserve every analytical claim, number, table row, source, English string,
  and Chinese string exactly as-is unless a listed error requires changing it.
- A missing callout title must be a short label derived from that callout's
  own content. A missing bilingual value must be authored from the
  surrounding context of that block only.
- Do not add, remove, or reorder sections or blocks unless a listed error
  requires it.
- Do not write files. Return only the JSON object matching the attached
  schema.
"""
    return _run_memo_local_json_artifact(
        prompt=prompt,
        schema=MEMO_FAST_BILINGUAL_PACKAGE_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message="Repairing memo package structure",
        timeout_label="memo package structure repair",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=[run_dir],
        model=_memo_role_model("REPAIR"),
        effort=_memo_role_effort("REPAIR"),
    )


_MEMO_BILINGUAL_UNIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "unit": {
            "type": "object",
            "additionalProperties": True,
        },
    },
    "required": ["unit"],
}

_MEMO_BILINGUAL_STYLE = """\
Chinese style:
- Formal written Chinese, not colloquial.
- Use Chinese punctuation in Chinese sentences.
- Keep a half-width space around Latin acronyms inside Chinese sentences.
- Preserve company names, executive names, tickers, dates, currency amounts,
  percentages, URLs, SAFE, SPV, ARR, NRR, IRR, EBITDA, CAGR, and other standard
  acronyms in Latin form where appropriate.
- Avoid prompt-scaffold terms such as `上行状态`, `现态`, `关键现实检查`,
  source-trace labels, memo-package labels, reviewer-prompt labels,
  decision-question labels, `硬 IP 墙`, or `软性工具`.
- Use these fixed translations for risk-card row labels: Risk Type →
  风险类型; Why it matters → 为什么重要; What we watch → 跟踪信号;
  Likelihood → 可能性; Risk Rating → 风险评分. A card heading
  "Risk N: <summary>" becomes "风险 N：<一句话概括>". Likelihood values
  High/Medium/Low become 高/中/低 (e.g. `高：<简短理由>`). Keep the
  rating value format `N/10` unchanged.
"""


def _adopt_zh_translations(source: Any, translated: Any) -> None:
    """Copy ONLY ``zh`` strings from ``translated`` into ``source`` in place.

    The merge is deliberately one-way and shape-conservative: English values,
    numbers, list lengths, and structure always come from ``source`` (the
    English package). A localized value is a ``{en, zh}`` dict; we adopt its
    ``zh`` only when the ``en`` on both sides matches, so a unit that drifted
    from its input cannot corrupt the package.
    """
    if isinstance(source, dict) and isinstance(translated, dict):
        if "en" in source and "zh" in source:
            if (
                str(translated.get("zh") or "").strip()
                and translated.get("en") == source.get("en")
                and not str(source.get("zh") or "").strip()
            ):
                source["zh"] = translated["zh"]
        for key, value in source.items():
            if key in translated:
                _adopt_zh_translations(value, translated[key])
        return
    if isinstance(source, list) and isinstance(translated, list):
        if len(source) == len(translated):
            for s_item, t_item in zip(source, translated):
                _adopt_zh_translations(s_item, t_item)


def _run_bilingual_unit(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    unit_label: str,
    unit_path: Path,
    progress,
    timeout_sec: int,
) -> tuple[dict | None, str | None]:
    prompt = f"""\
You are completing the Simplified Chinese strings of ONE part of a BSH
LP-facing investment memo package for {company_name} (run id: {run_id}).

Input English source JSON for this part ({unit_label}):
`{unit_path}`

Task:
- Read the input JSON.
- Return `unit` with exactly the same JSON structure, unchanged English
  values, same numbers, and same list lengths.
- Fill every blank `zh` user-facing string with native professional
  Simplified Chinese suitable for institutional investment readers.
- Do not soften risks or change any recommendation.
- Do not introduce new analysis.
- Do not write files. Return only the JSON object matching the attached
  schema.

{_MEMO_BILINGUAL_STYLE}"""
    result, error = _run_memo_local_json_artifact(
        prompt=prompt,
        schema=_MEMO_BILINGUAL_UNIT_SCHEMA,
        run_dir=run_dir,
        progress=progress,
        progress_message=f"Translating {unit_label}",
        timeout_label=f"memo Chinese package ({unit_label})",
        timeout_sec=timeout_sec,
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
        add_dirs=[run_dir],
        model=_memo_role_model("TRANSLATION"),
        effort=_memo_role_effort("TRANSLATION"),
    )
    if error:
        return None, error
    unit = (result or {}).get("unit")
    if not isinstance(unit, dict):
        return None, f"{unit_label} pass did not return a unit object"
    unit["claude_cost_usd"] = result.get("claude_cost_usd")
    unit["claude_duration_ms"] = result.get("claude_duration_ms")
    return unit, None


def _memo_zh_chase_workers() -> int:
    # Default 4: there are six chase units (envelope + five sections) and
    # with 2 workers they queued behind each other — the Phase-4 join then
    # waited ~1-2 minutes for the tail (measured on the 2026-08-28 runs).
    # Units arrive staggered as sections finish, so 4 clears the queue
    # without meaningfully raising peak subprocess pressure.
    raw = os.environ.get("BSH_MEMO_ZH_CHASE_WORKERS")
    try:
        value = int(raw) if raw is not None else 4
    except (TypeError, ValueError):
        value = 4
    return max(1, min(value, 6))


def _memo_zh_chase_join_timeout_sec() -> float:
    raw = os.environ.get("BSH_MEMO_ZH_CHASE_JOIN_TIMEOUT_SEC")
    try:
        value = float(raw) if raw is not None else 900.0
    except (TypeError, ValueError):
        value = 900.0
    return max(0.0, min(value, 1800.0))


class BilingualChaser:
    """Speculative Chinese translation racing the English synthesis.

    When the parallel English path is on, `on_spine`/`on_section` hooks
    snapshot each finished English unit to disk and immediately start its
    translation on a private pool — while other sections are still being
    written. After the English package is ACCEPTED, `collect()` joins the
    in-flight units (bounded wait) and `merge_into()` adopts translations
    via `_adopt_zh_translations`, whose exact-``en``-match rule silently
    drops anything a later repair or regeneration invalidated. Whatever is
    still blank falls to the normal gap-fill pass, so staleness can only
    ever waste money, never corrupt the memo.

    Hooks fire on attempt 1 of the full parallel pass only (the caller
    enforces this), bounding the worst-case waste at one translation round.
    A unit that misses the join deadline keeps running until its own
    subprocess timeout; its result is simply unused.
    """

    def __init__(
        self,
        *,
        run_dir: Path,
        company_name: str,
        run_id: str,
        stream=None,
        max_workers: int | None = None,
        unit_timeout_sec: int = 1200,
    ):
        from concurrent.futures import ThreadPoolExecutor

        self._run_dir = run_dir
        self._company_name = company_name
        self._run_id = run_id
        self._stream = stream
        self._timeout_sec = unit_timeout_sec
        self._units_dir = run_dir / "logs" / "bilingual_units" / "chase"
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers or _memo_zh_chase_workers(),
            thread_name_prefix="memo-zh-chase",
        )
        self._lock = threading.Lock()
        self._futures: dict[str, Any] = {}
        self._submitted: dict[str, tuple[str, float]] = {}
        # Terminal-event bookkeeping: a unit's finished/failed events are
        # emitted by its worker thread the moment it completes (so the job
        # UI shows real runtimes, not wait-for-join time); collect() emits
        # a failure only for units it abandons at the join deadline, and
        # the two sides use these sets to never double-emit.
        self._terminal_emitted: set[str] = set()
        self._abandoned: set[str] = set()

    @property
    def has_units(self) -> bool:
        return bool(self._futures)

    @property
    def unit_count(self) -> int:
        return len(self._futures)

    def on_spine(self, spine_payload: dict) -> None:
        """Hook: the envelope (company/run/sources) is stable once the spine
        lands — start its translation immediately."""
        try:
            skeleton = (spine_payload or {}).get("package_skeleton")
            if isinstance(skeleton, dict) and skeleton:
                self._submit(
                    "envelope", "package envelope (chase)", skeleton, 4.01
                )
        except Exception:  # noqa: BLE001
            logger.warning("zh chase spine hook failed", exc_info=True)

    def on_section(self, section_id: str, section: dict) -> None:
        try:
            if not isinstance(section, dict):
                return
            try:
                index = MEMO_PACKAGE_SECTION_IDS.index(str(section_id))
            except ValueError:
                index = len(MEMO_PACKAGE_SECTION_IDS)
            self._submit(
                str(section_id),
                f"section {section_id} (chase)",
                section,
                round(4.02 + index / 100, 4),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "zh chase section hook failed for %s", section_id, exc_info=True
            )

    def _submit(
        self, unit_id: str, label: str, payload: dict, phase_index: float
    ) -> None:
        with self._lock:
            if unit_id in self._futures:
                return
            self._units_dir.mkdir(parents=True, exist_ok=True)
            # Snapshot to disk NOW: later structure/quality repairs mutate
            # the live section objects, and the unit prompt reads a path.
            unit_path = self._units_dir / f"{unit_id}.en.json"
            unit_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            row_label = f"Chinese chase - {unit_id}"
            self._submitted[unit_id] = (
                datetime.now(timezone.utc).isoformat(),
                time.monotonic(),
            )
            if self._stream is not None:
                self._stream.emit(
                    "thread_planned",
                    thread=row_label,
                    title=row_label,
                    phase_index=phase_index,
                    parent_thread=_MEMO_PHASE4_THREAD,
                    group="memo_zh_chase",
                    unit_id=unit_id,
                    estimate_ms=300_000,
                    description=f"Speculatively translate the {label}",
                )
            self._futures[unit_id] = self._pool.submit(
                self._run_unit, unit_id, label, row_label, unit_path
            )

    def _run_unit(
        self, unit_id: str, label: str, row_label: str, unit_path: Path
    ) -> tuple[dict | None, str | None]:
        """Worker-thread body: run the translation and emit the unit's
        started/terminal events at their true times (a row emitted only at
        join time showed 15-minute walls for 75-second translations)."""
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic()
        unit_progress = None
        if self._stream is not None:
            self._stream.emit(
                "thread_started",
                thread=row_label,
                title=row_label,
                unit_id=unit_id,
            )
            self._stream.emit(
                "phase_timing",
                phase=f"zh_chase:{unit_id}",
                status="started",
                started_at=started_at,
                thread=row_label,
            )
            unit_progress = job_progress.ThreadProgress(self._stream, row_label)
        unit, error = _run_bilingual_unit(
            run_dir=self._run_dir,
            company_name=self._company_name,
            run_id=self._run_id,
            unit_label=label,
            unit_path=unit_path,
            progress=unit_progress,
            timeout_sec=self._timeout_sec,
        )
        duration_ms = int((time.monotonic() - started_monotonic) * 1000)
        finished_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if unit_id in self._abandoned:
                # collect() already closed this row at the join deadline;
                # the late result is unused and must not double-emit.
                return unit, error
            self._terminal_emitted.add(unit_id)
        if self._stream is not None:
            if error is None and isinstance(unit, dict):
                self._stream.emit(
                    "thread_finished",
                    thread=row_label,
                    unit_id=unit_id,
                    duration_ms=duration_ms,
                )
                self._stream.emit(
                    "phase_timing",
                    phase=f"zh_chase:{unit_id}",
                    status="finished",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row_label,
                    cost_usd=unit.get("claude_cost_usd"),
                    claude_duration_ms=unit.get("claude_duration_ms"),
                )
            else:
                self._stream.emit(
                    "thread_failed",
                    thread=row_label,
                    unit_id=unit_id,
                    duration_ms=duration_ms,
                    error=str(error)[:500],
                )
                self._stream.emit(
                    "phase_timing",
                    phase=f"zh_chase:{unit_id}",
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row_label,
                    error=str(error)[:500],
                )
        return unit, error

    def collect(self, join_timeout_sec: float | None = None) -> dict:
        """Join in-flight units under one shared deadline.

        Returns ``{"units": {unit_id: unit}, "missed": [...], "failed":
        [...], "cost_usd": float, "duration_ms": int}``. Missed units (still
        running at the deadline) are left to finish on their own; their
        results are unused and their cost is not captured here.
        """
        if join_timeout_sec is None:
            join_timeout_sec = _memo_zh_chase_join_timeout_sec()
        deadline = time.monotonic() + join_timeout_sec
        units: dict[str, dict] = {}
        missed: list[str] = []
        failed: list[str] = []
        cost = 0.0
        duration = 0
        for unit_id, future in list(self._futures.items()):
            remaining = max(0.0, deadline - time.monotonic())
            error: str | None = None
            unit: dict | None = None
            timed_out = False
            try:
                unit, error = future.result(timeout=remaining)
            except TimeoutError:
                timed_out = True
                error = (
                    f"chase unit {unit_id} not finished before the join "
                    "deadline; result unused"
                )
            except Exception as exc:  # noqa: BLE001
                error = f"chase unit {unit_id} crashed: {exc}"
            if error is None and isinstance(unit, dict):
                # The worker thread already emitted this unit's terminal
                # events at its true completion time.
                units[unit_id] = unit
                cost += _to_float(unit.get("claude_cost_usd"))
                duration += _to_int(unit.get("claude_duration_ms"))
                continue
            (missed if timed_out else failed).append(unit_id)
            if not timed_out:
                # Ran and failed (or crashed): the worker emitted the
                # failure row; a crashed future never reached the worker's
                # emit, but also never marked terminal — fall through only
                # for abandonment below when it never completed.
                continue
            # Abandoned at the join deadline: the worker hasn't emitted a
            # terminal event yet — close the row here, and mark it so the
            # late-finishing worker stays silent.
            with self._lock:
                if unit_id in self._terminal_emitted:
                    continue
                self._abandoned.add(unit_id)
            if self._stream is not None:
                row_label = f"Chinese chase - {unit_id}"
                submitted_at, submitted_monotonic = self._submitted.get(
                    unit_id,
                    (datetime.now(timezone.utc).isoformat(), time.monotonic()),
                )
                self._stream.emit(
                    "thread_failed",
                    thread=row_label,
                    unit_id=unit_id,
                    duration_ms=int(
                        (time.monotonic() - submitted_monotonic) * 1000
                    ),
                    error=str(error)[:500],
                )
                self._stream.emit(
                    "phase_timing",
                    phase=f"zh_chase:{unit_id}",
                    status="failed",
                    started_at=submitted_at,
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    duration_ms=int(
                        (time.monotonic() - submitted_monotonic) * 1000
                    ),
                    thread=row_label,
                    error=str(error)[:500],
                )
        return {
            "units": units,
            "missed": missed,
            "failed": failed,
            "cost_usd": round(cost, 6),
            "duration_ms": duration,
        }

    def merge_into(self, package: dict, units: dict[str, dict]) -> dict:
        """Adopt chased translations into the accepted English package.

        The envelope unit merges at the package root; section units merge
        into the matching ``sections[]`` entry by id (unmatched units are
        dropped). All adoption goes through ``_adopt_zh_translations`` —
        exact-``en``-match, blank-``zh``-only — so stale chases cannot
        corrupt anything. Returns ``{"adopted", "dropped_units",
        "blank_before", "blank_after"}``.
        """
        blank_before = _count_blank_zh(package)
        dropped_units = 0
        sections_by_id = {
            str(section.get("id") or ""): section
            for section in package.get("sections") or []
            if isinstance(section, dict)
        }
        for unit_id, unit in units.items():
            if not isinstance(unit, dict):
                dropped_units += 1
                continue
            if unit_id == "envelope":
                _adopt_zh_translations(package, unit)
                continue
            section = sections_by_id.get(unit_id)
            if isinstance(section, dict):
                _adopt_zh_translations(section, unit)
            else:
                dropped_units += 1
        blank_after = _count_blank_zh(package)
        return {
            "adopted": blank_before - blank_after,
            "dropped_units": dropped_units,
            "blank_before": blank_before,
            "blank_after": blank_after,
        }

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False)


def _has_blank_zh(obj: Any) -> bool:
    """True when any localized {en, zh} leaf has English but a blank zh."""
    if isinstance(obj, dict):
        if "en" in obj and "zh" in obj:
            en = str(obj.get("en") or "").strip()
            zh = str(obj.get("zh") or "").strip()
            if en and not zh:
                return True
        return any(_has_blank_zh(value) for value in obj.values())
    if isinstance(obj, list):
        return any(_has_blank_zh(value) for value in obj)
    return False


def _count_blank_zh(obj: Any) -> int:
    """Count localized {en, zh} leaves whose zh is still blank."""
    if isinstance(obj, dict):
        own = 0
        if "en" in obj and "zh" in obj:
            en = str(obj.get("en") or "").strip()
            zh = str(obj.get("zh") or "").strip()
            if en and not zh:
                own = 1
        return own + sum(_count_blank_zh(value) for value in obj.values())
    if isinstance(obj, list):
        return sum(_count_blank_zh(value) for value in obj)
    return 0


def _memo_bilingual_max_workers() -> int:
    raw = os.environ.get("BSH_MEMO_FAST_MAX_WORKERS")
    try:
        value = int(raw) if raw is not None else 8
    except (TypeError, ValueError):
        value = 8
    return max(1, min(value, 8))


def run_memo_fast_bilingual_package_parallel(
    *,
    run_dir: Path,
    company_name: str,
    run_id: str,
    english_package_path: Path,
    progress=None,
    timeout_sec: int = 1200,
    max_workers: int | None = None,
    stream=None,
    only_missing: bool = True,
) -> tuple[dict | None, str | None]:
    """Per-section fan-out of the bilingual pass (R6d).

    The Chinese pass is a pure translation of phase 3's output — nothing
    requires one 20-minute monolithic call. Split the package into one unit
    per section plus an envelope (everything else: company block, sources,
    top-level strings), translate the units on the shared thread pool, and
    reassemble with a zh-only merge that cannot alter English content.

    ``only_missing`` (default on) skips units whose strings are already
    fully translated — a no-op for a fresh English package (all zh blank),
    and the gap-fill behavior the chasing path relies on. ``stream`` is the
    run's ProgressLog; when provided, each unit gets its own thread row and
    ``zh_section:<unit_id>`` phase timings instead of collapsing into the
    single Phase 4 rail.

    Falls back to the monolithic ``run_memo_fast_bilingual_package`` when
    the package shape is unexpected or any unit fails — worst case this is
    exactly as slow and exactly as correct as before.
    """
    if os.environ.get("BSH_MEMO_BILINGUAL_PARALLEL", "1") != "1":
        return run_memo_fast_bilingual_package(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            english_package_path=english_package_path,
            progress=progress,
            timeout_sec=timeout_sec,
        )

    def _fallback(reason: str) -> tuple[dict | None, str | None]:
        logger.warning(
            "bilingual parallel pass falling back to monolithic: %s", reason
        )
        if progress is not None:
            progress.emit(
                "claude_action",
                action="thinking",
                text=f"Parallel Chinese pass unavailable ({reason}); "
                "running monolithic pass",
            )
        return run_memo_fast_bilingual_package(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            english_package_path=english_package_path,
            progress=progress,
            timeout_sec=timeout_sec,
        )

    try:
        package = json.loads(english_package_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return _fallback(f"could not read English package: {exc}")
    sections = package.get("sections")
    if not isinstance(sections, list) or not sections:
        return _fallback("package has no sections list")

    units_dir = run_dir / "logs" / "bilingual_units"
    units_dir.mkdir(parents=True, exist_ok=True)
    # (unit_id, unit_label, unit_path, source_object)
    units: list[tuple[str, str, Path, Any]] = []
    skipped = 0
    envelope = {k: v for k, v in package.items() if k != "sections"}
    if only_missing and not _has_blank_zh(envelope):
        skipped += 1
    else:
        envelope_path = units_dir / "envelope.en.json"
        envelope_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        units.append(("envelope", "package envelope", envelope_path, envelope))
    for index, section in enumerate(sections):
        section_id = (
            str(section.get("id") or f"section-{index}")
            if isinstance(section, dict)
            else f"section-{index}"
        )
        if only_missing and not _has_blank_zh(section):
            skipped += 1
            continue
        path = units_dir / f"{index:02d}_{section_id}.en.json"
        path.write_text(
            json.dumps(section, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        units.append((section_id, f"section {section_id}", path, section))

    if not units:
        if progress is not None:
            progress.emit(
                "stage",
                stage="memo_zh_units_skipped",
                message=(
                    f"All {skipped} package units are already translated; "
                    "no Chinese fill needed"
                ),
            )
        return (
            {
                "memo_package": package,
                "claude_cost_usd": None,
                "claude_duration_ms": None,
                "claude_usage": None,
            },
            None,
        )

    workers = max_workers or _memo_bilingual_max_workers()
    workers = max(1, min(workers, len(units)))

    if progress is not None:
        progress.emit(
            "stage",
            stage="memo_zh_parallel_dispatch",
            message=(
                f"Translating {len(units)} package units on "
                f"{workers} workers"
            ),
            units=[label for _, label, _, _ in units],
            max_workers=workers,
            skipped_complete=skipped,
        )
    if stream is not None:
        for index, (unit_id, label, _, _) in enumerate(units):
            row_label = f"Chinese - {label}"
            stream.emit(
                "thread_planned",
                thread=row_label,
                title=row_label,
                phase_index=round(4.11 + index / 100, 4),
                parent_thread=_MEMO_PHASE4_THREAD,
                group="memo_zh_unit",
                unit_id=unit_id,
                estimate_ms=300_000,
                description=f"Translate the {label} into Simplified Chinese",
            )

    def _run_unit_with_events(
        unit_id: str, label: str, path: Path
    ) -> tuple[dict | None, str | None]:
        row_label = f"Chinese - {label}"
        started_at = datetime.now(timezone.utc).isoformat()
        started_monotonic = time.monotonic()
        unit_progress = progress
        if stream is not None:
            unit_progress = job_progress.ThreadProgress(stream, row_label)
            stream.emit(
                "thread_started", thread=row_label, title=row_label, unit_id=unit_id
            )
            stream.emit(
                "phase_timing",
                phase=f"zh_section:{unit_id}",
                status="started",
                started_at=started_at,
                thread=row_label,
            )
        unit, error = _run_bilingual_unit(
            run_dir=run_dir,
            company_name=company_name,
            run_id=run_id,
            unit_label=label,
            unit_path=path,
            progress=unit_progress,
            timeout_sec=timeout_sec,
        )
        if stream is not None:
            duration_ms = int((time.monotonic() - started_monotonic) * 1000)
            finished_at = datetime.now(timezone.utc).isoformat()
            if error is None:
                stream.emit(
                    "thread_finished",
                    thread=row_label,
                    unit_id=unit_id,
                    duration_ms=duration_ms,
                )
                stream.emit(
                    "phase_timing",
                    phase=f"zh_section:{unit_id}",
                    status="finished",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row_label,
                    cost_usd=(unit or {}).get("claude_cost_usd"),
                    claude_duration_ms=(unit or {}).get("claude_duration_ms"),
                )
            else:
                stream.emit(
                    "thread_failed",
                    thread=row_label,
                    unit_id=unit_id,
                    duration_ms=duration_ms,
                    error=str(error)[:500],
                )
                stream.emit(
                    "phase_timing",
                    phase=f"zh_section:{unit_id}",
                    status="failed",
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    thread=row_label,
                    error=str(error)[:500],
                )
        return unit, error

    from concurrent.futures import ThreadPoolExecutor

    results: list[tuple[str, dict | None, str | None]] = []
    with ThreadPoolExecutor(
        max_workers=workers, thread_name_prefix="memo-bilingual"
    ) as pool:
        futures = {
            pool.submit(_run_unit_with_events, unit_id, label, path): (label, source)
            for unit_id, label, path, source in units
        }
        for future, (label, source) in futures.items():
            try:
                unit, error = future.result()
            except Exception as exc:  # noqa: BLE001
                unit, error = None, f"{label} crashed: {exc}"
            results.append((label, unit, error))
            if error is None:
                _adopt_zh_translations(source, unit)

    failed = [f"{label}: {error}" for label, _, error in results if error]
    if failed:
        return _fallback("; ".join(failed[:3]))

    cost = sum(
        _to_float(unit.get("claude_cost_usd")) for _, unit, _ in results if unit
    )
    duration = max(
        (_to_int(unit.get("claude_duration_ms")) for _, unit, _ in results if unit),
        default=0,
    )
    return (
        {
            "memo_package": package,
            "claude_cost_usd": round(cost, 6) if cost else None,
            "claude_duration_ms": duration or None,
            "claude_usage": None,
        },
        None,
    )


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def run_investment_memo(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    progress=None,
    timeout_sec: int = 3600,
) -> dict:
    """Spawn `claude -p` to run Serena's memo skill against a prepped run.

    Inputs the skill is allowed to read:
      - ``settings_path``  (Serena_Background.md)
      - ``companies_yaml_path`` (the registry; entry matching ``company_slug``)

    The skill writes its own analysis artifacts and ``logs/memo_package.json``
    into ``run_dir``. Python does not pre-extract anything and does not stage
    Document Library files; ``server.memo_analysis`` renders DOCX files after
    Claude exits.

    Returns ``{ok, cost_usd, duration_ms, error?}``.
    """
    if not is_available():
        return {
            "ok": False,
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            ),
        }
    if not run_dir.exists():
        return {"ok": False, "error": f"Run folder missing: {run_dir}"}
    if not settings_path.exists():
        return {"ok": False, "error": f"Settings file missing: {settings_path}"}
    if not companies_yaml_path.exists():
        return {"ok": False, "error": f"companies.yaml missing: {companies_yaml_path}"}

    prompt = _build_investment_memo_prompt(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        settings_path=settings_path,
        companies_yaml_path=companies_yaml_path,
        memo_paths=memo_paths,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
        company_registry_entry_yaml=_extract_company_registry_entry_yaml(
            companies_yaml_path,
            company_slug,
        ),
    )

    # The skill needs Read access to two paths outside the run folder:
    # the settings file and the company registry. We add-dir both. We
    # deliberately do NOT add-dir `data/uploads/` — that's the Document
    # Library and is not a memo input (see docs/architecture.md).
    add_dirs = [
        str(run_dir),
        str(settings_path.parent),
        str(companies_yaml_path.parent),
    ]
    if research_dir and research_dir.exists():
        add_dirs.append(str(research_dir))
    if analysis_session_path and analysis_session_path.exists():
        add_dirs.append(str(analysis_session_path))
    if lessons_path and lessons_path.exists():
        add_dirs.append(str(lessons_path.parent))
    cmd = [
        claude_path() or "claude",
        "-p",
        prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash,Grep,Glob",
        "--disallowedTools",
        "ToolSearch,Task,TaskCreate,TaskUpdate,TaskList,TaskOutput,TaskStop,TodoWrite",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    for d in add_dirs:
        cmd += ["--add-dir", d]

    if progress:
        progress.emit(
            "stage",
            stage="analysis_starting",
            message="Running investment-memo skill (analysis + translation)",
            run_dir=str(run_dir),
        )
        emit_memo_phase_planned(progress)

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    # Seed thread_map so _process_event tags Write/Edit events that
    # target the skill's analysis files with `thread=<pass label>`. That
    # lets the AI-Task modal group the 8 parallel passes into their own
    # collapsible sections.
    state: dict[str, Any] = {
        "thread_map": _MEMO_ANALYSIS_PASSES,
        "phase_thread": _MEMO_PHASE1_THREAD,
        "memo_phase_tracking": True,
    }

    def _handle_event(event: dict, prog, run_state: dict) -> None:
        if prog:
            _process_event(event, prog, run_state)

    _, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_handle_event,
        timeout_sec=timeout_sec,
        timeout_label="memo skill",
        # The analysis passes Read/Write constantly; extended silence means
        # a wedged CLI, and the wall-clock cap still bounds the whole run.
        silence_timeout_sec=300.0,
        stop_on_result=True,
    )
    result_event = state.get("result_event")
    if stream_error and result_event is None:
        return {"ok": False, "error": stream_error}

    # Close out any pass threads that we opened during the run. The
    # subprocess having reached `result` is the only completion signal we
    # have for the individual passes — the skill doesn't emit per-pass
    # markers — so we attribute success/failure to the overall return.
    if progress:
        finish_ok = bool(result_event) and not (
            result_event.get("subtype") == "error" or result_event.get("is_error")
        )
        final_error = None
        if result_event and not finish_ok:
            final_error = (
                result_event.get("error")
                or result_event.get("result")
                or "Claude skill run failed"
            )
        if state.get("phase_thread") and not state.get("phase_thread_closed"):
            _close_phase_thread(progress, state, failed=not finish_ok)
        finished_threads = state.get("threads_finished") or set()
        successful_artifacts = state.get("successful_artifact_threads") or set()
        for thread_label in state.get("threads_started") or ():
            if thread_label in finished_threads:
                continue
            if not finish_ok and thread_label in successful_artifacts:
                progress.emit("thread_finished", thread=thread_label)
                continue
            if not finish_ok:
                progress.emit(
                    "thread_failed",
                    thread=thread_label,
                    error=final_error,
                )
                continue
            progress.emit(
                "thread_finished",
                thread=thread_label,
            )

    if result_event and (
        result_event.get("subtype") == "error" or result_event.get("is_error")
    ):
        return {
            "ok": False,
            "error": (
                result_event.get("error")
                or result_event.get("result")
                or "Claude skill run failed"
            ),
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
            "usage": result_event.get("usage"),
            "subtype": result_event.get("subtype"),
            "api_error_status": result_event.get("api_error_status"),
        }

    if result_event is None and proc.returncode and proc.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return {
            "ok": False,
            "error": (
                f"claude exited {proc.returncode}"
                + (f": {tail[:600]}" if tail else "")
            ),
        }

    out: dict = {"ok": True}
    if result_event:
        out["cost_usd"] = result_event.get("total_cost_usd")
        out["duration_ms"] = result_event.get("duration_ms")
        out["usage"] = result_event.get("usage")
        out["subtype"] = result_event.get("subtype")
    return out


def _build_buffett_investment_memo_prompt(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    company_registry_entry_yaml: str | None = None,
) -> str:
    """Build the prompt for one Claude subprocess running the Buffett skill."""
    skill_text = _load_buffett_skill_text()
    memo_package_path = run_dir / "logs" / "memo_package.json"
    scope_warning_block = ""
    if scope_check and scope_check.get("outcome") == "warn":
        warning_lines = "\n".join(f"- {w}" for w in (warnings or []))
        scope_warning_block = f"""\
## Stage note from prep

Prep recorded a non-fatal stage warning:

- classification: `{scope_check.get("classification")}`
- reason: {scope_check.get("reason") or "(no reason recorded)"}

{warning_lines if warning_lines else "- No additional warnings recorded."}

Proceed. Do not decline solely because the company is early-stage. If the
economics cannot be understood, the honest call is Too Hard.

"""

    if research_dir and research_dir.exists():
        research_block = f"""\
Research materials for this company, if any, live at:

  `{research_dir}`

Read the raw files that are relevant. Do not dump the file inventory into
the memo. Continue to ignore `data/uploads/` — that is the Document Library
and is not an input.

"""
    else:
        research_block = """\
No research-folder files are staged for this run. Use the company registry
entry and independent reasoning. Do not invent undisclosed figures.

"""

    registry_block = ""
    if company_registry_entry_yaml:
        registry_block = f"""\
## Company registry entry (`{company_slug}`)

```yaml
{company_registry_entry_yaml}
```

"""

    return f"""\
You are writing an investment analysis and memorandum as Warren Buffett.

Company: {company_name} (`{company_slug}`)
Run id: {run_id}
Run folder: `{run_dir}`
Package output (required): `{memo_package_path}`
Predicted Word paths (Python will render these; do not write .docx yourself):
  - English: `{memo_paths.get("en")}`
  - Chinese: `{memo_paths.get("zh")}`
Companies registry file: `{companies_yaml_path}`

{scope_warning_block}{research_block}{registry_block}
Do not adopt BSH LP sell-side voice, Serena's persona, or any fund mandate
as your own. The author is Warren Buffett. The deliverable is an investment
memo with a Buy / Pass / Too Hard call.

Do not write `.docx` files or renderer scripts. Write `logs/memo_package.json`
and the Markdown working copies the skill specifies.

=================================================================
SKILL: bsh-buffett-investment-memo-v1 (verbatim — follow this)
=================================================================

{skill_text}
"""


def run_buffett_investment_memo(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    progress=None,
    timeout_sec: int = 3600,
) -> dict:
    """Spawn `claude -p` to run the Buffett investment-memo skill."""
    if not is_available():
        return {
            "ok": False,
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            ),
        }
    if not run_dir.exists():
        return {"ok": False, "error": f"Run folder missing: {run_dir}"}
    if not companies_yaml_path.exists():
        return {"ok": False, "error": f"companies.yaml missing: {companies_yaml_path}"}

    prompt = _build_buffett_investment_memo_prompt(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        companies_yaml_path=companies_yaml_path,
        memo_paths=memo_paths,
        research_dir=research_dir,
        scope_check=scope_check,
        warnings=warnings,
        company_registry_entry_yaml=_extract_company_registry_entry_yaml(
            companies_yaml_path,
            company_slug,
        ),
    )

    add_dirs = [str(run_dir), str(companies_yaml_path.parent)]
    if research_dir and research_dir.exists():
        add_dirs.append(str(research_dir))
    cmd = [
        claude_path() or "claude",
        "-p",
        prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash,Grep,Glob",
        "--disallowedTools",
        "ToolSearch,Task,TaskCreate,TaskUpdate,TaskList,TaskOutput,TaskStop,TodoWrite",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    for d in add_dirs:
        cmd += ["--add-dir", d]

    if progress:
        progress.emit(
            "stage",
            stage="analysis_starting",
            message="Running Buffett investment-memo skill",
            run_dir=str(run_dir),
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {
        "thread_map": _BUFFETT_ANALYSIS_PASSES,
    }

    def _handle_event(event: dict, prog, run_state: dict) -> None:
        if prog:
            _process_event(event, prog, run_state)

    _, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_handle_event,
        timeout_sec=timeout_sec,
        timeout_label="Buffett memo skill",
        silence_timeout_sec=300.0,
        stop_on_result=True,
    )
    result_event = state.get("result_event")
    if stream_error and result_event is None:
        return {"ok": False, "error": stream_error}

    if progress:
        finish_ok = bool(result_event) and not (
            result_event.get("subtype") == "error" or result_event.get("is_error")
        )
        final_error = None
        if result_event and not finish_ok:
            final_error = (
                result_event.get("error")
                or result_event.get("result")
                or "Claude skill run failed"
            )
        finished_threads = state.get("threads_finished") or set()
        for thread_label in state.get("threads_started") or ():
            if thread_label in finished_threads:
                continue
            if not finish_ok:
                progress.emit(
                    "thread_failed",
                    thread=thread_label,
                    error=final_error,
                )
                continue
            progress.emit("thread_finished", thread=thread_label)

    if result_event and (
        result_event.get("subtype") == "error" or result_event.get("is_error")
    ):
        return {
            "ok": False,
            "error": (
                result_event.get("error")
                or result_event.get("result")
                or "Claude skill run failed"
            ),
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
            "usage": result_event.get("usage"),
            "subtype": result_event.get("subtype"),
            "api_error_status": result_event.get("api_error_status"),
        }

    if result_event is None and proc.returncode and proc.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return {
            "ok": False,
            "error": (
                f"claude exited {proc.returncode}"
                + (f": {tail[:600]}" if tail else "")
            ),
        }

    out: dict = {"ok": True}
    if result_event:
        out["cost_usd"] = result_event.get("total_cost_usd")
        out["duration_ms"] = result_event.get("duration_ms")
        out["usage"] = result_event.get("usage")
        out["subtype"] = result_event.get("subtype")
    return out


def _build_resume_memo_package_prompt(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    company_registry_entry_yaml: str | None = None,
    quality_lint_path: Path | None = None,
    prior_package_path: Path | None = None,
    validation_feedback: str | None = None,
) -> str:
    """Build the narrow resume prompt that only authors memo_package.json."""
    package_path = run_dir / "logs" / "memo_package.json"
    analysis_dir = run_dir / "analysis"
    analysis_files = sorted(
        p.name for p in analysis_dir.glob("*.md")
    ) if analysis_dir.exists() else []
    analysis_list = "\n".join(f"- `analysis/{name}`" for name in analysis_files)
    if not analysis_list:
        analysis_list = "- (no analysis artifacts found; stop and report this)"
    research_files: list[Path] = []
    if research_dir and research_dir.exists():
        research_files = sorted(
            p for p in research_dir.iterdir()
            if p.is_file() and p.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json"}
        )
    analysis_session_files: list[Path] = []
    if analysis_session_path and analysis_session_path.exists():
        analysis_session_files = sorted(
            p for p in analysis_session_path.rglob("*")
            if p.is_file() and p.suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json"}
        )
    allowed_read_paths: list[Path] = [
        run_dir / "logs" / "run_manifest.md",
        settings_path,
        *[analysis_dir / name for name in analysis_files],
        *research_files,
        *analysis_session_files,
    ]
    if lessons_path and lessons_path.exists():
        allowed_read_paths.append(lessons_path)
    if quality_lint_path and quality_lint_path.exists():
        allowed_read_paths.append(quality_lint_path)
    if prior_package_path and prior_package_path.exists():
        allowed_read_paths.append(prior_package_path)
    allowed_read_list = "\n".join(f"- `{path}`" for path in allowed_read_paths)
    research_line = (
        f"- Company research folder: `{research_dir}`"
        if research_dir and research_dir.exists()
        else "- Company research folder: not populated"
    )
    analysis_session_line = (
        f"- Serena memo analysis session: `{analysis_session_path}`"
        if analysis_session_path and analysis_session_path.exists()
        else "- Serena memo analysis session: not provided"
    )
    lessons_line = (
        f"- Prior memo lessons: `{lessons_path}`"
        if lessons_path and lessons_path.exists()
        else "- Prior memo lessons: not provided"
    )
    quality_lint_line = (
        f"- Prior DOCX quality report: `{quality_lint_path}`"
        if quality_lint_path and quality_lint_path.exists()
        else "- Prior DOCX quality report: not provided"
    )
    prior_package_line = (
        f"- Prior memo package draft to repair: `{prior_package_path}`"
        if prior_package_path and prior_package_path.exists()
        else "- Prior memo package draft to repair: not provided"
    )
    warning_lines = "\n".join(f"- {w}" for w in (warnings or []))
    scope_block = ""
    if scope_check:
        scope_block = f"""\
## Scope context

- classification: `{scope_check.get('classification')}`
- outcome: `{scope_check.get('outcome')}`
- reason: {scope_check.get('reason') or '(no reason recorded)'}
{warning_lines if warning_lines else "- No additional warnings recorded."}

"""
    registry_block = ""
    if company_registry_entry_yaml:
        registry_block = f"""\
## Resolved company registry entry

Use this embedded YAML as the registry source for `{company_slug}`:

```yaml
{company_registry_entry_yaml}
```

"""

    quality_lint_block = ""
    if quality_lint_path and quality_lint_path.exists():
        quality_lint_block = f"""\
## Quality-gate remediation context

The previous rendered memo failed the DOCX quality gate. Read
`{quality_lint_path}` before writing the package, fix every P0 finding, and
avoid repeating the cited wording or tone. This is still only a memo-package
writing pass: do not rerun analysis, do not overwrite files in `analysis/`,
and do not write DOCX files.

"""
    prior_package_block = ""
    analysis_instruction = f"""\
Read the files below before writing the package:

{analysis_list}
"""
    if prior_package_path and prior_package_path.exists():
        prior_package_block = f"""\
## Prior package draft

Use `{prior_package_path}` as prior output evidence and structure context, not
as authoritative prose. Preserve only the package structure and source
treatment that still satisfies the current voice contract, then rewrite every
quality-gate issue and any adjacent stale wording that carries the same
problem. Read analysis artifacts whenever a changed claim needs support or
clarification; do not lock in prior phrasing just because it rendered once.

"""
        analysis_instruction = f"""\
The prior package is context for this repair pass. Read the analysis files
below as needed to verify or support changed claims:

{analysis_list}
"""

    validation_feedback_block = ""
    if validation_feedback:
        validation_feedback_block = f"""\
## Previous attempt failed pre-render validation

The package written by the previous attempt was rejected before rendering —
by the renderer's structural validation and/or the memo quality gates. Fix
EVERY error below while keeping the analytical content. Structural errors
name the exact JSON path that must change; quality-gate errors quote the
offending text — rewrite that text (and any nearby wording with the same
problem), do not just delete it:

{validation_feedback}

"""

    return f"""\
You are resuming a previously interrupted BSH late-stage investment memo run.
The analytical work already landed in the run folder. Your job in this resume
pass is narrow: read the existing artifacts and write the missing structured
memo package. Do not rerun the analysis passes and do not overwrite files in
`analysis/`.

This resume pass is not allowed to rediscover the project.
Use the existing run artifacts first. Avoid Bash, Grep, Glob, or Edit unless
you need a narrow local validation step, such as checking file existence or
valid JSON. Do not inspect `server/`, other memo runs, generated
previews, renderer code, or example packages. The JSON schema below is
authoritative; do not look for another schema or example.

## Run context

- Run folder / CWD: `{run_dir}`
- Company: {company_name} (`{company_slug}`)
- Run ID: {run_id}
- Output package to write: `{package_path}`
- Expected English DOCX rendered later by server: `{memo_paths.get('en')}`
- Expected Chinese DOCX rendered later by server: `{memo_paths.get('zh')}`
- Settings: `{settings_path}`
- Companies registry: `{companies_yaml_path}`
{research_line}
{analysis_session_line}
{lessons_line}
{quality_lint_line}
{prior_package_line}

{scope_block}{registry_block}{quality_lint_block}{prior_package_block}\
{validation_feedback_block}\
## Existing analysis artifacts to use

{analysis_instruction}

You may read only these exact supporting files:

{allowed_read_list}

If a claim is not supported by these analysis artifacts, the company registry,
settings, the memo analysis session, prior lessons, or the populated research
folder, do not present it as fact. Convert uncertainty into source class,
model treatment, scenario range, risk factor, valuation sensitivity, or
deal-mechanics disclosure.

## Fixed renderer contract

Write only `{package_path}`. Do not write DOCX files. Do not write or edit a
per-run renderer script such as `build_memo.py`, `build_memos.py`,
`generate_memo.py`, or `render_memo.py`. The server will call
`server.memo_docx_renderer` after you exit.

The package must be JSON with this shape:

```json
{{
  "schema_version": 1,
  "company": {{
    "name": "Company, Inc.",
    "descriptor": {{"en": "Category", "zh": "类别"}},
    "stage": "Late-stage / pre-IPO",
    "sector": "AI",
    "location": "City, Region",
    "round": "Round / valuation context"
  }},
  "run": {{"run_id": "{run_id}", "as_of": "YYYY-MM-DD"}},
  "sections": [
    {{
      "id": "executive_summary",
      "blocks": [
        {{"type": "heading", "level": 2, "text": {{"en": "Investment Opportunity", "zh": "投资机会"}}}},
        {{"type": "paragraph", "text": {{"en": "Body prose.", "zh": "正文。"}}}},
        {{"type": "bullets", "items": [{{"en": "Bullet.", "zh": "要点。"}}]}},
        {{"type": "callout", "tone": "warning", "title": {{"en": "Valuation Sensitivity", "zh": "估值敏感因素"}}, "items": []}},
        {{"type": "table", "component": "key_metrics_snapshot", "title": {{"en": "Key Metrics Snapshot", "zh": "关键指标快照"}}, "headers": [], "rows": []}}
      ]
    }}
  ],
  "sources": [
    {{
      "id": "S1",
      "title": "Source title",
      "class": {{"en": "Company material", "zh": "公司材料"}},
      "treatment": {{"en": "How used", "zh": "使用方式"}},
      "as_of": "YYYY-MM-DD"
    }}
  ]
}}
```

The final package must include at least these core section ids with non-empty,
substantive blocks: `executive_summary`, `company_overview`,
`investment_highlights`, `investment_risk`, and
`financial_forecast_valuation`. Include a non-empty `sources` list.

{MEMO_PACKAGE_SOURCES_CONTRACT}

Use `paragraph`, `heading`, `bullets`, `callout`, and `table` blocks where
useful. All final user-facing strings in blocks, tables, callouts, bullets,
and source treatment must be bilingual (`{{"en": "...", "zh": "..."}}`). The
ONLY values that may stay plain strings are fully language-neutral ones:
dates ("2026-05"), figures ("~$2.55B", "+180%"), source ids, tickers, and
proper-noun names ("Koch Disruptive Technologies"). The renderer rejects any
plain string containing ordinary lowercase English words — "120+ filed / 90+
issued" or "$10M/site (LOI expected)" MUST be a bilingual object. When in
doubt, use a bilingual object; identical en/zh is always valid.

Do not author a heading block that restates a numbered top-level section title;
the renderer emits the roman-numbered section titles automatically. Subheadings
inside sections must be plain labels.

The renderer fails closed on shallow content. Required core sections cannot be
only headings, title-only callouts, title-only tables, or generic filler.
`executive_summary` needs at least two substantive content blocks.
`investment_highlights` and `investment_risk` each need at least two
substantive bullets or equivalent explanatory prose/table/callout.
`financial_forecast_valuation` must explicitly address model treatment,
scenario ranges, valuation, revenue, margins, or valuation sensitivities.

{MEMO_CONTENT_PARITY_CONTRACT}

{MEMO_RISK_REGISTER_CONTRACT}

The Chinese memo must be native professional investment Chinese with analytical
parity to English. Do not translate prompt scaffolding into visible prose.
After reading the quality report and prior draft, write `{package_path}` as
soon as the corrections are clear. Do not spend the response drafting prose in
chat instead of writing the JSON package.

{HUMAN_EXEC_MEMO_VOICE_CONTRACT}
"""


def run_resume_memo_package(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    quality_lint_path: Path | None = None,
    prior_package_path: Path | None = None,
    validation_feedback: str | None = None,
    progress=None,
    timeout_sec: int = 1800,
) -> dict:
    """Resume a failed memo run by writing only logs/memo_package.json."""
    if not is_available():
        return {
            "ok": False,
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            ),
        }
    if not run_dir.exists():
        return {"ok": False, "error": f"Run folder missing: {run_dir}"}
    if not settings_path.exists():
        return {"ok": False, "error": f"Settings file missing: {settings_path}"}
    if not companies_yaml_path.exists():
        return {"ok": False, "error": f"companies.yaml missing: {companies_yaml_path}"}

    prompt = _build_resume_memo_package_prompt(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        settings_path=settings_path,
        companies_yaml_path=companies_yaml_path,
        memo_paths=memo_paths,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
        company_registry_entry_yaml=_extract_company_registry_entry_yaml(
            companies_yaml_path,
            company_slug,
        ),
        quality_lint_path=quality_lint_path,
        prior_package_path=prior_package_path,
        validation_feedback=validation_feedback,
    )
    add_dirs = [
        str(run_dir),
        str(settings_path.parent),
        str(companies_yaml_path.parent),
    ]
    if research_dir and research_dir.exists():
        add_dirs.append(str(research_dir))
    if analysis_session_path and analysis_session_path.exists():
        add_dirs.append(str(analysis_session_path))
    if lessons_path and lessons_path.exists():
        add_dirs.append(str(lessons_path.parent))
    if prior_package_path and prior_package_path.exists():
        add_dirs.append(str(prior_package_path.parent))

    cmd = [
        claude_path() or "claude",
        "-p",
        prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash,Grep,Glob",
        "--disallowedTools",
        "ToolSearch,Task,TaskCreate,TaskUpdate,TaskList,TaskOutput,TaskStop,TodoWrite",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    for d in add_dirs:
        cmd += ["--add-dir", d]

    if progress:
        progress.emit(
            "stage",
            stage="resume_package_starting",
            message="Resuming memo from existing analysis artifacts",
            memo_package=str(run_dir / "logs" / "memo_package.json"),
        )
        emit_memo_phase_planned(progress, start_phase=4)

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {
        "thread_map": {},
        "phase_thread": _MEMO_PHASE4_THREAD,
        "memo_phase_tracking": True,
        "resume_packaging": True,
    }
    _, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_event,
        timeout_sec=timeout_sec,
        timeout_label="memo package resume",
        silence_timeout_sec=MEMO_PACKAGE_SILENCE_TIMEOUT_SEC,
    )
    result_event: dict | None = state.get("result_event")
    if stream_error:
        return {"ok": False, "error": stream_error}

    if progress:
        finish_ok = bool(result_event) and not (
            result_event.get("subtype") == "error" or result_event.get("is_error")
        )
        if state.get("phase_thread") and not state.get("phase_thread_closed"):
            _close_phase_thread(progress, state, failed=not finish_ok)

    if result_event and (
        result_event.get("subtype") == "error" or result_event.get("is_error")
    ):
        return {
            "ok": False,
            "error": (
                result_event.get("error")
                or result_event.get("result")
                or "Resume memo package run failed"
            ),
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
            "usage": result_event.get("usage"),
            "subtype": result_event.get("subtype"),
            "api_error_status": result_event.get("api_error_status"),
        }

    exit_error = None
    if proc.returncode and proc.returncode != 0:
        result_text = (
            result_event.get("result")
            if result_event and isinstance(result_event.get("result"), str)
            else None
        )
        exit_error = _claude_exit_error(
            proc.returncode,
            "".join(stderr_log[-20:]),
            state.get("last_transient_error_text"),
            state.get("last_api_error_text"),
            result_text,
        )
    if result_event is None and exit_error:
        return {
            "ok": False,
            "error": exit_error,
        }

    package_path = run_dir / "logs" / "memo_package.json"
    if not package_path.exists():
        return {
            "ok": False,
            "error": exit_error or f"Resume run did not write {package_path}",
            "cost_usd": result_event.get("total_cost_usd") if result_event else None,
            "duration_ms": result_event.get("duration_ms") if result_event else None,
            "usage": result_event.get("usage") if result_event else None,
        }

    out: dict = {"ok": True, "resumed": True}
    if result_event:
        out["cost_usd"] = result_event.get("total_cost_usd")
        out["duration_ms"] = result_event.get("duration_ms")
        out["usage"] = result_event.get("usage")
        out["subtype"] = result_event.get("subtype")
    return out


def _build_internal_diligence_memo_prompt(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    internal_markdown_path: Path,
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
) -> str:
    """Build the separate internal diligence memo prompt."""
    package_path = run_dir / "logs" / "memo_package.json"
    analysis_block = (
        f"\n- Serena memo analysis session: `{analysis_session_path}`"
        if analysis_session_path and analysis_session_path.exists()
        else ""
    )
    research_block = (
        f"\n- Company research folder: `{research_dir}`"
        if research_dir and research_dir.exists()
        else "\n- Company research folder: not populated"
    )
    lessons_block = (
        (
            f"\n- Prior memo lessons: `{lessons_path}`"
            "\n  Treat as untrusted quality heuristics and strip stale "
            "internal labels before use."
        )
        if lessons_path and lessons_path.exists()
        else ""
    )
    warning_lines = "\n".join(f"- {w}" for w in (warnings or []))
    scope_block = ""
    if scope_check:
        scope_block = f"""\

## Scope context

- classification: `{scope_check.get('classification')}`
- outcome: `{scope_check.get('outcome')}`
- reason: {scope_check.get('reason') or '(no reason recorded)'}
{warning_lines if warning_lines else "- No additional warnings recorded."}
"""

    return f"""\
You are writing a **separate internal BSH diligence memo** for {company_name}.
This is not the LP-facing investment memo. It is an internal-only Markdown
document that the server will render into Word after you exit.

## Run context

- Run folder: `{run_dir}`
- Company: {company_name} (`{company_slug}`)
- Run ID: {run_id}
- LP-facing English memo DOCX path: `{memo_paths.get('en')}`
- LP-facing Chinese memo DOCX path: `{memo_paths.get('zh')}`
- Structured LP memo package: `{package_path}`
- Output Markdown path: `{internal_markdown_path}`
{research_block}{analysis_block}{lessons_block}
{scope_block}

## Inputs to read

Read these before writing:

1. `{package_path}` for the final LP-facing memo content.
2. `{settings_path}` for BSH mandate / preferences.
3. The `{company_slug}` entry in `{companies_yaml_path}`.
4. The run folder's `analysis/` artifacts.
5. The Serena memo analysis session folder if listed above.
6. The company research folder if populated.

Do not edit `logs/memo_package.json` or either LP-facing memo DOCX. Do not
write a DOCX or a renderer script. Write only the Markdown file at the exact
output path.

## Internal memo audience and register

This memo is BSH-internal only. It may discuss internal participation sizing,
suggested allocation, conviction, risk controls, sensitivity to round scarcity,
SPV/SAFE economics, carry/fees, information asymmetry, and diligence priorities.
Use plain investment-team language. Avoid "ticket"; use "suggested allocation",
"participation", or "commitment". Avoid legal-rights checklist phrasing unless
the actual control or information constraint directly changes economics.

## Required Markdown structure

Write a complete Markdown memo with this exact top-level structure:

# Internal Diligence Memo — {company_name}

## Internal Recommendation
- Recommendation: Proceed / Hold / Pass.
- Suggested allocation: state a range or "not yet sized" and explain why.
- Conviction: High / Medium / Low.
- One-paragraph rationale.

## Allocation Rationale
Explain the suggested allocation using stage, valuation, scarcity,
oversubscription, sponsor access, company quality, expected upside, and
unresolved proof points. Do not default to a small allocation just because ARR,
margin, or lead-investor details are undisclosed if those gaps are normal for
the stage.

## Internal Diligence Priorities
List the 5-8 highest-value diligence items that would change allocation,
timing, or pass/revisit posture.

## Structure, Fees, And Economics
Explain SPV/SAFE mechanics, carry, fees, conversion assumptions, dilution,
valuation entry, and any document-confirmation items in economic terms.

## Risk Controls And Downside Sensitivities
Give the internal risk controls, monitoring items, and downside sensitivities.

## LP-Facing Memo Delta
List what is intentionally internal and must not appear in the LP-facing
sell-side memo.

## Source Notes
Use source-class language and short file/source names. Do not include bracketed
source-token scaffolding like `[S1]` unless referring to the final package's
source index.

## Output requirements

- Write only `{internal_markdown_path}`.
- Markdown only. No front matter. No code fences around the memo.
- Keep it concise but substantive: roughly 1,200-2,500 words.
- Include at least one Markdown table where useful.
- End with a one-line "Internal use only" footer.
"""


def run_internal_diligence_memo(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
    internal_markdown_path: Path,
    research_dir: Path | None = None,
    analysis_session_path: Path | None = None,
    lessons_path: Path | None = None,
    scope_check: dict | None = None,
    warnings: list[str] | None = None,
    progress=None,
    timeout_sec: int = 1200,
) -> dict:
    """Spawn Claude to write the separate internal diligence memo Markdown."""
    if not is_available():
        return {
            "ok": False,
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            ),
        }
    if not run_dir.exists():
        return {"ok": False, "error": f"Run folder missing: {run_dir}"}
    if not settings_path.exists():
        return {"ok": False, "error": f"Settings file missing: {settings_path}"}
    if not companies_yaml_path.exists():
        return {"ok": False, "error": f"companies.yaml missing: {companies_yaml_path}"}

    prompt = _build_internal_diligence_memo_prompt(
        run_dir=run_dir,
        company_name=company_name,
        company_slug=company_slug,
        run_id=run_id,
        settings_path=settings_path,
        companies_yaml_path=companies_yaml_path,
        memo_paths=memo_paths,
        internal_markdown_path=internal_markdown_path,
        research_dir=research_dir,
        analysis_session_path=analysis_session_path,
        lessons_path=lessons_path,
        scope_check=scope_check,
        warnings=warnings,
    )
    add_dirs = [
        str(run_dir),
        str(settings_path.parent),
        str(companies_yaml_path.parent),
    ]
    if research_dir and research_dir.exists():
        add_dirs.append(str(research_dir))
    if analysis_session_path and analysis_session_path.exists():
        add_dirs.append(str(analysis_session_path))
    if lessons_path and lessons_path.exists():
        add_dirs.append(str(lessons_path.parent))

    cmd = [
        claude_path() or "claude",
        "-p",
        prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash,Grep,Glob",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    for d in add_dirs:
        cmd += ["--add-dir", d]

    if progress:
        progress.emit(
            "stage",
            stage="internal_diligence_memo_starting",
            message="Writing internal diligence memo",
            output=str(internal_markdown_path),
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    result_event: dict | None = None
    state: dict[str, Any] = {}
    try:
        for line in proc.stdout or []:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                if progress:
                    _process_event(event, progress, state)
            except Exception:
                logger.exception("progress event handling failed")
            if event.get("type") == "result":
                result_event = event
                break
        if result_event is not None:
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "internal memo claude subprocess kept running after result; "
                    "terminating process group"
                )
                _terminate_process_group(proc, grace_s=2.0)
        else:
            proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc, grace_s=2.0)
        return {"ok": False, "error": f"Claude timed out after {timeout_sec}s"}

    if result_event and (
        result_event.get("subtype") == "error" or result_event.get("is_error")
    ):
        return {
            "ok": False,
            "error": (
                result_event.get("error")
                or result_event.get("result")
                or "Internal memo run failed"
            ),
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
            "usage": result_event.get("usage"),
            "subtype": result_event.get("subtype"),
            "api_error_status": result_event.get("api_error_status"),
        }
    if result_event is None and proc.returncode and proc.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return {
            "ok": False,
            "error": (
                f"claude exited {proc.returncode}"
                + (f": {tail[:600]}" if tail else "")
            ),
        }

    if not internal_markdown_path.exists():
        return {
            "ok": False,
            "error": f"Internal memo markdown was not written: {internal_markdown_path}",
        }
    out: dict = {"ok": True}
    if result_event:
        out["cost_usd"] = result_event.get("total_cost_usd")
        out["duration_ms"] = result_event.get("duration_ms")
        out["usage"] = result_event.get("usage")
        out["subtype"] = result_event.get("subtype")
    return out


def _build_hormuz_appendix_prompt(
    *,
    run_dir: Path,
    target_date: str,
    previous_date: str | None,
    date_range: str,
    source_paths: list[str],
    previous_source_paths: list[str],
    output_basename_cn: str,
    output_basename_en: str,
) -> str:
    """Operational header + the Hormuz skill verbatim (mirrors the memo
    prompt builder). The header maps the skill's abstract I/O contract to
    this run's concrete absolute paths."""
    skill_text = _load_hormuz_skill_text()

    def _bullets(paths: list[str]) -> str:
        return "\n".join(f"  - `{p}`" for p in paths) or "  - (none)"

    prev_block = (
        f"- **PREVIOUS_REPORTS** (date `{previous_date}`, baseline only):\n"
        f"{_bullets(previous_source_paths)}"
        if previous_date
        else "- **PREVIOUS_REPORTS:** none — no prior-day baseline exists. "
        "Treat all probabilities as new and state that explicitly; write "
        "前值概率 as `N/A（无前日基线）`."
    )

    return f"""\
You are running the **bsh-hormuz-appendix-v3** skill for one real run.
The skill text is included below as the source standard. The run-specific I/O
contract in this header takes precedence where it is more concrete.

## Run-specific operational context

- **Run folder (your CWD):** `{run_dir}` — write all four output files
  directly here (no subfolders).
- **TARGET_DATE:** {target_date}
- **DATE_RANGE:** {date_range}
- **OUTPUT_BASENAME_CN:** {output_basename_cn}
- **OUTPUT_BASENAME_EN:** {output_basename_en}
- **USER_FOCUS:** (none specified)

## Inputs

- **SOURCE_REPORTS** (date `{target_date}`, the current day):
{_bullets(source_paths)}
{prev_block}

Read the source files with the `markitdown` Bash tool if available,
otherwise `pandoc`, otherwise the Read tool. Do not invent sources.

## Output contract — exactly four files in the run folder

  - `{run_dir}/{output_basename_cn}.md`
  - `{run_dir}/{output_basename_cn}.pdf`
  - `{run_dir}/{output_basename_en}.md`
  - `{run_dir}/{output_basename_en}.pdf`

Phase 1 produces the Chinese Markdown then its PDF; Phase 2 translates
the Chinese Markdown to English Markdown then renders its PDF. Use the
PDF recipe in the skill (pandoc → HTML → headless Google Chrome) and run
the render-check. Do not paste the appendix body into chat.

=================================================================
SKILL: bsh-hormuz-appendix-v3 (verbatim — follow this)
=================================================================

{skill_text}
"""


def run_hormuz_appendix(
    *,
    run_dir: Path,
    target_date: str,
    previous_date: str | None,
    date_range: str,
    source_paths: list[str],
    previous_source_paths: list[str],
    sources_root: str,
    output_basename_cn: str,
    output_basename_en: str,
    progress=None,
    timeout_sec: int = 3600,
) -> dict:
    """Spawn one `claude -p` running the Hormuz appendix skill verbatim.

    Returns ``{ok, cost_usd, duration_ms, error?}``. Mirrors
    ``run_investment_memo``.
    """
    if not is_available():
        return {
            "ok": False,
            "error": (
                "Claude Code (`claude`) not found on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and run "
                "`claude` once to authenticate."
            ),
        }
    if not run_dir.exists():
        return {"ok": False, "error": f"Run folder missing: {run_dir}"}
    if not source_paths:
        return {"ok": False, "error": "No source reports for the target date"}

    prompt = _build_hormuz_appendix_prompt(
        run_dir=run_dir,
        target_date=target_date,
        previous_date=previous_date,
        date_range=date_range,
        source_paths=source_paths,
        previous_source_paths=previous_source_paths,
        output_basename_cn=output_basename_cn,
        output_basename_en=output_basename_en,
    )

    # The skill reads source PDFs under the sources tree and writes the
    # appendix into the run folder. add-dir both.
    add_dirs = [str(run_dir), sources_root]
    cmd = [
        claude_path() or "claude",
        "-p",
        prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Write,Edit,Bash,Grep,Glob",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    for d in add_dirs:
        cmd += ["--add-dir", d]

    if progress:
        progress.emit(
            "stage",
            stage="analysis_starting",
            message="Running Hormuz appendix skill (CN generate → EN translate)",
            run_dir=str(run_dir),
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    def _handle_event(event: dict, prog, run_state: dict) -> None:
        if prog:
            _process_event(event, prog, run_state)

    state: dict[str, Any] = {}
    _, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_handle_event,
        timeout_sec=timeout_sec,
        timeout_label="hormuz appendix",
        silence_timeout_sec=300.0,
        stop_on_result=True,
    )
    result_event = state.get("result_event")
    if stream_error and result_event is None:
        return {"ok": False, "error": stream_error}
    if result_event and (
        result_event.get("subtype") == "error" or result_event.get("is_error")
    ):
        return {
            "ok": False,
            "error": (
                result_event.get("error")
                or result_event.get("result")
                or "Claude skill run failed"
            ),
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
            "subtype": result_event.get("subtype"),
        }

    out: dict = {"ok": True}
    if result_event:
        out["cost_usd"] = result_event.get("total_cost_usd")
        out["duration_ms"] = result_event.get("duration_ms")
        out["subtype"] = result_event.get("subtype")
    return out


# --- Generic structured-prompt helper -------------------------------------

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def _process_structured_prompt_event(event: dict, progress) -> None:
    """Translate text-only structured-prompt stream events for the job rail."""
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        progress.emit(
            "claude_action",
            action="init",
            session=event.get("session_id"),
            model=event.get("model"),
            tools=event.get("tools") or [],
        )
        return
    if etype == "assistant":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text:
                    progress.emit("claude_action", action="thinking", text=text[:600])
        return
    if etype == "result":
        progress.emit(
            "claude_action",
            action="result",
            subtype=event.get("subtype"),
            cost_usd=event.get("total_cost_usd"),
            duration_ms=event.get("duration_ms"),
            usage=event.get("usage"),
        )


def _process_structured_prompt_event_with_state(
    event: dict, progress, state: dict
) -> None:
    _process_structured_prompt_event(event, progress)
    if event.get("type") == "result":
        state["result_event"] = event


QUICK_SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title_en": {
            "type": ["string", "null"],
            "description": "Concise display title in English (≤80 chars). "
                           "Null if the doc has no good built-in title.",
        },
        "title_zh": {
            "type": ["string", "null"],
            "description": "The same title in Simplified Chinese (简体中文). "
                           "Translated from the source language. Null only "
                           "if title_en is also null.",
        },
        "doc_type": {
            "type": ["string", "null"],
            "description": "Short categorization of what this document is — "
                           "e.g. 'PitchBook profile', 'Investor deck', "
                           "'Partner research note', 'News article', "
                           "'Regulatory filing', 'Internal memo'.",
        },
        "summary_en": {
            "type": "string",
            "description": "3–4 sentences in English. What this document is, "
                           "what it actually says, and why it matters to an "
                           "analyst.",
        },
        "summary_zh": {
            "type": "string",
            "description": "The same 3–4 sentence summary in Simplified "
                           "Chinese (简体中文). Translated from summary_en. "
                           "Preserve numbers, currency amounts, and dates in "
                           "their original Latin form.",
        },
        "key_points_en": {
            "type": "array",
            "items": {"type": "string"},
            "description": "4–7 short bullets in English. Specific facts "
                           "(numbers, names, dates, claims) — never "
                           "marketing language.",
        },
        "key_points_zh": {
            "type": "array",
            "items": {"type": "string"},
            "description": "The same bullets in Simplified Chinese — must "
                           "be the same length as key_points_en and one-to-"
                           "one translated.",
        },
        "key_figures": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "label_en": {"type": "string"},
                    "label_zh": {"type": "string"},
                    "value": {"type": "string"},
                    "context_en": {"type": ["string", "null"]},
                    "context_zh": {"type": ["string", "null"]},
                },
                "required": [
                    "label_en", "label_zh", "value",
                    "context_en", "context_zh",
                ],
            },
            "description": "0–8 important numbers / dates / multiples / sizes "
                           "extracted verbatim. `value` stays in original "
                           "Latin form. label_en / context_en give the "
                           "English version; label_zh / context_zh give the "
                           "Chinese translation.",
        },
        "entities": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "people": {"type": "array", "items": {"type": "string"}},
                "organizations": {"type": "array", "items": {"type": "string"}},
                "products": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["people", "organizations", "products"],
            "description": "Named entities of interest, deduplicated. Keep "
                           "lists short (≤8 each). Use names as they appear "
                           "in the source — do not transliterate.",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3–6 short topical tags (1–3 words each) that "
                           "describe what the doc covers (e.g. 'financials', "
                           "'team', 'moat', 'regulatory'). English only.",
        },
        "source_traces": {
            "type": "array",
            "description": (
                "Up to five source-backed traces for important claims. Use "
                "document locators such as Page 3, Slide 2, Slide 2 notes, "
                "or Document."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": ["string", "null"]},
                    "locator": {"type": "string"},
                    "excerpt": {
                        "type": "string",
                        "description": (
                            "Short evidence excerpt used only for source support."
                        ),
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
            "description": "Detected source language of the document.",
        },
        "description_en": {
            "type": ["string", "null"],
            "description": "**Image documents only.** A detailed textual "
                           "description of what the image shows, in English. "
                           "Multi-paragraph; describes layout, text content, "
                           "charts/diagrams (including the values they "
                           "depict), notable visual elements, and any "
                           "evident context. Null for non-image documents.",
        },
        "description_zh": {
            "type": ["string", "null"],
            "description": "**Image documents only.** The same detailed "
                           "description as ``description_en``, rendered in "
                           "Simplified Chinese (简体中文). Preserve numbers, "
                           "names, currency amounts, percentages, and dates "
                           "in their original Latin form. Null for non-"
                           "image documents.",
        },
    },
    "required": [
        "title_en", "title_zh", "doc_type",
        "summary_en", "summary_zh",
        "key_points_en", "key_points_zh",
        "key_figures",
        "entities", "topics", "source_traces", "language",
        "description_en", "description_zh",
    ],
}


def _quick_summary_read_instructions(kind: str, filename: str) -> str:
    """Per-kind instructions for how Claude reads the source file."""
    if kind == "pdf":
        return (
            f"This is a PDF. Use the Read tool on `{filename}` with "
            f"`pages=\"1-8\"` to look at the first chunk (no more than 8 "
            f"pages per Read — that's the token + image-count safe limit). "
            f"If the document is longer than 8 pages, read a second chunk "
            f"`pages=\"9-16\"` only if the first chunk doesn't give you "
            f"enough to summarize. Stop reading as soon as you can produce "
            f"a confident summary."
        )
    if kind in ("pptx", "ppt"):
        return (
            f"This is a presentation deck. Use the Read tool on "
            f"`{filename}` with `pages=\"1-8\"`. Read a second chunk only "
            f"if needed to summarize."
        )
    if kind == "docx":
        return (
            f"This is a Word document. First convert it with Bash: "
            f"`pandoc {filename} -t markdown -o {filename}.md`. Then "
            f"Read the resulting markdown."
        )
    if kind == "doc":
        return (
            f"This is a legacy .doc file. Try `pandoc {filename} -t "
            f"markdown` via Bash; if that fails, fall back to "
            f"`python -m markitdown {filename}`. Then Read the output."
        )
    if kind == "text":
        return f"Plain text / markdown. Use the Read tool on `{filename}`."
    if kind == "image":
        return (
            f"This is an image. Use the Read tool on `{filename}` — the "
            f"file renders inline so you can see it directly.\n\n"
            f"For images, the **primary deliverable is a detailed textual "
            f"description**, produced in BOTH English (description_en) and "
            f"Simplified Chinese (description_zh). The description must:\n"
            f"  - Cover the full visible content: any text, headers, "
            f"captions, labels, axis labels, legends, footnotes, source "
            f"attributions.\n"
            f"  - For charts / diagrams / tables: enumerate the data points "
            f"or rows the image actually shows. Preserve every number, "
            f"date, percentage, currency amount verbatim.\n"
            f"  - For photos / screenshots: describe layout, components, "
            f"and any informational content (buttons, fields, status "
            f"text).\n"
            f"  - Be multi-paragraph when warranted. Don't pad, but don't "
            f"under-describe either — an analyst reading just the "
            f"description (without seeing the image) can act on its "
            f"contents.\n"
            f"  - The Chinese version is a faithful translation of the "
            f"English version, not a paraphrase or summary. Same content, "
            f"different language. Preserve numbers / dates / currency / "
            f"percentages / proper nouns in their original Latin form. "
            f"Use Chinese-style punctuation (，。；：「」《》) inside "
            f"Chinese sentences.\n"
            f"{INVESTMENT_RESEARCH_CHINESE_STYLE}"
        )
    return f"Use the Read tool on `{filename}`."


def run_quick_summary(
    *,
    source_path: Path,
    work_dir: Path,
    kind: str,
    hint_title: str | None = None,
    progress=None,
    timeout_sec: int = 240,
    cancel_event: threading.Event | None = None,
) -> dict:
    """Produce a rich structured summary of a single research document.

    Streaming variant: spawns `claude -p --output-format stream-json` so
    each Read / Bash / thinking event is emitted to ``progress`` (a
    ``job_progress.ProgressLog``) and surfaces in the unified AI Tasks
    rail. Caller is responsible for the surrounding ``job_init`` event.

    Returns the parsed JSON dict on success, or ``{"error": "..."}``.
    """
    if not is_available():
        return {
            "error": (
                "Claude Code (`claude`) not on PATH. Install it with "
                "`npm install -g @anthropic-ai/claude-code` and authenticate."
            )
        }
    if not work_dir.exists():
        return {"error": f"Work folder missing: {work_dir}"}

    staged = work_dir / source_path.name
    if not staged.exists():
        try:
            staged.write_bytes(source_path.read_bytes())
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Failed to stage source file: {exc}"}

    schema_str = json.dumps(QUICK_SUMMARY_SCHEMA, indent=2, ensure_ascii=False)
    read_hint = _quick_summary_read_instructions(kind, source_path.name)
    title_line = (
        f"(Hint: this file is titled \"{hint_title}\".)\n" if hint_title else ""
    )

    prompt = f"""\
You are producing a RICH structured summary of one background document for
an investment-research analyst. This summary surfaces alongside the file in
a "Background Documents" panel — be tight, factual, and concrete. Skim
enough to capture the essentials; don't read every page if not necessary.

Source file (in your current working directory): `{source_path.name}`
{title_line}

How to read it:
{read_hint}

Once you have enough to summarize, STOP reading and produce the output.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output the JSON object ONLY. No prose, no commentary, no markdown
  fences, no explanation. The first character of your response is `{{`
  and the last is `}}`.
- BILINGUAL output: for text-bearing fields you MUST produce BOTH an
  English version and a Simplified Chinese (简体中文) version. Regardless
  of the document's source language, fill out both _en and _zh fields by
  translating one to the other. Preserve numbers, currency amounts,
  percentages, and dates in their original Latin form. Preserve proper
  nouns (company names, product names, people) in the form they appear
  in the source — do not transliterate.
- When producing Chinese fields, apply this style guide:
{INVESTMENT_RESEARCH_CHINESE_STYLE}
- summary_en / summary_zh: 3–4 sentences each. No marketing adjectives,
  no "this document covers various topics" filler. summary_zh is a
  faithful translation of summary_en (or vice versa), not a different
  summary.
- key_points_en / key_points_zh: 4–7 short bullets, ONE-TO-ONE: same
  count, same order, each item translated. If the doc is very short,
  fewer bullets is fine.
- key_figures: extract 0–8 important numbers / dates / multiples /
  sizes. `value` is the verbatim figure (Latin / numeric). label_en
  and label_zh describe what the figure measures. context_en /
  context_zh briefly say where it came from in the doc. Both _en and
  _zh strings are required for label; context may be null on both sides.
- entities: deduplicated lists of people / organizations / products
  mentioned, capped at 8 each. Use the names as they appear in the doc
  (a single list, not bilingual).
- topics: 3–6 short topical tags (1–3 words each), English only.
- source_traces: up to five important source-backed traces. For each trace,
  state the claim it supports, the locator (for example Page 3, Slide 2,
  Slide 2 notes, or Document), a short evidence excerpt or faithful
  paraphrase used only for source support, and confidence.
- doc_type: a short categorization (e.g. "PitchBook profile",
  "Investor deck", "Partner research note", "News article",
  "Regulatory filing", "Internal memo", "Chart / diagram",
  "Screenshot"). Null if you can't tell. English only.
- title_en / title_zh: concise display title (≤80 chars), in both
  languages. Null only when the doc has no good built-in title.
- language: en / zh / other based on what dominates the source text.
- description_en and description_zh: for **image documents only**,
  produce a detailed textual description in BOTH English and Simplified
  Chinese (per the image read instructions above). For non-image
  documents, both fields MUST be null.
"""

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Reading document",
            file=source_path.name,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return {"error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_event,
        timeout_sec=timeout_sec,
        timeout_label="quick summary",
        cancel_event=cancel_event,
    )
    if stream_error:
        return {"error": stream_error}

    if proc.returncode and proc.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return {
            "error": (
                f"claude exited {proc.returncode}"
                + (f": {tail[:600]}" if tail else "")
            )
        }

    result_event = state.get("result_event")
    if not final_text and result_event:
        final_text = result_event.get("result")
    if not final_text:
        return {"error": "claude returned empty result"}

    final_text = final_text.strip()
    parsed = _parse_json_tolerant(final_text)
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```",
                            final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if parsed is None:
        return {"error": f"claude output didn't parse as JSON: {final_text[:300]}"}

    if result_event:
        parsed["claude_cost_usd"] = result_event.get("total_cost_usd")
        parsed["claude_duration_ms"] = result_event.get("duration_ms")
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed


def run_structured_prompt(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str = "structured_output",
    timeout_sec: int = 180,
    progress=None,
    cancel_event: threading.Event | None = None,
) -> tuple[dict | None, str | None]:
    """Run a one-shot `claude -p` call and parse a strict-JSON response.

    Use this for any text-in / structured-JSON-out task that doesn't need
    tools (translation, text summarization, classification). Returns
    ``(data, error)`` — exactly one of the two is non-None.

    The schema is embedded directly in the prompt rather than passed
    via ``--json-schema``: the CLI's schema-validation behavior is
    flaky for text-only prompts (returns empty or commentary instead of
    a constrained JSON). Embedding the schema + parsing tolerantly is
    more reliable for this use case.

    ``name`` is a debug label that ends up in error messages.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    schema_str = json.dumps(schema, indent=2, ensure_ascii=False)
    combined = (
        f"{system_prompt}\n\n"
        f"---\n"
        f"{user_prompt}\n"
        f"---\n\n"
        f"OUTPUT REQUIREMENTS (these override anything contradictory above):\n"
        f"- Respond with ONE JSON object that conforms to this schema:\n\n"
        f"```json\n{schema_str}\n```\n\n"
        f"- Output the JSON object ONLY. No prose, no commentary, no "
        f"markdown fences, no explanation. The first character of your "
        f"response is `{{` and the last is `}}`.\n"
        f"- Every required field in the schema must be present. Use null "
        f"for fields you can't fill in.\n"
        f"- For arrays declared in the schema, return the same number of "
        f"items as the source where applicable; never invent extras."
    )

    cmd = [
        claude_path() or "claude",
        "-p", combined,
        "--output-format", "stream-json" if progress else "json",
        *(["--verbose"] if progress else []),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Analyzing with Claude",
            name=name,
        )
        stderr_log: list[str] = []
        try:
            proc = _popen_claude(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            return None, f"Failed to launch claude: {exc}"

        stderr_thread = threading.Thread(
            target=_drain_stderr, args=(proc, stderr_log), daemon=True
        )
        stderr_thread.start()

        state: dict[str, Any] = {}
        final_text, stream_error = _consume_stream_json_process(
            proc,
            stderr_log=stderr_log,
            progress=progress,
            state=state,
            event_handler=_process_structured_prompt_event_with_state,
            timeout_sec=timeout_sec,
            timeout_label=name,
            cancel_event=cancel_event,
        )
        if stream_error:
            return None, stream_error

        if proc.returncode != 0:
            return None, _claude_exit_error(
                proc.returncode, "".join(stderr_log[-20:])
            )
        result_event = state.get("result_event")
        if not final_text and result_event:
            final_text = (result_event.get("result") or "").strip()
        if not final_text:
            return None, "claude returned empty result"
    else:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except subprocess.TimeoutExpired:
            return None, f"claude timed out after {timeout_sec}s ({name})"
        except FileNotFoundError as exc:
            return None, f"Failed to launch claude: {exc}"

        if proc.returncode != 0:
            return None, _claude_exit_error(
                proc.returncode, proc.stderr, proc.stdout
            )

        try:
            envelope = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError as exc:
            return None, f"claude returned non-JSON envelope: {exc}"

        final_text = (envelope.get("result") or "").strip()
        if not final_text:
            return None, "claude returned empty result"

    # First try: parse the whole thing as JSON.
    parsed = _parse_json_tolerant(final_text)
    if parsed is not None:
        return parsed, None

    # Fallback: strip code fences if Claude added them despite instructions.
    text = final_text
    if "```" in text:
        # Pull the largest fenced block.
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        if fenced:
            text = max(fenced, key=len).strip()
            parsed = _parse_json_tolerant(text)
            if parsed is not None:
                return parsed, None

    # Last resort: extract the first {...} block.
    m = _JSON_OBJ_RE.search(final_text)
    if m:
        parsed = _parse_json_tolerant(m.group(0))
        if parsed is not None:
            return parsed, None

    return None, (
        f"claude output didn't parse as JSON (name={name}): "
        f"{final_text[:300]}"
    )


SERENA_RESEARCH_TASK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "answer": {
            "type": "string",
            "description": (
                "Direct memo-grade answer to the research task. Explain what "
                "was found, what remains uncertain, and how it changes "
                "valuation support or model treatment."
            ),
        },
        "supporting_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_id": {"type": ["string", "null"]},
                    "filename": {"type": ["string", "null"]},
                    "locator": {"type": ["string", "null"]},
                    "excerpt": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "file_id",
                    "filename",
                    "locator",
                    "excerpt",
                    "confidence",
                ],
            },
            "description": "Evidence that supports the answer.",
        },
        "contradicting_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_id": {"type": ["string", "null"]},
                    "filename": {"type": ["string", "null"]},
                    "locator": {"type": ["string", "null"]},
                    "excerpt": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "file_id",
                    "filename",
                    "locator",
                    "excerpt",
                    "confidence",
                ],
            },
            "description": "Evidence that contradicts or weakens the answer.",
        },
        "remaining_evidence_limits": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Evidence limits stated with the investment implication, "
                "source treatment, or valuation sensitivity they create."
            ),
        },
        "sources_checked": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "file_id": {"type": ["string", "null"]},
                    "filename": {"type": ["string", "null"]},
                    "source_type": {"type": ["string", "null"]},
                    "notes": {"type": ["string", "null"]},
                },
                "required": ["file_id", "filename", "source_type", "notes"],
            },
            "description": "Files, web sources, filings, or source categories actually checked.",
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
            "description": "Confidence in the result based on source quality and coverage.",
        },
    },
    "required": [
        "answer",
        "supporting_evidence",
        "contradicting_evidence",
        "remaining_evidence_limits",
        "sources_checked",
        "confidence",
    ],
}


_SERENA_RISK_EVIDENCE_ITEM: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "file_id": {"type": ["string", "null"]},
        "filename": {"type": ["string", "null"]},
        "locator": {"type": ["string", "null"]},
        "excerpt": {"type": "string"},
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
        "source_class": {
            "type": "string",
            "enum": [
                "first_party",
                "third_party",
                "market_data",
                "filing",
                "transcript",
                "news",
                "research_file",
                "inference",
            ],
        },
    },
    "required": [
        "file_id",
        "filename",
        "locator",
        "excerpt",
        "confidence",
        "source_class",
    ],
}

SERENA_STRATEGIC_RISK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "risks": {
            "type": "array",
            "minItems": 5,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "description": {
                        "type": "string",
                        "description": "One or two sentences on what the risk actually is.",
                    },
                    "decision_question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "materiality": {
                        "type": "string",
                        "description": (
                            "Why this is a genuine investment risk rather than "
                            "a technically possible but practically irrelevant issue."
                        ),
                    },
                    "bull_case_answer": {"type": "string"},
                    "bear_case_answer": {"type": "string"},
                    "key_questions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence_needed": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "best_sources": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "supporting_evidence": {
                        "type": "array",
                        "items": _SERENA_RISK_EVIDENCE_ITEM,
                    },
                    "contradicting_evidence": {
                        "type": "array",
                        "items": _SERENA_RISK_EVIDENCE_ITEM,
                    },
                    "missing_evidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "evidence_that_would_change_assessment": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "research_prompt": {"type": "string"},
                    "memo_section": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "likelihood": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "mitigation_or_monitoring": {"type": "string"},
                    "suggested_posture": {
                        "type": "string",
                        "enum": [
                            "lead_risk",
                            "downside_trigger",
                            "valuation_sensitivity",
                            "monitoring",
                        ],
                    },
                    "status": {
                        "type": "string",
                        "enum": ["unresearched", "researched", "needs_review"],
                    },
                },
                "required": [
                    "title",
                    "description",
                    "decision_question",
                    "why_it_matters",
                    "materiality",
                    "bull_case_answer",
                    "bear_case_answer",
                    "key_questions",
                    "evidence_needed",
                    "best_sources",
                    "supporting_evidence",
                    "contradicting_evidence",
                    "missing_evidence",
                    "evidence_that_would_change_assessment",
                    "research_prompt",
                    "memo_section",
                    "severity",
                    "likelihood",
                    "mitigation_or_monitoring",
                    "suggested_posture",
                    "status",
                ],
            },
        },
        "source_basis": {
            "type": "object",
            "additionalProperties": True,
            "description": "Short metadata describing source types used.",
        },
    },
    "required": ["risks", "source_basis"],
}


SERENA_RISK_REFINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": SERENA_STRATEGIC_RISK_SCHEMA["properties"]["risks"]["items"]["properties"],
    "required": SERENA_STRATEGIC_RISK_SCHEMA["properties"]["risks"]["items"]["required"],
}


SERENA_THESIS_SPINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "investment_highlights": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"},
                    "detail": {"type": "string"},
                    "state": {
                        "type": "string",
                        "description": (
                            "present_state, upside_state, risk_adjusted, or "
                            "source_limited."
                        ),
                    },
                    "source_trace": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "needs_stronger_evidence": {"type": "boolean"},
                },
                "required": [
                    "claim",
                    "detail",
                    "state",
                    "source_trace",
                    "needs_stronger_evidence",
                ],
            },
        },
        "investment_risks": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "claim": {"type": "string"},
                    "detail": {"type": "string"},
                    "source_trace": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "needs_stronger_evidence": {"type": "boolean"},
                },
                "required": [
                    "claim",
                    "detail",
                    "source_trace",
                    "needs_stronger_evidence",
                ],
            },
        },
        "recommendation_logic": {
            "type": "string",
            "description": (
                "Direct recommendation rationale for BSH, including the "
                "risk and valuation sensitivities that matter."
            ),
        },
        "risk_valuation_sensitivities": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sensitivity": {
                        "type": "string",
                        "description": (
                            "Measurable risk or valuation variable that can "
                            "strengthen or weaken the investment case."
                        ),
                    },
                    "support_evidence": {
                        "type": "string",
                        "description": (
                            "Specific source-backed evidence that supports "
                            "the recommendation or base-case valuation."
                        ),
                    },
                    "evidence_context": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "downside_impact": {"type": "string"},
                    "recommendation_sensitivity": {"type": "string"},
                },
                "required": [
                    "sensitivity",
                    "support_evidence",
                    "evidence_context",
                    "downside_impact",
                    "recommendation_sensitivity",
                ],
            },
        },
        "bull_case_must_be_true": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {"type": "string"},
        },
        "downside_sensitivities": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {
                "type": "string",
                "description": (
                    "Investor-facing downside sensitivity stated as a factual "
                    "risk or valuation implication, not as a stop/revisit "
                    "condition, checklist, or pass trigger."
                ),
            },
        },
        "source_basis": {
            "type": "object",
            "additionalProperties": True,
            "description": "Short metadata describing source types used.",
        },
    },
    "required": [
        "investment_highlights",
        "investment_risks",
        "recommendation_logic",
        "risk_valuation_sensitivities",
        "bull_case_must_be_true",
        "downside_sensitivities",
        "source_basis",
    ],
}


SERENA_BENCHMARK_DASHBOARD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "public_comps": {
            "type": "array",
            "minItems": 3,
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "company": {"type": "string"},
                    "ticker": {"type": ["string", "null"]},
                    "why_relevant": {"type": "string"},
                    "revenue_growth_pct": {"type": ["number", "null"]},
                    "gross_margin_pct": {"type": ["number", "null"]},
                    "ev_revenue": {"type": ["number", "null"]},
                    "ev_ebitda": {"type": ["number", "null"]},
                    "fcf_margin_pct": {"type": ["number", "null"]},
                    "rule_of_40": {"type": ["number", "null"]},
                    "metric_period": {"type": ["string", "null"]},
                    "sell_side_theme": {"type": "string"},
                    "source_traces": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "title": {"type": ["string", "null"]},
                                "url": {"type": ["string", "null"]},
                                "locator": {"type": ["string", "null"]},
                                "excerpt": {"type": "string"},
                                "confidence": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                            },
                            "required": [
                                "title",
                                "url",
                                "locator",
                                "excerpt",
                                "confidence",
                            ],
                        },
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "company",
                    "ticker",
                    "why_relevant",
                    "revenue_growth_pct",
                    "gross_margin_pct",
                    "ev_revenue",
                    "ev_ebitda",
                    "fcf_margin_pct",
                    "rule_of_40",
                    "metric_period",
                    "sell_side_theme",
                    "source_traces",
                    "confidence",
                ],
            },
        },
        "benchmark_gaps": {
            "type": "array",
            "items": {"type": "string"},
        },
        "must_prove": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source_traces": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": ["string", "null"]},
                    "url": {"type": ["string", "null"]},
                    "locator": {"type": ["string", "null"]},
                    "excerpt": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": ["title", "url", "locator", "excerpt", "confidence"],
            },
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": [
        "summary",
        "public_comps",
        "benchmark_gaps",
        "must_prove",
        "source_traces",
        "confidence",
    ],
}


SERENA_SOURCE_TRACE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
        "locator": {"type": ["string", "null"]},
        "excerpt": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["title", "url", "locator", "excerpt", "confidence"],
}


SERENA_REVIEWER_PROMPT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "prompt": {"type": "string"},
        "required": {"type": "boolean"},
        "options": {"type": "array", "items": {"type": "string"}},
        "resolved_choice": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
        "status": {"type": "string"},
    },
    "required": [
        "id",
        "prompt",
        "required",
        "options",
        "resolved_choice",
        "rationale",
        "status",
    ],
}


SERENA_INFOGRAPHIC_SOURCE_BRIEF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "compact_claims": {
            "type": "array",
            "minItems": 1,
            "maxItems": 16,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "claim": {"type": "string"},
                    "evidence_status": {"type": "string"},
                    "source_traces": {
                        "type": "array",
                        "items": SERENA_SOURCE_TRACE_SCHEMA,
                    },
                    "contradictions": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "warnings": {"type": "array", "items": {"type": "string"}},
                    "prohibited_for_visuals": {"type": "boolean"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "id",
                    "claim",
                    "evidence_status",
                    "source_traces",
                    "contradictions",
                    "warnings",
                    "prohibited_for_visuals",
                    "confidence",
                ],
            },
        },
        "numeric_metrics": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "value": {"type": ["string", "number", "null"]},
                    "unit": {"type": ["string", "null"]},
                    "period": {"type": ["string", "null"]},
                    "calculation": {"type": "string"},
                    "denominator_note": {"type": "string"},
                    "source_traces": {
                        "type": "array",
                        "items": SERENA_SOURCE_TRACE_SCHEMA,
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "id",
                    "label",
                    "value",
                    "unit",
                    "period",
                    "calculation",
                    "denominator_note",
                    "source_traces",
                    "confidence",
                ],
            },
        },
        "source_traces": {"type": "array", "items": SERENA_SOURCE_TRACE_SCHEMA},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "missing_evidence": {"type": "array", "items": {"type": "string"}},
        "no_go_claims": {"type": "array", "items": {"type": "string"}},
        "visual_opportunities": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "paired_claim_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_trace_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "id",
                    "title",
                    "rationale",
                    "paired_claim_ids",
                    "source_trace_ids",
                    "confidence",
                ],
            },
        },
        "narrative_opportunities": {
            "type": "array",
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "rationale": {"type": "string"},
                    "paired_claim_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_trace_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "id",
                    "title",
                    "rationale",
                    "paired_claim_ids",
                    "source_trace_ids",
                    "confidence",
                ],
            },
        },
        "reviewer_prompts": {
            "type": "array",
            "items": SERENA_REVIEWER_PROMPT_SCHEMA,
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "summary",
        "compact_claims",
        "numeric_metrics",
        "source_traces",
        "contradictions",
        "missing_evidence",
        "no_go_claims",
        "visual_opportunities",
        "narrative_opportunities",
        "reviewer_prompts",
        "confidence",
    ],
}


SERENA_CHART_SPEC_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "generated_from_brief_id": {"type": ["string", "null"]},
        "specs": {
            "type": "array",
            "minItems": 3,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "takeaway": {"type": "string"},
                    "recommended_visual_format": {"type": "string"},
                    "alternate_formats": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "image_generation_mode": {
                        "type": "string",
                        "enum": [
                            "no_text_overlay",
                            "text_in_image",
                            "operator_choice_required",
                        ],
                    },
                    "text_overlay_plan": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "headline": {"type": "string"},
                            "labels": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "callouts": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "footnotes": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "safe_copy_length": {"type": "string"},
                        },
                        "required": [
                            "headline",
                            "labels",
                            "callouts",
                            "footnotes",
                            "safe_copy_length",
                        ],
                    },
                    "required_metrics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "value": {"type": ["string", "number", "null"]},
                                "unit": {"type": ["string", "null"]},
                                "period": {"type": ["string", "null"]},
                                "calculation": {"type": "string"},
                                "denominator_note": {"type": "string"},
                                "source_available": {"type": "boolean"},
                                "source_traces": {
                                    "type": "array",
                                    "items": SERENA_SOURCE_TRACE_SCHEMA,
                                },
                                "confidence": {
                                    "type": "string",
                                    "enum": ["low", "medium", "high"],
                                },
                            },
                            "required": [
                                "id",
                                "label",
                                "value",
                                "unit",
                                "period",
                                "calculation",
                                "denominator_note",
                                "source_available",
                                "source_traces",
                                "confidence",
                            ],
                        },
                    },
                    "source_availability": {
                        "type": "string",
                        "enum": ["available", "partial", "missing"],
                    },
                    "source_traces": {
                        "type": "array",
                        "items": SERENA_SOURCE_TRACE_SCHEMA,
                    },
                    "information_gaps": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "data_payload": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "label": {"type": "string"},
                                "value": {"type": ["string", "number", "null"]},
                                "unit": {"type": ["string", "null"]},
                                "period": {"type": ["string", "null"]},
                                "notes": {"type": "string"},
                            },
                            "required": [
                                "id",
                                "label",
                                "value",
                                "unit",
                                "period",
                                "notes",
                            ],
                        },
                    },
                    "design_prompt": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "composition": {"type": "string"},
                            "visual_metaphor": {"type": "string"},
                            "style_constraints": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "aspect_ratio": {"type": "string"},
                            "prohibited_claims": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "composition",
                            "visual_metaphor",
                            "style_constraints",
                            "aspect_ratio",
                            "prohibited_claims",
                        ],
                    },
                    "owner": {"type": "string"},
                    "source_limitations": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "memo_section_placement": {"type": "string"},
                    "include_in_final_memo": {"type": "boolean"},
                    "memo_inclusion_decision": {"type": "string"},
                    "reviewer_prompts": {
                        "type": "array",
                        "items": SERENA_REVIEWER_PROMPT_SCHEMA,
                    },
                    "status": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                },
                "required": [
                    "id",
                    "title",
                    "purpose",
                    "takeaway",
                    "recommended_visual_format",
                    "alternate_formats",
                    "image_generation_mode",
                    "text_overlay_plan",
                    "required_metrics",
                    "source_availability",
                    "source_traces",
                    "information_gaps",
                    "data_payload",
                    "design_prompt",
                    "owner",
                    "source_limitations",
                    "memo_section_placement",
                    "include_in_final_memo",
                    "memo_inclusion_decision",
                    "reviewer_prompts",
                    "status",
                    "confidence",
                ],
            },
        },
        "reviewer_prompts": {
            "type": "array",
            "items": SERENA_REVIEWER_PROMPT_SCHEMA,
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "summary",
        "generated_from_brief_id",
        "specs",
        "reviewer_prompts",
        "confidence",
    ],
}


SERENA_NARRATIVE_HOOKS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "generated_from_brief_id": {"type": ["string", "null"]},
        "openings": {"type": "array", "minItems": 2, "items": {}},
        "transitions": {"type": "array", "items": {}},
        "endings": {"type": "array", "minItems": 2, "items": {}},
        "selected_opening_id": {"type": ["string", "null"]},
        "selected_transition_id": {"type": ["string", "null"]},
        "selected_ending_id": {"type": ["string", "null"]},
        "reviewer_prompts": {
            "type": "array",
            "items": SERENA_REVIEWER_PROMPT_SCHEMA,
        },
        "status": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": [
        "summary",
        "generated_from_brief_id",
        "openings",
        "transitions",
        "endings",
        "selected_opening_id",
        "selected_transition_id",
        "selected_ending_id",
        "reviewer_prompts",
        "status",
        "confidence",
    ],
}

_SERENA_NARRATIVE_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "text": {"type": "string"},
        "purpose": {"type": "string"},
        "tone": {"type": "string"},
        "supported_claims": {"type": "array", "items": {"type": "string"}},
        "evidence_references": {"type": "array", "items": {"type": "string"}},
        "source_traces": {"type": "array", "items": SERENA_SOURCE_TRACE_SCHEMA},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "overclaiming_risk": {"type": "string"},
        "paired_infographic_ids": {
            "type": "array",
            "items": {"type": "string"},
        },
        "reviewer_prompts": {
            "type": "array",
            "items": SERENA_REVIEWER_PROMPT_SCHEMA,
        },
        "status": {"type": "string"},
    },
    "required": [
        "id",
        "text",
        "purpose",
        "tone",
        "supported_claims",
        "evidence_references",
        "source_traces",
        "confidence",
        "overclaiming_risk",
        "paired_infographic_ids",
        "reviewer_prompts",
        "status",
    ],
}
SERENA_NARRATIVE_HOOKS_SCHEMA["properties"]["openings"]["items"] = (
    _SERENA_NARRATIVE_CANDIDATE_SCHEMA
)
SERENA_NARRATIVE_HOOKS_SCHEMA["properties"]["transitions"]["items"] = (
    _SERENA_NARRATIVE_CANDIDATE_SCHEMA
)
SERENA_NARRATIVE_HOOKS_SCHEMA["properties"]["endings"]["items"] = (
    _SERENA_NARRATIVE_CANDIDATE_SCHEMA
)


SERENA_MEMO_GRADER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "completed_report_id": {"type": "string"},
        "completed_run_id": {"type": ["string", "null"]},
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "area": {"type": "string"},
                    "score": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["area", "score", "rationale"],
            },
        },
        "strongest_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "weakest_sections": {
            "type": "array",
            "items": {"type": "string"},
        },
        "evidence_limits": {
            "type": "array",
            "items": {"type": "string"},
        },
        "rewrite_guidance": {
            "type": "array",
            "items": {"type": "string"},
        },
        "lessons_for_future_memo_runs": {
            "type": "array",
            "items": {"type": "string"},
        },
        "source_files_reviewed": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {
            "type": "string",
            "enum": ["low", "medium", "high"],
        },
    },
    "required": [
        "completed_report_id",
        "completed_run_id",
        "scores",
        "strongest_sections",
        "weakest_sections",
        "evidence_limits",
        "rewrite_guidance",
        "lessons_for_future_memo_runs",
        "source_files_reviewed",
        "confidence",
    ],
}


def _serena_research_file_names(research_dir: Path) -> list[str]:
    if not research_dir.exists():
        return []
    try:
        return [
            p.name
            for p in sorted(research_dir.iterdir())
            if p.is_file() and p.name != "index.yaml"
        ][:100]
    except Exception:
        return []


def _parse_claude_json_object(final_text: str) -> dict | None:
    parsed = _parse_json_tolerant(final_text.strip())
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    return parsed if isinstance(parsed, dict) else None


def _run_serena_json_artifact(
    *,
    prompt: str,
    schema: dict[str, Any],
    work_dir: Path,
    progress,
    progress_message: str,
    company_id: str,
    timeout_label: str,
    timeout_sec: int,
    silence_timeout_sec: int,
    extra_add_dirs: list[Path] | None = None,
) -> tuple[dict | None, str | None]:
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    work_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash,WebSearch,WebFetch",
        "--json-schema", json.dumps(schema),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    for directory in extra_add_dirs or []:
        if directory.exists():
            cmd.extend(["--add-dir", str(directory)])

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message=progress_message,
            company_id=company_id,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label=timeout_label,
        silence_timeout_sec=silence_timeout_sec,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"
    parsed = _parse_claude_json_object(final_text)
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed, None


def run_serena_infographic_source_brief(
    *,
    company: dict,
    artifacts: dict,
    research_dir: Path,
    lessons_path: Path | None = None,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Run Serena's infographic source brief distillation through Claude Code."""
    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_infographic_source_{company_id or 'company'}"
    )
    local_files = _serena_research_file_names(research_dir)
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."
    analysis_context = {
        "thesis_spine": artifacts.get("thesis_spine"),
        "strategic_risks": artifacts.get("strategic_risks"),
        "risk_priorities": artifacts.get("risk_priorities"),
        "research_tasks": artifacts.get("research_tasks"),
        "evidence_matrix": artifacts.get("evidence_matrix"),
        "benchmark_dashboard": artifacts.get("benchmark_dashboard"),
        "readiness_reviews": artifacts.get("readiness_reviews"),
        "chart_specs": artifacts.get("chart_specs"),
        "narrative_hooks": artifacts.get("narrative_hooks"),
        "memo_grader": artifacts.get("memo_grader"),
    }
    schema_str = json.dumps(
        SERENA_INFOGRAPHIC_SOURCE_BRIEF_SCHEMA,
        indent=2,
        ensure_ascii=False,
    )
    context_str = json.dumps(
        analysis_context,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    lessons_block = ""
    extra_dirs: list[Path] = []
    if lessons_path and lessons_path.exists():
        lessons_block = f"""\

Memo lessons:
`{lessons_path}`

Use these as quality heuristics only. Current company evidence and current
Memo Studio artifacts override stale or contradictory lessons. Strip stale
internal labels, prompt labels, and process/checklist wording before use.
"""
        extra_dirs.append(lessons_path.parent)

    prompt = f"""\
You are Serena's infographic source-brief distiller for a BSH late-stage
investment memo about {company_name}.

Company:
```json
{company_str}
```

Current Memo Studio artifacts:
```json
{context_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}
{lessons_block}

Instructions:
- Build a compact, durable source brief for later infographic and narrative
  generation. Do not write final memo prose.
- Use the current thesis spine, selected risks, research-task evidence,
  evidence matrix-like contradictions, benchmark metrics, evidence-readiness
  notes, selected chart/narrative state, prior quality guidance, and selected
  research-folder excerpts.
- Narrative opportunities must explicitly identify the strongest available
  source-backed material for three final memo passages: the intro stance, the
  risk-section stance, and the conclusion/recommendation verdict.
- Use the Serena research folder above for local company documents. Do NOT read
  from `data/uploads/` or the Document Library.
- If local research files exist, inspect only the high-signal files needed for
  source support. Use WebSearch/WebFetch only for public current evidence that
  affects a metric, contradiction, or visual claim.
- Keep claims compact and mark missing, contradicted, source_needed, or
  prohibited_for_visuals when the evidence is not good enough for visuals.
- Numeric metrics must include unit, period, denominator or calculation notes,
  and source evidence details when available. Use null when unavailable.
- Put ambiguous tone, aggressiveness, visual mode, or claim-framing choices in
  operator review notes rather than silently resolving them.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
"""
    parsed, error = _run_serena_json_artifact(
        prompt=prompt,
        schema=SERENA_INFOGRAPHIC_SOURCE_BRIEF_SCHEMA,
        work_dir=work_dir,
        progress=progress,
        progress_message="Distilling infographic source brief with Claude",
        company_id=company_id,
        timeout_label="serena infographic source brief",
        timeout_sec=timeout_sec,
        silence_timeout_sec=silence_timeout_sec,
        extra_add_dirs=extra_dirs,
    )
    if error:
        return None, error
    if not isinstance(parsed, dict) or not parsed.get("compact_claims"):
        return None, "claude output missing compact_claims"
    return parsed, None


def run_serena_chart_spec_builder(
    *,
    company: dict,
    artifacts: dict,
    research_dir: Path,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Run Serena's image-generation-ready chart planner through Claude Code."""
    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_chart_specs_{company_id or 'company'}"
    )
    local_files = _serena_research_file_names(research_dir)
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."
    analysis_context = {
        "infographic_source_brief": artifacts.get("infographic_source_brief"),
        "thesis_spine": artifacts.get("thesis_spine"),
        "research_tasks": artifacts.get("research_tasks"),
        "benchmark_dashboard": artifacts.get("benchmark_dashboard"),
        "chart_specs": artifacts.get("chart_specs"),
    }
    schema_str = json.dumps(
        SERENA_CHART_SPEC_SCHEMA,
        indent=2,
        ensure_ascii=False,
    )
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    context_str = json.dumps(
        analysis_context,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    prompt = f"""\
You are Serena's image-generation-ready infographic planner for a BSH
late-stage investment memo about {company_name}.

Company:
```json
{company_str}
```

Compact source brief and current chart state:
```json
{context_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}

Instructions:
- Use infographic_source_brief as the primary factual input. Inspect local
  research files or web sources only when necessary to preserve or verify
  source support. Do NOT read from `data/uploads/` or the Document Library.
- Plan high-quality memo infographics, not low-fidelity deterministic charts.
- Support two production modes: no_text_overlay for image generation without
  text plus app-rendered typography, and text_in_image when fully generated
  text is the better fit. Use operator_choice_required plus operator review
  notes when the choice is ambiguous.
- For every plan, include title, purpose, visual format, overlay copy,
  required metrics, data payload, source availability, citations, information
  gaps, image generation composition brief, unsupported claims, owner, evidence
  limits, memo section placement, and memo inclusion decision.
- Do not invent metrics, source support, periods, denominators, or claims. Use
  null or information_gaps when evidence is missing.
- Preserve selected/include intent from existing chart_specs when it remains
  semantically relevant.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
"""
    parsed, error = _run_serena_json_artifact(
        prompt=prompt,
        schema=SERENA_CHART_SPEC_SCHEMA,
        work_dir=work_dir,
        progress=progress,
        progress_message="Planning memo infographics with Claude",
        company_id=company_id,
        timeout_label="serena chart spec builder",
        timeout_sec=timeout_sec,
        silence_timeout_sec=silence_timeout_sec,
    )
    if error:
        return None, error
    if not isinstance(parsed, dict) or not parsed.get("specs"):
        return None, "claude output missing specs"
    return parsed, None


def run_serena_narrative_hooks(
    *,
    company: dict,
    artifacts: dict,
    research_dir: Path,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Run Serena's source-backed narrative hook planner through Claude Code."""
    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_narrative_hooks_{company_id or 'company'}"
    )
    local_files = _serena_research_file_names(research_dir)
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."
    analysis_context = {
        "infographic_source_brief": artifacts.get("infographic_source_brief"),
        "thesis_spine": artifacts.get("thesis_spine"),
        "strategic_risks": artifacts.get("strategic_risks"),
        "risk_priorities": artifacts.get("risk_priorities"),
        "research_tasks": artifacts.get("research_tasks"),
        "evidence_matrix": artifacts.get("evidence_matrix"),
        "benchmark_dashboard": artifacts.get("benchmark_dashboard"),
        "chart_specs": artifacts.get("chart_specs"),
        "narrative_hooks": artifacts.get("narrative_hooks"),
        "memo_grader": artifacts.get("memo_grader"),
        "readiness_reviews": artifacts.get("readiness_reviews"),
    }
    schema_str = json.dumps(
        SERENA_NARRATIVE_HOOKS_SCHEMA,
        indent=2,
        ensure_ascii=False,
    )
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    context_str = json.dumps(
        analysis_context,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    prompt = f"""\
You are Serena's source-backed narrative hook planner for a BSH late-stage
investment memo about {company_name}.

Company:
```json
{company_str}
```

Compact source brief, infographic plans, and current hook state:
```json
{context_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}

Instructions:
- Use infographic_source_brief, thesis_spine, selected risk priorities,
  completed research-task evidence, contradictions, benchmark dashboard, chart
  plans, memo-grader lessons, and reviewed source limits as the factual base. Do NOT
  read from `data/uploads/` or the Document Library.
- Draft operator-selectable candidates for three final memo passages:
  1. openings = intro stance: the first 2-4 sentences' judgment and proof burden;
  2. transitions = risk-section posture: lead risk and recommendation-moving
     evidence;
  3. endings = conclusion/recommendation verdict: conviction, valuation
     sensitivities, failure modes, and deal mechanics.
- Generate at least three distinct openings, at least two risk-posture
  transitions, and at least three endings when the evidence allows.
- Candidate text must be IC-ready guidance or near-final memo language:
  specific, compressed, evidence-grounded, and free of meta phrases such as
  document-process framing, analysis-process framing, or section narration.
- Endings and recommendation candidates must use first-person sponsor voice:
  "we recommend participating", "we do not recommend participating", or
  "we do not recommend participating unless..." only where the evidence
  requires a conditional posture. Do not write detached third-person
  recommendation, opportunity, or base-case framing.
- Each candidate must include supported claims, evidence references, source
  traces where available, confidence, overclaiming risk, and suggested
  infographic pairings where useful.
- Preserve selected opening/transition/ending ids when current choices remain
  semantically valid.
- Use operator review notes only for genuine operator HIL choices about intro
  stance, risk posture, or conclusion posture that cannot be safely inferred
  from the evidence. Make them optional unless approval is unsafe without
  the operator's answer.
- Do not invent facts. Unsupported claims must become risk factors, missing
  evidence, or valuation sensitivities.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
"""
    parsed, error = _run_serena_json_artifact(
        prompt=prompt,
        schema=SERENA_NARRATIVE_HOOKS_SCHEMA,
        work_dir=work_dir,
        progress=progress,
        progress_message="Planning narrative hooks with Claude",
        company_id=company_id,
        timeout_label="serena narrative hooks",
        timeout_sec=timeout_sec,
        silence_timeout_sec=silence_timeout_sec,
    )
    if error:
        return None, error
    if not isinstance(parsed, dict) or not parsed.get("openings"):
        return None, "claude output missing openings"
    if not parsed.get("endings"):
        return None, "claude output missing endings"
    return parsed, None


def run_serena_strategic_risk_mapper(
    *,
    company: dict,
    research_dir: Path,
    lessons_path: Path | None = None,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Run Serena's strategic risk mapper through Claude Code.

    The caller owns lifecycle and persistence. This helper returns a parsed
    artifact-shaped payload with 5-8 risks or an error string.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_risk_mapper_{company_id or 'company'}"
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    local_files: list[str] = []
    if research_dir.exists():
        try:
            local_files = [
                p.name
                for p in sorted(research_dir.iterdir())
                if p.is_file() and p.name != "index.yaml"
            ][:100]
        except Exception:
            local_files = []

    schema_str = json.dumps(
        SERENA_STRATEGIC_RISK_SCHEMA,
        indent=2,
        ensure_ascii=False,
    )
    company_str = json.dumps(
        company_risk_context(company),
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."
    lessons_block = ""
    if lessons_path and lessons_path.exists():
        lessons_block = f"""\

Serena memo lessons:
`{lessons_path}`

Read these lessons as quality heuristics. Current company evidence and current
public data override stale or contradictory lessons. Strip stale internal
labels, prompt labels, and process/checklist wording before using them.
"""

    prompt = f"""\
You are writing the investment-risk section of a late-stage memo for {company_name}.
Identify the 5-8 risks that actually control the recommendation — not a
generic risk catalog.

Company record (use these facts; do not invent others):
```json
{company_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}
{lessons_block}

What a useful risk looks like:
- Specific to this company, this business model, and this stage.
- Material to valuation, terms, or whether we participate.
- Sharp enough to become one memo sentence.
- Supported by a sourced fact, filing, contract, metric, or explicit gap.
- Paired with a real bull reading and a real bear reading.

What to reject:
- Template risks that would apply to any company in the sector.
- Technically possible issues that would not change the investment call.
- Duplicate risks that restate the same failure mode.
- Risks included only because a document happened to mention them.

Instructions:
- Read local research files with Read/Bash when they exist. Do NOT read
  `data/uploads/` or the Document Library.
- Use company news, funding, filings, industry/comps, and research-folder
  documents as the evidence base.
- Use WebSearch/WebFetch only for current public facts you cannot get locally.
- Separate verified evidence from inference. Tag source_class honestly.
- For each risk, fill bull and bear as competing interpretations of the
  same facts, not as cheerleading and scare language.
- Name the evidence that would change the call.
- Prefer fewer, sharper risks over padding to eight. Five excellent risks
  beat eight generic ones.
- Write like an investment analyst: short, concrete, no filler, no
  "it is important to note", no restating the title in the description.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
- Omit `id`; the application assigns stable risk ids.
"""

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash,WebSearch,WebFetch",
        "--json-schema", json.dumps(SERENA_STRATEGIC_RISK_SCHEMA),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if lessons_path and lessons_path.exists():
        cmd.extend(["--add-dir", str(lessons_path.parent)])

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Mapping strategic risks with Claude",
            company_id=company_id,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label="serena strategic risk mapper",
        silence_timeout_sec=silence_timeout_sec,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"

    parsed = _parse_json_tolerant(final_text.strip())
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    risks = parsed.get("risks")
    if not isinstance(risks, list) or not risks:
        return None, "claude output missing risks"
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed, None


def run_serena_risk_refine(
    *,
    company: dict,
    risk: dict,
    framing: str,
    analyst_note: str = "",
    research_dir: Path,
    progress=None,
    timeout_sec: int = 600,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Regenerate one strategic risk through an analyst-chosen framing."""
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    from .risk_workbench import FRAMINGS, apply_framing, company_risk_context

    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    seeded = apply_framing(dict(risk), framing, analyst_note)
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_risk_refine_{company_id or 'company'}"
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    schema_str = json.dumps(SERENA_RISK_REFINE_SCHEMA, indent=2, ensure_ascii=False)
    prompt = f"""\
You are refining ONE investment risk for {company_name}. Do not rewrite
the rest of the risk map.

Analyst framing: {seeded.get("framing") or framing}
Allowed framings: {", ".join(FRAMINGS)}
Analyst note: {analyst_note or "(none)"}

Current risk:
```json
{json.dumps(seeded, indent=2, ensure_ascii=False, default=str)}
```

Company context:
```json
{json.dumps(company_risk_context(company), indent=2, ensure_ascii=False, default=str)}
```

Serena research folder: `{research_dir}`

Instructions:
- Keep the same investment issue unless the analyst note clearly redirects it.
- Develop the analysis through the chosen framing.
- Keep competing bull and bear readings visible.
- Cite supporting, contradicting, missing, and decision-changing evidence.
- Write like an investment analyst. No filler. No generic sector language.
- Use Read/Bash on local research files. Do not read `data/uploads/`.
- Use WebSearch/WebFetch only for missing public facts.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
- Omit `id`.
"""
    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash,WebSearch,WebFetch",
        "--json-schema", json.dumps(SERENA_RISK_REFINE_SCHEMA),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Refining one strategic risk with Claude",
            company_id=company_id,
            risk_id=risk.get("id"),
        )
    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"
    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()
    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label="serena risk refine",
        silence_timeout_sec=silence_timeout_sec,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"
    parsed = _parse_json_tolerant(final_text.strip())
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    parsed["id"] = risk.get("id")
    parsed["framing"] = seeded.get("framing")
    parsed["edited_by_human"] = True
    if analyst_note:
        parsed["analyst_note"] = analyst_note
    return parsed, None


def run_serena_thesis_spine_builder(
    *,
    company: dict,
    artifacts: dict,
    research_dir: Path,
    lessons_path: Path | None = None,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Run Serena's thesis spine builder through Claude Code.

    The caller owns lifecycle and persistence. This helper returns a parsed
    artifact-shaped payload or an error string.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_thesis_spine_{company_id or 'company'}"
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    local_files: list[str] = []
    if research_dir.exists():
        try:
            local_files = [
                p.name
                for p in sorted(research_dir.iterdir())
                if p.is_file() and p.name != "index.yaml"
            ][:100]
        except Exception:
            local_files = []

    analysis_context = {
        "strategic_risks": artifacts.get("strategic_risks"),
        "risk_priorities": artifacts.get("risk_priorities"),
        "ordered_strategic_risks": artifacts.get("ordered_strategic_risks"),
        "research_tasks": artifacts.get("research_tasks"),
        "chart_specs": artifacts.get("chart_specs"),
        "benchmark_dashboard": artifacts.get("benchmark_dashboard"),
    }
    schema_str = json.dumps(
        SERENA_THESIS_SPINE_SCHEMA,
        indent=2,
        ensure_ascii=False,
    )
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    context_str = json.dumps(
        analysis_context,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."
    lessons_block = ""
    if lessons_path and lessons_path.exists():
        lessons_block = f"""\

Serena memo lessons:
`{lessons_path}`

Read these lessons as quality heuristics. Current company evidence, current
public data, and current Memo Studio artifacts override stale or contradictory
lessons. Strip stale internal labels, prompt labels, and process/checklist
wording before using them.
"""

    prompt = f"""\
You are Serena's Thesis Spine Builder for a BSH investment memo.
Convert the current Memo Studio analysis into the memo's core investment
spine for {company_name}.

Company:
```json
{company_str}
```

Current Memo Studio analysis:
```json
{context_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}
{lessons_block}

Instructions:
- Use the current strategic risks, risk priorities, selected research-task
  results, chart specs, and benchmark context above.
- Treat `ordered_strategic_risks` and `risk_priorities` as the analyst's
  ranking. Lead with rank 1. Skip dismissed risks. Honor any analyst
  framing or note on a risk.
- Build 3-5 investment highlights, 3-5 investment risks, direct
  recommendation logic, the top risk and valuation sensitivities for defending
  the investment recommendation, bull-case drivers, and downside sensitivities.
- Write every highlight and risk as final-memo raw material: concise,
  judgment-led, source-backed, and free of process language. Convert research
  task answers into conclusions instead of copying task labels or confidence
  scaffolding.
- Investment risks must identify what can change BSH's recommendation, not
  generic operating risks. Each risk detail must carry the specific data,
  contradiction, or missing proof that makes the risk matter.
- recommendation_logic must be usable as the conclusion spine: conviction,
  valuation sensitivities, failure modes, and concrete downside impact. Write it
  as advocacy for the investment case, not as a passive diligence checklist.
- Top sensitivities are not questions or conditions. For each sensitivity,
  state the measurable variable, the support evidence, and the downside impact
  if the fact pattern weakens. Use risk and valuation language, not
  company/sponsor capability questions or passive availability framing.
- Do not produce stop/revisit headings, pass triggers, investment-condition
  lists, protected-trait thesis-fit exceptions, or internal BSH mandate
  preference language. If founder background is relevant, tie it only to
  sourced operating history, domain expertise, technical authorship, or
  company-building record.
- Treat incomplete research-task results, partial chart specs, and nullable
  benchmark metrics as evidence gaps, not as facts.
- Source_trace values must name artifact/source categories actually used,
  such as strategic_risks, research_tasks, chart_specs, benchmark_dashboard,
  Serena research folder files, public filings, transcripts, or web sources.
- Use the Serena research folder above for local company documents. Do NOT
  read from `data/uploads/` or the Document Library.
- If local research files exist, inspect relevant files with Read/Bash.
- Use WebSearch/WebFetch when public filings, transcripts, market data, or
  current public evidence are needed.
- Separate verified evidence from inference. Do not invent facts.
- Mark needs_stronger_evidence true whenever a claim is not yet independently
  supported enough for a final memo.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
- Omit ids; the application assigns stable ids.
"""

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash,WebSearch,WebFetch",
        "--json-schema", json.dumps(SERENA_THESIS_SPINE_SCHEMA),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
    if lessons_path and lessons_path.exists():
        cmd.extend(["--add-dir", str(lessons_path.parent)])

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Building thesis spine with Claude",
            company_id=company_id,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label="serena thesis spine builder",
        silence_timeout_sec=silence_timeout_sec,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"

    parsed = _parse_json_tolerant(final_text.strip())
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    highlights = parsed.get("investment_highlights")
    memo_risks = parsed.get("investment_risks")
    sensitivities = parsed.get("risk_valuation_sensitivities")
    if not isinstance(highlights, list) or not highlights:
        return None, "claude output missing investment_highlights"
    if not isinstance(memo_risks, list) or not memo_risks:
        return None, "claude output missing investment_risks"
    if not isinstance(sensitivities, list) or not sensitivities:
        return None, "claude output missing risk_valuation_sensitivities"
    if not str(parsed.get("recommendation_logic") or "").strip():
        return None, "claude output missing recommendation_logic"
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed, None


def run_serena_private_benchmark_dashboard(
    *,
    company: dict,
    artifacts: dict,
    research_dir: Path,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
) -> tuple[dict | None, str | None]:
    """Run Serena's private benchmark dashboard through Claude Code."""
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_benchmark_{company_id or 'company'}"
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    local_files: list[str] = []
    if research_dir.exists():
        try:
            local_files = [
                p.name
                for p in sorted(research_dir.iterdir())
                if p.is_file() and p.name != "index.yaml"
            ][:100]
        except Exception:
            local_files = []

    analysis_context = {
        "strategic_risks": artifacts.get("strategic_risks"),
        "risk_priorities": artifacts.get("risk_priorities"),
        "research_tasks": artifacts.get("research_tasks"),
        "thesis_spine": artifacts.get("thesis_spine"),
    }
    schema_str = json.dumps(
        SERENA_BENCHMARK_DASHBOARD_SCHEMA,
        indent=2,
        ensure_ascii=False,
    )
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    context_str = json.dumps(
        analysis_context,
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."

    prompt = f"""\
You are Serena's Private Benchmark Dashboard builder for a late-stage BSH
investment memo. Build a source-backed public comp and metrics view for
{company_name}.

Company:
```json
{company_str}
```

Current Memo Studio analysis:
```json
{context_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}

Instructions:
- Identify mature public comps that actually inform the private
  company, not flattering category labels.
- Use current public filings, earnings transcripts, investor presentations,
  and reliable market-data pages where needed for growth, margin, valuation,
  and sell-side theme context.
- Use the Serena research folder above for local company context. Do NOT read
  from `data/uploads/` or the Document Library.
- If local research files exist, inspect relevant files with Read/Bash.
- Use WebSearch/WebFetch for public comp metrics and recent public evidence.
- Set nullable metric fields to null when source-backed values are not found.
- Source evidence notes must identify titles, URLs or local locators, concise
  excerpts, and source reliability. Do not invent metrics or sources.
- Benchmark evidence limits are source-quality or model-treatment limitations that matter
  before memo use.
- Private-company proof points must translate the benchmark work into private-company
  proof points that would strengthen or weaken valuation support and the
  recommendation.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output JSON only. No prose, no markdown fences.
- Omit ids; the application assigns stable comp ids.
"""

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash,WebSearch,WebFetch",
        "--json-schema", json.dumps(SERENA_BENCHMARK_DASHBOARD_SCHEMA),
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Building benchmark dashboard with Claude",
            company_id=company_id,
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_search_event,
        timeout_sec=timeout_sec,
        timeout_label="serena benchmark dashboard",
        silence_timeout_sec=silence_timeout_sec,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"

    parsed = _parse_json_tolerant(final_text.strip())
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    comps = parsed.get("public_comps")
    if not isinstance(comps, list) or not comps:
        return None, "claude output missing public_comps"
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed, None


def run_serena_memo_grader(
    *,
    company: dict,
    report: dict,
    memo_packet_path: Path | None,
    run_dir: Path | None,
    progress=None,
    timeout_sec: int = 600,
) -> tuple[dict | None, str | None]:
    """Grade a completed Serena memo run and extract reusable lessons."""
    company_name = company.get("name") or company.get("id") or "the company"
    packet_text = ""
    if memo_packet_path and Path(memo_packet_path).exists():
        try:
            packet_text = Path(memo_packet_path).read_text(
                encoding="utf-8",
                errors="replace",
            )[:60000]
        except Exception:
            packet_text = ""
    run_files: list[str] = []
    if run_dir and Path(run_dir).exists():
        try:
            run_files = [
                str(path.relative_to(run_dir))
                for path in sorted(Path(run_dir).rglob("*"))
                if path.is_file()
            ][:200]
        except Exception:
            run_files = []

    system_prompt = (
        "You are Serena's memo grader. Grade the completed late-stage BSH "
        "investment memo for reusable final-prose quality lessons. Be direct, "
        "evidence-aware, and focused on improving future memo runs."
    )
    user_prompt = f"""\
Company:
```json
{json.dumps(company, indent=2, ensure_ascii=False, default=str)}
```

Completed report:
```json
{json.dumps(report, indent=2, ensure_ascii=False, default=str)}
```

Run folder:
`{run_dir or ""}`

Run files:
{chr(10).join(f"- {name}" for name in run_files) or "- No run files listed."}

Approved memo packet excerpt:
```markdown
{packet_text or "(memo_packet.md missing or empty)"}
```

Grade against:
- Investment highlights sharpness.
- Risk sharpness and falsification quality.
- Evidence quality and source provenance.
- Chart/table clarity.
- Opening and ending strength.
- Missing evidence, source-quality limits, unsupported-claim handling, or
  model-treatment gaps that would change valuation support.
- Specific lessons for future Serena memo runs.

Current evidence overrides stale lessons. Do not reward unsupported claims, and
do not preserve internal IC, diligence, prompt, artifact, or process labels as
future generation guidance.
"""
    return run_structured_prompt(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=SERENA_MEMO_GRADER_SCHEMA,
        name="serena_memo_grader",
        timeout_sec=timeout_sec,
        progress=progress,
    )


def run_serena_research_task(
    *,
    company: dict,
    task: dict,
    risk: dict | None,
    research_dir: Path,
    source_manifest: list[dict] | None = None,
    progress=None,
    timeout_sec: int = 900,
    silence_timeout_sec: int = 180,
    cancel_event: threading.Event | None = None,
) -> tuple[dict | None, str | None]:
    """Run one Memo Studio research task through Claude Code.

    The caller owns job lifecycle and persistence. This helper only performs
    the streamed Claude subprocess and returns a parsed task-result payload.
    Claude may read Serena's research folder and may use web tools; the
    Document Library remains outside the allow-list.
    """
    if not is_available():
        return None, (
            "Claude Code (`claude`) not on PATH. Install it with "
            "`npm install -g @anthropic-ai/claude-code` and authenticate."
        )

    company_name = company.get("name") or company.get("id") or "the company"
    company_id = company.get("id") or ""
    research_dir = Path(research_dir)
    work_dir = research_dir if research_dir.exists() else (
        Path("/tmp") / f"bsh_serena_research_{company_id or 'company'}"
    )
    work_dir.mkdir(parents=True, exist_ok=True)

    local_files: list[str] = []
    if research_dir.exists():
        try:
            local_files = [
                p.name
                for p in sorted(research_dir.iterdir())
                if p.is_file() and p.name != "index.yaml"
            ][:80]
        except Exception:
            local_files = []

    schema_str = json.dumps(SERENA_RESEARCH_TASK_SCHEMA, indent=2, ensure_ascii=False)
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    task_str = json.dumps(task, indent=2, ensure_ascii=False, default=str)
    risk_str = json.dumps(risk or {}, indent=2, ensure_ascii=False, default=str)
    source_manifest_str = json.dumps(
        source_manifest or [],
        indent=2,
        ensure_ascii=False,
        default=str,
    )
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."

    prompt = f"""\
You are running one selected evidence review for Serena's Memo Studio before
an investment memo is drafted. Be factual, skeptical, and source-aware.

Company:
```json
{company_str}
```

Selected strategic risk:
```json
{risk_str}
```

Evidence review task:
```json
{task_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}

Selected source manifest:
```json
{source_manifest_str}
```

Instructions:
- Use only the Serena research folder above for local company documents. Do
  NOT read from `data/uploads/` or the Document Library.
- If the selected source manifest is non-empty, inspect only those selected
  source files for local evidence. Use web tools only when the task needs
  public evidence beyond the selected local files.
- If local research files are relevant, use Read/Bash to inspect them.
- Use WebSearch/WebFetch when public filings, transcripts, market data, or
  current public evidence are needed.
- Separate verified evidence from inference. Do not invent source facts.
- Preserve useful numbers, dates, names, and source titles.
- If evidence is thin, state the limitation and list the next evidence targets.
- Evidence entries must include file_id, filename, locator, a short evidence
  excerpt or faithful paraphrase, and confidence when a local selected source
  supports them. Use null file_id / filename only for web or source-category
  evidence.

OUTPUT REQUIREMENTS:
- Respond with ONE JSON object that conforms to this schema:

```json
{schema_str}
```

- Output the JSON object ONLY. No prose, no commentary, no markdown fences.
- The first character of your response is `{{` and the last is `}}`.
"""

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,Bash,WebSearch,WebFetch",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]

    if progress:
        progress.emit(
            "stage",
            stage="claude_starting",
            message="Running selected evidence review with Claude",
            task_id=task.get("id"),
            risk_id=task.get("risk_id"),
        )

    stderr_log: list[str] = []
    try:
        proc = _popen_claude(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    ).start()

    state: dict[str, Any] = {}
    final_text, stream_error = _consume_stream_json_process(
        proc,
        stderr_log=stderr_log,
        progress=progress,
        state=state,
        event_handler=_process_event,
        timeout_sec=timeout_sec,
        timeout_label="serena research task",
        silence_timeout_sec=silence_timeout_sec,
        cancel_event=cancel_event,
    )
    if stream_error:
        return None, stream_error
    if not final_text:
        return None, "claude returned empty result"

    parsed = _parse_json_tolerant(final_text.strip())
    if parsed is None and "```" in final_text:
        fenced = re.findall(r"```(?:json)?\s*\n?(.*?)```", final_text, re.DOTALL)
        if fenced:
            parsed = _parse_json_tolerant(max(fenced, key=len).strip())
    if parsed is None:
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        return None, f"claude output didn't parse as JSON: {final_text[:300]}"
    summary = str(parsed.get("answer") or parsed.get("result_summary") or "").strip()
    if not summary:
        return None, "claude output missing answer"
    parsed["generated_at"] = datetime.now(timezone.utc).isoformat()
    return parsed, None


# ---- Console: hydrate / ask / summary -----------------------------------
#
# The Console feature (see docs/console-feature.md) is the first subprocess
# flow in this codebase that needs Claude session persistence — hydrate
# uses ``--session-id``, ask uses ``--resume``. The helpers below build
# the right command lines, stream events into a ProgressLog, and surface a
# cancellation hook (a ``threading.Event``) plus a watchdog (event-silence
# timeout + wall-clock cap) that triggers SIGINT — the same signal a human
# Ctrl-C in ``claude -p`` would send.


def _preview_console_tool_input(name: str, inp: dict) -> str:
    if name == "Read":
        s = inp.get("file_path") or ""
        if inp.get("pages"):
            s += f"  (pages={inp.get('pages')})"
        return s
    if name == "Bash":
        return inp.get("command") or ""
    if name in ("WebSearch",):
        return inp.get("query") or ""
    if name == "WebFetch":
        return inp.get("url") or ""
    try:
        return json.dumps(inp, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(inp)


def _process_console_event(event: dict, progress, state: dict) -> None:
    """Translate stream-json events from a Console hydrate/ask/summary run
    into ``progress.emit("claude_action", ...)`` calls.

    Captures assistant text into ``state["assistant_text_parts"]`` so the
    caller can reassemble the final reply without re-parsing the result
    event (which omits inline text blocks beyond the canonical `result`
    field).
    """
    etype = event.get("type")
    if etype == "system" and event.get("subtype") == "init":
        progress.emit(
            "claude_action",
            action="init",
            session=event.get("session_id"),
            model=event.get("model"),
            cwd=event.get("cwd"),
            tools=event.get("tools") or [],
        )
        return
    if etype == "assistant":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text = (block.get("text") or "").strip()
                if text:
                    progress.emit("claude_action", action="thinking", text=text[:600])
                    state.setdefault("assistant_text_parts", []).append(text)
            elif btype == "tool_use":
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                state["last_tool"] = {"id": block.get("id"), "name": name}
                preview = _preview_console_tool_input(name, inp)
                progress.emit(
                    "claude_action", action="tool_use",
                    tool=name, preview=preview[:500],
                )
        return
    if etype == "user":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_result":
                tool = state.get("last_tool", {}).get("name", "?")
                content = block.get("content")
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            parts.append(c.get("text") or "")
                    content_str = "\n".join(parts)
                else:
                    content_str = content if isinstance(content, str) else ""
                progress.emit(
                    "claude_action", action="tool_result",
                    tool=tool, is_error=bool(block.get("is_error")),
                    preview=(content_str or "")[:200],
                )
        return
    if etype == "result":
        progress.emit(
            "claude_action", action="result",
            subtype=event.get("subtype"),
            cost_usd=event.get("total_cost_usd"),
            duration_ms=event.get("duration_ms"),
            usage=event.get("usage"),
        )
        return


# Watchdog constants — duplicated as defaults so callers (tests) can
# override per call. The authoritative copies live in console_store.
_CONSOLE_EVENT_SILENCE_DEFAULT_S = 90.0
_CONSOLE_KILL_GRACE_DEFAULT_S = 30.0
_CONSOLE_WALL_CLOCK_DEFAULT_S = 600.0


class _ConsoleRunHandle:
    """Internal bookkeeping for a streaming Console subprocess. Bundles the
    Popen, the reader thread, the queue of decoded events, and the final
    result event when it arrives.
    """

    def __init__(self, proc: subprocess.Popen):
        import queue as _queue

        self.proc = proc
        self.events: _queue.Queue = _queue.Queue()
        self.result_event: dict | None = None
        self.stderr_log: list[str] = []
        self.reader: threading.Thread | None = None


def _reader_thread(handle: _ConsoleRunHandle) -> None:
    """Drain stdout into a queue. One queued item per parsed JSON line.

    The terminal item is ``None``, signalling EOF.
    """
    stdout = handle.proc.stdout
    if stdout is None:
        handle.events.put(None)
        return
    try:
        for line in stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            handle.events.put(event)
    finally:
        handle.events.put(None)


def _spawn_console(cmd: list[str], cwd: Path | None) -> _ConsoleRunHandle:
    # start_new_session so cancellation can reap the whole process group —
    # console runs use the Bash tool, and killing only the direct PID left
    # its children running.
    proc = _popen_claude(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    handle = _ConsoleRunHandle(proc)
    handle.reader = threading.Thread(
        target=_reader_thread, args=(handle,), daemon=True
    )
    handle.reader.start()
    threading.Thread(
        target=_drain_stderr, args=(proc, handle.stderr_log), daemon=True
    ).start()
    return handle


def _terminate_console(
    handle: _ConsoleRunHandle, *, grace_s: float
) -> str:
    """SIGINT → wait → group SIGKILL. Returns the signal name that succeeded.

    SIGINT goes to the process group so the CLI's own children (Bash tool
    subprocesses) get the interrupt too; the escalation kills the whole
    group rather than just the direct child.
    """
    import signal as _signal

    if handle.proc.poll() is not None:
        return "exited"
    pid = getattr(handle.proc, "pid", None)
    interrupted = False
    if pid is not None:
        try:
            os.killpg(pid, _signal.SIGINT)
            interrupted = True
        except (ProcessLookupError, PermissionError, OSError):
            pass
    if not interrupted:
        try:
            handle.proc.send_signal(_signal.SIGINT)
        except ProcessLookupError:
            return "exited"
    try:
        handle.proc.wait(timeout=grace_s)
        return "SIGINT"
    except subprocess.TimeoutExpired:
        pass
    if pid is not None:
        try:
            os.killpg(pid, _signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        handle.proc.kill()
    except ProcessLookupError:
        return "exited"
    try:
        handle.proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        pass
    return "SIGKILL"


def _consume_stream(
    handle: _ConsoleRunHandle,
    *,
    progress,
    state: dict,
    cancel_event: threading.Event | None,
    event_silence_timeout_s: float,
    wall_clock_cap_s: float,
    grace_kill_s: float,
) -> dict:
    """Drain events from the reader thread, dispatch to ``progress``, and
    enforce the watchdog. Returns a small dict::

        {ok: bool, subtype: str, usage: dict|None, cost_usd: float|None,
         duration_ms: int|None, error?: str, interrupt_reason?: str}

    ``subtype`` mirrors the result-event subtype (``success`` or
    ``error``), or is set to ``error`` with an ``interrupt_reason`` when
    the watchdog or the cancel event interrupted the run.
    """
    import queue as _queue

    start = time.monotonic()
    last_event_at = start
    interrupt_reason: str | None = None

    while True:
        # Check the cancel event without blocking.
        if cancel_event is not None and cancel_event.is_set():
            interrupt_reason = "user_cancelled"
            break
        # Watchdog: event silence.
        if (time.monotonic() - last_event_at) > event_silence_timeout_s:
            interrupt_reason = "event_silence_timeout"
            break
        # Watchdog: wall-clock cap.
        if (time.monotonic() - start) > wall_clock_cap_s:
            interrupt_reason = "wall_clock_cap"
            break
        try:
            event = handle.events.get(timeout=0.25)
        except _queue.Empty:
            # Detect a dead subprocess: if it has exited and the reader
            # thread is done, the queue will have already received its
            # terminal None. If it exited but we haven't drained yet, the
            # next iteration will pick it up.
            if handle.proc.poll() is not None and not handle.reader.is_alive():
                # Drain any remaining events synchronously.
                while not handle.events.empty():
                    event = handle.events.get_nowait()
                    if event is None:
                        break
                    last_event_at = time.monotonic()
                    try:
                        _process_console_event(event, progress, state)
                    except Exception:  # noqa: BLE001
                        logger.exception("console event handling failed")
                    if event.get("type") == "result":
                        handle.result_event = event
                break
            continue

        if event is None:
            # Reader EOF — subprocess closed stdout. Wait for it to exit.
            break

        last_event_at = time.monotonic()
        try:
            _process_console_event(event, progress, state)
        except Exception:  # noqa: BLE001
            logger.exception("console event handling failed")
        if event.get("type") == "result":
            handle.result_event = event
            # Stay in the loop briefly to drain any trailing events; the
            # reader will then put a terminal None and we break.

    if interrupt_reason is not None:
        sig = _terminate_console(handle, grace_s=grace_kill_s)
        progress.emit(
            "claude_action",
            action="interrupted",
            reason=interrupt_reason,
            signal=sig,
        )

    # Best-effort: wait for subprocess to actually exit.
    try:
        handle.proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        try:
            handle.proc.kill()
        except ProcessLookupError:
            pass

    result_event = handle.result_event
    if result_event is not None and interrupt_reason is None:
        return {
            "ok": result_event.get("subtype") == "success",
            "subtype": result_event.get("subtype") or "error",
            "usage": result_event.get("usage") or {},
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
        }

    if interrupt_reason is not None:
        return {
            "ok": False,
            "subtype": "error",
            "usage": (result_event or {}).get("usage") or {},
            "cost_usd": (result_event or {}).get("total_cost_usd"),
            "duration_ms": (result_event or {}).get("duration_ms"),
            "error": f"Interrupted ({interrupt_reason})",
            "interrupt_reason": interrupt_reason,
        }

    # No result event AND no explicit interrupt → subprocess died without
    # writing one.
    tail = "".join(handle.stderr_log[-20:]).strip()
    code = handle.proc.returncode
    return {
        "ok": False,
        "subtype": "error",
        "usage": {},
        "cost_usd": None,
        "duration_ms": None,
        "error": (
            f"Claude subprocess exited unexpectedly (code={code})"
            + (f": {tail[:600]}" if tail else "")
        ),
        "interrupt_reason": "subprocess_died",
    }


_CONSOLE_LANGUAGE_NAMES = {
    "en": "English",
    "zh": "Simplified Chinese (简体中文)",
}


def _console_language_directive(language: str | None) -> str:
    """Return the system-prompt block that pins all output to one
    language for the duration of the Console session. Empty when the
    caller doesn't specify a language (legacy behavior — Claude mirrors
    the user's input language per the skill prompt).
    """
    name = _CONSOLE_LANGUAGE_NAMES.get(language or "")
    if not name:
        return ""
    style = (
        f"\nWhen writing in Simplified Chinese, apply this style guide:\n"
        f"{INVESTMENT_RESEARCH_CHINESE_STYLE}\n"
        if language == "zh"
        else ""
    )
    return (
        "\n\n## Output language (session-wide)\n\n"
        f"All replies in this Console session MUST be written in {name}, "
        "for every turn, regardless of what language the user types in. "
        "This directive overrides the bilingual default in the analyst "
        f"persona above.\n{style}"
    )


def _console_skill_text(skill_path: Path, language: str | None = None) -> str:
    """Read the bundled analyst persona and append the session's
    language directive (if any). Passed verbatim to
    ``--append-system-prompt`` on every hydrate / ask invocation.
    """
    try:
        text = skill_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    return text + _console_language_directive(language)


def run_console_hydrate(
    *,
    claude_session_id: str,
    work_dir: Path,
    file_list: list[Path],
    skill_path: Path,
    progress,
    output_language: str | None = None,
    cancel_event: threading.Event | None = None,
    event_silence_timeout_s: float = _CONSOLE_EVENT_SILENCE_DEFAULT_S,
    grace_kill_s: float = _CONSOLE_KILL_GRACE_DEFAULT_S,
    wall_clock_cap_s: float = _CONSOLE_WALL_CLOCK_DEFAULT_S,
) -> dict:
    """One-shot hydration: spawn ``claude -p`` with ``--session-id``, ask it
    to Read every staged document into context, and return a small dict
    with the usage/cost from the result event.
    """
    if not is_available():
        return {"ok": False, "error": "Claude CLI not available"}

    work_dir.mkdir(parents=True, exist_ok=True)

    relative_names = [Path(p).name for p in file_list]
    bulleted = "\n".join(f"- {n}" for n in relative_names) or "(no documents staged)"
    lang_line = ""
    if output_language and output_language in _CONSOLE_LANGUAGE_NAMES:
        lang_line = (
            "All output in this session — starting with the "
            f"acknowledgement below — must be written in "
            f"{_CONSOLE_LANGUAGE_NAMES[output_language]}.\n\n"
        )
        if output_language == "zh":
            lang_line += (
                "When writing in Simplified Chinese, apply this style guide:\n"
                f"{INVESTMENT_RESEARCH_CHINESE_STYLE}\n"
            )
    prompt = (
        "You are entering a Console session for a BSH analyst. The "
        "following documents are staged in your current working "
        "directory:\n\n"
        f"{bulleted}\n\n"
        f"{lang_line}"
        "Use the Read tool on each one to load its contents into your "
        "context. Then reply with EXACTLY a one-line acknowledgement of "
        "the form `Ready. N documents loaded.` (translated as needed) "
        "and nothing else, where N is the count of files you successfully "
        "read. Do not summarize the documents in the reply. Do not "
        "preview them. Just Read each one and acknowledge."
    )

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--session-id", claude_session_id,
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,WebSearch,WebFetch,Bash",
        "--append-system-prompt", _console_skill_text(skill_path, output_language),
    ]

    progress.emit(
        "job_init",
        kind="console_hydrate",
        title="Hydrating console",
        file_count=len(file_list),
    )
    progress.emit("stage", stage="starting", message="Starting hydration")

    try:
        handle = _spawn_console(cmd, cwd=work_dir)
    except FileNotFoundError as exc:
        progress.emit("error", error=f"Failed to launch claude: {exc}")
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    state: dict = {}
    outcome = _consume_stream(
        handle,
        progress=progress, state=state,
        cancel_event=cancel_event,
        event_silence_timeout_s=event_silence_timeout_s,
        wall_clock_cap_s=wall_clock_cap_s,
        grace_kill_s=grace_kill_s,
    )

    text = "".join(state.get("assistant_text_parts") or []).strip()
    outcome["text"] = text
    if outcome.get("ok"):
        progress.emit("done", text=text, usage=outcome.get("usage"),
                      cost_usd=outcome.get("cost_usd"))
    else:
        progress.emit("error", error=outcome.get("error") or "Hydration failed",
                      interrupt_reason=outcome.get("interrupt_reason"))
    return outcome


def run_console_ask(
    *,
    claude_session_id: str,
    work_dir: Path,
    user_prompt: str,
    skill_path: Path,
    progress,
    attachments: list[str] | None = None,
    output_language: str | None = None,
    cancel_event: threading.Event | None = None,
    event_silence_timeout_s: float = _CONSOLE_EVENT_SILENCE_DEFAULT_S,
    grace_kill_s: float = _CONSOLE_KILL_GRACE_DEFAULT_S,
    wall_clock_cap_s: float = _CONSOLE_WALL_CLOCK_DEFAULT_S,
) -> dict:
    """One user turn: spawn ``claude -p --resume`` and stream the response
    through ``progress``. Returns the same shape as ``run_console_hydrate``
    plus ``text`` (the assistant's final reply, reassembled from text
    blocks).

    ``attachments`` is a list of relative filenames inside
    ``work_dir/attachments/`` to append to the prompt as a Read hint.
    """
    if not is_available():
        return {"ok": False, "error": "Claude CLI not available", "text": ""}

    work_dir.mkdir(parents=True, exist_ok=True)

    final_prompt = user_prompt.rstrip()
    if attachments:
        names = ", ".join(f"`attachments/{n}`" for n in attachments)
        final_prompt += (
            "\n\n(Attached: " + names + ". Use the Read tool to view "
            "each one.)"
        )

    cmd = [
        claude_path() or "claude",
        "-p", final_prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--resume", claude_session_id,
        "--add-dir", str(work_dir),
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--allowedTools", "Read,WebSearch,WebFetch,Bash",
        "--append-system-prompt", _console_skill_text(skill_path, output_language),
    ]

    progress.emit(
        "job_init",
        kind="console_ask",
        title=f"Q&A: {user_prompt[:40]}",
    )
    progress.emit("stage", stage="starting", message="Asking Claude")

    try:
        handle = _spawn_console(cmd, cwd=work_dir)
    except FileNotFoundError as exc:
        progress.emit("error", error=f"Failed to launch claude: {exc}")
        return {"ok": False, "error": f"Failed to launch claude: {exc}",
                "text": ""}

    state: dict = {}
    outcome = _consume_stream(
        handle,
        progress=progress, state=state,
        cancel_event=cancel_event,
        event_silence_timeout_s=event_silence_timeout_s,
        wall_clock_cap_s=wall_clock_cap_s,
        grace_kill_s=grace_kill_s,
    )

    text = "".join(state.get("assistant_text_parts") or []).strip()
    outcome["text"] = text
    if outcome.get("ok"):
        progress.emit("done", text=text, usage=outcome.get("usage"),
                      cost_usd=outcome.get("cost_usd"))
    else:
        progress.emit("error", error=outcome.get("error") or "Ask failed",
                      interrupt_reason=outcome.get("interrupt_reason"))
    return outcome


def run_console_title(
    *,
    user_prompt: str,
    assistant_text: str,
    timeout_sec: int = 30,
) -> str | None:
    """Generate a 3-6 word title for a Console session given its first turn.

    Tiny single-shot Claude call (~$0.001). Returns the title or None on
    any failure — the caller falls back to the timestamp title.
    """
    if not is_available():
        return None
    prompt = (
        "Below is the first Q&A turn from a research analyst's Console "
        "session. Reply with a 3-6 word title for the session — concise, "
        "specific to the topic. No quotes, no trailing punctuation, no "
        '"Re:" prefix. Reply with just the title text and nothing else.\n\n'
        f"USER: {user_prompt[:1000]}\n\nASSISTANT: {assistant_text[:1500]}"
    )
    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
        "--allowedTools", "",
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_sec,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if proc.returncode != 0:
        return None
    try:
        envelope = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    text = (envelope.get("result") or "").strip()
    # Strip surrounding quotes / trailing punctuation if Claude defied the
    # instruction.
    text = text.strip().strip('"').strip("'").rstrip(".!?")
    if not text or len(text) > 80:
        return None
    return text


def run_console_summary(
    *,
    turns: list[dict],
    progress,
    timeout_sec: int = 180,
) -> dict:
    """Generate a 3-bullet retrospective summary for an archived session.

    Single-shot, no session persistence — the prompt embeds the full
    ``turns.jsonl`` as a quoted block.
    """
    if not is_available():
        return {"error": "Claude CLI not available"}

    transcript_lines: list[str] = []
    for t in turns:
        role = t.get("role")
        text = (t.get("text") or "").strip()
        if not text:
            continue
        transcript_lines.append(f"[{role.upper()}]\n{text}\n")
    transcript = "\n".join(transcript_lines)[-12000:]  # cap context

    prompt = (
        "Below is the transcript of a Console Q&A session between a BSH "
        "analyst and Claude. Produce a short retrospective summary in "
        "JSON with two fields:\n\n"
        "  - headline: a 3-6 word title for the session (e.g. "
        '"AMI Labs Pitchdeck Q&A").\n'
        "  - bullets: an array of 2-4 one-sentence bullets capturing "
        "the key questions explored and conclusions reached.\n\n"
        "Reply with ONE JSON object and nothing else.\n\n"
        "--- TRANSCRIPT START ---\n"
        f"{transcript}\n"
        "--- TRANSCRIPT END ---"
    )

    cmd = [
        claude_path() or "claude",
        "-p", prompt,
        "--output-format", "json",
        "--permission-mode", "bypassPermissions",
        "--dangerously-skip-permissions",
        "--no-session-persistence",
        "--allowedTools", "Read",
    ]

    progress.emit("job_init", kind="console_summary", title="Summarizing session")
    progress.emit("stage", stage="starting", message="Summarizing")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_sec
        )
    except subprocess.TimeoutExpired:
        progress.emit("error", error=f"Summary timed out after {timeout_sec}s")
        return {"error": f"Summary timed out after {timeout_sec}s"}
    except FileNotFoundError as exc:
        progress.emit("error", error=f"Failed to launch claude: {exc}")
        return {"error": f"Failed to launch claude: {exc}"}

    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-600:]
        msg = f"claude exited {proc.returncode}: {tail}"
        progress.emit("error", error=msg)
        return {"error": msg}

    try:
        envelope = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        progress.emit("error", error=f"Non-JSON envelope: {exc}")
        return {"error": f"Non-JSON envelope: {exc}"}

    final_text = (envelope.get("result") or "").strip()
    parsed = _parse_json_tolerant(final_text)
    if not isinstance(parsed, dict):
        # Try to recover the first {...} block.
        m = _JSON_OBJ_RE.search(final_text)
        if m:
            parsed = _parse_json_tolerant(m.group(0))
    if not isinstance(parsed, dict):
        progress.emit("error", error="Summary output didn't parse as JSON")
        return {"error": "Summary output didn't parse as JSON"}

    headline = (parsed.get("headline") or "").strip() or None
    bullets_raw = parsed.get("bullets") or []
    bullets = [str(b).strip() for b in bullets_raw if str(b).strip()]
    result = {
        "headline": headline,
        "bullets": bullets,
        "cost_usd": envelope.get("total_cost_usd"),
        "usage": envelope.get("usage"),
    }
    progress.emit("done", **result)
    return result
