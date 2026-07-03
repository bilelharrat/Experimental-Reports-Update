from __future__ import annotations

import json

from server import auth_store, local_generation, stock_research, storage


def _redirect_runtime(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")
    monkeypatch.setattr(auth_store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth_store, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(stock_research, "STOCK_RESEARCH_ROOT", tmp_path / "stock_research")


def test_generate_local_runtime_state_materializes_all_startup_seeds(
    monkeypatch,
    tmp_path,
):
    _redirect_runtime(monkeypatch, tmp_path)

    summary = local_generation.generate_local_runtime_state()

    assert summary["data_dir"] == str(tmp_path)
    assert summary["company_records_materialized"] == 1
    assert summary["company_count"] >= 1
    assert summary["users_bootstrapped"] is True
    assert summary["fixture_companies_included"] is False
    assert summary["stock_research_tracker_count"] == 8
    assert storage.get_company("zainar-inc")["positioning"]["category"]
    assert storage.get_company("databricks") is None
    assert auth_store.USERS_FILE.exists()
    assert (
        stock_research.STOCK_RESEARCH_ROOT
        / "trackers"
        / "us-macro"
        / "tracker.json"
    ).exists()


def test_local_generation_cli_prints_json_summary(monkeypatch, tmp_path, capsys):
    _redirect_runtime(monkeypatch, tmp_path)

    rc = local_generation.main(["--skip-users", "--skip-stock-research", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data_dir"] == str(tmp_path)
    assert payload["users_bootstrapped"] is False
    assert payload["stock_research_tracker_count"] is None
    assert payload["company_records_materialized"] == 1


def test_local_generation_cli_can_include_fixture_company_pack(
    monkeypatch,
    tmp_path,
    capsys,
):
    _redirect_runtime(monkeypatch, tmp_path)

    rc = local_generation.main([
        "--skip-users",
        "--skip-stock-research",
        "--include-fixture-companies",
        "--json",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fixture_companies_included"] is True
    assert payload["company_records_materialized"] == 5
    assert storage.get_company("databricks")["status"] == "private"
    assert storage.get_company("nextnav")["company_type"] == "public"
    assert storage.get_company("fixture-empty-company")["products"] == []
