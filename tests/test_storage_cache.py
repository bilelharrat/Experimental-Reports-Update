"""The companies/reports read caches must be correct: reflect writes, never
leak shared mutable state, and key on file identity."""
from __future__ import annotations

import pytest

from server import storage


@pytest.fixture
def tmp_data(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")
    # Reset module-level caches so tests don't bleed into each other.
    storage._companies_cache_key = None
    storage._companies_cache_list = []
    storage._companies_cache_index = {}
    storage._reports_cache = {}
    (tmp_path / "reports").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_companies(records):
    storage._write_yaml(storage.COMPANIES_FILE, records)


def test_list_companies_reflects_writes(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha"}])
    assert [c["id"] for c in storage.list_companies()] == ["a"]
    _write_companies([{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}])
    assert sorted(c["id"] for c in storage.list_companies()) == ["a", "b"]


def test_list_companies_returns_independent_copies(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha", "tags": ["x"]}])
    first = storage.list_companies()
    first[0]["name"] = "MUTATED"
    first[0]["tags"].append("y")
    # A second call must not see the mutation (no shared references).
    second = storage.list_companies()
    assert second[0]["name"] == "Alpha"
    assert second[0]["tags"] == ["x"]


def test_get_company_uses_index_and_copies(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}])
    rec = storage.get_company("b")
    assert rec["name"] == "Beta"
    rec["name"] = "MUTATED"
    assert storage.get_company("b")["name"] == "Beta"
    assert storage.get_company("missing") is None


def test_update_company_persists_and_cache_refreshes(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha"}])
    storage.list_companies()  # warm cache
    storage.update_company("a", description="hello")
    assert storage.get_company("a")["description"] == "hello"


def test_search_companies_reads_current_data(tmp_data):
    _write_companies([{"id": "a", "name": "Anduril"}, {"id": "s", "name": "Stripe"}])
    hits = storage.search_companies("and")
    assert [c["id"] for c in hits] == ["a"]
    hits[0]["name"] = "MUTATED"
    assert storage.search_companies("and")[0]["name"] == "Anduril"


def test_list_reports_reflects_new_and_deleted(tmp_data):
    r1 = storage.REPORTS_DIR / "r1.yaml"
    storage._write_yaml(r1, {"id": "r1", "created_at": "2026-01-01"})
    assert [r["id"] for r in storage.list_reports()] == ["r1"]
    storage._write_yaml(
        storage.REPORTS_DIR / "r2.yaml", {"id": "r2", "created_at": "2026-02-01"}
    )
    # newest first
    assert [r["id"] for r in storage.list_reports()] == ["r2", "r1"]
    r1.unlink()
    assert [r["id"] for r in storage.list_reports()] == ["r2"]


def test_list_reports_returns_independent_copies(tmp_data):
    storage._write_yaml(
        storage.REPORTS_DIR / "r1.yaml", {"id": "r1", "created_at": "2026-01-01"}
    )
    first = storage.list_reports()
    first[0]["id"] = "MUTATED"
    assert storage.list_reports()[0]["id"] == "r1"


# ---- company ext sidecars (trader_snapshot / translation) ----

def test_update_company_routes_ext_fields_to_sidecar(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha"}])
    out = storage.update_company(
        "a",
        description="core field",
        trader_snapshot={"schema_version": 3},
        translation={"language": "zh"},
    )
    # Returned record is the merged view.
    assert out["description"] == "core field"
    assert out["trader_snapshot"] == {"schema_version": 3}
    # The hot index file stays slim...
    raw = storage._read_yaml(storage.COMPANIES_FILE, [])
    assert "trader_snapshot" not in raw[0]
    assert "translation" not in raw[0]
    assert (tmp_data / "company_ext" / "a.yaml").exists()
    # ...list is slim, get_company merges.
    assert "trader_snapshot" not in storage.list_companies()[0]
    merged = storage.get_company("a")
    assert merged["trader_snapshot"] == {"schema_version": 3}
    assert merged["translation"] == {"language": "zh"}


def test_update_company_ext_only_returns_none_for_unknown_company(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha"}])
    assert storage.update_company("missing", trader_snapshot={"x": 1}) is None
    assert not (tmp_data / "company_ext" / "missing.yaml").exists()


def test_get_company_ext_reflects_writes_and_copies(tmp_data):
    _write_companies([{"id": "a", "name": "Alpha"}])
    assert storage.get_company_ext("a") == {}
    storage.set_company_ext("a", "translation", {"language": "zh"})
    ext = storage.get_company_ext("a")
    assert ext["translation"]["language"] == "zh"
    ext["translation"]["language"] = "MUTATED"
    assert storage.get_company_ext("a")["translation"]["language"] == "zh"


def test_migrate_company_ext_hoists_inline_fields(tmp_data):
    _write_companies([
        {
            "id": "a",
            "name": "Alpha",
            "trader_snapshot": {"schema_version": 2},
            "translation": {"language": "zh"},
        },
        {"id": "b", "name": "Beta"},
    ])
    assert storage.migrate_company_ext() == 1
    raw = storage._read_yaml(storage.COMPANIES_FILE, [])
    assert all(
        "trader_snapshot" not in c and "translation" not in c for c in raw
    )
    merged = storage.get_company("a")
    assert merged["trader_snapshot"] == {"schema_version": 2}
    assert merged["translation"] == {"language": "zh"}
    # Idempotent.
    assert storage.migrate_company_ext() == 0


def test_migrate_trader_snapshots_works_on_sidecars(tmp_data):
    _write_companies([
        {
            "id": "a",
            "name": "Alpha",
            "trader_snapshot": {
                "schema_version": 1,
                "heat_card": {"rel_volume_20d": 2.0},
            },
        },
    ])
    assert storage.migrate_trader_snapshots(target_schema_version=3) == 1
    snap = storage.get_company("a")["trader_snapshot"]
    assert snap["schema_version"] == 3
    assert snap["heat_card"] is None
    assert storage.migrate_trader_snapshots(target_schema_version=3) == 0
