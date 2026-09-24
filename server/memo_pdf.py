"""Lazy, cached PDFs of memo documents.

A PDF is what readers forward: paginated, page-numbered, fixed layout. The
pipeline does not render one (Word automation is slow and optional), so
PDFs are made on demand — by ``GET /api/reports/{id}/preview`` — or in the
background right after a run completes (``schedule_pdf``, which the
late-stage and Buffett pipelines call). Modelled on
``files_store.get_or_create_preview``.

The cache sits next to the document: ``memo/_pdf/<docx stem>.<key>.pdf``,
where ``key`` comes from the docx's size and modification time. A
re-rendered docx (resume, quality regeneration, review stamp) therefore
gets a new key and a new PDF; its stale PDFs are pruned. A ``pdf_path`` the
pipeline recorded itself is honoured only while it is newer than its docx.

Conversion goes through ``docx_pdf.convert_docx_to_pdf`` (Word, then
LibreOffice when installed), serialized there. Everything here is optional:
with no converter, callers get ``(None, reason)`` and the web viewer keeps
rendering the docx.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from . import docx_pdf, memo_prep, storage

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "zh")
# After a failed conversion, don't hammer Word again for this long.
FAILURE_BACKOFF_SECONDS = 600.0
# How long a GET waits for a conversion another request already started.
WAIT_FOR_INFLIGHT_SECONDS = float(os.environ.get("BSH_MEMO_PDF_WAIT", "75"))

_LOCK = threading.Lock()
_INFLIGHT: dict[str, threading.Event] = {}
_FAILURES: dict[str, tuple[float, str]] = {}


def _repo_root() -> Path:
    return memo_prep.DATA_DIR.parent


def docx_path(report: dict, language: str, *, artifact: str = "memo") -> Path | None:
    """The on-disk docx for a memo language (or the internal memo)."""
    if artifact == "internal":
        entries = report.get("internal_memo_files") or []
        entry = next(
            (f for f in entries if isinstance(f, dict) and f.get("path")),
            None,
        )
    else:
        entry = next(
            (
                f
                for f in report.get("memo_files") or []
                if isinstance(f, dict) and f.get("language") == language and f.get("path")
            ),
            None,
        )
    if not entry:
        return None
    path = _repo_root() / str(entry["path"])
    return path if path.exists() else None


def _legacy_pdf(report: dict, language: str, *, artifact: str = "memo") -> Path | None:
    entries = (
        report.get("internal_memo_files") if artifact == "internal" else report.get("memo_files")
    ) or []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("pdf_path"):
            continue
        if artifact != "internal" and entry.get("language") != language:
            continue
        return _repo_root() / str(entry["pdf_path"])
    return None


def cache_path(docx: Path) -> Path:
    """Where the PDF for this exact docx version lives."""
    stat = docx.stat()
    key = hashlib.sha1(f"{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()[:12]
    return docx.parent / "_pdf" / f"{docx.stem}.{key}.pdf"


def cached_pdf(report: dict, language: str, *, artifact: str = "memo") -> Path | None:
    """A fresh PDF for the current docx, or None. Never converts."""
    docx = docx_path(report, language, artifact=artifact)
    if docx is None:
        return None
    try:
        docx_mtime = docx.stat().st_mtime_ns
        legacy = _legacy_pdf(report, language, artifact=artifact)
        if legacy is not None and legacy.exists() and legacy.stat().st_mtime_ns >= docx_mtime:
            return legacy
        cached = cache_path(docx)
    except OSError:
        return None
    try:
        if cached.exists() and cached.stat().st_size > 0:
            return cached
    except OSError:
        return None
    return None


def status(report: dict, language: str, *, artifact: str = "memo") -> str:
    """``ready`` | ``building`` | ``failed`` | ``unavailable`` (no converter
    on this server) | ``pending`` (convertible, not made yet) | ``none``
    (no document). Cheap: stats only."""
    docx = docx_path(report, language, artifact=artifact)
    if docx is None:
        return "none"
    if cached_pdf(report, language, artifact=artifact) is not None:
        return "ready"
    try:
        key = str(cache_path(docx))
    except OSError:
        return "none"
    with _LOCK:
        if key in _INFLIGHT:
            return "building"
        failure = _FAILURES.get(key)
    if not docx_pdf.converter_available():
        return "unavailable"
    if failure and time.monotonic() - failure[0] < FAILURE_BACKOFF_SECONDS:
        return "failed"
    return "pending"


def _cached_versions(cache_dir: Path, docx_stem: str) -> list[Path]:
    """Cached PDFs of one document (any version). Matched by name, not by a
    glob: company names can carry glob metacharacters."""
    prefix = f"{docx_stem}."
    try:
        return [
            path
            for path in cache_dir.iterdir()
            if path.suffix == ".pdf"
            and path.name.startswith(prefix)
            and "." not in path.name[len(prefix):-len(".pdf")]
        ]
    except OSError:
        return []


def _prune_stale(target: Path) -> None:
    """Remove older cached PDFs of the same document."""
    stem = target.name.rsplit(".", 2)[0]
    for other in _cached_versions(target.parent, stem):
        if other != target:
            try:
                other.unlink(missing_ok=True)
            except OSError:
                pass


def get_or_create(
    report: dict,
    language: str,
    *,
    artifact: str = "memo",
    wait_seconds: float | None = None,
) -> tuple[Path | None, str | None]:
    """Return ``(pdf_path, error)`` for a memo language, converting now when
    no fresh PDF exists. Waits for a conversion another caller started."""
    docx = docx_path(report, language, artifact=artifact)
    if docx is None:
        return None, "No document is on file for this language."
    ready = cached_pdf(report, language, artifact=artifact)
    if ready is not None:
        return ready, None
    try:
        target = cache_path(docx)
    except OSError as exc:
        return None, f"Document unreadable: {exc}"
    key = str(target)
    with _LOCK:
        event = _INFLIGHT.get(key)
        owner = event is None
        if owner:
            failure = _FAILURES.get(key)
            if failure and time.monotonic() - failure[0] < FAILURE_BACKOFF_SECONDS:
                return None, failure[1]
            event = threading.Event()
            _INFLIGHT[key] = event
    if not owner:
        event.wait(WAIT_FOR_INFLIGHT_SECONDS if wait_seconds is None else wait_seconds)
        if target.exists():
            return target, None
        with _LOCK:
            failure = _FAILURES.get(key)
        if failure:
            return None, failure[1]
        return None, "building"
    try:
        if not docx_pdf.converter_available():
            return None, "No PDF converter is available on this server (Word or LibreOffice)."
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            ok, error = docx_pdf.convert_docx_to_pdf(docx, target)
        except Exception as exc:  # noqa: BLE001 — a PDF must never sink a request
            logger.exception("PDF conversion crashed for %s", docx)
            ok, error = False, f"PDF conversion crashed: {type(exc).__name__}: {exc}"
        if ok and target.exists():
            _prune_stale(target)
            with _LOCK:
                _FAILURES.pop(key, None)
            return target, None
        error = error or "PDF conversion failed."
        with _LOCK:
            _FAILURES[key] = (time.monotonic(), error)
        return None, error
    finally:
        with _LOCK:
            _INFLIGHT.pop(key, None)
        event.set()


def _background_enabled() -> bool:
    raw = os.environ.get("BSH_MEMO_PDF_BACKGROUND")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    # Under pytest a background conversion would drive the real Word; tests
    # that exercise this set BSH_MEMO_PDF_BACKGROUND=1 and mock conversion.
    return "PYTEST_CURRENT_TEST" not in os.environ


def schedule_pdf(report_id: str, *, languages: tuple[str, ...] = LANGUAGES) -> threading.Thread | None:
    """Make the PDFs for a finished memo in a background thread.

    The pipelines call this once a run reaches complete /
    complete_with_warnings (and a re-render calls it again). Returns the
    thread, or None when nothing was scheduled (background PDFs off, no
    converter, report missing or without documents). Never raises.
    """
    try:
        if not _background_enabled() or not docx_pdf.converter_available():
            return None
        report = storage.get_report(report_id)
        if report is None or not memo_prep.is_memo_kind(report.get("kind")):
            return None
        wanted = [lang for lang in languages if docx_path(report, lang) is not None]
        if not wanted:
            return None
    except Exception:  # noqa: BLE001
        logger.warning("schedule_pdf failed for %s", report_id, exc_info=True)
        return None

    def _run() -> None:
        for lang in wanted:
            try:
                fresh = storage.get_report(report_id) or report
                pdf, error = get_or_create(fresh, lang)
                if pdf is None:
                    logger.info("Background PDF for %s (%s) not made: %s", report_id, lang, error)
            except Exception:  # noqa: BLE001
                logger.exception("Background PDF crashed for %s (%s)", report_id, lang)

    thread = threading.Thread(target=_run, name=f"memo-pdf-{report_id}", daemon=True)
    thread.start()
    return thread


def invalidate(report: dict) -> int:
    """Remove every cached PDF of a report's documents (the cache key already
    ignores a changed docx; this also frees the disk). Returns files removed."""
    removed = 0
    for lang in LANGUAGES:
        docx = docx_path(report, lang)
        if docx is None:
            continue
        for path in _cached_versions(docx.parent / "_pdf", docx.stem):
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                continue
    return removed
