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


def _drain_stderr(proc: subprocess.Popen, log: list[str]) -> None:
    """Background thread that buffers stderr so a long stderr can't deadlock
    the subprocess."""
    if proc.stderr is None:
        return
    for line in proc.stderr:
        log.append(line)


def _process_event(event: dict, progress, state: dict) -> None:
    """Translate a stream-json event into our ProgressLog vocabulary.

    `state` is per-job mutable scratch — we use it to track the latest tool
    invocation so we can pair tool_result events back to their tool_use.
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
                    if inp.get("offset") is not None or inp.get("limit") is not None:
                        preview += (
                            f"  (offset={inp.get('offset')}, limit={inp.get('limit')})"
                        )
                    if inp.get("pages"):
                        preview += f"  (pages={inp.get('pages')})"
                elif name == "Write":
                    fp = inp.get("file_path") or ""
                    body = inp.get("content") or ""
                    preview = f"{fp}  ({len(body)} chars)"
                    # Mirror progress.md writes as discrete progress events too
                    if fp.endswith("progress.md"):
                        for line in body.splitlines():
                            line = line.strip().lstrip("- ").strip()
                            if line.lower().startswith("slide "):
                                # Extract slide number for slide_extracted events
                                rest = line[6:]
                                num, _, body_text = rest.partition(":")
                                try:
                                    sn = int(num.strip())
                                except ValueError:
                                    continue
                                progress.emit(
                                    "slide_extracted",
                                    slide_no=sn,
                                    preview=body_text.strip()[:160],
                                )
                elif name == "Edit":
                    preview = inp.get("file_path") or ""
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


def run_summary(
    *,
    work_dir: Path,
    source_path: Path,
    hint_title: str | None,
    schema: dict,
    quality_bar: str,
    progress=None,
    timeout_sec: int = 600,
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

    progress_md = work_dir / "progress.md"
    progress_md.write_text(
        f"# Summary job — {source_path.name}\n\n"
        "_Per-slide observations are appended below as Claude reads the deck._\n\n",
        encoding="utf-8",
    )
    summary_json = work_dir / "summary.json"
    summary_json.unlink(missing_ok=True)

    user_prompt = _build_prompt(
        deck_filename=source_path.name,
        hint_title=hint_title or source_path.name,
        quality_bar=quality_bar,
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
            message="Spawning Claude Code",
            work_dir=str(work_dir),
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
        try:
            data = json.loads(source_text)
        except json.JSONDecodeError:
            continue
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


def _build_prompt(*, deck_filename: str, hint_title: str, quality_bar: str) -> str:
    return f"""\
You are analyzing a presentation deck for an investment-research dashboard.

The deck has been staged in your current working directory as: ./{deck_filename}
(Hint: titled "{hint_title}".)

WORKFLOW — follow this exactly:

1. Read the deck. Use the Read tool on ./{deck_filename}. For PDFs over 20
   pages, read in chunks of 20 pages at a time using the `pages` parameter
   (e.g. pages="1-20", then "21-40", etc.) so you can process the whole deck.

2. As you process each slide/page, APPEND one bullet line to ./progress.md
   in this exact format (one line per slide):
       - Slide N: <one specific observation, ~80–160 chars>
   Use the Write or Edit tool to append. Do this incrementally as you read,
   not all at the end — the operator is watching this file in real time.

3. After processing the entire deck, produce your FINAL ANSWER as a JSON
   object that exactly matches the schema attached to this run via
   --json-schema. Both fields under `exec_summary` and inside each
   `sections[*].title` / `body` must be filled — English in `en`, 简体中文 in
   `zh`. `slide_refs` are 1-indexed slide numbers from the source deck.

4. ALSO write a copy of that exact JSON to ./summary.json using Write.

QUALITY BAR — every word earns its place:
{quality_bar}

Begin now. Start by reading the deck.
"""
