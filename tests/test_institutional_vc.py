"""Founder dossier and deal pipeline: record-backed only, no invented data."""
from starlette.testclient import TestClient

from server import storage
from server.main import app

client = TestClient(app)


def _seed(company_id: str = "zainar-inc", **extra) -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {
                "id": company_id,
                "name": "ZaiNar, Inc.",
                "status": "private",
                "company_type": "private",
                "industry": "Wireless",
                **extra,
            }
        ],
    )


def test_founder_dossier_uses_only_recorded_people():
    _seed(
        key_people=[
            {"name": "Ada Example", "role": "CEO", "linkedin_url": "https://linkedin.com/in/ada"},
            {"name": "Grace Board", "role": "Board Director"},
        ]
    )
    response = client.get("/api/companies/zainar-inc/founder-dossier")
    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == "zainar-inc"
    assert [p["name"] for p in data["founders"]] == ["Ada Example"]
    assert [p["name"] for p in data["advisors_and_board"]] == ["Grace Board"]
    ada = data["founders"][0]
    # Nothing is inferred: unrecorded fields stay empty rather than plausible.
    assert ada["education"] is None
    assert ada["past_companies"] == []
    assert ada["pedigree_tags"] == []
    assert ada["prior_exits"] is None
    assert data["team_headcount"] is None
    assert data["developer_traction"] is None
    assert data["is_deep_audited"] is False


def test_founder_dossier_is_empty_without_people():
    _seed()
    data = client.get("/api/companies/zainar-inc/founder-dossier").json()
    assert data["founders"] == []
    assert data["advisors_and_board"] == []


def test_deep_search_does_not_claim_an_audit():
    _seed()
    response = client.post("/api/companies/zainar-inc/founder-dossier/deep-search")
    assert response.status_code == 200
    assert response.json()["is_deep_audited"] is False


def test_deal_pipeline_starts_empty_and_accepts_updates():
    _seed()
    get_res = client.get("/api/companies/zainar-inc/deal-pipeline")
    assert get_res.status_code == 200
    pipeline = get_res.json()
    assert pipeline["stage"] == "Sourced"
    assert pipeline["deal_lead"] is None
    assert pipeline["warmth_score"] is None
    assert pipeline["intro_path"] is None

    put_res = client.put(
        "/api/companies/zainar-inc/deal-pipeline",
        json={"stage": "Term Sheet / IC", "warmth_score": 98, "ignored": "x"},
    )
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["stage"] == "Term Sheet / IC"
    assert updated["warmth_score"] == 98
    assert "ignored" not in updated


def test_deal_pipeline_rejects_unknown_stage():
    _seed()
    res = client.put("/api/companies/zainar-inc/deal-pipeline", json={"stage": "Moon"})
    assert res.status_code == 400
