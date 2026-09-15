"""Read caches behind firm search, signal watch and per-company reports: correct copies,
invalidation on report-file and data-dir changes, and stale-while-rebuilding search."""
from __future__ import annotations

import json
import threading
import time

import pytest
import yaml

from server import firm, firm_search, portfolio, signal_score, signal_watch, storage


def _seed(*companies: dict) -> None:
    storage._write_yaml(storage.COMPANIES_FILE, list(companies) or [{"id": "acme-ai", "name": "Acme AI", "status": "private"}])


def _write_report(report_id: str, company_id: str, created_at: str, **extra) -> None:
    storage._write_yaml(storage.REPORTS_DIR / f"{report_id}.yaml", {"id": report_id, "company_id": company_id, "created_at": created_at, **extra})


def _point_data_dir(monkeypatch, root) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", root / "threads")


def _wait_for_index_idle(timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        entry = firm_search._INDEXES.get(str(storage.DATA_DIR))
        if entry is None or not entry["building"]:
            return
        time.sleep(0.01)
    raise AssertionError("firm search index rebuild did not finish")


def test_list_reports_for_returns_only_that_companys_independent_copies():
    _write_report("r1", "acme", "2026-01-01", status="complete")
    _write_report("r2", "beta", "2026-02-01")
    _write_report("r3", "acme", "2026-03-01", stages=[{"name": "scope"}])

    got = storage.list_reports_for("acme")
    assert [r["id"] for r in got] == ["r3", "r1"]
    assert got == [r for r in storage.list_reports() if r.get("company_id") == "acme"]
    assert storage.list_reports_for("missing") == []

    got[0]["stages"].append({"name": "mutated"})
    got[1]["status"] = "mutated"
    again = storage.list_reports_for("acme")
    assert again[0]["stages"] == [{"name": "scope"}]
    assert again[1]["status"] == "complete"

    by_company = storage.reports_by_company()
    assert sorted(by_company) == ["acme", "beta"]
    by_company["acme"][0]["id"] = "mutated"
    assert storage.list_reports_for("acme")[0]["id"] == "r3"
    assert storage.list_reports()[0]["id"] == "r3"


def test_reports_index_follows_file_changes_and_data_dir(monkeypatch, tmp_path):
    _write_report("r1", "acme", "2026-01-01", status="queued")
    version = storage.reports_version()
    assert storage.reports_version() == version
    assert storage.list_reports_for("acme")[0]["status"] == "queued"

    storage.update_report("r1", status="complete")
    assert storage.list_reports_for("acme")[0]["status"] == "complete"
    assert storage.reports_version() != version

    _write_report("r2", "acme", "2026-02-01")
    assert [r["id"] for r in storage.list_reports_for("acme")] == ["r2", "r1"]
    (storage.REPORTS_DIR / "r2.yaml").unlink()
    assert [r["id"] for r in storage.list_reports_for("acme")] == ["r1"]
    _write_report("r3", "acme", "2026-03-01")
    storage.delete_report("r3")
    assert [r["id"] for r in storage.list_reports_for("acme")] == ["r1"]

    version = storage.reports_version()
    _point_data_dir(monkeypatch, tmp_path / "other")
    assert storage.list_reports_for("acme") == []
    assert storage.list_reports() == []
    assert storage.reports_version() != version
    _write_report("r9", "acme", "2026-09-01")
    assert [r["id"] for r in storage.list_reports_for("acme")] == ["r9"]


def test_read_yaml_matches_the_pure_python_loader_and_rejects_bad_yaml(tmp_path):
    assert storage._SAFE_LOADER is (yaml.CSafeLoader if yaml.__with_libyaml__ else yaml.SafeLoader)
    good = tmp_path / "good.yaml"
    storage._write_yaml(good, {"名称": "值", "n": [1, 2.5, None, True], "nested": {"at": "2026-01-01T00:00:00Z"}})
    good.write_text(good.read_text(encoding="utf-8") + "when: 2026-01-01\n", encoding="utf-8")
    assert storage._read_yaml(good, None) == yaml.safe_load(good.read_text(encoding="utf-8"))
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        storage._read_yaml(bad, None)
    assert storage._read_yaml_lenient(bad, {"default": 1}) == {"default": 1}


def test_firm_search_serves_previous_index_while_a_rebuild_is_dirty(monkeypatch):
    _seed()
    firm.post_message("general", text="Churn is rising at Acme", author="ana@firm.com")
    assert firm_search.search("churn")["total"] == 1

    real_build = firm_search._build
    started, release = threading.Event(), threading.Event()
    builds: list[str] = []

    def slow_build(data_dir: str) -> list[dict]:
        builds.append(data_dir)
        started.set()
        assert release.wait(10)
        return real_build(data_dir)

    monkeypatch.setattr(firm_search, "_build", slow_build)
    firm.post_message("general", text="Churn again in the August cohort", author="ben@firm.com")
    firm_search.invalidate()

    assert firm_search.search("churn")["total"] == 1
    assert started.wait(5)
    firm_search.invalidate()
    assert firm_search.search("churn")["total"] == 1
    assert len(builds) == 1

    release.set()
    deadline = time.monotonic() + 10
    while firm_search.search("churn")["total"] != 2:
        assert time.monotonic() < deadline, "rebuilt index never served"
        time.sleep(0.01)
    _wait_for_index_idle()
    assert 2 <= len(builds) <= 3


def test_firm_search_picks_up_report_changes_in_the_background(monkeypatch):
    _seed()
    assert firm_search.search("lidar")["total"] == 0

    run_dir = storage.DATA_DIR / "memos" / "run1"
    (run_dir / "logs").mkdir(parents=True)
    package = {"sections": [{"title": "Risks", "blocks": [{"text": "Lidar supply is concentrated in one vendor."}]}]}
    (run_dir / "logs" / "memo_package.json").write_text(json.dumps(package), encoding="utf-8")
    _write_report("r1", "acme-ai", "2026-01-01", status="complete", run_dir=str(run_dir.relative_to(storage.DATA_DIR.parent)))

    assert firm_search.search("lidar")["total"] == 0
    _wait_for_index_idle()
    out = firm_search.search("lidar")
    assert [(i["kind"], i["company_id"], i["ref"]) for i in out["items"]] == [("memo", "acme-ai", "Risks")]


def test_firm_search_index_is_keyed_by_data_dir(monkeypatch, tmp_path):
    _seed()
    firm.post_message("general", text="Churn is rising at Acme", author="ana@firm.com")
    assert firm_search.search("churn")["total"] == 1

    _point_data_dir(monkeypatch, tmp_path / "other")
    _seed({"id": "beta", "name": "Beta Robotics", "status": "private"})
    assert firm_search.search("churn")["total"] == 0
    assert [i["company_id"] for i in firm_search.search("robotics")["items"]] == ["beta"]


def test_signal_watch_reuses_scores_until_their_inputs_change(monkeypatch, tmp_path):
    _seed()
    real_compute = signal_score.compute
    calls: list[str] = []

    def counting_compute(company_id: str, **kwargs) -> dict:
        calls.append(company_id)
        return real_compute(company_id, **kwargs)

    monkeypatch.setattr(signal_score, "compute", counting_compute)

    first = signal_watch.moves()
    assert calls == ["acme-ai"]
    assert first["items"][0]["coverage"] == "0 of 6 components have data"
    assert signal_watch.moves()["items"] == first["items"]
    assert len(calls) == 1

    portfolio.add_kpi("acme-ai", {"as_of": "2026-03-31", "arr_usd": 1_000_000})
    signal_watch.moves()
    assert len(calls) == 2
    signal_watch.snapshot()
    assert len(calls) == 2

    _write_report("r1", "acme-ai", "2026-01-01", status="complete")
    out = signal_watch.moves()
    assert len(calls) == 3
    assert out["items"][0]["coverage"] == "1 of 6 components have data"
    assert out["previous_snapshot_at"] is not None

    monkeypatch.setattr(signal_watch, "CACHE_TTL_S", 0.0)
    signal_watch.moves()
    assert len(calls) == 4
    monkeypatch.setattr(signal_watch, "CACHE_TTL_S", 120.0)

    _point_data_dir(monkeypatch, tmp_path / "other")
    _seed({"id": "beta", "name": "Beta Robotics", "status": "private"})
    assert [i["company_id"] for i in signal_watch.moves()["items"]] == ["beta"]
    assert calls[-1] == "beta"
