from __future__ import annotations

import re

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


# ---- the ZaiNar demo values are labelled as demo data (R4) --------------------
# The ~$24M ARR, +180% growth, ~$45B TAM, the industry-view metrics, the 95.5%
# cap table and the "BSH Research" stances come from the v2 design mock, not
# from diligence. The seed is re-applied on every start, so the labels live
# there.


_CLAIMS_DILIGENCE = re.compile(r"\b(?:bsh|diligence|internal)\b", re.I)
_SAYS_DEMO = re.compile(r"\b(?:demo|placeholder|mock)\b", re.I)


def _zainar_seed() -> dict:
    return next(r for r in storage._load_company_seed_records() if r["id"] == "zainar-inc")


def _provenance_labels(zainar: dict) -> list[str]:
    labels: list[str] = []
    for metric in zainar["metrics"]:
        labels.append(str(metric.get("source_class") or ""))
        labels += [str(ref.get("label") or "") for ref in metric.get("source_refs") or []]
        labels += [str(ref.get("source_class") or "") for ref in metric.get("source_refs") or []]
    labels += [str(row.get("source_class") or "") for row in zainar["cap_table_lineage"]]
    labels += [str(row.get("source_class") or "") for row in zainar["industry_view"]["metrics"]]
    for opinion in zainar["expert_opinions"]:
        labels += [str(opinion.get(key) or "") for key in ("speaker", "affiliation", "source_class")]
    return labels


def test_zainar_seed_never_labels_demo_values_as_diligence():
    zainar = _zainar_seed()
    labels = _provenance_labels(zainar)
    assert labels and not [label for label in labels if _CLAIMS_DILIGENCE.search(label)]
    by_label = {metric["label"]: metric for metric in zainar["metrics"]}
    # The values themselves are kept for the company page's designed layout.
    assert (by_label["ARR"]["value"], by_label["YoY Growth"]["value"], by_label["TAM"]["value"]) == ("~$24M", "+180%", "~$45B")
    for label in ("ARR", "YoY Growth", "TAM"):
        assert _SAYS_DEMO.search(by_label[label]["source_class"])
        assert all(_SAYS_DEMO.search(ref["label"]) for ref in by_label[label]["source_refs"])
    assert by_label["Valuation"]["source_class"] == "company"  # a real company disclosure
    assert sum(float(row["ownership"].rstrip("%")) for row in zainar["cap_table_lineage"]) == 95.5
    assert all(_SAYS_DEMO.search(row["source_class"]) for row in zainar["cap_table_lineage"])
    assert all(_SAYS_DEMO.search(row["source_class"]) for row in zainar["industry_view"]["metrics"])
    assert all(_SAYS_DEMO.search(row["speaker"]) for row in zainar["expert_opinions"])
    assert "not diligence" in zainar["demo_data_note"]


def test_zainar_demo_metrics_are_not_private_inventory():
    from server import memo_fact_check

    inventory = memo_fact_check.private_inventory(None, _zainar_seed())
    assert [item for item in inventory if item["kind"] == "registry_metric"] == []


def test_materializing_the_seed_replaces_the_old_diligence_labels(monkeypatch, tmp_path):
    _redirect_storage(monkeypatch, tmp_path)
    old = _zainar_seed()
    old["metrics"][0]["source_class"] = "BSH diligence"
    old["metrics"][0]["source_refs"] = [{"label": "BSH PRD reference package", "source_class": "BSH primary diligence"}]
    old["expert_opinions"][0]["speaker"] = "BSH Research"
    old.pop("demo_data_note")
    storage._write_yaml(storage.COMPANIES_FILE, [old])

    assert storage.materialize_seed_company_records() == 1

    company = storage.get_company("zainar-inc")
    assert not [label for label in _provenance_labels(company) if _CLAIMS_DILIGENCE.search(label)]
    assert company["metrics"][0]["value"] == "~$24M"
    assert company["demo_data_note"] == _zainar_seed()["demo_data_note"]
    assert storage.materialize_seed_company_records() == 0
