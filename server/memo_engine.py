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
# `sources` is the source cache: hundreds of fetched pages that the
# known_sources.md digest already summarises for the prompt.
_SKIP_DIRS = {"logs", "previews", "previews_cn", "memo", "__pycache__", "sources"}
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
        if name in {"fact_ledger.md", "recent_news.md", "decision_record.md", "known_sources.md"}:
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


def memo_web_research_enabled() -> bool:
    """``BSH_MEMO_GEMINI_WEB_RESEARCH`` (default on): whether a Gemini
    memo's research passes search the web. Off, they answer from the
    research material inlined into the prompt and the model's memory — how
    every Gemini memo ran before 2026-09-21."""
    return os.environ.get("BSH_MEMO_GEMINI_WEB_RESEARCH", "1") != "0"


# A grounded pass reports a dozen pages at most in practice; fetching them is
# the slow part of the pass, so it is bounded and runs in parallel.
GROUNDED_FETCH_MAX_PAGES = 12
GROUNDED_FETCH_WORKERS = 6


def _resolve_only(url: str) -> str | None:
    """Follow a redirect to the page's real address without reading it —
    for a page that would not hand over its text (a PDF, a 403) but whose
    address is still worth citing."""
    import httpx

    from . import link_preview

    try:
        with httpx.Client(
            timeout=8.0,
            headers=link_preview.HEADERS,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            with client.stream("GET", url) as response:
                return str(response.url)
    except Exception:  # noqa: BLE001
        return None


def fetch_grounded_pages(meta: dict, run_dir: Path | None) -> list[dict]:
    """Fetch every page a grounded search reported, at its real address, and
    store the ones that yield text in the company's source cache and the
    run's frozen manifest — what a Claude run's WebFetch results already
    get. Returns ``[{"title", "url"}]`` for every page whose real address is
    known, fetched or not. Never raises.

    Gemini reports pages as links through Google's redirector; those are
    not citations, so each one is followed to where it lands.
    """
    from concurrent.futures import ThreadPoolExecutor

    from . import link_preview, source_cache

    reported = [
        row
        for row in (meta.get("sources") if isinstance(meta, dict) else None) or []
        if isinstance(row, dict) and str(row.get("url") or "").strip()
    ][:GROUNDED_FETCH_MAX_PAGES]
    if not reported:
        return []
    capture = None
    if run_dir is not None:
        try:
            from . import claude_runner

            capture = claude_runner.memo_run_source_capture(run_dir)
        except Exception:  # noqa: BLE001
            capture = None

    def one(row: dict) -> dict | None:
        preview = link_preview.fetch(str(row["url"]))
        url = preview.final_url
        if source_cache.is_grounding_redirect(url):
            url = _resolve_only(str(row["url"])) or ""
        if not url or source_cache.is_grounding_redirect(url):
            return None
        title = preview.title or str(row.get("title") or "") or url
        if capture and not preview.error and preview.text.strip():
            try:
                source_cache.record_run_source(
                    capture["company_id"],
                    run_dir,
                    tool="GroundedFetch",
                    text=preview.text,
                    url=url,
                    title=title,
                    run_id=capture.get("run_id"),
                )
            except Exception:  # noqa: BLE001
                logger.warning("grounded page not recorded: %s", url, exc_info=True)
        return {"title": title, "url": url}

    with ThreadPoolExecutor(max_workers=GROUNDED_FETCH_WORKERS) as pool:
        pages = [page for page in pool.map(one, reported) if page]
    if capture and capture.get("research_dir") and pages:
        try:
            from . import claude_runner

            source_cache.write_known_sources_file(
                capture["company_id"],
                capture["research_dir"],
                claude_runner.MEMO_KNOWN_SOURCES_FILENAME,
            )
        except Exception:  # noqa: BLE001
            logger.warning("known-sources refresh failed", exc_info=True)
    return pages


def _pages_addendum(pages: list[dict]) -> str:
    if not pages:
        return ""
    lines = "\n".join(f"- {page['title']} — {page['url']}" for page in pages)
    return (
        "Pages the search returned, at their real addresses. A source drawn "
        "from one of these carries its URL exactly as listed here:\n" + lines
    )


def run_artifact(
    *,
    prompt: str,
    schema: dict,
    add_dirs: list[Path] | None,
    timeout_label: str,
    timeout_sec: int,
    model: str | None = None,
    run_dir: Path | None = None,
    web_research: bool = False,
) -> tuple[dict | None, str | None]:
    """One memo stage on Gemini. Same ``(data, error)`` contract as the
    Claude funnel, so every caller, retry and repair pass is unchanged.

    ``web_research`` marks a research pass. A Claude pass searches the web
    as it works; a Gemini call does not unless it is grounded, and until
    2026-09-21 none was — every Gemini memo's research, and every URL in
    it, came from the model's memory, and the source cache and fact check
    saw nothing. A research pass now runs grounded (search, then structure
    as a separate call), and the pages it found are fetched and stored."""
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
    if web_research and memo_web_research_enabled():
        data, meta, error = gemini_runner.run_grounded_json(
            system_prompt="",
            user_prompt=combined,
            schema=schema,
            name=timeout_label,
            timeout_sec=timeout_sec,
            model=model or memo_gemini_model(),
            thinking_level=memo_thinking_level(),
            max_output_tokens=MEMO_MAX_OUTPUT_TOKENS,
            # The structuring step sees the pass's own instructions, not
            # the research material — that was the first step's input.
            task_context=prompt,
            notes_addendum=lambda found: _pages_addendum(
                fetch_grounded_pages(found, run_dir)
            ),
        )
        if not meta.get("grounded"):
            logger.warning(
                "memo_engine: %s ran as a research pass but did not search", timeout_label
            )
    else:
        data, meta, error = gemini_runner.run_structured_prompt_with_meta(
            system_prompt="",
            user_prompt=combined,
            schema=schema,
            name=timeout_label,
            timeout_sec=timeout_sec,
            model=model or memo_gemini_model(),
            thinking_level=memo_thinking_level(),
            max_output_tokens=MEMO_MAX_OUTPUT_TOKENS,
        )
    if isinstance(data, dict):
        # The pipeline carries per-call spend in these two keys, set from
        # the Claude CLI's result event. A Gemini call reports the same
        # thing in `usageMetadata`, so it rides the same fields and every
        # phase timing, run total and UI reader works unchanged — the name
        # is the pipeline's, not a claim about which engine ran.
        # Only what the call actually reported: a null here would put the
        # key on every payload and say nothing.
        if meta.get("usage") is not None and "claude_usage" not in data:
            data["claude_usage"] = meta["usage"]
        if meta.get("cost_usd") is not None and "claude_cost_usd" not in data:
            data["claude_cost_usd"] = meta["cost_usd"]
    return data, error


def memo_gemini_model() -> str:
    """The Gemini model memo stages run on when no role is known.

    ``BSH_MEMO_GEMINI_MODEL`` pins it for memos alone; otherwise the
    app-wide ``BSH_GEMINI_MODEL`` / ``gemini-3.8-flash``. Callers must not
    pass the Claude quality tier's role model here — "sonnet" is not a
    Gemini model. Stages that know their role use ``gemini_model_for_role``.
    """
    raw = str(os.environ.get("BSH_MEMO_GEMINI_MODEL") or "").strip()
    return raw or gemini_runner.default_model()


# ---- per-role Gemini models ------------------------------------------------
#
# A Gemini memo ran every stage on one model — the flash default, unless the
# owner pinned BSH_MEMO_GEMINI_MODEL for all of them. The Claude tiers spend
# the top model where the founder reads the output (the writing wave) and a
# cheaper one on research, verification and translation; the Gemini engine
# now mirrors that split. BSH_MEMO_GEMINI_MODEL still pins every role at
# once, as before.
#
# There is no default Pro model: on 2026-09-23 Google's model list carried
# gemini-3.8-flash but no gemini-3.8-pro (the newest Pro was
# gemini-3.1-pro-preview, an older generation), and a guessed name would
# fail every writer call. Until BSH_MEMO_GEMINI_MODEL_PRO names one, the
# writer roles run on the flash model like everything else.

GEMINI_PRO_MODEL_DEFAULT: str | None = None

# The roles that write the memo; the same set claude_runner pins with
# BSH_MEMO_WRITER_MODEL (kept here as well so this module stays importable
# without claude_runner, which imports it).
GEMINI_WRITER_ROLES = frozenset({"ENGLISH", "SPINE", "SECTION", "REPAIR", "ARTIFACTS"})


def memo_gemini_pro_model() -> str:
    """The Gemini model the writer roles run on: ``BSH_MEMO_GEMINI_MODEL_PRO``
    when set, else the flash model (no Pro default exists, see above)."""
    raw = str(os.environ.get("BSH_MEMO_GEMINI_MODEL_PRO") or "").strip()
    return raw or GEMINI_PRO_MODEL_DEFAULT or memo_gemini_flash_model()


def memo_gemini_flash_model() -> str:
    """The Gemini model the research, check and translation roles run on
    below the "best" tier: the app-wide default (``BSH_GEMINI_MODEL`` /
    ``gemini-3.8-flash``)."""
    return gemini_runner.default_model()


def gemini_model_for_role(role: str | None, quality: str | None = "best") -> str:
    """Which Gemini model a memo stage runs on.

    - ``BSH_MEMO_GEMINI_MODEL`` set: that model, for every role (the
      owner's override, unchanged).
    - writer roles (ENGLISH, SPINE, SECTION, REPAIR, ARTIFACTS): the pro
      model on every tier.
    - ANALYSIS_PASS, SPINE_CHECK, TRANSLATION (and an unnamed stage): the
      pro model on "best", the flash model on "balanced" / "economy".
    """
    override = str(os.environ.get("BSH_MEMO_GEMINI_MODEL") or "").strip()
    if override:
        return override
    tier = str(quality or "best").strip().lower() or "best"
    if str(role or "").strip().upper() in GEMINI_WRITER_ROLES:
        return memo_gemini_pro_model()
    if tier in ("balanced", "economy"):
        return memo_gemini_flash_model()
    return memo_gemini_pro_model()


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

# Mirrors memo_docx_renderer's fallback when a section sets no multiple, so
# the floor sits under the same ceiling the renderer enforces.
_BUDGET_GRACE = 1.10

# Revision passes an out-of-band section gets before its draft stands as-is.
# Each trim takes roughly a sixth off; a valuation section that came back
# 63% over (5,220 against a 3,680 ceiling, Koch 2026-09-18) needed three.
DEPTH_ROUNDS = 3

_WORD_RANGE_RE = re.compile(r"(\d[\d,]*)\s*[-–—]\s*(\d[\d,]*)\s+words", re.IGNORECASE)


@dataclass(frozen=True)
class WordTarget:
    target: int
    low: int
    high: int

    def distance(self, words: int) -> int:
        """How far ``words`` sits outside the band; 0 inside it. The gate
        keeps whichever draft scores lower, so a revision is accepted only
        when it actually moved toward the band."""
        if words < self.low:
            return self.low - words
        if words > self.high:
            return words - self.high
        return 0


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
            # A compact profile states a target and a hard cap per section,
            # and the renderer already rejects anything above the cap. What
            # it never had is a FLOOR — Claude overshoots, so nobody needed
            # one. Gemini's failure is the opposite: a monolithic call came
            # back at ~2,700 words against a ~12,200 reference. Without a
            # floor here the gate skipped the profile the fund actually
            # ships, so a short Gemini section stood as written.
            #
            # The band is the profile's own numbers — target, and the cap
            # the renderer enforces — so it can never drift from what the
            # Claude twin is asked for.
            cap = int(
                section.budget_words
                * (section.budget_hard_multiple or _BUDGET_GRACE)
            )
            targets[section.id] = WordTarget(
                target=section.budget_words,
                low=int(round(section.budget_words * LENGTH_BAND[0])),
                high=cap,
            )
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
    full sections as 0 before this.

    This counts what the worker WROTE, which is not the same as what the
    reader gets: a string the repair step cannot wrap is dropped by the
    renderer, and this still counts it. Anything deciding whether a section
    is long enough wants ``renderable_en_word_count`` instead.
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


def split_target(target: WordTarget, parts: int) -> WordTarget:
    """One subsection's share of a section's length band.

    A section drafted one subsection per call must not hand each call the
    whole section's target, or every piece writes a whole section. The band
    arithmetic stays here so it cannot drift from the band it divides.
    """
    if parts <= 1:
        return target
    return WordTarget(
        target=max(1, int(round(target.target / parts))),
        low=max(1, int(round(target.low / parts))),
        high=max(1, int(round(target.high / parts))),
    )


def renderable_en_word_count(section: dict | None) -> int:
    """English words the RENDERER will accept from this section.

    ``en_word_count`` counts every plain string a raw draft carries, which
    is right for reading a worker's own output but wrong for deciding
    whether a section is deep enough: a string in a shape the repair step
    cannot wrap never reaches the reader. On the live Gemini run of
    2026-09-19 that gap let ``thesis_market`` through the depth gate at
    3,753 words against a 2,610 floor when the renderer could use only
    1,625 of them — 2,128 words sat in nodes with no ``en`` key, the
    section shipped a thousand words short, and no depth round ever fired.

    So repair a copy exactly as the package pipeline will, then count what
    survives. A merely raw draft is unaffected — the repair wraps its plain
    strings, which is the case ``en_word_count`` exists for.
    """
    if not isinstance(section, dict):
        return 0
    # Local import: the renderer pulls in python-docx, and memo_engine is
    # imported on paths that never render anything.
    from server import memo_docx_renderer

    repaired, _ = memo_docx_renderer.repair_package_structure(
        {"sections": [section]}
    )
    sections = repaired.get("sections") if isinstance(repaired, dict) else None
    if not isinstance(sections, list) or not sections:
        return 0
    return memo_docx_renderer.section_en_word_count(sections[0])


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


def length_condense(target: WordTarget, previous_path: Path, words: int) -> str:
    """The prompt block for the gate's condense pass: tighten the draft on
    disk without dropping anything it establishes.

    Length is a contract in both directions. Left to itself Gemini overran
    the reference by a quarter (13,958 English words against 12,200 on the
    first live run under the contract), and a renderer-validation retry
    inflated the same sections further (18,084). Cutting is asked for the
    way extending is: same blocks, same facts, fewer words.
    """
    return f"""\
## Length trim
Your previous draft of this section is at `{previous_path}`: {words:,} English
words against the {target.low:,}–{target.high:,} this section runs to (aim for
{target.target:,}). Return the SAME section, tightened to fit: keep every
block, every component the section spec names, every table and every row,
every number, name, source reference and pinned sentence, in the same order.
Cut only words, never content — drop restatement of the shared fact sheet,
recap sentences that repeat an earlier paragraph, throat-clearing before a
judgment, and adjectives doing no work. Say each thing once, in the place it
belongs. Do not merge sections, drop a subsection heading, summarize a table
into prose, or soften a risk to save words.
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
