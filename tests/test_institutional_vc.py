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


def test_founder_dossier_merges_the_same_person_across_record_fields():
    """key_people carries name + role; team_profiles carries the bio and links.
    The dossier keeps both instead of dropping the richer row as a duplicate."""
    _seed(
        key_people=[
            {"name": "Daniel Jacker", "role": "Co-founder & CEO"},
            {"name": "Steve Jurvetson", "role": "Board Member (Future Ventures)"},
        ],
        team_profiles=[
            {
                "name": "Daniel Jacker",
                "role": "Co-founder / CEO",
                "bio": "Leads PNT architecture.",
                "linkedin_url": "https://linkedin.com/in/daniel",
                "profile_url": "https://zainartech.com",
            }
        ],
        board_investors=[
            {"name": "Steve Jurvetson", "role": "Board / Future Ventures lead", "profile_url": "https://future.ventures"},
            {"name": "Foundation Capital", "role": "Series A lead investor"},
        ],
        employee_band="50-200",
    )
    data = client.get("/api/companies/zainar-inc/founder-dossier").json()
    assert [p["name"] for p in data["founders"]] == ["Daniel Jacker"]
    daniel = data["founders"][0]
    assert daniel["role"] == "Co-founder & CEO"  # first-seen role wins
    assert daniel["bio"] == "Leads PNT architecture."
    assert daniel["linkedin_url"] == "https://linkedin.com/in/daniel"
    assert daniel["profile_url"] == "https://zainartech.com"
    board = {p["name"]: p for p in data["advisors_and_board"]}
    assert list(board) == ["Steve Jurvetson", "Foundation Capital"]
    assert board["Steve Jurvetson"]["profile_url"] == "https://future.ventures"
    assert data["team_headcount"]["employee_count_estimate"] == "50-200"


def test_founder_radar_alias_matches_founder_dossier():
    """The iOS/iPadOS Team tab requests ``founder-radar``; it must not 404."""
    _seed(key_people=[{"name": "Ada Example", "role": "CEO"}])
    radar = client.get("/api/companies/zainar-inc/founder-radar")
    assert radar.status_code == 200
    dossier = client.get("/api/companies/zainar-inc/founder-dossier").json()
    a, b = radar.json(), dossier
    a.pop("searched_at"), b.pop("searched_at")
    assert a == b
    assert client.get("/api/companies/nope/founder-radar").status_code == 404


def test_founder_dossier_is_empty_without_people():
    _seed()
    data = client.get("/api/companies/zainar-inc/founder-dossier").json()
    assert data["founders"] == []
    assert data["advisors_and_board"] == []


def test_deep_search_degrades_to_the_record_when_research_fails(monkeypatch):
    """A failed research pass must leave the Team tab showing the record,
    not an error — and it may not claim an audit it did not perform."""
    from server import founder_dossier

    monkeypatch.setattr(
        founder_dossier.ai_engine,
        "grounded",
        lambda **_kw: (None, {"engine": "gemini"}, "gemini HTTP 503"),
    )
    _seed(key_people=[{"name": "Ada Example", "role": "CEO"}])
    response = client.post("/api/companies/zainar-inc/founder-dossier/deep-search")
    assert response.status_code == 200
    body = response.json()
    assert body["is_deep_audited"] is False
    assert body["research_error"] == "gemini HTTP 503"
    assert [p["name"] for p in body["founders"]] == ["Ada Example"]


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


def test_deal_pipeline_flags_a_next_step_past_its_due_date():
    _seed()
    url = "/api/companies/zainar-inc/deal-pipeline"

    past = client.put(url, json={"next_step": "Send the term sheet", "next_step_due": "2020-01-31"})
    assert past.status_code == 200
    assert past.json()["next_step_due"] == "2020-01-31"
    assert past.json()["next_step_overdue"] is True
    # and it survives a re-read
    assert client.get(url).json()["next_step_overdue"] is True

    future = client.put(url, json={"next_step_due": "2999-12-31"})
    assert future.json()["next_step_overdue"] is False

    # the due date belongs to the step: clearing the step clears it
    cleared = client.put(url, json={"next_step": None})
    assert cleared.json()["next_step_due"] is None
    assert cleared.json()["next_step_overdue"] is False


def test_deal_pipeline_rejects_a_due_date_that_is_not_a_date():
    _seed()
    res = client.put("/api/companies/zainar-inc/deal-pipeline", json={"next_step_due": "next week"})
    assert res.status_code == 400
    assert "YYYY-MM-DD" in res.json()["detail"]
