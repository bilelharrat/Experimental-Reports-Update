"""BSH's previous memo on a company reaches the next run as a verdict, a
score, an entry mark and a date — pinned verbatim, never as evidence."""
from __future__ import annotations

import json

import pytest

from server import claude_runner, memo_analysis, memo_prep, storage

SPINE = {
    "verdict": "Watch",
    "scorecard": {"total": 72},
    "entry": {"valuation": "$900M post-money"},
    "recommendation_sentence": "Recommendation: watch ACME — the trigger is a priced round.",
}


@pytest.fixture
def data_root(monkeypatch, tmp_path):
    root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", root / "memos")
    return root


def _delivered(
    data_root, company_id, *, created_at, spine, status="complete", kind=memo_prep.LATESTAGE_KIND
):
    run_dir = data_root / "memos" / company_id / f"run-{created_at[:10]}-{status}-{kind[:3]}"
    (run_dir / "logs" / "english_units").mkdir(parents=True, exist_ok=True)
    if spine is not None:
        (run_dir / "logs" / "english_units" / "spine.json").write_text(
            json.dumps({"shared_facts": spine}), encoding="utf-8"
        )
    report = storage.create_report_record(
        company_id=company_id,
        company_name="ACME",
        kind=kind,
        status=status,
        run_dir=memo_prep._rel(run_dir),
        memo_files=[],
    )
    storage.update_report(report["id"], created_at=created_at)
    return storage.get_report(report["id"])


def test_prior_view_is_the_latest_earlier_delivered_memo_of_the_same_kind(data_root, monkeypatch):
    first = _delivered(
        data_root, "acme", created_at="2026-07-01T10:00:00Z",
        spine={**SPINE, "verdict": "Pass", "scorecard": {"total": 55}},
    )
    second = _delivered(data_root, "acme", created_at="2026-08-01T10:00:00Z", spine=SPINE)
    # Neither a failed run, a Buffett memo, a v1 memo (no spine) nor a
    # later run is the prior view.
    _delivered(data_root, "acme", created_at="2026-08-15T10:00:00Z", spine=SPINE, status="failed")
    _delivered(data_root, "acme", created_at="2026-08-20T10:00:00Z", spine=SPINE, kind=memo_prep.BUFFETT_KIND)
    _delivered(data_root, "acme", created_at="2026-08-25T10:00:00Z", spine=None)
    current = _delivered(data_root, "acme", created_at="2026-09-01T10:00:00Z", spine=None, status="analyzing")
    _delivered(data_root, "acme", created_at="2026-09-05T10:00:00Z", spine=SPINE)

    prior = memo_analysis.prior_view_for_report(current)
    assert prior["report_id"] == second["id"]
    assert prior["sentence"] == (
        "BSH's previous memo on ACME (2026-08-01) concluded Watch — 72/100 at $900M post-money."
    )
    assert prior["recommendation"] == SPINE["recommendation_sentence"]
    assert prior["verdict"] == "Watch" and prior["date"] == "2026-08-01"
    # The first memo on a company has none; the second sees the first.
    assert memo_analysis.prior_view_for_report(first) is None
    assert memo_analysis.prior_view_for_report(second)["report_id"] == first["id"]
    assert memo_analysis.prior_view_for_report({"id": "x", "kind": memo_prep.LATESTAGE_KIND}) is None

    # Registered per run and pinned verbatim; BSH_MEMO_PRIOR_VIEW=0 turns it off.
    run_dir = data_root / "memos" / "acme" / "run-current"
    run_dir.mkdir(parents=True)
    monkeypatch.delenv("BSH_MEMO_PRIOR_VIEW", raising=False)
    memo_analysis._register_prior_view(current, run_dir)
    try:
        facts: dict = {}
        assert claude_runner.pin_prior_view(facts, run_dir) == prior["sentence"]
        assert facts["prior_view_sentence"] == prior["sentence"]
        monkeypatch.setenv("BSH_MEMO_PRIOR_VIEW", "0")
        memo_analysis._register_prior_view(current, run_dir)
        assert claude_runner.pin_prior_view({}, run_dir) is None
    finally:
        claude_runner.register_memo_run_prior_view(run_dir, None)


def test_prior_view_fits_its_pin_and_compares_timestamps_as_instants(data_root):
    long_entry = {**SPINE, "entry": {"valuation": "x" * 40}}
    _delivered(data_root, "longco", created_at="2026-08-01T10:00:00Z", spine=long_entry)
    current = _delivered(data_root, "longco", created_at="2026-09-01T10:00:00Z", spine=None, status="analyzing")
    report = {**current, "company_name": "N" * 170}
    prior = memo_analysis.prior_view_for_report(report)
    # Too long with the entry mark: the mark goes, the verdict stays.
    assert prior["sentence"].endswith("concluded Watch — 72/100.")
    assert len(prior["sentence"]) <= claude_runner.MEMO_PRIOR_VIEW_SCHEMA["maxLength"]
    assert memo_analysis.prior_view_for_report({**current, "company_name": "N" * 260}) is None
    # "+00:00" and "Z" stamps: an earlier memo stamped "…+00:00" at 09:00
    # is earlier than a run stamped "…Z" at 10:00 on the same day, although
    # the text sorts the other way at the seconds' fraction.
    _delivered(data_root, "tsco", created_at="2026-09-01T09:00:00.500000+00:00", spine=SPINE)
    run = _delivered(data_root, "tsco", created_at="2026-09-01T09:00:00Z", spine=None, status="analyzing")
    assert memo_analysis.prior_view_for_report(run) is None
    later = _delivered(data_root, "tsco", created_at="2026-09-01T09:00:01Z", spine=None, status="analyzing")
    assert memo_analysis.prior_view_for_report(later) is not None
