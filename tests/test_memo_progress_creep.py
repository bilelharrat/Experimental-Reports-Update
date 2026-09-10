"""Unit tests for memo progress heartbeat (keeps the meter off 15%)."""

from __future__ import annotations

import time

import pytest

from server import memo_analysis, memo_prep, storage


@pytest.fixture
def memo_env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    return data_root


def test_creeping_report_progress_advances_past_floor(memo_env):
    report = storage.create_report_record(
        company_id="amd",
        company_name="AMD",
        status="analyzing",
        stage="Running parallel analysis passes",
        progress=15,
        kind="investment_memo",
    )
    with memo_analysis._creeping_report_progress(
        report["id"],
        floor=15,
        ceiling=78,
        interval_sec=0.05,
        half_life_sec=0.2,
        stage="Running parallel analysis passes",
    ):
        time.sleep(0.35)

    updated = storage.get_report(report["id"])
    assert updated is not None
    assert int(updated["progress"]) > 15
    assert int(updated["progress"]) <= 78


def test_creeping_report_progress_does_not_overwrite_higher_milestone(memo_env):
    report = storage.create_report_record(
        company_id="amd",
        status="analyzing",
        progress=85,
        kind="investment_memo",
    )
    with memo_analysis._creeping_report_progress(
        report["id"],
        floor=15,
        ceiling=78,
        interval_sec=0.05,
        half_life_sec=0.05,
    ):
        time.sleep(0.2)

    updated = storage.get_report(report["id"])
    assert updated is not None
    assert int(updated["progress"]) == 85
