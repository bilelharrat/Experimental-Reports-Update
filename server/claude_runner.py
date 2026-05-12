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
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def is_available() -> bool:
    """True if `claude` is on PATH."""
    return shutil.which("claude") is not None


def claude_path() -> str | None:
    return shutil.which("claude")


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
            "error": (
                f"claude exited {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:600]}"
            ),
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


def _process_event(event: dict, progress, state: dict) -> None:
    """Translate a stream-json event into our ProgressLog vocabulary.

    `state` is per-job mutable scratch — we use it to track the latest tool
    invocation so we can pair tool_result events back to their tool_use, plus
    which slides we've emitted so we can dedup and detect stage transitions.
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
            elif btype == "tool_use":
                name = block.get("name") or "?"
                inp = block.get("input") or {}
                tool_id = block.get("id")
                state["last_tool"] = {"id": tool_id, "name": name}
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
                else:
                    preview = json.dumps(inp, ensure_ascii=False)
                progress.emit(
                    "claude_action",
                    action="tool_use",
                    tool=name,
                    preview=preview[:500],
                )
        return
    if etype == "user":
        msg = event.get("message") or {}
        for block in msg.get("content") or []:
            if block.get("type") == "tool_result":
                tool = state.get("last_tool", {}).get("name", "?")
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
language, same facts, same numbers.

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
            tail = (proc.stderr or "").strip()[-600:]
            return None, f"claude exited {proc.returncode}: {tail}"

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
        )
    except FileNotFoundError as exc:
        return None, f"Failed to launch claude: {exc}"

    stderr_log: list[str] = []
    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc_stream, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {}
    final_text: str | None = None
    try:
        for line in proc_stream.stdout or []:  # type: ignore[union-attr]
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            try:
                _process_search_event(event, progress, state)
            except Exception:
                logger.exception("search progress event handling failed")
            if event.get("type") == "result":
                # When --json-schema produced a StructuredOutput tool call,
                # the JSON lives in that tool's `input` and the assistant
                # `result` text is just a prose summary. Prefer the
                # structured payload; fall back to the raw result text.
                structured = state.get("structured_output")
                if isinstance(structured, dict):
                    final_text = json.dumps(structured)
                else:
                    final_text = event.get("result")
        proc_stream.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc_stream.kill()
        return None, f"claude search timed out after {timeout_sec}s"

    if proc_stream.returncode and proc_stream.returncode != 0:
        tail = "".join(stderr_log[-20:]).strip()
        return None, (
            f"claude exited {proc_stream.returncode}"
            + (f": {tail[:600]}" if tail else "")
        )

    return _parse_search_result(final_text, max_results)


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
        )
    except FileNotFoundError as exc:
        return {"error": f"Failed to launch claude: {exc}"}

    stderr_log: list[str] = []
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
                    _process_pdf_translation_event(event, progress, state)
            except Exception:
                logger.exception("translation progress event handling failed")
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


def _load_skill_text() -> str:
    if not _SKILL_PATH.exists():
        raise RuntimeError(f"Skill file missing: {_SKILL_PATH}")
    return _SKILL_PATH.read_text(encoding="utf-8")


def _build_investment_memo_prompt(
    *,
    run_dir: Path,
    company_name: str,
    company_slug: str,
    run_id: str,
    settings_path: Path,
    companies_yaml_path: Path,
    memo_paths: dict[str, str],
) -> str:
    """Build the prompt for one Claude subprocess running Serena's skill.

    The prompt is **Serena's skill text verbatim**, with a short
    operational header that:
      - maps the skill's `[BSH Assistant]/` paths onto our `data/` tree,
      - lists the actual inputs (Serena_Background.md + the
        companies.yaml record) — note: no Document Library files,
      - hints that the eight orthogonal analysis passes have no
        inter-dependencies and should run via parallel tool calls in a
        single response.

    Everything else is the skill, untouched.
    """
    skill_text = _load_skill_text()
    rel_run_dir = run_dir.name

    return f"""\
You are running the **bsh-investment-memo-latestage-v1** skill (Serena's
script) for one real run. The skill text is included verbatim below.
**Follow it exactly.** The only deviation from the text is the
parallel-passes hint below.

## Run-specific operational context

- **Run folder (your CWD):** `{rel_run_dir}` — everything is relative
  to here. The subfolders `analysis/`, `memo/`, `logs/`,
  `logs/previews/`, and `logs/previews_cn/` already exist.
- **Company:** {company_name} (slug `{company_slug}`)
- **Run ID:** {run_id}

## Inputs (Serena's "company folder" + Settings)

The skill text describes a `[BSH Assistant]/[Company Name]/` folder
that historically held PitchBook PDFs, partner notes, CB Insights
exports, etc. **For this run, that folder is not populated.** Treat
the company folder as empty — proceed without external research
materials, exactly as the skill says to do when the folder is absent.

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
Lanes, Top 3 Gating Questions, Pre-Mortem, Reverse IC), the memo
drafting step, the translation step, and the `.docx` rendering step
remain sequential.

## Output contract — exactly per the skill text

Produce all artifacts the skill specifies, at the paths the skill
specifies — including the two `.docx` files in `memo/`. The expected
absolute paths are:

  - `{memo_paths['en']}`
  - `{memo_paths['zh']}`

Append the analysis finalization block to `logs/run_manifest.md` when
you're done.

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
    progress=None,
    timeout_sec: int = 3600,
) -> dict:
    """Spawn `claude -p` to run Serena's memo skill against a prepped run.

    Inputs the skill is allowed to read:
      - ``settings_path``  (Serena_Background.md)
      - ``companies_yaml_path`` (the registry; entry matching ``company_slug``)

    The skill writes its own analysis artifacts and ``.docx`` files into
    ``run_dir``. Python does not pre-extract anything, does not produce
    any output for the skill, and does not stage Document Library files.

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
        "entities", "topics", "language",
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
            f"Chinese sentences."
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
        )
    except FileNotFoundError as exc:
        return {"error": f"Failed to launch claude: {exc}"}

    stderr_thread = threading.Thread(
        target=_drain_stderr, args=(proc, stderr_log), daemon=True
    )
    stderr_thread.start()

    state: dict[str, Any] = {}
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
                logger.exception("quick-summary progress event failed")
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
        "--output-format", "json",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
    ]
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
        tail = (proc.stderr or "").strip()[-600:]
        return None, f"claude exited {proc.returncode}: {tail}"

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

