"""Unit tests for institutional VC pillars: founder dossier, deep search, and deal pipeline."""
import pytest
from starlette.testclient import TestClient

from server.main import app

client = TestClient(app)


def test_get_founder_dossier():
    response = client.get("/api/companies/zainar-inc/founder-dossier")
    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == "zainar-inc"
    assert "founders" in data
    assert len(data["founders"]) > 0
    first_founder = data["founders"][0]
    assert "name" in first_founder
    assert "pedigree_tags" in first_founder
    assert "developer_traction" in data


def test_deep_search_founder():
    response = client.post("/api/companies/zainar-inc/founder-dossier/deep-search")
    assert response.status_code == 200
    data = response.json()
    assert data["company_id"] == "zainar-inc"
    assert data["is_deep_audited"] is True


def test_get_and_update_deal_pipeline():
    # 1. Get initial pipeline
    get_res = client.get("/api/companies/zainar-inc/deal-pipeline")
    assert get_res.status_code == 200
    pipeline = get_res.json()
    assert pipeline["company_id"] == "zainar-inc"
    assert "stage" in pipeline
    assert "warmth_score" in pipeline
    assert "intro_path" in pipeline

    # 2. Update stage
    put_res = client.put(
        "/api/companies/zainar-inc/deal-pipeline",
        json={"stage": "Term Sheet / IC", "warmth_score": 98},
    )
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["stage"] == "Term Sheet / IC"
    assert updated["warmth_score"] == 98
