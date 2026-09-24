"""The Team tab's research layer: grounded research merged over the record.

``ai_engine.grounded`` is stubbed throughout — no network, no model spend.
"""
from __future__ import annotations

import pytest

from server import founder_dossier, storage

COMPANY = {
    "id": "acme",
    "name": "Acme Robotics",
    "website": "https://acme.example",
    "stage": "Series B",
    "description": "Warehouse automation.",
    "key_people": [{"name": "Dana Reeve", "role": "Co-founder & CEO"}],
    "board_investors": [{"name": "Kit Alvarez", "role": "Board Director"}],
    "employee_band": "50-100",
}


@pytest.fixture
def company():
    storage._write_yaml(storage.COMPANIES_FILE, [dict(COMPANY)])
    return dict(COMPANY)


def _stub_grounded(monkeypatch, data, meta=None, error=None):
    calls: list[dict] = []

    def grounded(**kwargs):
        calls.append(kwargs)
        return data, (meta if meta is not None else {}), error

    monkeypatch.setattr(founder_dossier.ai_engine, "grounded", grounded)
    return calls


GEMINI_META = {
    "engine": "gemini",
    "model": "gemini-3.8-flash",
    "sources": [{"title": "Acme team page", "url": "https://acme.example/team"}],
    "queries": ["Acme Robotics founders"],
    "fallback_reason": None,
}


# ---- the record layer is unchanged ----------------------------------------


def test_reading_a_dossier_never_calls_a_model(monkeypatch, company):
    monkeypatch.setattr(
        founder_dossier.ai_engine,
        "grounded",
        lambda **_kw: pytest.fail("a plain read must not spend a model call"),
    )
    dossier = founder_dossier.get_or_synthesize_founder_dossier("acme")
    assert [p["name"] for p in dossier["founders"]] == ["Dana Reeve"]
    assert [p["name"] for p in dossier["advisors_and_board"]] == ["Kit Alvarez"]
    assert dossier["is_deep_audited"] is False
    assert dossier["engine"] is None


def test_unknown_company_raises(company):
    with pytest.raises(ValueError):
        founder_dossier.deep_search_founder_dossier("nope")


# ---- merge semantics ------------------------------------------------------


def test_research_fills_blanks_without_overwriting_the_record(monkeypatch, company):
    _stub_grounded(
        monkeypatch,
        {
            "people": [
                {
                    "name": "Dana Reeve",
                    "role": "CEO",  # the record says "Co-founder & CEO" and wins
                    "education": "PhD Robotics, CMU",
                    "past_companies": ["Boston Dynamics"],
                    "linkedin_url": "https://linkedin.com/in/danareeve",
                }
            ]
        },
        GEMINI_META,
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    dana = dossier["founders"][0]
    assert dana["role"] == "Co-founder & CEO"
    assert dana["education"] == "PhD Robotics, CMU"
    assert dana["past_companies"] == ["Boston Dynamics"]
    assert set(dana["researched_fields"]) == {"education", "past_companies", "linkedin_url"}


def test_new_people_are_added_and_tagged(monkeypatch, company):
    _stub_grounded(
        monkeypatch,
        {
            "people": [
                {"name": "Ira Okonkwo", "role": "Co-founder & CTO", "is_board_or_advisor": False},
                {"name": "Sam Vance", "role": "Advisor", "is_board_or_advisor": True},
            ]
        },
        GEMINI_META,
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    founders = {p["name"]: p for p in dossier["founders"]}
    board = {p["name"]: p for p in dossier["advisors_and_board"]}
    assert founders["Ira Okonkwo"]["source"] == "research"
    assert "Sam Vance" in board
    # Recorded people keep their provenance.
    assert "source" not in founders["Dana Reeve"]


def test_board_flag_falls_back_to_the_role_text(monkeypatch, company):
    _stub_grounded(
        monkeypatch,
        {"people": [{"name": "Robin Shah", "role": "Board Observer"}]},
        GEMINI_META,
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert [p["name"] for p in dossier["advisors_and_board"]] == ["Kit Alvarez", "Robin Shah"]


def test_headcount_merges_without_clobbering_the_recorded_band(monkeypatch, company):
    _stub_grounded(
        monkeypatch,
        {
            "people": [],
            "team_headcount": {
                "employee_count_estimate": "200+",
                "open_roles_count": 8,
                "hiring_velocity": "steady",
            },
        },
        GEMINI_META,
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert dossier["team_headcount"]["employee_count_estimate"] == "50-100"
    assert dossier["team_headcount"]["open_roles_count"] == 8
    assert dossier["team_headcount"]["hiring_velocity"] == "steady"


def test_nameless_rows_are_dropped(monkeypatch, company):
    _stub_grounded(
        monkeypatch,
        {"people": [{"role": "CFO"}, "not a dict", {"name": "  ", "role": "COO"}]},
        GEMINI_META,
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert [p["name"] for p in dossier["founders"]] == ["Dana Reeve"]


# ---- provenance -----------------------------------------------------------


def test_a_grounded_run_records_its_sources_and_engine(monkeypatch, company):
    _stub_grounded(monkeypatch, {"people": [], "notes": "CFO seat is vacant."}, GEMINI_META)
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert dossier["is_deep_audited"] is True
    assert dossier["engine"] == "gemini"
    assert dossier["model"] == "gemini-3.8-flash"
    assert dossier["sources"] == GEMINI_META["sources"]
    assert dossier["research_notes"] == "CFO seat is vacant."


def test_a_sourceless_run_is_not_an_audit(monkeypatch, company):
    """Gemini can answer from memory without searching; a run that read no
    sources may not claim the audited badge."""
    _stub_grounded(
        monkeypatch,
        {"people": [{"name": "Ira Okonkwo", "role": "CTO"}]},
        {"engine": "gemini", "model": "gemini-3.8-flash", "sources": [], "fallback_reason": None},
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert dossier["engine"] == "gemini"
    assert dossier["is_deep_audited"] is False
    assert [p["name"] for p in dossier["founders"]] == ["Dana Reeve", "Ira Okonkwo"]


def test_research_failure_degrades_to_the_record(monkeypatch, company):
    _stub_grounded(monkeypatch, None, {"engine": "gemini"}, "gemini HTTP 429 — quota")
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert dossier["research_error"] == "gemini HTTP 429 — quota"
    assert [p["name"] for p in dossier["founders"]] == ["Dana Reeve"]
    assert dossier["is_deep_audited"] is False


# ---- caching --------------------------------------------------------------


def test_a_research_pass_is_cached_and_replayed_on_read(monkeypatch, company):
    _stub_grounded(
        monkeypatch,
        {"people": [{"name": "Ira Okonkwo", "role": "CTO", "education": "MIT"}]},
        GEMINI_META,
    )
    founder_dossier.deep_search_founder_dossier("acme")

    monkeypatch.setattr(
        founder_dossier.ai_engine,
        "grounded",
        lambda **_kw: pytest.fail("a read must replay the cache, not re-research"),
    )
    dossier = founder_dossier.get_or_synthesize_founder_dossier("acme")
    ira = {p["name"]: p for p in dossier["founders"]}["Ira Okonkwo"]
    assert ira["education"] == "MIT"
    assert dossier["is_deep_audited"] is True
    assert dossier["sources"] == GEMINI_META["sources"]


def test_record_edits_show_up_over_a_cached_research_pass(monkeypatch, company):
    _stub_grounded(monkeypatch, {"people": []}, GEMINI_META)
    founder_dossier.deep_search_founder_dossier("acme")

    updated = dict(COMPANY)
    updated["key_people"] = [
        {"name": "Dana Reeve", "role": "President"},
        {"name": "Noor Haddad", "role": "CEO"},
    ]
    storage._write_yaml(storage.COMPANIES_FILE, [updated])

    dossier = founder_dossier.get_or_synthesize_founder_dossier("acme")
    names = {p["name"]: p["role"] for p in dossier["founders"]}
    assert names == {"Dana Reeve": "President", "Noor Haddad": "CEO"}


def test_a_corrupt_cache_falls_back_to_the_record(monkeypatch, company):
    path = founder_dossier._dossier_path("acme")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    dossier = founder_dossier.get_or_synthesize_founder_dossier("acme")
    assert [p["name"] for p in dossier["founders"]] == ["Dana Reeve"]
    assert dossier["is_deep_audited"] is False


# ---- the prompt -----------------------------------------------------------


def test_the_prompt_seeds_the_people_already_on_file(monkeypatch, company):
    calls = _stub_grounded(monkeypatch, {"people": []}, GEMINI_META)
    founder_dossier.deep_search_founder_dossier("acme")
    prompt = calls[0]["user_prompt"]
    assert "Acme Robotics" in prompt
    assert "Dana Reeve — Co-founder & CEO" in prompt
    assert "Kit Alvarez — Board Director" in prompt
    assert "https://acme.example" in prompt


# ---- engine: Gemini only --------------------------------------------------


@pytest.fixture(params=["claude", "gemini"])
def claude_calls(request, monkeypatch):
    """The desk is on Claude, or on Gemini-then-Claude; Team research must
    reach Claude under neither. Returns the Claude calls made."""
    engine = founder_dossier.ai_engine
    monkeypatch.setattr(engine, "policy", lambda: request.param)
    calls: list[str] = []
    monkeypatch.setattr(
        engine.claude_runner,
        "run_web_research_json",
        lambda **kw: calls.append(kw["name"]) or ({"people": []}, None),
    )
    return calls


def test_team_research_runs_on_gemini_whatever_the_desk_engine_is(
    monkeypatch, company, claude_calls
):
    gemini = founder_dossier.ai_engine.gemini_runner
    monkeypatch.setattr(gemini, "is_available", lambda: True)
    calls: list[dict] = []
    monkeypatch.setattr(
        gemini,
        "run_grounded_json",
        lambda **kw: calls.append(kw)
        or (
            {"people": [{"name": "Ira Okonkwo", "role": "CTO"}]},
            {"model": "gemini-3.8-flash-lite", "grounded": True, "sources": GEMINI_META["sources"]},
            None,
        ),
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert (dossier["engine"], dossier["model"]) == ("gemini", "gemini-3.8-flash-lite")
    assert dossier["research_error"] is None
    assert claude_calls == []
    # The cheapest, fastest tier: a team roster is a short, well-defined
    # lookup, and cheap enough that the button doesn't stop to confirm
    # (frontend/src/confirmTokens.js).
    assert calls[0]["model"] == founder_dossier.RESEARCH_MODEL == "gemini-3.8-flash-lite"


def test_a_gemini_failure_is_shown_not_handed_to_claude(monkeypatch, company, claude_calls):
    gemini = founder_dossier.ai_engine.gemini_runner
    monkeypatch.setattr(gemini, "is_available", lambda: True)
    monkeypatch.setattr(
        gemini, "run_grounded_json", lambda **kw: (None, {}, "gemini HTTP 503 — unavailable")
    )
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert "503" in dossier["research_error"]
    assert claude_calls == []


def test_without_a_gemini_key_the_refresh_says_so(monkeypatch, company, claude_calls):
    monkeypatch.setattr(founder_dossier.ai_engine.gemini_runner, "is_available", lambda: False)
    dossier = founder_dossier.deep_search_founder_dossier("acme")
    assert dossier["research_error"] == "no Gemini API key configured"
    assert claude_calls == []
