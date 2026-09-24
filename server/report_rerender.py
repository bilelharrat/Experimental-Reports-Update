"""Re-render a finished memo's documents from its stored package — no model call.

Used when a memo is approved or withdrawn (the document header then carries
the review stamp) and for bringing old memos onto today's renderer (R13).

``rerender_report(report_id, review=..., strict_sources=False)``:

1. loads ``logs/memo_package.json`` — the bilingual package the renderer
   consumed — and, for a review, sets ``package["run"]["review"] = {state,
   reviewer, reviewed_at}`` on an in-memory copy (the stored package is
   never edited, so resume and later re-renders start from the original);
2. refuses when any account holds ink on the report
   (``data/report_annotations/*/<id>/``) unless ``force=True`` — ink would
   float over re-paginated pages; with force the ink moves aside with the
   old documents;
3. moves the current docx pair (and, for late-stage runs, copies of the
   validation logs, inventory and manifest; for Buffett runs, the markdown
   working copies) into ``memo/_prev/<timestamp>/`` before rendering, and
   puts them back if rendering fails;
4. renders with ``memo_docx_renderer.render_memos`` (late-stage) or
   ``buffett_memo_renderer.render_package`` (Buffett) into the same paths,
   so the record's ``memo_files`` stay valid;
5. stamps ``rendered_at`` / ``renderer_version`` on the record and drops the
   stale cached PDFs (then schedules fresh ones).

Renderer support for the review stamp and for ``strict_sources`` is being
added alongside this module, so it is feature-detected: a render function
that accepts a ``review`` keyword, or a renderer module that sets
``SUPPORTS_REVIEW_STAMP = True``, can stamp; ``strict_sources`` is passed
only when the render function accepts it. When a review stamp is asked for
and the renderer cannot print one, nothing is re-rendered (the result says
``skipped``) — re-rendering would change the layout for no visible reason.

Run from the command line for R13-style re-renders::

    uv run python -m server.report_rerender --report <id> [--dry-run]
        [--force] [--lenient-sources] [--relint]
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import inspect
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import annotation_store, memo_prep, storage

logger = logging.getLogger(__name__)

COMPLETE_STATUSES = ("complete", "complete_with_warnings")
_LATE_LOG_FILES = ("validation.txt", "validation_cn.txt", "file_inventory.md", "run_manifest.md")
_BUFFETT_MARKDOWN = ("buffett_memo.en.md", "buffett_memo.zh.md")


class RerenderRefused(Exception):
    """The re-render was refused before anything changed on disk."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _run_dir(report: dict) -> Path | None:
    rel = report.get("run_dir")
    return (memo_prep.DATA_DIR.parent / str(rel)) if rel else None


def _memo_paths(report: dict) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for entry in report.get("memo_files") or []:
        if isinstance(entry, dict) and entry.get("language") in ("en", "zh") and entry.get("path"):
            paths[str(entry["language"])] = memo_prep.DATA_DIR.parent / str(entry["path"])
    return paths


# ---- capabilities ------------------------------------------------------------------


def _render_function(kind: str | None):
    if memo_prep.is_buffett_kind(kind):
        from . import buffett_memo_renderer

        return buffett_memo_renderer, buffett_memo_renderer.render_package
    from . import memo_docx_renderer

    return memo_docx_renderer, memo_docx_renderer.render_memos


def _accepts(func, name: str) -> bool:
    """True when ``func`` names ``name`` as a parameter (a bare ``**kwargs``
    does not count: it says nothing about whether the value is used)."""
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    return name in params


def renderer_capabilities(kind: str | None) -> dict:
    """What the renderer for ``kind`` can do today: ``review`` (print the
    review stamp) and ``strict_sources`` (accept the legacy source-URL
    leniency switch), plus its version string.

    A renderer that declares ``SUPPORTS_REVIEW_STAMP`` is taken at its word
    (True or False). Only a renderer that declares nothing is inspected: it
    can stamp when its render function takes ``review`` or it defines the
    stamp reader for ``package["run"]["review"]`` (``review_stamp`` /
    ``_review_stamp``)."""
    module, func = _render_function(kind)
    declared = getattr(module, "SUPPORTS_REVIEW_STAMP", None)
    if declared is not None:
        review = bool(declared)
    else:
        review = (
            _accepts(func, "review")
            or callable(getattr(module, "review_stamp", None))
            or callable(getattr(module, "_review_stamp", None))
        )
    return {
        "review": review,
        "review_kwarg": _accepts(func, "review"),
        "strict_sources": _accepts(func, "strict_sources"),
        "renderer_version": renderer_version(kind),
    }


def renderer_version(kind: str | None) -> str | None:
    """The renderer's ``RENDERER_VERSION`` when it declares one, else a short
    hash of its source file (what actually rendered the document)."""
    module, _func = _render_function(kind)
    declared = getattr(module, "RENDERER_VERSION", None)
    if declared:
        return str(declared)
    try:
        source = Path(inspect.getfile(module)).read_bytes()
    except (OSError, TypeError):
        return None
    return "src-" + hashlib.sha1(source).hexdigest()[:10]


# ---- ink ----------------------------------------------------------------------------


def ink_annotations(report_id: str) -> list[Path]:
    """Annotation folders (one per account) that hold live ink on the report.
    A cleared tombstone (meta ``cleared: true``, no drawing) is not ink."""
    root = annotation_store.ANNOTATIONS_ROOT
    try:
        safe_id = annotation_store._safe_report_id(report_id)
    except ValueError:
        return []
    found: list[Path] = []
    if not root.exists():
        return found
    for account_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        folder = account_dir / safe_id
        if not folder.is_dir():
            continue
        has_ink = any(
            (folder / name).is_file() and (folder / name).stat().st_size > 0
            for name in ("drawing.pkdrawing", "overlay.png")
        )
        if has_ink:
            found.append(folder)
    return found


# ---- helpers ------------------------------------------------------------------------


def package_revision(report: dict) -> str | None:
    """A short content hash of the stored package (else the docx pair): the
    revision a reviewer approved."""
    run_dir = _run_dir(report)
    digest = hashlib.sha256()
    package = run_dir / "logs" / "memo_package.json" if run_dir else None
    try:
        if package is not None and package.is_file():
            digest.update(package.read_bytes())
            return digest.hexdigest()[:12]
        paths = _memo_paths(report)
        if not paths:
            return None
        for lang in sorted(paths):
            if paths[lang].is_file():
                digest.update(paths[lang].read_bytes())
        return digest.hexdigest()[:12]
    except OSError:
        return None


def record_review(report: dict) -> dict | None:
    """The review stamp a record has earned (approved or withdrawn), in the
    renderer's ``{state, reviewer, reviewed_at}`` shape; None for a draft."""
    state = str(report.get("review_state") or "draft")
    if state not in ("approved", "withdrawn"):
        return None
    return {
        "state": state,
        "reviewer": report.get("reviewer_name") or report.get("reviewer"),
        "reviewed_at": report.get("reviewed_at"),
    }


def _move(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def _backup(report: dict, run_dir: Path, prev_dir: Path, *, buffett: bool) -> list[tuple[Path, Path, str]]:
    """Move/copy what the render will replace. Returns (original, backup,
    how) rows for a rollback."""
    moved: list[tuple[Path, Path, str]] = []
    for lang, path in sorted(_memo_paths(report).items()):
        if path.is_file():
            target = prev_dir / path.name
            _move(path, target)
            moved.append((path, target, "move"))
            for pdf in (path.with_suffix(".pdf"),):
                if pdf.is_file():
                    pdf_target = prev_dir / pdf.name
                    _move(pdf, pdf_target)
                    moved.append((pdf, pdf_target, "move"))
    if buffett:
        for name in _BUFFETT_MARKDOWN:
            source = run_dir / "memo" / name
            if source.is_file():
                target = prev_dir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                moved.append((source, target, "copy"))
    else:
        for name in _LATE_LOG_FILES:
            source = run_dir / "logs" / name
            if source.is_file():
                target = prev_dir / "logs" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                moved.append((source, target, "copy"))
    return moved


def _rollback(moved: list[tuple[Path, Path, str]], prev_dir: Path) -> None:
    for original, backup, how in reversed(moved):
        try:
            if how == "move":
                if original.exists():
                    original.unlink()
                _move(backup, original)
            else:
                shutil.copy2(backup, original)
        except OSError:
            logger.exception("rollback failed for %s", original)
    shutil.rmtree(prev_dir, ignore_errors=True)


def _relint(report: dict, run_dir: Path, package: dict) -> dict | None:
    """Re-run the quality lint and Chinese parity on the new pair, report-only
    (the record's status never changes on a re-render)."""
    paths = _memo_paths(report)
    if "en" not in paths or "zh" not in paths:
        return None
    try:
        from . import memo_analysis, memo_chinese_parity, memo_quality_lint, memo_structure

        structure = memo_structure.for_package(package)
        # The run's facts (check size supplied, deal terms on file, the
        # stage's hurdle, the spine's pins) for the lint's P1/P2 checks.
        lint = memo_quality_lint.lint_memo_docx(
            paths["en"], structure, **memo_analysis._lint_context(run_dir, structure)
        ).to_dict()
        parity = memo_chinese_parity.lint_chinese_memo_pair(
            paths["en"], paths["zh"], structure, package=package
        ).to_dict()
    except Exception as exc:  # noqa: BLE001
        return {"at": _iso(_now()), "error": f"{type(exc).__name__}: {exc}"}

    def slim(payload: dict) -> dict:
        return {key: payload.get(key) for key in ("status", "p0_count", "finding_count")}

    return {"at": _iso(_now()), "quality_lint": slim(lint), "chinese_parity": slim(parity)}


# ---- the re-render ------------------------------------------------------------------------


def plan_rerender(report_id: str, *, review: dict | None = None) -> dict:
    """What a re-render would do, without doing it (``--dry-run``)."""
    report = storage.get_report(report_id)
    if report is None:
        raise RerenderRefused("not_found", "Report not found")
    kind = report.get("kind")
    caps = renderer_capabilities(kind)
    run_dir = _run_dir(report)
    return {
        "report_id": report_id,
        "kind": kind,
        "status": report.get("status"),
        "capabilities": caps,
        "package": bool(run_dir and (run_dir / "logs" / "memo_package.json").is_file()),
        "documents": {lang: str(path) for lang, path in _memo_paths(report).items() if path.is_file()},
        "ink": [str(p) for p in ink_annotations(report_id)],
        "would_skip": bool(review is not None and not caps["review"]),
    }


def rerender_report(
    report_id: str,
    *,
    review: dict | None = None,
    strict_sources: bool = False,
    force: bool = False,
    relint: bool = False,
    reason: str = "review",
) -> dict:
    """Re-render one finished memo from its stored package. See the module
    docstring. Returns ``{"status": "rendered" | "skipped" | "failed", ...}``;
    raises ``RerenderRefused`` (nothing changed) for a missing report or
    package, an unfinished run, or ink without ``force``."""
    report = storage.get_report(report_id)
    if report is None:
        raise RerenderRefused("not_found", "Report not found")
    kind = report.get("kind")
    if not memo_prep.is_memo_kind(kind):
        raise RerenderRefused("not_memo", "Only investment memos can be re-rendered")
    if str(report.get("status") or "") not in COMPLETE_STATUSES:
        raise RerenderRefused("not_finished", "Only finished memos can be re-rendered")
    run_dir = _run_dir(report)
    package_path = run_dir / "logs" / "memo_package.json" if run_dir else None
    if package_path is None or not package_path.is_file():
        raise RerenderRefused("no_package", "The memo package is not on disk; nothing to render from")
    paths = _memo_paths(report)
    if "en" not in paths or "zh" not in paths:
        raise RerenderRefused("no_documents", "The report records no English/Chinese document paths")
    caps = renderer_capabilities(kind)
    buffett = memo_prep.is_buffett_kind(kind)
    requested_review = review is not None
    if review is None:
        # A plain re-render keeps the stamp the record already earned.
        review = record_review(report)
    if requested_review and not caps["review"]:
        note = (
            "The renderer cannot print a review stamp yet; the documents were "
            "left as they are."
        )
        logger.info("rerender %s skipped: %s", report_id, note)
        return {"status": "skipped", "reason": note, "capabilities": caps}
    inks = ink_annotations(report_id)
    if inks and not force:
        raise RerenderRefused(
            "ink",
            "This report has ink annotations that would drift on a re-rendered "
            "document. Re-render with force to move the ink aside with the old "
            "documents.",
        )
    try:
        package = json.loads(package_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RerenderRefused("bad_package", f"The memo package is unreadable: {exc}") from exc
    if not isinstance(package, dict):
        raise RerenderRefused("bad_package", "The memo package is not an object")

    payload = copy.deepcopy(package)
    if review is not None:
        run_meta = payload.get("run") if isinstance(payload.get("run"), dict) else {}
        run_meta = dict(run_meta)
        run_meta["review"] = {
            "state": review.get("state"),
            "reviewer": review.get("reviewer"),
            "reviewed_at": review.get("reviewed_at"),
        }
        payload["run"] = run_meta

    started = _now()
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    prev_dir = run_dir / "memo" / "_prev" / stamp
    suffix = 1
    while prev_dir.exists():
        suffix += 1
        prev_dir = run_dir / "memo" / "_prev" / f"{stamp}-{suffix}"
    moved = _backup(report, run_dir, prev_dir, buffett=buffett)
    module, render = _render_function(kind)
    kwargs: dict[str, Any] = {}
    if caps["review_kwarg"] and review is not None:
        kwargs["review"] = review
    if caps["strict_sources"] and not buffett:
        kwargs["strict_sources"] = strict_sources
    notes: list[str] = []
    if not strict_sources and not caps["strict_sources"] and not buffett:
        notes.append("renderer has no strict_sources switch; the source-URL rule applied as usual")
    try:
        if buffett:
            rendered = render(
                payload, run_dir=run_dir, memo_paths={"en": paths["en"], "zh": paths["zh"]}, **kwargs
            )
        else:
            rendered = render(
                payload,
                out_en=paths["en"],
                out_zh=paths["zh"],
                manifest_path=run_dir / "logs" / "run_manifest.md",
                inventory_path=run_dir / "logs" / "file_inventory.md",
                **kwargs,
            )
        if not paths["en"].is_file() or not paths["zh"].is_file():
            raise RuntimeError("the renderer did not write both documents")
    except Exception as exc:  # noqa: BLE001 — restore the old pair, report the error
        logger.warning("rerender %s failed: %s", report_id, exc, exc_info=True)
        _rollback(moved, prev_dir)
        return {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "capabilities": caps,
            "notes": notes,
        }

    moved_ink: list[str] = []
    for folder in inks:
        target = prev_dir / "annotations" / folder.parent.name / folder.name
        try:
            _move(folder, target)
            moved_ink.append(memo_prep._rel(target))
        except OSError:
            logger.exception("could not move ink %s aside", folder)

    finished = _now()
    history = list(report.get("rerender_history") or [])[-19:]
    entry = {
        "at": _iso(finished),
        "reason": reason,
        "review_state": (review or {}).get("state"),
        "prev_dir": memo_prep._rel(prev_dir),
        "renderer_version": caps.get("renderer_version"),
        "moved_ink": moved_ink,
    }
    history.append(entry)
    rendered = rendered if isinstance(rendered, dict) else {}
    patch: dict[str, Any] = {
        "rendered_at": _iso(finished),
        "renderer_version": rendered.get("renderer_version") or caps.get("renderer_version"),
        "rerender_history": history,
    }
    # What the render says about the call (Buffett: decision, buy price in
    # both languages, kind of Pass, call label, valuation) goes back on the
    # record, so an old record gains the fields a fresh run writes.
    report_fields = getattr(module, "report_fields", None)
    if callable(report_fields) and rendered:
        try:
            fields = report_fields(rendered)
        except Exception:  # noqa: BLE001
            logger.warning("report_fields failed after rerender of %s", report_id, exc_info=True)
            fields = None
        if isinstance(fields, dict):
            patch.update({key: value for key, value in fields.items() if key != "rerender_history"})
    if relint and not buffett:
        relint_result = _relint(report, run_dir, package)
        if relint_result is not None:
            patch["relint"] = relint_result
    updated = storage.update_report(report_id, **patch) or report
    try:
        from . import report_reader

        report_reader.persist_reader_block(report_id)
    except Exception:  # noqa: BLE001
        logger.warning("reader block refresh after rerender failed for %s", report_id, exc_info=True)
    try:
        from . import memo_pdf

        memo_pdf.invalidate(updated)
        memo_pdf.schedule_pdf(report_id)
    except Exception:  # noqa: BLE001
        logger.warning("PDF refresh after rerender failed for %s", report_id, exc_info=True)
    return {
        "status": "rendered",
        "prev_dir": memo_prep._rel(prev_dir),
        "moved_ink": moved_ink,
        "capabilities": caps,
        "notes": notes,
        "rendered_at": patch["rendered_at"],
        **({"relint": patch["relint"]} if "relint" in patch else {}),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-render finished memos from their stored packages.")
    parser.add_argument("--report", action="append", required=True, help="report id (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen")
    parser.add_argument("--force", action="store_true", help="move ink aside and re-render anyway")
    parser.add_argument(
        "--lenient-sources",
        action="store_true",
        help="pass strict_sources=False (legacy packages without source URLs)",
    )
    parser.add_argument("--relint", action="store_true", help="re-run lint and parity, report-only")
    args = parser.parse_args(argv)
    status = 0
    for report_id in args.report:
        try:
            if args.dry_run:
                result = plan_rerender(report_id)
            else:
                result = rerender_report(
                    report_id,
                    strict_sources=not args.lenient_sources,
                    force=args.force,
                    relint=args.relint,
                    reason="rerender",
                )
        except RerenderRefused as exc:
            result = {"status": "refused", "code": exc.code, "detail": exc.detail}
            status = 1
        print(json.dumps({"report_id": report_id, **result}, ensure_ascii=False, indent=2))
        if result.get("status") == "failed":
            status = 1
    return status


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
