"""Before spending: the readiness pre-flight, run estimates, the provider
limit record, and the fund return policy that memos will answer to."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from server import api, claude_runner, fund_policy, memo_prep, provider_limits, storage
from server.main import app

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def client():
    return TestClient(app)


# ---- provider limit record -------------------------------------------------------------


def test_limit_parsed_from_the_message_and_expires():
    entry = provider_limits.record_provider_limit(
        "Claude usage limit reached. Resets in 2 hr 30 min", now=NOW
    )
    assert entry["reset_at"] == "2026-09-22T14:30:00Z"
    assert entry["reset_parsed"] is True
    live = provider_limits.current_limit(now=NOW + timedelta(hours=1))
    assert live and live["seconds_remaining"] == 5400
    assert provider_limits.current_limit(now=NOW + timedelta(hours=3)) is None


def test_limit_reset_from_epoch_or_clock_time_and_default_expiry():
    epoch_ms = int((NOW + timedelta(minutes=90)).timestamp() * 1000)
    assert provider_limits.record_provider_limit("rate_limit", epoch_ms, now=NOW)["reset_at"] == (
        "2026-09-22T13:30:00Z"
    )
    la = provider_limits.record_provider_limit(
        "You've hit your limit · resets 3pm (America/Los_Angeles)", now=NOW
    )
    assert la["reset_at"] == "2026-09-22T22:00:00Z"  # 3pm PDT
    unknown = provider_limits.record_provider_limit("quota exceeded", now=NOW)
    assert unknown["reset_parsed"] is False
    assert unknown["reset_at"] == "2026-09-22T12:30:00Z"
    assert provider_limits.clear_provider_limit() is True
    assert provider_limits.current_limit(now=NOW) is None


def test_limit_record_lives_in_the_data_dir():
    provider_limits.record_provider_limit("usage limit", now=datetime.now(timezone.utc))
    assert (storage.DATA_DIR / "_api" / "provider_limits.json").exists()


# ---- readiness ---------------------------------------------------------------------------


def test_readiness_uses_only_free_signals(client, monkeypatch):
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(
        claude_runner, "health_check", lambda **_k: pytest.fail("readiness must never spawn a prompt")
    )
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    ready = client.get("/api/reports/readiness?company_id=zainar-inc").json()
    assert ready["ready"] is True
    assert ready["company"]["exists"] is True and ready["company"]["real_name"] is True
    assert ready["engines"]["gemini"]["available"] is True

    provider_limits.record_provider_limit("usage limit reached; resets in 3 hr")
    limited = client.get("/api/reports/readiness?company_id=zainar-inc").json()
    assert limited["ready"] is False
    assert limited["blockers"][0]["code"] == "claude_limited"
    assert limited["blockers"][0]["reset_at"]
    assert limited["blockers"][0]["zh"]
    assert limited["suggest_engine"] == "gemini"
    assert limited["engines"]["claude"]["limited"] is True
    # The same run on Gemini is fine.
    assert client.get("/api/reports/readiness?company_id=zainar-inc&engine=gemini").json()["ready"] is True


def test_readiness_flags_missing_company_cli_and_key(client, monkeypatch):
    monkeypatch.setattr(claude_runner, "is_available", lambda: False)
    body = client.get("/api/reports/readiness?company_id=nope").json()
    codes = [b["code"] for b in body["blockers"]]
    assert codes == ["company_not_found", "claude_cli_missing"]
    assert body["suggest_engine"] is None  # no Gemini key either
    gemini = client.get("/api/reports/readiness?engine=gemini").json()
    assert [b["code"] for b in gemini["blockers"]] == ["gemini_key_missing"]
    assert client.get("/api/reports/readiness?engine=gpt").status_code == 400


# ---- estimates -----------------------------------------------------------------------------


def _finished(report_type, *, kind=memo_prep.LATESTAGE_KIND, duration=None, cost=None, status="complete", **extra):
    return storage.create_report_record(
        company_id="acme",
        report_type=report_type,
        kind=kind,
        status=status,
        claude_duration_ms=duration,
        claude_cost_usd=cost,
        **extra,
    )


def test_estimates_only_for_settings_with_three_runs(client):
    for duration, cost in ((1_200_000, 6.0), (1_800_000, 10.0), (2_400_000, 17.6)):
        _finished(memo_prep.REPORT_TYPE, duration=duration, cost=cost)
    for duration in (300_000, 400_000, 500_000):
        _finished(memo_prep.BUFFETT_REPORT_TYPE, kind=memo_prep.BUFFETT_KIND, duration=duration)
    _finished(memo_prep.REPORT_TYPE, duration=900_000, cost=2.0, structure_mode="compact")
    _finished(memo_prep.REPORT_TYPE, duration=9_999_999, cost=99.0, status="failed_during_analysis")
    body = client.get("/api/reports/estimates").json()
    assert body["min_samples"] == 3
    assert body["cost_basis"] == "api_equivalent"
    rows = {(r["report_type"], r["structure_mode"]): r for r in body["estimates"]}
    assert set(rows) == {(memo_prep.REPORT_TYPE, "full"), (memo_prep.BUFFETT_REPORT_TYPE, "full")}
    late = rows[(memo_prep.REPORT_TYPE, "full")]
    assert late["samples"] == 3
    assert late["duration_ms"] == {"median": 1_800_000.0, "min": 1_200_000.0, "max": 2_400_000.0}
    assert late["cost_usd"]["median"] == 10.0
    assert late["model_quality"] == "best" and late["engine"] == "claude"
    buffett = rows[(memo_prep.BUFFETT_REPORT_TYPE, "full")]
    assert buffett["unpriced"] is True and buffett["cost_usd"] is None


# ---- fund policy ------------------------------------------------------------------------------


def test_policy_is_unset_by_default_and_reaches_no_prompt(client):
    body = client.get("/api/settings/fund-policy").json()
    assert body["set"] is False
    assert body["stages"] == {"early": None, "growth": None, "late": None}
    for stage in ("early", "growth", "late", None, "bogus"):
        assert fund_policy.prompt_block(stage) == ""
    assert fund_policy.hurdle_text("late") == ""


def test_policy_needs_settings_update_and_validates(client, monkeypatch):
    monkeypatch.setattr(api, "_caller_role", lambda request: "analyst")
    assert client.put("/api/settings/fund-policy", json={"stages": {}}).status_code == 403
    monkeypatch.setattr(api, "_caller_role", lambda request: "partner")
    monkeypatch.setattr(api, "_caller_email", lambda request: "seline.sun@bshfoundation.org")
    for bad in (
        {"stages": {"late": {"basis": "after tax"}}},
        {"stages": {"seed": {"target_moic": 3}}},
        {"stages": {"late": {"target_moic": 0.5}}},
        {"stages": {"late": {"target_irr_pct": "a lot"}}},
        {"stages": {"late": {"hurdle": 2}}},
        {"extra": 1},
    ):
        assert client.put("/api/settings/fund-policy", json=bad).status_code == 400, bad
    saved = client.put(
        "/api/settings/fund-policy",
        json={
            "stages": {
                "late": {
                    "target_moic": 2,
                    "target_irr_pct": "20%",
                    "max_hold_years": 5,
                    "max_position_pct": 10,
                    "basis": "Net",
                }
            }
        },
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["set"] is True
    assert body["stages"]["late"] == {
        "target_moic": 2.0,
        "target_irr_pct": 20.0,
        "max_hold_years": 5.0,
        "max_position_pct": 10.0,
        "basis": "net",
    }
    assert body["updated_by"] == "seline.sun@bshfoundation.org"
    block = fund_policy.prompt_block("late")
    assert "2x (net)" in block and "20% (net)" in block and "5 years" in block and "10% of the fund" in block
    assert fund_policy.prompt_block("growth") == ""
    assert fund_policy.hurdle_text("late") == "2x net MOIC / 20% net IRR over at most 5 years (late stage)"
    cleared = client.put("/api/settings/fund-policy", json={"stages": {"late": None}}).json()
    assert cleared["set"] is False


def test_fund_context_is_read_only_and_never_prompted(client, monkeypatch):
    from server import portfolio, thesis_store

    portfolio.save_reserves_settings({"fund_size_musd": 250})
    thesis_store.save_thesis({"check_size_min_musd": 2, "check_size_max_musd": 10})
    fund_policy.save_policy({"stages": {"late": {"target_moic": 3}}})
    body = client.get("/api/settings/fund-policy").json()
    assert body["context"] == {
        "fund_size_musd": 250.0,
        "check_size_min_musd": 2.0,
        "check_size_max_musd": 10.0,
    }
    assert "250" not in fund_policy.prompt_block("late")
    assert fund_policy.save_policy({"clear": True})["set"] is False
