"""Decision Record store + CRUD API."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import decisions_store, storage
from server.main import app


@pytest.fixture()
def company():
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    companies = storage.list_companies()
    assert companies
    return companies[0]["id"]


def test_add_list_remove_roundtrip(company):
    row = decisions_store.add_decision(
        company,
        verdict="invest",
        explanation="Strong pipeline and fair terms.",
        created_by="Ben",
    )
    assert row["verdict"] == "invest"
    assert row["retrospectives"] == []
    assert row["created_by"] == "Ben"
    assert row["decided_at"]

    listed = decisions_store.list_decisions(company)
    assert [r["id"] for r in listed["items"]] == [row["id"]]

    assert decisions_store.remove_decision(company, row["id"]) is True
    assert decisions_store.list_decisions(company)["items"] == []
    assert decisions_store.remove_decision(company, row["id"]) is False


def test_validation(company):
    with pytest.raises(ValueError):
        decisions_store.add_decision(
            company, verdict="maybe", explanation="x", created_by="b"
        )
    with pytest.raises(ValueError):
        decisions_store.add_decision(
            company, verdict="pass", explanation="   ", created_by="b"
        )
    with pytest.raises(ValueError):
        decisions_store.add_decision(
            company,
            verdict="pass",
            explanation="ok",
            decided_at="not-a-date",
            created_by="b",
        )
    with pytest.raises(ValueError):
        decisions_store._company_dir("###")  # nothing survives sanitization
    # Traversal characters are stripped, never traversed.
    assert decisions_store._company_dir("../../etc").name == "etc"


def test_backdating_and_sort_order(company):
    old = decisions_store.add_decision(
        company,
        verdict="pass",
        explanation="Valuation too rich at the time.",
        decided_at="2024-03-01",
        created_by="b",
    )
    assert old["decided_at"].startswith("2024-03-01")
    new = decisions_store.add_decision(
        company, verdict="watch", explanation="Waiting on Q3.", created_by="b"
    )
    items = decisions_store.list_decisions(company)["items"]
    assert [r["id"] for r in items] == [new["id"], old["id"]]  # newest first


def test_append_retrospectives_validates_and_caps(company):
    row = decisions_store.add_decision(
        company, verdict="pass", explanation="Churn too high.", created_by="b"
    )
    count = decisions_store.append_retrospectives(
        company,
        [
            {
                "decision_id": row["id"],
                "verdict": "looks_wrong",
                "rationale_en": "They fixed churn and raised at 3x.",
                "rationale_zh": "客户流失已改善，估值翻三倍。",
                "news_ids": ["abc123"],
                "news_titles": ["Series C at $900M"],
            },
            {"decision_id": "nope", "verdict": "still_right"},  # unknown id
            {"decision_id": row["id"], "verdict": "shrug"},  # bad verdict
        ],
        source="tracking_sync",
    )
    assert count == 1
    stored = decisions_store.list_decisions(company)["items"][0]
    assert len(stored["retrospectives"]) == 1
    retro = stored["retrospectives"][0]
    assert retro["verdict"] == "looks_wrong"
    assert retro["rationale_zh"].startswith("客户流失")
    assert retro["source"] == "tracking_sync"

    # Cap: newest first, at most 10 kept.
    for i in range(12):
        decisions_store.append_retrospectives(
            company,
            [
                {
                    "decision_id": row["id"],
                    "verdict": "still_right",
                    "rationale_en": f"check {i}",
                    "rationale_zh": f"复核 {i}",
                }
            ],
            source="tracking_sync",
        )
    stored = decisions_store.list_decisions(company)["items"][0]
    assert len(stored["retrospectives"]) == 10
    assert stored["retrospectives"][0]["rationale_en"] == "check 11"


def test_api_roundtrip(company):
    client = TestClient(app)

    assert client.get("/api/companies/nope/decisions").status_code == 404

    response = client.post(
        f"/api/companies/{company}/decisions",
        json={
            "verdict": "invest",
            "explanation": "Team + traction.",
            "decided_at": "2026-01-15",
            "created_by": "spoofed-client-value",  # must be ignored
        },
    )
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["decided_at"].startswith("2026-01-15")
    assert row["created_by"] != "spoofed-client-value"

    listed = client.get(f"/api/companies/{company}/decisions").json()
    assert [r["id"] for r in listed["items"]] == [row["id"]]

    bad = client.post(
        f"/api/companies/{company}/decisions",
        json={"verdict": "maybe", "explanation": "x"},
    )
    assert bad.status_code == 400

    assert (
        client.delete(
            f"/api/companies/{company}/decisions/{row['id']}"
        ).status_code
        == 204
    )
    assert (
        client.delete(
            f"/api/companies/{company}/decisions/{row['id']}"
        ).status_code
        == 404
    )


def test_render_decision_record_md(company):
    assert decisions_store.render_decision_record_md(company) is None

    row = decisions_store.add_decision(
        company,
        verdict="pass",
        explanation="Unit economics unproven.",
        decided_at="2024-01-10",
        created_by="b",
    )
    decisions_store.append_retrospectives(
        company,
        [
            {
                "decision_id": row["id"],
                "verdict": "questionable",
                "rationale_en": "Gross margin turned positive.",
                "rationale_zh": "毛利率转正。",
            }
        ],
        source="tracking_sync",
    )
    text = decisions_store.render_decision_record_md(company)
    assert text.startswith("# BSH decision record")
    assert "Decision: pass — decided 2024-01-10 (over 12 months old)" in text
    assert "Reason: Unit economics unproven." in text
    assert "questionable — Gross margin turned positive." in text
    assert "historical context only" in text

    # Truncation happens on decision boundaries.
    for i in range(60):
        decisions_store.add_decision(
            company,
            verdict="watch",
            explanation=f"Reason number {i} " + "x" * 120,
            created_by="b",
        )
    clipped = decisions_store.render_decision_record_md(company, max_chars=800)
    assert len(clipped) < 1200
    assert "(older decisions truncated)" in clipped
