"""Bootstrap a Hormuz V3 appendix run for one target date.

Synchronous handshake between ``POST /external/hormuz/appendix/<date>/
generate`` and the long-running worker in ``hormuz_analysis.py``. One
idempotent run per date: re-generating a date reuses
``data/hormuz_appendix/<date>/`` and truncates its ``logs/stream.jsonl``.

Mirrors ``memo_prep`` but is not company-scoped and runs no scope check.
"""
from __future__ import annotations

import logging

from . import hormuz_store, job_progress, storage

logger = logging.getLogger(__name__)

SKILL_NAME = "bsh-hormuz-appendix-v3"
SKILL_VERSION = 3
JOB_KIND = "hormuz"


def stream_path(run_dir):
    """Match memo_prep's convention so the shared resolver/stream work."""
    from pathlib import Path

    return Path(run_dir) / "logs" / "stream.jsonl"


def bootstrap_appendix_run(target_date: str) -> dict:
    """Prep + launch the appendix worker for ``target_date``.

    Raises ValueError for caller-facing errors (bad date, no sources).
    Returns a result dict with the report id and run dir.
    """
    if not hormuz_store.is_valid_date(target_date):
        raise ValueError(f"Bad target date (expected YYYY-MM-DD): {target_date!r}")

    src_files = hormuz_store.source_files(target_date)
    if not src_files:
        raise ValueError(
            f"No source reports uploaded for {target_date}. Upload the "
            f"daily report(s) for that date first."
        )

    prev_date = hormuz_store.previous_date(target_date)
    prev_files = hormuz_store.source_files(prev_date) if prev_date else []

    run_dir = hormuz_store.appendix_dir(target_date)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    # truncate=True → a re-run starts a clean transcript for this date.
    stream = job_progress.ProgressLog(stream_path(run_dir), truncate=True)

    cn_base, en_base = hormuz_store.output_basenames(target_date)
    out = hormuz_store.appendix_output_paths(target_date)

    date_range = (
        f"{prev_date} → {target_date}" if prev_date else target_date
    )

    report = storage.create_report_record(
        kind="hormuz_appendix",
        report_type="Hormuz V3 Appendix",
        status="prepping",
        stage="Preparing run",
        progress=5,
        target_date=target_date,
        previous_date=prev_date,
        date_range=date_range,
        run_dir=hormuz_store._rel(run_dir),
        skill=SKILL_NAME,
        skill_version=SKILL_VERSION,
        source_files=[hormuz_store._rel(p) for p in src_files],
        previous_source_files=[hormuz_store._rel(p) for p in prev_files],
        appendix_files={
            "cn_md": hormuz_store._rel(out["cn_md"]),
            "cn_pdf": hormuz_store._rel(out["cn_pdf"]),
            "en_md": hormuz_store._rel(out["en_md"]),
            "en_pdf": hormuz_store._rel(out["en_pdf"]),
        },
        warnings=[],
    )

    stream.emit(
        "job_init",
        kind=JOB_KIND,
        title=f"Hormuz V3 appendix — {target_date}",
        subtitle=date_range,
        report_id=report["id"],
        target_date=target_date,
        run_dir=str(run_dir),
        skill=SKILL_NAME,
    )
    stream.emit(
        "stage",
        stage="prep_started",
        message=f"Preparing appendix for {target_date}",
    )
    stream.emit(
        "sources_resolved",
        target_date=target_date,
        previous_date=prev_date,
        source_files=[p.name for p in src_files],
        previous_source_files=[p.name for p in prev_files],
    )

    if not prev_files:
        report_warn = "No previous-day baseline found — probability deltas will be marked N/A."
        storage.update_report(report["id"], warnings=[report_warn])
        stream.emit("stage", stage="no_baseline", message=report_warn)

    storage.update_report(
        report["id"],
        status="analyzing",
        stage="Generating bilingual appendix",
        progress=10,
    )
    stream.emit(
        "stage",
        stage="prep_complete",
        message="Prep finished — handing off to appendix worker",
    )

    # Local import to avoid a circular import at module load.
    from . import hormuz_analysis

    hormuz_analysis.start_analysis(report["id"])

    return {
        "report_id": report["id"],
        "target_date": target_date,
        "previous_date": prev_date,
        "run_dir": str(run_dir),
        "run_dir_rel": hormuz_store._rel(run_dir),
        "stream_path": str(stream_path(run_dir)),
    }
