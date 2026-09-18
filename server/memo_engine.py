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
import re
import threading
from dataclasses import dataclass
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


_BACKTICK_PATH_RE = re.compile(r"`([^`\n]{1,400})`")
REFERENCED_FILE_BUDGET_CHARS = 250_000


def referenced_files(prompt: str, add_dirs: list[Path] | None) -> list[tuple[str, Path]]:
    """Files the prompt names in backticks, as ``(as_written, path)`` pairs.

    The repair passes do not describe the package to fix — they hand the
    agent its path: ``Input package (fails renderer validation): `<run>/logs/
    memo_package.en.invalid.json` `` and expect it to be opened. Under
    ``logs/`` it is exactly what the folder walk skips, so on Gemini every
    repair pass ran blind and "did not clear renderer validation" — it had
    never seen the package. Anything the prompt points at by path is inlined
    here, under the path exactly as the prompt wrote it, so the reference
    resolves. Bare relative paths are tried against each add_dir.
    """
    found: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    roots = [Path(d) for d in (add_dirs or []) if d]
    for raw in _BACKTICK_PATH_RE.findall(prompt or ""):
        if "/" not in raw and "." not in raw:
            continue  # a backticked word or key, not a path
        candidates = [Path(raw)] + [root / raw for root in roots]
        for candidate in candidates:
            try:
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved in seen or candidate.suffix.lower() in _SKIP_SUFFIXES:
                break
            seen.add(resolved)
            found.append((raw, candidate))
            break
    return found


def inline_referenced(prompt: str, add_dirs: list[Path] | None) -> tuple[str, set[Path]]:
    """Inline every file the prompt names. Returns ``(text, resolved paths)``."""
    blocks: list[str] = []
    used = 0
    resolved: set[Path] = set()
    for as_written, path in referenced_files(prompt, add_dirs):
        text = file_text(path).strip()
        if not text:
            continue
        if used + len(text) > REFERENCED_FILE_BUDGET_CHARS:
            blocks.append(
                f"=== FILE: {as_written} ===\n[not inlined: referenced-file budget reached]"
            )
            continue
        used += len(text)
        resolved.add(path.resolve())
        blocks.append(f"=== FILE: {as_written} ===\n{text}")
    if not blocks:
        return "", resolved
    return (
        "FILES THE TASK REFERS TO BY PATH (inlined in full; do not try to open them):\n\n"
        + "\n\n".join(blocks),
        resolved,
    )


def _registry_entry_text(companies_yaml: Path, company_slug: str) -> str:
    """This company's entry from companies.yaml, as YAML, or ""."""
    try:
        import yaml

        data = yaml.safe_load(companies_yaml.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.warning("memo_engine: could not read %s", companies_yaml, exc_info=True)
        return ""
    records = data.get("companies") if isinstance(data, dict) else data
    for item in records or []:
        if isinstance(item, dict) and str(item.get("id") or "") == company_slug:
            return yaml.safe_dump(item, sort_keys=False, allow_unicode=True, width=100).strip()
    return ""


def _is_permission_root(directory: Path, run_dir: Path | None) -> bool:
    """A granted directory that contains the run itself is a permission
    root, not source material.

    The Claude path grants `--add-dir data/` so an agent MAY open
    companies.yaml; it opens one entry. Walking that grant inlines every
    file under data/ — other companies' memo artifacts, briefs, uploads —
    until the budget fills, and the "analysis" priority then matches every
    run's analysis folder, not this one's. A live ZaiNar memo came back
    without its founders, board or Tokyo office although every one of them
    sat in this run's own artifacts: they were drowned by other runs'.
    """
    if run_dir is None:
        return False
    try:
        run_dir.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return directory.resolve() != run_dir.resolve()


def inline_research(
    add_dirs: list[Path] | None,
    *,
    budget: int = RESEARCH_BUDGET_CHARS,
    per_file: int = PER_FILE_BUDGET_CHARS,
    already: set[Path] | None = None,
    run_dir: Path | None = None,
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

    seen: set[Path] = set(already or ())
    candidates: list[Path] = []
    registry_blocks: list[str] = []
    for directory in add_dirs:
        try:
            if not directory or not Path(directory).is_dir():
                continue
            root = Path(directory)
            if _is_permission_root(root, run_dir):
                # From a permission root take exactly what the agent would
                # have opened: this company's registry entry. The company
                # slug is the run folder's parent (data/memos/<slug>/<run>).
                registry = root / "companies.yaml"
                slug = run_dir.parent.name if run_dir is not None else ""
                if registry.is_file() and slug and registry.resolve() not in seen:
                    entry = _registry_entry_text(registry, slug)
                    if entry:
                        seen.add(registry.resolve())
                        registry_blocks.append(
                            f"=== FILE: companies.yaml (entry `{slug}` only) ===\n{entry}"
                        )
                continue
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

    blocks = registry_blocks + blocks
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
    run_dir: Path | None = None,
) -> tuple[dict | None, str | None]:
    """One memo stage on Gemini. Same ``(data, error)`` contract as the
    Claude funnel, so every caller, retry and repair pass is unchanged."""
    if not gemini_runner.is_available():
        return None, (
            "Gemini API key not configured. Set GEMINI_API_KEY in .env, or "
            "run this memo on Claude."
        )
    referenced, already = inline_referenced(prompt, add_dirs)
    research = inline_research(add_dirs, already=already, run_dir=run_dir)
    combined = (
        f"{prompt}\n\n"
        "---\n"
        "RESEARCH MATERIAL\n"
        "You have no file access in this run. Everything available to you is "
        "below; any instruction above to read, open or list files refers to "
        "this material.\n"
        "---\n"
        + (f"{referenced}\n\n" if referenced else "")
        + f"{research}\n"
    )
    return gemini_runner.run_structured_prompt(
        system_prompt="",
        user_prompt=combined,
        schema=schema,
        name=timeout_label,
        timeout_sec=timeout_sec,
        model=model or memo_gemini_model(),
        thinking_level=memo_thinking_level(),
        max_output_tokens=MEMO_MAX_OUTPUT_TOKENS,
    )


def memo_gemini_model() -> str:
    """The Gemini model memo stages run on.

    ``BSH_MEMO_GEMINI_MODEL`` pins it for memos alone; otherwise the
    app-wide ``BSH_GEMINI_MODEL`` / ``gemini-3.8-flash``. Callers must not
    pass the Claude quality tier's role model here — "sonnet" is not a
    Gemini model.
    """
    raw = str(os.environ.get("BSH_MEMO_GEMINI_MODEL") or "").strip()
    return raw or gemini_runner.default_model()


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


# ---- Length parity with the Claude engine ----------------------------------
#
# Same prompts, same stage graph, and a Gemini section still comes back at
# roughly half the length of its Claude twin: the ZaiNar wave wrote 7,695
# English words where the two benchmarked Claude waves on the same company
# wrote 12,202 and 12,212 (docs/memo-benchmarks.md, Round 2). The late-stage
# editorial prompts under skills/memo/ carry no word targets — Claude never
# needed one — so the target lives here, on the engine that does. Every
# Gemini section worker is told the length its Claude twin writes, and a
# deterministic gate after the section wave sends any section that came
# back short to its worker again, with the draft, to deepen rather than
# redraft. Claude runs see none of this.

CLAUDE_REFERENCE_WORDS = 12_200
"""English words in a late-stage memo written on Claude — both Round-2
benchmark runs (docs/memo-benchmarks.md). ``BSH_MEMO_GEMINI_WORDS`` moves
it; 0 switches the contract and the gate off."""

# How the reference splits across the late v1 sections, weighted by what
# each has to carry: the thesis and one snapshot table; three tables of
# company record; three tables plus the highlight argument; four to six
# risk cards plus disconfirming evidence; seven valuation components.
# Sums to CLAUDE_REFERENCE_WORDS.
_LATE_V1_WORDS: dict[str, int] = {
    "executive_summary": 1_400,
    "company_overview": 2_400,
    "investment_highlights": 2_800,
    "investment_risk": 2_400,
    "financial_forecast_valuation": 3_200,
}

# Accepted floor and suggested ceiling, as shares of a section's target.
LENGTH_BAND = (0.90, 1.15)

# Extension passes a short section gets before its draft stands as-is.
DEPTH_ROUNDS = 2

_WORD_RANGE_RE = re.compile(r"(\d[\d,]*)\s*[-–—]\s*(\d[\d,]*)\s+words", re.IGNORECASE)


@dataclass(frozen=True)
class WordTarget:
    target: int
    low: int
    high: int


def reference_words() -> int | None:
    """The English-word total a Gemini late-stage memo is held to, or None
    when the contract is off (``BSH_MEMO_GEMINI_WORDS=0``)."""
    raw = str(os.environ.get("BSH_MEMO_GEMINI_WORDS") or "").strip()
    if not raw:
        return CLAUDE_REFERENCE_WORDS
    try:
        value = int(raw.replace(",", "").replace("_", ""))
    except ValueError:
        logger.warning(
            "BSH_MEMO_GEMINI_WORDS=%r is not a number; using the Claude reference",
            raw,
        )
        return CLAUDE_REFERENCE_WORDS
    return value if value > 0 else None


def _band(target: int) -> WordTarget:
    return WordTarget(
        target=target,
        low=int(round(target * LENGTH_BAND[0])),
        high=int(round(target * LENGTH_BAND[1])),
    )


def section_word_targets(run_dir: Path | str | None, structure) -> dict[str, WordTarget]:
    """Per-section English-word targets for a Gemini run; ``{}`` on Claude,
    when the contract is off, or for a profile that sets its own ceilings.

    Late v1 — the profile with no word guidance of its own — takes the
    calibrated split of the reference total. A profile that writes its own
    ranges into the section specs (growth, early, late v2) is read as
    written, the midpoint being the target. One that declares
    ``budget_words`` ceilings (compact) is left alone: a floor under a
    ceiling is not this gate's to set.
    """
    if run_engine(run_dir) != "gemini":
        return {}
    total = reference_words()
    if total is None:
        return {}
    if str(structure.stage) == "late" and int(structure.version) == 1:
        scale = total / CLAUDE_REFERENCE_WORDS
        return {
            section_id: _band(int(round(words * scale)))
            for section_id, words in _LATE_V1_WORDS.items()
            if section_id in structure.section_ids
        }
    targets: dict[str, WordTarget] = {}
    for section in structure.sections:
        if section.budget_words:
            continue
        match = _WORD_RANGE_RE.search(section.contract_md or "")
        if not match:
            continue
        low = int(match.group(1).replace(",", ""))
        high = int(match.group(2).replace(",", ""))
        if low <= 0 or high < low:
            continue
        targets[section.id] = WordTarget(target=(low + high) // 2, low=low, high=high)
    return targets


# Block keys that name structure, not content: never words the reader gets.
_STRUCTURAL_KEYS = frozenset(
    {
        "type", "id", "component", "slug", "level", "style", "align", "kind",
        "format", "variant", "source_ids", "citations", "series", "zh",
    }
)


def en_word_count(section: dict | None) -> int:
    """English words in a section's blocks — prose, bullets, table cells and
    captions alike.

    A localized string counts its ``en`` half. A raw worker draft — whose
    strings are still plain, under whatever keys the model chose (``text``,
    ``content``, ``title``, cells), because the repair step wraps them as
    ``{"en", "zh"}`` only later — counts the strings themselves, so the gate
    reads the draft the worker actually returned: a live run measured five
    full sections as 0 before this. On a repaired package this counts
    exactly as the renderer's compact-ceiling gate does
    (``memo_docx_renderer._section_en_word_count``).
    """
    words = 0

    def walk(value) -> None:
        nonlocal words
        if isinstance(value, dict):
            if "en" in value:
                words += len(str(value.get("en") or "").split())
                return
            for key, item in value.items():
                if key not in _STRUCTURAL_KEYS:
                    walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
        elif isinstance(value, str):
            words += len(value.split())

    walk((section or {}).get("blocks") or [])
    return words


def length_contract(target: WordTarget) -> str:
    """The prompt block a Gemini section worker drafts under."""
    return f"""\
## Length contract (this engine)
Write {target.low:,}–{target.high:,} English words for this section — aim for
{target.target:,} — counting prose, bullets and table cells together. That is
the length this section runs to on the reference engine, and the two
engines' memos must read at the same depth: argue every pinned fact through
to its consequence, fill each table row with the specific figure or name the
research material gives, and treat every component the section spec names in
full. Reach the length with substance only — no restating the shared fact
sheet, no recap of what the section has already said, no invented numbers.
Stay inside the band: past {target.high:,} words the section is over-long
for its reader, so stop adding once every component has its full treatment.
"""


def length_extension(target: WordTarget, previous_path: Path, words: int) -> str:
    """The prompt block for the gate's extension pass: deepen the draft on
    disk, keep everything it already says."""
    return f"""\
## Length extension
Your previous draft of this section is at `{previous_path}`: {words:,} English
words against the {target.low:,}–{target.high:,} this section runs to (aim for
{target.target:,}). Return the SAME section, extended: keep every existing
block, claim, number, table row and source reference exactly as written and
in order, then deepen it — carry each argument through to its consequence,
add the specifics from the research material the draft left out, add the
table rows the material supports, and give every component the section spec
names its full treatment. Substance only: no restatement of the shared fact
sheet, no recap paragraphs, no numbers that are not in the fact sheet or the
research material.
"""
