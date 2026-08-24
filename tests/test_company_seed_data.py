from __future__ import annotations

import yaml

from server import storage


def _redirect_storage(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")


def test_materialize_seed_company_records_updates_profile_but_keeps_local_state(
    monkeypatch,
    tmp_path,
):
    _redirect_storage(monkeypatch, tmp_path)
    seed_file = tmp_path / "company_records.yaml"
    seed_file.write_text(
        yaml.safe_dump(
            [
                {
                    "id": "zainar-inc",
                    "name": "ZaiNar, Inc.",
                    "status": "private",
                    "description": "Tracked PRD profile.",
                    "positioning": {"category": "network-based positioning"},
                    "metrics": [{"label": "ARR", "value": "~$24M"}],
                    "translation": {"language": "zh", "description": "seed"},
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {
                "id": "zainar-inc",
                "name": "ZaiNar",
                "status": "private",
                "description": "Old local profile.",
                "translation": {"language": "zh", "description": "local"},
                "trader_snapshot": {"schema_version": 2},
                "local_only": True,
            },
        ],
    )

    changed = storage.materialize_seed_company_records(seed_file)

    assert changed == 1
    company = storage.get_company("zainar-inc")
    assert company["name"] == "ZaiNar, Inc."
    assert company["description"] == "Tracked PRD profile."
    assert company["positioning"]["category"] == "network-based positioning"
    assert company["metrics"][0]["value"] == "~$24M"
    assert company["company_type"] == "private"
    assert company["translation"]["description"] == "local"
    assert company["trader_snapshot"] == {"schema_version": 2}
    assert company["local_only"] is True

    assert storage.materialize_seed_company_records(seed_file) == 0


def test_materialize_seed_company_records_creates_runtime_file(monkeypatch, tmp_path):
    _redirect_storage(monkeypatch, tmp_path)
    seed_file = tmp_path / "company_records.yaml"
    seed_file.write_text(
        yaml.safe_dump(
            [
                {
                    "id": "zainar-inc",
                    "name": "ZaiNar, Inc.",
                    "status": "private",
                    "positioning": {"category": "network-based positioning"},
                },
            ],
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    changed = storage.materialize_seed_company_records(seed_file)

    assert changed == 1
    assert storage.get_company("zainar-inc")["company_type"] == "private"


def test_tracked_company_seed_contains_zainar_prd_overview_fields():
    records = storage._load_company_seed_records()
    zainar = next(record for record in records if record["id"] == "zainar-inc")

    assert zainar["positioning"]["category"]
    assert {metric["label"] for metric in zainar["metrics"]} >= {
        "ARR",
        "YoY Growth",
        "Valuation",
        "TAM",
    }
    assert zainar["team_profiles"]
    assert any(comp["name"] == "NextNav" for comp in zainar["competitors"])
    assert zainar["board_investors"]
    assert zainar["cap_table_lineage"]
    assert zainar["company_news"]
    assert zainar["industry_view"]["metrics"]
    assert zainar["expert_opinions"]
    assert zainar["disclosures"]


def test_fixture_company_pack_materializes_only_when_requested(monkeypatch, tmp_path):
    _redirect_storage(monkeypatch, tmp_path)

    storage.materialize_seed_company_records()

    assert storage.get_company("zainar-inc") is not None
    assert storage.get_company("databricks") is None
    assert storage.get_company("fixture-empty-company") is None

    changed = storage.materialize_seed_company_records(include_fixtures=True)

    assert changed == 4
    assert storage.get_company("databricks")["positioning"]["category"]
    assert storage.get_company("stripe-inc")["metrics"][0]["label"] == "Payment Volume"
    assert storage.get_company("nextnav")["ticker"] == "NN"
    assert storage.get_company("fixture-empty-company")["products"] == []


def test_fixture_company_pack_does_not_overwrite_existing_real_record(
    monkeypatch,
    tmp_path,
):
    _redirect_storage(monkeypatch, tmp_path)
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {
                "id": "stripe-inc",
                "name": "Stripe, Inc.",
                "status": "private",
                "description": "Richer local Stripe profile.",
                "metrics": [{"label": "Local Metric", "value": "Keep"}],
            },
        ],
    )

    changed = storage.materialize_seed_company_records(include_fixtures=True)

    assert changed == 4
    stripe = storage.get_company("stripe-inc")
    assert stripe["description"] == "Richer local Stripe profile."
    assert stripe["metrics"] == [{"label": "Local Metric", "value": "Keep"}]
    assert "seed_kind" not in stripe
    assert storage.get_company("databricks")["seed_kind"] == "fixture"


def test_materialize_analyst_background_seeds_default(monkeypatch, tmp_path):
    _redirect_storage(monkeypatch, tmp_path)

    assert storage.materialize_analyst_background() is True

    target = storage.analyst_background_file()
    content = target.read_text(encoding="utf-8")
    assert content == storage.ANALYST_BACKGROUND_SEED_FILE.read_text(
        encoding="utf-8"
    )
    assert "AI-generated default" in content
    # Idempotent: a second call sees the existing file and leaves it alone.
    assert storage.materialize_analyst_background() is False


def test_materialize_analyst_background_keeps_local_background(
    monkeypatch,
    tmp_path,
):
    _redirect_storage(monkeypatch, tmp_path)
    target = tmp_path / "settings" / "serena_background.md"
    target.parent.mkdir(parents=True)
    target.write_text("# My own thesis\n", encoding="utf-8")

    assert storage.materialize_analyst_background() is False

    assert target.read_text(encoding="utf-8") == "# My own thesis\n"


def test_materialize_analyst_background_without_seed_is_a_noop(
    monkeypatch,
    tmp_path,
):
    _redirect_storage(monkeypatch, tmp_path)

    assert storage.materialize_analyst_background(tmp_path / "missing.md") is False

    assert not storage.analyst_background_file().exists()
