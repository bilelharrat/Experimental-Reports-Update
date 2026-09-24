"""A company whose id is only Chinese characters must get a memo.

``storage.upsert_company_from_match`` slugs a Chinese legal name into a
CJK-only id, and ``serena_analysis`` used an ASCII-stripping ``_safe_id``
for the lessons path and the completed-run lookup: the stripped id was ""
and every late-stage / Auto memo run for such a company died with
``ValueError('Invalid company id')`` right after prep (R14). The run below
goes end to end through ``memo_analysis._run`` with the same fakes as
``test_memo_analysis`` (no model call).
"""
from __future__ import annotations

import test_memo_analysis as fixtures

from server import (
    claude_runner,
    company_paths,
    job_progress,
    memo_analysis,
    memo_prep,
    serena_analysis,
    storage,
)

memo_env = fixtures.memo_env  # the shared fixture: isolated data root, no PDFs

CJK_ID = "中经网数据有限公司"


def _make_cjk_memo_report(data_root):
    run_id = "2026-09-22__101010"
    key = company_paths.storage_key(CJK_ID)
    run_dir = data_root / "memos" / key / f"{run_id}__{key}__memo-run"
    memo_dir = run_dir / "memo"
    memo_dir.mkdir(parents=True)
    en_path = memo_dir / f"{CJK_ID} - Investment Memo - {run_id}.docx"
    zh_path = memo_dir / f"{CJK_ID} - 投资备忘录 - {run_id}.docx"
    report = storage.create_report_record(
        company_id=CJK_ID,
        company_name=CJK_ID,
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind="investment_memo_latestage",
        status="analyzing",
        progress=95,
        stage="Rendering PDF previews",
        run_id=run_id,
        run_dir=memo_prep._rel(run_dir),
        memo_files=[
            {"language": "en", "path": memo_prep._rel(en_path)},
            {"language": "zh", "path": memo_prep._rel(zh_path)},
        ],
    )
    return report, run_dir


def test_memo_run_completes_for_a_chinese_only_company_id(memo_env, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_RENDER_PDF_PREVIEWS", raising=False)
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    report, run_dir = _make_cjk_memo_report(memo_env)
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit(
        "job_init",
        kind="memo",
        title=f"Investment memo — {CJK_ID}",
        report_id=report["id"],
        company_id=CJK_ID,
        run_id=report["run_id"],
    )

    def fake_run_investment_memo(**kwargs):
        assert kwargs["company_slug"] == CJK_ID
        fixtures._write_memo_package(run_dir)
        return {"ok": True, "cost_usd": 0.0, "duration_ms": 1}

    monkeypatch.setattr(claude_runner, "run_investment_memo", fake_run_investment_memo)

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete", updated.get("error")
    # The lessons path the run consulted is keyed like every other store.
    assert serena_analysis.memo_lessons_path(CJK_ID).parent == (
        serena_analysis.TRAINING_ROOT / company_paths.storage_key(CJK_ID)
    )
    # And the finished memo is visible to Memo Studio's grader.
    assert [row["id"] for row in serena_analysis.completed_memo_runs(CJK_ID)] == [report["id"]]
