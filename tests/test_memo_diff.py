"""What changed between two memos on the same company: deterministic,
side by side, and conservative about pairing rows whose labels drifted."""
from __future__ import annotations

import itertools
import json

import pytest
from fastapi.testclient import TestClient

from server import memo_diff, memo_prep, storage
from server.main import app

_COUNTER = itertools.count(1)


@pytest.fixture
def env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    return data_root


def cell(en, zh=None):
    return {"en": en, "zh": zh or en}


def package(*, scenarios, risks, metrics, sources, decision_en="We pass."):
    return {
        "schema_version": 1,
        "company": {"name": "CIeNET"},
        "run": {"as_of": "2026-08-20"},
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {
                        "type": "table",
                        "component": "key_metrics_snapshot",
                        "headers": [cell("Metric"), cell("Figure")],
                        "rows": [[cell(label), value] for label, value in metrics],
                    }
                ],
            },
            {
                "id": "investment_risk",
                "blocks": [
                    {
                        "type": "table",
                        "component": "risk_register",
                        "layout": "key_value",
                        "title": cell(f"Risk {i + 1}"),
                        "headers": [],
                        "rows": [
                            [cell("Risk Type"), cell(risk_type)],
                            [cell("Risk Rating"), cell(rating)],
                        ],
                    }
                    for i, (risk_type, rating) in enumerate(risks)
                ],
            },
            {
                "id": "financial_forecast_valuation",
                "blocks": [
                    {
                        "type": "table",
                        "component": "scenario_analysis",
                        "headers": [cell("Scenario"), cell("Value")],
                        "rows": [[cell(label), value] for label, value in scenarios],
                    }
                ],
            },
            {
                "id": "investment_decision",
                "blocks": [{"type": "paragraph", "text": cell(decision_en)}],
            },
        ],
        "sources": sources,
    }


def make(data_root, pkg, *, created_at, kind=memo_prep.LATESTAGE_KIND, decision=None, spine=None, company_id="cienet"):
    n = next(_COUNTER)
    run_dir = data_root / "memos" / company_id / f"run-{n}"
    (run_dir / "logs").mkdir(parents=True)
    if pkg is not None:
        (run_dir / "logs" / "memo_package.json").write_text(json.dumps(pkg), encoding="utf-8")
    if spine is not None:
        (run_dir / "logs" / "english_units").mkdir()
        (run_dir / "logs" / "english_units" / "spine.json").write_text(
            json.dumps({"shared_facts": spine}), encoding="utf-8"
        )
    report = storage.create_report_record(
        company_id=company_id,
        company_name="CIeNET",
        kind=kind,
        status="complete",
        run_dir=memo_prep._rel(run_dir),
        memo_files=[],
        **({"decision": decision} if decision else {}),
    )
    storage.update_report(report["id"], created_at=created_at)
    return storage.get_report(report["id"])


OLD = package(
    scenarios=[("Bear", "$35M"), ("Base", "$300M"), ("Bull", "$900M"), ("All scenarios", "unpriceable")],
    risks=[("Deal Structure", "9/10"), ("Customer concentration", "7/10")],
    metrics=[("Entity revenue", "$40M"), ("Growth rate", "12%"), ("Customers", "40+")],
    sources=[
        {"id": "S1", "title": cell("ALTEN release"), "url": "https://www.alten.com/press/1", "as_of": "2021-11-08"},
        {"id": "S2", "title": cell("Registry"), "as_of": "2026-08-20"},
    ],
    decision_en="No capital commitment.",
)
NEW = package(
    scenarios=[("Bear (30%)", "$20M"), ("Base (50%)", "$40M"), ("Bull (20%)", "$60M"), ("Access overlay", "n/a")],
    risks=[("Structure", "9/10"), ("Customer concentration", "8/10")],
    metrics=[
        ("Last disclosed revenue", "$38M"),
        ("Modeled 2026 revenue", "$45M"),
        ("Growth", "10%"),
        ("Customers", "40+"),
    ],
    sources=[
        {"id": "S1", "title": cell("ALTEN press release"), "url": "http://alten.com/press/1/", "as_of": "2021-11-08"},
        {"id": "S3", "title": cell("New filing"), "url": "https://example.org/f"},
    ],
    decision_en="No private allocation; watch position.",
)


def test_label_matching_is_conservative():
    pairs = memo_diff.match_labels(
        ["Growth", "Revenue", "Customers"],
        ["Growth rate", "Last disclosed revenue", "Modeled 2026 revenue", "Customers"],
    )
    by_current = {c: (p, how) for c, p, how in pairs if c is not None}
    assert by_current[2] == (3, "exact")
    assert by_current[0] == (0, "fuzzy")
    # "Revenue" could be either of two rows: not paired, never "removed".
    assert by_current[1] == (None, "none")
    assert sum(1 for c, p, how in pairs if c is None) == 2


def test_late_stage_diff_side_by_side(env):
    old = make(env, OLD, created_at="2026-08-20T19:50:00+00:00")
    new = make(env, NEW, created_at="2026-08-20T23:41:00+00:00")
    result = memo_diff.diff_reports(new, old)
    tables = {t["component"]: t for t in result["tables"]}
    scenario_rows = {r["key"]: r for r in tables["scenario_analysis"]["rows"] if r["match"] == "scenario"}
    assert set(scenario_rows) == {"bear", "base", "bull"}
    assert scenario_rows["base"]["previous"][1]["en"] == "$300M"
    assert scenario_rows["base"]["current"][1]["en"] == "$40M"
    assert scenario_rows["base"]["changed"] is True
    unmatched = [r for r in tables["scenario_analysis"]["rows"] if r["match"] == "none"]
    assert len(unmatched) == 2  # "All scenarios" and "Access overlay" stand alone
    risks = tables["risk_register"]["rows"]
    concentration = next(r for r in risks if r["match"] == "exact")
    assert concentration["rating_changed"] is True
    # "Deal Structure" / "Structure": one label contains the other and each
    # is the other's only candidate, so they sit side by side as "fuzzy".
    structure = next(r for r in risks if r["match"] == "fuzzy")
    assert structure["risk_type"]["previous"]["en"] == "Deal Structure"
    assert structure["risk_type"]["current"]["en"] == "Structure"
    assert structure["rating_changed"] is False
    metrics = {r["label"]["current"]["en"] if r["label"]["current"] else None: r for r in tables["key_metrics_snapshot"]["rows"]}
    assert metrics["Customers"]["match"] == "exact" and metrics["Customers"]["changed"] is False
    assert metrics["Growth"]["match"] == "fuzzy"
    sources = result["sources"]
    assert sources["matched"] == 1  # same URL despite scheme / www / trailing slash
    assert sources["rows"][0]["match"] == "url"
    assert any("side by side" in note for note in result["notes"])
    assert result["verdict"]["changed"] is False


def test_buffett_diff_and_unstable_call(env):
    old = make(env, {"decision": "Buy", "buy_price": "Up to $360"}, created_at="2026-08-25T00:31:53+00:00",
               kind=memo_prep.BUFFETT_KIND, decision="Buy", company_id="google-llc")
    new = make(env, {"decision": "Pass", "buy_price": "$215 or less"}, created_at="2026-08-25T18:48:56+00:00",
               kind=memo_prep.BUFFETT_KIND, decision="Pass", company_id="google-llc")
    result = memo_diff.diff_reports(new, old)
    assert result["verdict"] == {"current": "Pass", "previous": "Buy", "changed": True, "unstable": True}
    fields = {f["field"]: f for f in result["buffett"]["fields"]}
    assert fields["buy_price"]["previous"] == "Up to $360" and fields["buy_price"]["changed"] is True


def test_spine_facts_compared_when_present(env):
    old = make(env, OLD, created_at="2026-08-20T19:50:00+00:00", spine={"verdict": "Pass", "entry": {"valuation": "$40M"}})
    new = make(env, NEW, created_at="2026-08-21T19:50:00+00:00", spine={"verdict": "Watch", "entry": {"valuation": "$30M"}})
    result = memo_diff.diff_reports(new, old)
    fields = {f["field"]: f for f in result["spine"]["fields"]}
    assert fields["verdict"]["changed"] is True
    assert fields["entry"]["previous"] == {"valuation": "$40M"}


def test_diff_endpoint_defaults_to_the_previous_version(env):
    client = TestClient(app)
    old = make(env, OLD, created_at="2026-08-20T19:50:00+00:00")
    new = make(env, NEW, created_at="2026-08-20T23:41:00+00:00")
    body = client.get(f"/api/reports/{new['id']}/diff").json()
    assert body["against_id"] == old["id"]
    assert body["previous"]["headline"]["en"] == "No capital commitment."
    assert client.get(f"/api/reports/{old['id']}/diff").status_code == 404
    buffett = make(env, {"decision": "Buy"}, created_at="2026-08-22T00:00:00+00:00", kind=memo_prep.BUFFETT_KIND)
    assert client.get(f"/api/reports/{new['id']}/diff?against={buffett['id']}").status_code == 400
    assert client.get(f"/api/reports/{new['id']}/diff?against={old['id']}").status_code == 200
    assert client.get(f"/api/reports/{new['id']}/diff?against=missing").status_code == 404
