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

import json
import logging
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chinese_style import INVESTMENT_RESEARCH_CHINESE_STYLE

logger = logging.getLogger(__name__)


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

    if proc.returncode != 0:
        return {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "duration_ms": duration_ms,
            "error": _claude_exit_error(proc.returncode, proc.stderr, proc.stdout),
        }

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "available": True,
            "path": path,
            "version": version,
            "duration_ms": duration_ms,
            "error": "claude returned non-JSON output",
            "stdout_preview": (proc.stdout or "")[:300],
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


def _thread_for_tool_use(name: str, inp: dict, state: dict) -> str | None:
    """If this tool_use should be attributed to a sub-thread (e.g. one of
    the memo skill's parallel analysis passes), return the thread label.

    Driven by `state["thread_map"]` (filename → label). Only writers
    (Write/Edit) get attributed — Reads/Bash/Grep aren't pass-specific.
    Runners that don't set `thread_map` get no threading.
    """
    thread_map = state.get("thread_map")
    if not thread_map:
        return None
    if name not in ("Write", "Edit"):
        return None
    fp = (inp.get("file_path") or "").replace("\\", "/")
    if not fp:
        return None
    leaf = fp.rsplit("/", 1)[-1]
    return thread_map.get(leaf)


def _process_event(event: dict, progress, state: dict) -> None:
    """Translate a stream-json event into our ProgressLog vocabulary.

    `state` is per-job mutable scratch — we use it to track the latest tool
    invocation so we can pair tool_result events back to their tool_use, plus
    which slides we've emitted so we can dedup and detect stage transitions.

    If `state["thread_map"]` is set (filename → pass label), Write/Edit
    events to those files are tagged with `thread=<label>` so the
    JobLogModal can render them as composite/threaded sub-tasks.
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
                    progress.emit(
                        "claude_action", action="thinking", text=text[:600]
                    )
            elif btype == "tool_use":
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                tool_id = block.get("id")
                thread_label = _thread_for_tool_use(name, inp, state)
                state["last_tool"] = {
                    "id": tool_id,
                    "name": name,
                    "thread": thread_label,
                }
                # Track all in-flight tools by id so the user-message
                # handler can re-attach thread labels even when many
                # parallel tool calls are pending at once.
                in_flight = state.setdefault("in_flight", {})
                if tool_id:
                    in_flight[tool_id] = {"name": name, "thread": thread_label}
                if thread_label:
                    threads_started = state.setdefault("threads_started", set())
                    if thread_label not in threads_started:
                        threads_started.add(thread_label)
                        progress.emit(
                            "thread_started",
                            thread=thread_label,
                            title=thread_label,
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
                if thread_label:
                    emit_kwargs["thread"] = thread_label
                progress.emit("claude_action", **emit_kwargs)
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
                thread_label = meta.get("thread")
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
                if thread_label:
                    tr_kwargs["thread"] = thread_label
                progress.emit("claude_action", **tr_kwargs)
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
    staged_deck = work_dir / source_path.name
    if not staged_deck.exists() or staged_deck.stat().st_size != source_path.stat().st_size:
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
        proc = subprocess.Popen(
            cmd,
            cwd=str(work_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return {"error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {"page_count": page_count}
    final_text: str | None = None
    result_event: dict | None = None
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
                final_text = event.get("result")
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"error": f"Claude timed out after {timeout_sec}s"}

    if proc.returncode and proc.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return {
            "error": (
                f"claude exited {proc.returncode}"
                + (f": {tail[:600]}" if tail else "")
            )
        }

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
) -> tuple[str | None, str | None]:
    """Consume Claude stream-json without blocking forever on stdout.

    Returns ``(final_text, error)``. ``final_text`` prefers a captured
    StructuredOutput payload when present, matching the previous parser
    behavior.
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

    if interrupted is not None:
        _terminate_process_group(proc, grace_s=5.0)
        if progress is not None:
            progress.emit(
                "claude_action",
                action="interrupted",
                reason=interrupted,
            )
        return None, interrupted

    try:
        proc.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc, grace_s=5.0)
        return None, f"{timeout_label} did not exit cleanly"

    if proc.returncode and proc.returncode != 0:
        return None, _claude_exit_error(
            proc.returncode, "".join(stderr_log[-20:])
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
        proc_stream = subprocess.Popen(
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
        proc = subprocess.Popen(
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
        proc = subprocess.Popen(
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
        proc = subprocess.Popen(
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


# Maps the analysis artifacts produced by Serena's memo skill to the
# human-readable "pass" label the JobLogModal renders. When Claude writes
# any of these files, _process_event tags the event with `thread=<label>`
# so the AI-Task modal can group the parallel passes as their own
# collapsible sections instead of one flat firehose.
_MEMO_ANALYSIS_PASSES: dict[str, str] = {
    "pressure_tests.md": "Arithmetic / pressure tests",
    "time_base_checks.md": "Time-base integrity",
    "growth_bridge.md": "Growth bridge",
    "disconfirming_evidence.md": "Alternative explanations",
    "adoption_ladder.md": "Adoption ladder",
    "core_franchise_resilience.md": "Core franchise resilience",
    "claim_register.md": "Claim register",
    "distribution_notes.md": "Distribution / GTM",
    "replacement_vs_coexistence.md": "Replacement vs coexistence",
    "scenario_swim_lanes.md": "Scenario swim lanes",
    "validation_log.md": "Validation log",
    "gating_questions.md": "Decision questions",
}

HUMAN_EXEC_MEMO_VOICE_CONTRACT = """\
## Human Executive Memo Voice Contract

This is a final-writing override. It supersedes any older skill instruction
that asks for inline source markers, bracketed source traces, scaffolded
taxonomy labels, or prompt-visible headings in final prose. Preserve the full
diligence standard from the skill, but the finished English memo is an
exec-ready sell-side investment memo for BSH partners, not a generated
research report and not a buyer-side diligence memo.

Final memo prose must:
- write like a senior investor making an allocation case under uncertainty;
- convert evidence into judgment;
- avoid process language, methodology narration, task labels, and validation
  scaffolding in the body;
- avoid meta-commentary about "the memo", "the analysis", "the framework",
  "this section", or what the writer is doing;
- state uncertainty directly instead of explaining why certainty is
  unavailable;
- avoid template-visible language, symmetrical model phrasing, and repetitive
  paragraph openings;
- keep analytical artifacts private unless a fact or conclusion belongs in
  the memo;
- use source-class language in Sections I-V, with detailed source IDs only in
  a separate Sources, Source Classes, and Fact Reference Index;
- convert disclosure gaps into confirmation items, scenario ranges, Fermi
  estimates, or closing diligence.

Sell-side investment memo posture:
- Do not write as if BSH is negotiating control terms in a private-equity
  process. BSH is assessing whether to take available allocation in a scarce
  financing.
- Do not default to "small/minimum" allocation because revenue, ARR, gross
  margin, lead investor, or detailed SAFE side terms are undisclosed. For
  early-growth or Series A/A2 deep-tech rounds, those gaps are normal unless
  the supplied source package says otherwise. Calibrate expectations to the
  stage, round, sponsor channel, scarcity of allocation, and strength of the
  syndicate.
- If the round is oversubscribed, has top-tier participation, or the available
  economics are attractive versus what others are receiving, reflect that as
  positive evidence for allocation size and urgency. Do not recommend the
  minimum allocation unless the facts show BSH's conviction is genuinely low.
- Treat SPV/SAFE economics as deal mechanics to explain plainly, not as a
  thesis-breaking risk by default. Use "confirm economics before funding" only
  when the actual documents are ambiguous.
- Decision questions should be few and deal-relevant. They should not be a
  generic late-stage checklist. Avoid questions that would also disqualify
  normal early-growth financings that top firms routinely complete.

Final memo body and operating tables must not contain:
- bracketed source tokens or file references such as `[S1]`, `[WV]`,
  `[WV SPV memo]`, `[companies.yaml]`, `[internal]`, or similar;
- internal artifact names such as `companies.yaml`, `memo_packet`,
  `source_trace`, `claim_register`, `research_tasks`, `reviewer_prompts`, or
  analysis file names;
- scaffold headings or labels such as `Critical Reality Check`,
  `present-state`, `upside-state`, `upside-only`,
  `Strongest independent support`, `Strongest disconfirming facts`, or
  `Still unproven`;
- cute or fuzzy finance phrasing such as `soft instrument`, `hard IP wall`,
  `moat narrows`, `no-rights SAFE`, `where nothing else works`, or
  `least-proven part of the story`;
- buyer-side, bank/debt, or control-investor process language. Use
  investment-case, allocation, confirmation, decision, and stop/revisit
  vocabulary instead of process labels, small-check reflexes, or
  control-rights checklist phrasing;
- em dash bridging in English body prose or operating tables;
- meta-language about `the memo`, `the analysis`, `the framework`, or
  `this section`.

Memo spine requirement:
- core_bet: what has to be true for BSH to make money;
- entry_tension: what the valuation or instrument already assumes;
- current_proof: what is proven today by source class;
- unproven_but_modelable: what is missing but can be modeled conservatively;
- stop_or_revisit: what would make BSH decline or revisit later;
- action: recommended allocation range, conviction posture, confirmation
  items, and next diligence.

The opening, Investment View, risk section, scenario section, and final
Investment Decision / Closing View must use the same spine. The first two
body paragraphs must state company, transaction, valuation / entry terms,
central price/proof tension, and recommendation posture. The substantive
ending must state what BSH should do, target allocation posture, confirmation
items, stop/revisit conditions, and next diligence actions before any sources
or disclosures.

Positive examples for early-commercial infrastructure deals:
- "ZaiNar is a scarce technical asset in network-side positioning; the A2
  prices real IP, technical depth, and early commercial pull before the full
  revenue curve is visible."
- "Company-reported contract and MOU figures support commercial momentum; the
  base case should credit the binding portion and leave upside for MOU and
  carrier conversion."
- "Pipeline is not contracted revenue. Use a 5-15% conversion range for
  scenario construction until named site-level commitments are available."
- "An SPV interest depends on the SAFE converting as described; explain the
  economics and document-confirmation points without turning them into a
  control-rights checklist."
- "If the round is meaningfully oversubscribed and BSH has differentiated
  access, the allocation recommendation should reflect scarcity and upside,
  not mechanically default to a minimum check."

Banned phrase / rewrite guidance:

| Avoid | Prefer |
|---|---|
| The investment case is not that... | This is not a conventional SaaS case. |
| The memo therefore... | Remove, or rewrite as direct judgment. |
| The analysis suggests... | State the conclusion directly. |
| Due to lack of data... | Revenue is not disclosed. |
| Proving the case | investment case, base case, conviction, support |
| Sizing the position | allocation, position size, commitment |
| Sharp open questions | Top 3 Decision Questions or Top 3 Gating Questions |
| Missing proof | What Still Needs Confirmation |
| Recommendation labels | Proceed / Proceed if confirmed / Hold pending confirmation / Pass |
| Decision discipline | stop/revisit conditions |
| implies false precision | would be misleading to forecast precisely |
| not treated as ARR | not revenue-recognized |
| commercial momentum is material, but... | The pipeline is large but not contractually binding. |
| The principal risk is that... | Key risk centers on... |
| soft instrument | SPV interest whose economics depend on SAFE conversion. |
| hard IP wall | patent estate and technical approach that still need claim-scope review. |
| moat narrows | upside shifts from product margin to patent leverage and deployment relationships. |

Before DOCX generation, run a final prose QA pass. Remove banned phrases,
meta language, methodology leakage, over-explained risks, template-visible
structure, and unnatural model voice. The output should sound like an
experienced investor making a call under uncertainty.
"""


def _load_skill_text() -> str:
    if not _SKILL_PATH.exists():
        raise RuntimeError(f"Skill file missing: {_SKILL_PATH}")
    return _SKILL_PATH.read_text(encoding="utf-8")


_HORMUZ_SKILL_PATH = (
    Path(__file__).resolve().parent / "skills" / "bsh_hormuz_appendix.md"
)


def _load_hormuz_skill_text() -> str:
    if not _HORMUZ_SKILL_PATH.exists():
        raise RuntimeError(f"Skill file missing: {_HORMUZ_SKILL_PATH}")
    return _HORMUZ_SKILL_PATH.read_text(encoding="utf-8")


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
        inter-dependencies and should run via parallel tool calls in a
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
## Scope-warning override from prep

The pre-run scope check produced a **non-fatal warning**:

- classification: `{scope_check.get('classification')}`
- reason: {scope_check.get('reason') or '(no reason recorded)'}

{warning_lines if warning_lines else "- No additional warnings recorded."}

Proceed with the memo anyway. Do **not** stop or decline solely because the
company is early-stage or indeterminate. Instead, make the stage mismatch,
thin late-stage diligence base, missing unit economics, and fit with the
late-stage/pre-IPO memo framework explicit caveats in the memo. Preserve the
late-stage analytical standard where possible, but label assumptions and
confidence limits clearly.

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
Investment Highlights, Investment Risks, Top 3 Decision Questions,
infographic choices, selected operator narrative choices, source-brief
warnings, intro stance, risk-section posture, and conclusion posture should
come from this packet when they are supported by evidence. Treat selected
openings, risk framings, and endings as operator HIL guidance, not copy-paste
text. Do not convert draft status, source-brief no-go claims, missing
evidence, unresolved readiness blockers, or reviewer prompts into factual
memo claims.

"""

    lessons_block = ""
    if lessons_path and lessons_path.exists():
        lessons_block = f"""\
## Serena memo lessons

Serena has stored lessons from prior completed memo runs for this company:

  `{lessons_path}`

Read this file before drafting. Use these lessons as memo-quality heuristics,
not as facts. Current company evidence, current public data, and the approved
analysis packet override stale or contradictory lessons.

"""

    return f"""\
You are running the **bsh-investment-memo-latestage-v1** skill (Serena's
script) for one real run. The skill text is included verbatim below.
**Follow it exactly.** The only deviations from the text are the non-fatal
scope-warning override, the server-owned DOCX rendering handoff, and the
parallel-passes hint below.

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
    "round": "Round / valuation context",
    "bsh_allocation": "Target allocation / position size if known"
  }},
  "run": {{"run_id": "{run_id}", "as_of": "YYYY-MM-DD"}},
  "sections": [
    {{
      "id": "executive_summary",
      "blocks": [
        {{"type": "heading", "level": 2, "text": {{"en": "Investment Opportunity", "zh": "投资机会"}}}},
        {{"type": "paragraph", "text": {{"en": "Body prose.", "zh": "正文。"}}}},
        {{"type": "bullets", "items": [{{"en": "Bullet.", "zh": "要点。"}}]}},
        {{"type": "callout", "tone": "warning", "title": {{"en": "Decision Gate", "zh": "决策关口"}}, "items": []}},
        {{"type": "table", "title": {{"en": "Key Metrics Snapshot", "zh": "关键指标快照"}}, "headers": [], "rows": []}}
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
and `table` blocks. Tables should carry headers and rows as arrays; callouts
should carry concise title/body/items. The same package drives both EN and ZH
output, so every final user-facing string in blocks, table cells, and source
treatment must be bilingual (`{{"en": "...", "zh": "..."}}`) unless it is a
proper noun, date, numeric value, source id, or intentionally language-neutral
source title. This applies to descriptive prose inside table cells too: deal
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
treatment, scenario ranges, valuation, revenue, margins, or diligence
thresholds.

The Chinese memo must be native professional investment Chinese with
analytical parity to English: same recommendation, confidence level, risks,
valuation posture, evidence, caveats, tables, and decision questions. Do not
translate prompt scaffolding into visible prose. Avoid terms like `上行状态`,
`现态`, `关键现实检查`, `源追踪`, `备忘录包`, `审阅者提示`, `声明登记`,
`硬 IP 墙`, or `软性工具`; rewrite them as precise investment judgments,
evidence chains, diligence thresholds, scenario ranges, valuation support, or
specific deal mechanics.

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
Lanes, Top 3 Decision Questions, Pre-Mortem, Reverse IC), the memo
drafting step, the translation step, and the package-writing step
remain sequential. Server-side `.docx` rendering happens after Claude exits.

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

=================================================================
SKILL: bsh-investment-memo-latestage-v1 (verbatim — follow this)
=================================================================

{skill_text}
"""


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

    stderr_log: list[str] = []
    try:
        proc = subprocess.Popen(
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
    state: dict[str, Any] = {"thread_map": _MEMO_ANALYSIS_PASSES}
    result_event: dict | None = None
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
                    "memo claude subprocess kept running after result; "
                    "terminating process group"
                )
                _terminate_process_group(proc, grace_s=2.0)
        else:
            proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc, grace_s=2.0)
        return {"ok": False, "error": f"Claude timed out after {timeout_sec}s"}

    # Close out any pass threads that we opened during the run. The
    # subprocess having reached `result` is the only completion signal we
    # have for the individual passes — the skill doesn't emit per-pass
    # markers — so we attribute success/failure to the overall return.
    if progress:
        finish_ok = (
            bool(result_event) and result_event.get("subtype") != "error"
        )
        for thread_label in state.get("threads_started") or ():
            progress.emit(
                "thread_finished" if finish_ok else "thread_failed",
                thread=thread_label,
            )

    if result_event and result_event.get("subtype") == "error":
        return {
            "ok": False,
            "error": result_event.get("error") or "Claude skill run failed",
            "cost_usd": result_event.get("total_cost_usd"),
            "duration_ms": result_event.get("duration_ms"),
            "subtype": result_event.get("subtype"),
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
The skill text is included verbatim below. **Follow it exactly.** This
header only fills in the run-specific I/O contract.

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
        proc = subprocess.Popen(
            cmd,
            cwd=str(run_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {}
    result_event: dict | None = None
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
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.kill()
        return {"ok": False, "error": f"Claude timed out after {timeout_sec}s"}

    if proc.returncode and proc.returncode != 0:
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
                           "what it actually says, and why an analyst should "
                           "care.",
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
                            "Short exact excerpt copied from the source."
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
    """Per-kind instructions for how Claude should read the source file."""
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
            f"description (without seeing the image) should be able to "
            f"act on its contents.\n"
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
  Slide 2 notes, or Document), a short exact excerpt copied from the source,
  and confidence. Do not paraphrase excerpts.
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
        proc = subprocess.Popen(
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
            proc = subprocess.Popen(
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
                "was found, what remains uncertain, and how it changes the "
                "investment question."
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
        "open_questions": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific gaps Serena still needs to close before memo generation.",
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
        "open_questions",
        "sources_checked",
        "confidence",
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
                    "decision_question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "bull_case_answer": {"type": "string"},
                    "bear_case_answer": {"type": "string"},
                    "evidence_needed": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "best_sources": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "research_prompt": {"type": "string"},
                    "memo_section": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["unresearched", "researched", "needs_review"],
                    },
                },
                "required": [
                    "title",
                    "decision_question",
                    "why_it_matters",
                    "bull_case_answer",
                    "bear_case_answer",
                    "evidence_needed",
                    "best_sources",
                    "research_prompt",
                    "memo_section",
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
                            "diligence_needed."
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
                "A direct recommendation stance or conditional logic for BSH."
            ),
        },
        "top_gating_questions": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "question": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "evidence_needed": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["question", "why_it_matters", "evidence_needed"],
            },
        },
        "bull_case_must_be_true": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {"type": "string"},
        },
        "pass_triggers": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "items": {"type": "string"},
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
        "top_gating_questions",
        "bull_case_must_be_true",
        "pass_triggers",
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
                            "needs_human_choice",
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
                    "diligence_needed": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "memo_section_placement": {"type": "string"},
                    "include_in_final_memo": {"type": "boolean"},
                    "final_memo_inclusion_state": {"type": "string"},
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
                    "diligence_needed",
                    "memo_section_placement",
                    "include_in_final_memo",
                    "final_memo_inclusion_state",
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
        "missing_diligence": {
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
        "missing_diligence",
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
        proc = subprocess.Popen(
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
Memo Studio artifacts override stale or contradictory lessons.
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
  evidence matrix-like contradictions, benchmark metrics, readiness waivers,
  selected chart/narrative state, memo lessons, and selected research-folder
  excerpts.
- Narrative opportunities must explicitly identify the strongest available
  source-backed material for three final memo moments: the intro stance, the
  risk-section posture, and the conclusion/recommendation posture.
- Use the Serena research folder above for local company documents. Do NOT read
  from `data/uploads/` or the Document Library.
- If local research files exist, inspect only the high-signal files needed for
  source traces. Use WebSearch/WebFetch only for public current evidence that
  affects a metric, contradiction, or visual claim.
- Keep claims compact and mark missing, contradicted, source_needed, or
  prohibited_for_visuals when the evidence is not good enough for visuals.
- Numeric metrics must include unit, period, denominator or calculation notes,
  and source traces when available. Use null when unavailable.
- Ambiguous tone, aggressiveness, visual mode, or claim-framing choices should
  appear as reviewer_prompts rather than silently resolved.

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
  research files or web sources only when necessary to preserve or verify a
  source trace. Do NOT read from `data/uploads/` or the Document Library.
- Plan high-quality memo infographics, not low-fidelity deterministic charts.
- Support two production modes: no_text_overlay for image generation without
  text plus app-rendered typography, and text_in_image when fully generated
  text is the better fit. Use needs_human_choice plus reviewer_prompts when
  the choice is ambiguous.
- For every plan, include title, purpose, visual format, overlay copy,
  required metrics, data payload, source availability, citations, information
  gaps, image generation design prompt, prohibited claims, owner, diligence
  needed, memo section placement, and final memo inclusion state.
- Do not invent metrics, source traces, periods, denominators, or claims. Use
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
  plans, memo-grader lessons, and readiness waivers as the factual base. Do NOT
  read from `data/uploads/` or the Document Library.
- Draft operator-selectable candidates for three final memo moments:
  1. openings = intro stance: the first 2-4 sentences' judgment and proof burden;
  2. transitions = risk-section posture: how the risk section should lead and
     what can change the recommendation;
  3. endings = conclusion/recommendation posture: conviction, conditions,
     failure modes, and next diligence.
- Generate at least three distinct openings, at least two risk-posture
  transitions, and at least three endings when the evidence allows.
- Candidate text should be IC-ready guidance or near-final memo language:
  specific, compressed, evidence-grounded, and free of meta phrases such as
  "the memo should", "the analysis suggests", or "this section".
- Each candidate must include supported claims, evidence references, source
  traces where available, confidence, overclaiming risk, and suggested
  infographic pairings where useful.
- Preserve selected opening/transition/ending ids when current choices remain
  semantically valid.
- Use reviewer_prompts only for genuine operator HIL choices about intro
  stance, risk posture, or conclusion posture that cannot be safely inferred
  from the evidence. Make them optional unless approval would be unsafe without
  the operator's answer.
- Do not invent facts. Unsupported claims should be explicitly framed as
  questions, missing evidence, or pass triggers.

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
    company_str = json.dumps(company, indent=2, ensure_ascii=False, default=str)
    files_str = "\n".join(f"- {name}" for name in local_files) or "- No local research files found."
    lessons_block = ""
    if lessons_path and lessons_path.exists():
        lessons_block = f"""\

Serena memo lessons:
`{lessons_path}`

Read these lessons as quality heuristics. Current company evidence and current
public data override stale or contradictory lessons.
"""

    prompt = f"""\
You are Serena's Strategic Risk Mapper for a late-stage investment memo.
Generate the 5-8 decision-grade strategic risks that should control whether
BSH should invest in {company_name}.

Company:
```json
{company_str}
```

Serena research folder:
`{research_dir}`

Available files in that folder:
{files_str}
{lessons_block}

Instructions:
- Frame risks as investment decision questions, not generic risk labels. The
  risk title should be sharp enough to become a one-sentence memo risk.
- Prefer risks that can change a BSH recommendation: valuation durability,
  deployment depth, revenue quality, market abstraction, moat durability,
  budget ownership, public-comp support, and disconfirming evidence.
- For each risk, include the best bull answer, best bear answer, concrete
  evidence needed, and the source types that can actually settle the question.
- Prioritize risks that help an operator choose the final risk-section posture:
  lead-risk, pass trigger, conditional-yes dependency, or monitoring item.
- Use the Serena research folder above for local company documents. Do NOT
  read from `data/uploads/` or the Document Library.
- If local research files exist, inspect the relevant files with Read/Bash.
- Use WebSearch/WebFetch when public filings, transcripts, market data, or
  current public evidence are needed.
- Separate verified evidence from inference. Do not invent facts.
- Include concrete evidence Serena should gather and the best source types.
- Make research_prompt actionable enough that a later background job can run it.

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
        proc = subprocess.Popen(
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
lessons.
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
- Build 3-5 investment highlights, 3-5 investment risks, direct
  recommendation logic, the top decision questions, bull-case
  requirements, and pass triggers.
- Write every highlight and risk as final-memo raw material: concise,
  judgment-led, source-backed, and free of process language. Convert research
  task answers into conclusions instead of copying task labels or confidence
  scaffolding.
- Investment risks should identify what can change BSH's recommendation, not
  generic operating risks. Each risk detail should carry the specific data,
  contradiction, or missing proof that makes the risk matter.
- recommendation_logic should be usable as the conclusion spine: conviction,
  dependencies, failure modes, and the operator's likely proceed / proceed-if-
  confirmed / hold-pending-confirmation / pass posture.
- Top decision questions should become operator HIL choices where applicable:
  ask what Serena must decide, which evidence would change the answer, and what
  the memo conclusion should do if the evidence remains missing.
- Treat incomplete research-task results, partial chart specs, and nullable
  benchmark metrics as evidence gaps, not as facts.
- Source_trace values should name artifact/source categories actually used,
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
        proc = subprocess.Popen(
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
    gates = parsed.get("top_gating_questions")
    if not isinstance(highlights, list) or not highlights:
        return None, "claude output missing investment_highlights"
    if not isinstance(memo_risks, list) or not memo_risks:
        return None, "claude output missing investment_risks"
    if not isinstance(gates, list) or not gates:
        return None, "claude output missing top_gating_questions"
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
- Source traces should identify titles, URLs or local locators, concise
  excerpts, and confidence. Do not invent metrics or sources.
- Benchmark gaps should be the missing data that matters before memo use.
- Must-prove claims should translate the benchmark work into private-company
  proof points BSH needs before making the investment decision.

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
        proc = subprocess.Popen(
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
        "investment memo as a reusable training artifact. Be direct, "
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
- Missing diligence that would matter at IC.
- Specific lessons future Serena memo runs should reuse.

Current evidence overrides stale lessons. Do not reward unsupported claims.
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
You are running one selected research prompt for Serena's Memo Studio before
an investment memo is drafted. Be factual, skeptical, and source-aware.

Company:
```json
{company_str}
```

Selected strategic risk:
```json
{risk_str}
```

Research task:
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
- If evidence is thin, say so plainly and list what Serena should check next.
- Evidence entries must include file_id, filename, locator, exact excerpt, and
  confidence when a local selected source supports them. Use null file_id /
  filename only for web or source-category evidence.

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
            message="Running selected research prompt with Claude",
            task_id=task.get("id"),
            risk_id=task.get("risk_id"),
        )

    stderr_log: list[str] = []
    try:
        proc = subprocess.Popen(
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
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
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
    """SIGINT → wait → SIGKILL. Returns the signal name that succeeded."""
    import signal as _signal

    if handle.proc.poll() is not None:
        return "exited"
    try:
        handle.proc.send_signal(_signal.SIGINT)
    except ProcessLookupError:
        return "exited"
    try:
        handle.proc.wait(timeout=grace_s)
        return "SIGINT"
    except subprocess.TimeoutExpired:
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
