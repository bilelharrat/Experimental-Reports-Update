"""Engine selection for memo and report runs.

The memo pipeline is the one place where swapping engines is not a matter of
changing a call. Every stage — the eight parallel analysis passes, the
English spine, the bilingual package, every repair pass — funnels through
``claude_runner._run_memo_local_json_artifact``, which spawns a Claude CLI
subprocess with ``--add-dir`` and ``Read,Bash,Grep,Glob``. The prompts hand
the agent a *listing* of the company's research folder and expect it to open
those files itself.

Gemini has no filesystem. So the Gemini path keeps everything that makes a
memo a memo — the same prompts, the same schemas, the same stage graph,
retries, repair passes, validation and DOCX renderer — and replaces only the
mechanism by which research reaches the model: files are extracted to text
here and inlined into the prompt, in place of the listing the Claude agent
would have walked.

What that means in practice, stated plainly because it affects output:

- A Claude run reads only the files it decides it needs, and can re-read a
  page. A Gemini run is handed everything up front, truncated to a budget.
- Scanned PDFs with no text layer yield nothing here, where a Claude agent
  could still have described the pages it read.
- Everything downstream is identical, so a Gemini memo is validated, linted
  and rendered by exactly the code that handles a Claude memo.

Selection mirrors the quality tier: a run registers its engine once and
every subprocess of that run resolves against it.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from . import gemini_runner

logger = logging.getLogger(__name__)

ENGINES = ("claude", "gemini")
DEFAULT_ENGINE = "claude"

# How much research text a Gemini memo stage may carry. Flash takes a 1M
# token context; this is a character budget well inside it that still leaves
# room for the prompt, the schema and a long structured answer.
RESEARCH_BUDGET_CHARS = 400_000
PER_FILE_BUDGET_CHARS = 60_000

TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".json", ".csv"}

# Inside a memo run directory these are machine plumbing or this run's own
# output, never source material: the event stream is enormous and the
# rendered DOCX/previews are what the run is trying to produce.
_SKIP_DIRS = {"logs", "previews", "previews_cn", "memo", "__pycache__"}
_SKIP_SUFFIXES = {".docx", ".pdf.tmp", ".jsonl", ".png", ".jpg", ".jpeg", ".zip"}

_RUN_ENGINE: dict[str, str] = {}
_RUN_ENGINE_LOCK = threading.Lock()


def default_engine() -> str:
    """``BSH_MEMO_ENGINE``: the engine a run uses when it registers none.

    Defaults to Claude. A memo is the most expensive and most scrutinised
    thing this system produces, so moving one to a different model stays an
    explicit per-run choice rather than something an env default does
    quietly.
    """
    raw = str(os.environ.get("BSH_MEMO_ENGINE") or "").strip().lower()
    return raw if raw in ENGINES else DEFAULT_ENGINE


def register_run_engine(run_dir: Path | str, engine: str | None) -> str:
    """Pin a run's engine so every stage of that run resolves against it."""
    chosen = str(engine or "").strip().lower()
    if chosen not in ENGINES:
        chosen = default_engine()
    key = str(Path(run_dir).resolve())
    with _RUN_ENGINE_LOCK:
        _RUN_ENGINE[key] = chosen
    return chosen


def run_engine(run_dir: Path | str | None) -> str:
    if run_dir is None:
        return default_engine()
    key = str(Path(run_dir).resolve())
    with _RUN_ENGINE_LOCK:
        return _RUN_ENGINE.get(key, default_engine())


def clear_run_engine(run_dir: Path | str) -> None:
    key = str(Path(run_dir).resolve())
    with _RUN_ENGINE_LOCK:
        _RUN_ENGINE.pop(key, None)


# ---- research inlining ----------------------------------------------------


def _read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        logger.warning("memo_engine: could not read %s", path, exc_info=True)
        return ""


def _read_pdf_or_deck(path: Path) -> str:
    """PDF/PPTX text via the extractor the Document Library already uses."""
    suffix = path.suffix.lower()
    kind = {".pdf": "pdf", ".pptx": "pptx", ".ppt": "ppt"}.get(suffix)
    if kind is None:
        return ""
    try:
        from .deck_summary import extract_slides

        slides = extract_slides(path, kind)
    except Exception:  # noqa: BLE001 — one unreadable file never fails a memo
        logger.warning("memo_engine: could not extract %s", path, exc_info=True)
        return ""
    parts = []
    for slide in slides:
        text = (getattr(slide, "text", "") or "").strip()
        if text:
            parts.append(f"[page {getattr(slide, 'slide_no', '?')}]\n{text}")
    return "\n\n".join(parts)


def _read_docx(path: Path) -> str:
    try:
        import docx  # type: ignore

        document = docx.Document(str(path))
    except Exception:  # noqa: BLE001
        logger.warning("memo_engine: could not read docx %s", path, exc_info=True)
        return ""
    return "\n".join(p.text for p in document.paragraphs if p.text and p.text.strip())


def file_text(path: Path) -> str:
    """Extract a research file to text, or "" when it carries none."""
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return _read_text_file(path)
    if suffix in {".pdf", ".pptx", ".ppt"}:
        return _read_pdf_or_deck(path)
    if suffix == ".docx":
        return _read_docx(path)
    return ""


def inline_research(
    add_dirs: list[Path] | None,
    *,
    budget: int = RESEARCH_BUDGET_CHARS,
    per_file: int = PER_FILE_BUDGET_CHARS,
) -> str:
    """The research folder as prompt text, standing in for the file listing.

    Ordered so the machine-written digests a memo leans on most
    (``fact_ledger.md``, ``recent_news.md``, ``decision_record.md``) and the
    distilled ``*_analysis.md`` briefs come first, because they are what
    survives if the budget runs out. Truncation is always announced in the
    text: a silently shortened source would be read as a complete one.
    """
    if not add_dirs:
        return "- No research directory is populated for this run."

    seen: set[Path] = set()
    candidates: list[Path] = []
    for directory in add_dirs:
        try:
            if not directory or not Path(directory).is_dir():
                continue
            root = Path(directory)
            # Walk, don't list. Many stages pass the memo RUN directory, and
            # the artifacts the package stage is told to read are written to
            # `<run_dir>/analysis/*.md`. A flat listing of the run dir finds
            # none of them, and the package comes back empty.
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                if any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
                    continue
                if path.name.startswith("index.yaml") or path.suffix.lower() in _SKIP_SUFFIXES:
                    continue
                if path.name.endswith(".progress.jsonl"):
                    continue
                resolved = path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                candidates.append(path)
        except OSError:
            logger.warning("memo_engine: could not list %s", directory, exc_info=True)

    def priority(path: Path) -> tuple[int, str]:
        name = path.name.lower()
        if name in {"fact_ledger.md", "recent_news.md", "decision_record.md"}:
            return (0, name)
        # The run's own analysis artifacts: the package stage is written to
        # build on these, so they outrank raw sources.
        if path.parent.name.lower() == "analysis":
            return (1, name)
        if name.endswith("_analysis.md"):
            return (2, name)
        return (3, name)

    blocks: list[str] = []
    skipped: list[str] = []
    used = 0
    for path in sorted(candidates, key=priority):
        text = file_text(path).strip()
        if not text:
            skipped.append(f"{path.name} (no extractable text)")
            continue
        if len(text) > per_file:
            text = text[:per_file] + f"\n[... {path.name} truncated at {per_file} characters]"
        if used + len(text) > budget:
            skipped.append(f"{path.name} (context budget reached)")
            continue
        used += len(text)
        label = (
            f"{path.parent.name}/{path.name}"
            if path.parent.name.lower() == "analysis"
            else path.name
        )
        blocks.append(f"=== FILE: {label} ===\n{text}")

    if not blocks and not skipped:
        return "- No research files found."

    out = []
    if blocks:
        out.append(
            "The company research folder is inlined below in full. These are "
            "the files themselves, not a listing — do not attempt to open "
            "anything, and treat their contents as the source material.\n\n"
            + "\n\n".join(blocks)
        )
    if skipped:
        out.append(
            "\n\nNOT INCLUDED (do not assume their contents; say so if a "
            "conclusion would depend on them):\n"
            + "\n".join(f"- {name}" for name in skipped)
        )
    return "".join(out)


# ---- the artifact call ----------------------------------------------------


def run_artifact(
    *,
    prompt: str,
    schema: dict,
    add_dirs: list[Path] | None,
    timeout_label: str,
    timeout_sec: int,
    model: str | None = None,
) -> tuple[dict | None, str | None]:
    """One memo stage on Gemini. Same ``(data, error)`` contract as the
    Claude funnel, so every caller, retry and repair pass is unchanged."""
    if not gemini_runner.is_available():
        return None, (
            "Gemini API key not configured. Set GEMINI_API_KEY in .env, or "
            "run this memo on Claude."
        )
    research = inline_research(add_dirs)
    combined = (
        f"{prompt}\n\n"
        "---\n"
        "RESEARCH MATERIAL\n"
        "You have no file access in this run. Everything available to you is "
        "below; any instruction above to read, open or list files refers to "
        "this material.\n"
        "---\n"
        f"{research}\n"
    )
    return gemini_runner.run_structured_prompt(
        system_prompt="",
        user_prompt=combined,
        schema=schema,
        name=timeout_label,
        timeout_sec=timeout_sec,
        model=model,
        thinking_level=memo_thinking_level(),
        max_output_tokens=MEMO_MAX_OUTPUT_TOKENS,
    )


# A memo package is a whole investment memo as one JSON object — every
# section, every analysis artifact, and in the bilingual stage both
# languages. 32k truncated it mid-document on a live run; this is the
# model's ceiling.
MEMO_MAX_OUTPUT_TOKENS = 64_000


def memo_thinking_level() -> str:
    """``BSH_MEMO_GEMINI_THINKING`` — default high; a memo is the one place
    worth paying for reasoning."""
    raw = str(os.environ.get("BSH_MEMO_GEMINI_THINKING") or "").strip().lower()
    return raw if raw in gemini_runner.THINKING_LEVELS else "high"
