"""Run Claude Code (the `claude` CLI) as a subprocess for summarization jobs.

Why this instead of the OpenAI SDK directly:
- Uses the user's existing Claude Code subscription / token allowance.
- Gives us file-system observability — Claude writes a `progress.md` to the
  job's work directory as it processes each slide, so we have a durable
  trail and can tail it for granular progress.
- The `stream-json` output format yields one event per assistant turn /
  tool call / tool result, which we translate into our existing
  ProgressLog so the SSE feed stays granular (per-slide, per-tool).
- The native `--json-schema` flag validates the final structured summary
  for free; no manual JSON cleanup needed.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
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
        "--permission-mode", "acceptEdits",
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
STAGE 2 — PER-SLIDE ANALYSIS (batched 20-page Reads, but per-slide bullets).
The Read tool caps at 20 pages per call, so:

  - Read ./{deck_filename} pages="1-20"
  - Read ./{deck_filename} pages="21-40"
  - ... continue in 20-page chunks; the final chunk can be shorter
    (e.g. pages="41-{last_page}") but must NEVER exceed 20 pages.

After EACH Read, append one bullet PER SLIDE in that chunk to
./progress.md (so 20 bullets after the first Read, etc.):

      - Slide 1: <observation>
      - Slide 2: <observation>
      ...

For the very first Read, ./progress.md does not exist — use the Write
tool with a header line plus your 20 bullets. For every subsequent
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
        'Begin Stage 2 now. Read pages="1-20".'
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
