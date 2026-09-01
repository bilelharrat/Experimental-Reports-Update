"""Tests for the Memo Studio card ↔ spine round trip.

Seed direction: ``memo_editor_store.apply_agent_spine`` (spine → cards).
Generate direction: ``memo_studio_bridge.compose_spine`` (cards → spine).
The composed ``shared_facts`` is what the pin-echo gate enforces, so the
round trip is the studio's whole correctness story.
"""
from __future__ import annotations

import pytest
import yaml

from server import memo_editor_store, memo_studio_bridge, serena_analysis, storage


@pytest.fixture
def studio_env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(memo_editor_store, "EDITOR_ROOT", data_root / "memo_editor")
    monkeypatch.setattr(serena_analysis, "ANALYSIS_ROOT", data_root / "serena_analysis")
    monkeypatch.setattr(serena_analysis, "TRAINING_ROOT", data_root / "serena_training")
    data_root.mkdir(parents=True)
    companies = [
        {
            "id": "zainar-test",
            "name": "ZaiNar Test",
            "status": "private",
            "metrics": [
                {"label": "ARR", "value": "$24M", "as_of": "2026-06-13"}
            ],
        }
    ]
    with (data_root / "companies.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(companies, f, sort_keys=False)
    return data_root


def _investigation_spine() -> dict:
    return {
        "package_skeleton": {
            "schema_version": 1,
            "company": {"name": "ZaiNar Test"},
            "run": {"run_id": "r1", "language": "en"},
            "sources": [
                {"id": "S1", "title": {"en": "Data room", "zh": ""}},
                {"id": "S2", "title": {"en": "10-Q", "zh": ""}},
            ],
        },
        "shared_facts": {
            "recommendation_sentence": "We recommend participating in the round.",
            "key_metrics": [
                {
                    "name": "Contracts and MOUs",
                    "value": "$500M+",
                    "as_of": "2026-06-13",
                    "source_ids": ["S1"],
                }
            ],
            "scenarios": {
                "bear": "0.8x on $40M",
                "base": "1.5x on $75M",
                "bull": "2.4x on $120M",
            },
            "risks": [
                {"summary": "Customer concentration", "rating": "8/10", "likelihood": "Medium"},
                {"summary": "Execution slip", "rating": "6/10", "likelihood": "High"},
                {"summary": "Competitive compression", "rating": "5/10", "likelihood": "Medium"},
                {"summary": "Regulatory drag", "rating": "3/10", "likelihood": "Low"},
            ],
            "source_topics": {"S1": "Contract book", "S2": "Concentration"},
        },
        "section_notes": {"company_overview": "Note the carrier deployments."},
        "studio_extras": {
            "thesis_points": [
                {
                    "title": "Contracted demand",
                    "support": "The $500M+ book covers the plan.",
                    "source_ids": ["S1"],
                },
                {
                    "title": "Network moat",
                    "support": "Existing 5G infrastructure reuse.",
                },
            ],
            "conclusion_options": [
                {
                    "label": "Invest",
                    "recommendation_sentence": "We recommend participating in the round.",
                    "rationale": "Contracted demand covers the case.",
                },
                {
                    "label": "Decline",
                    "recommendation_sentence": "We recommend passing on this round.",
                    "rationale": "Concentration is unresolved.",
                },
            ],
        },
    }


def _provenance() -> dict:
    return {"report_id": "abc123", "run_id": "r1", "mode": "studio"}


# ---- seed direction -------------------------------------------------------


def test_apply_agent_spine_seeds_all_sections(studio_env):
    state = memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )

    exec_section = state["sections"]["executive_summary"]
    assert exec_section["recommendation"] == (
        "We recommend participating in the round."
    )
    assert "Contracts and MOUs: $500M+ (as of 2026-06-13)." in exec_section["body"]

    risks = state["sections"]["risks_mitigations"]["cards"]
    assert [card["title"] for card in risks] == [
        "Customer concentration",
        "Execution slip",
        "Competitive compression",
        "Regulatory drag",
    ]
    assert risks[0]["severity"] == "high"
    assert risks[0]["agent_rating"] == "8/10"
    assert risks[0]["likelihood"] == "Medium"
    assert risks[0]["agent_rank"] == 1
    assert risks[3]["severity"] == "low"
    assert [card["rank"] for card in risks] == [1, 2, 3, 4]

    thesis = state["sections"]["investment_thesis"]["cards"]
    assert [card["title"] for card in thesis] == [
        "Contracted demand",
        "Network moat",
    ]
    assert thesis[0]["bullets"][0]["text"] == "The $500M+ book covers the plan."

    conclusion = state["sections"]["conclusion"]
    assert [option["label"] for option in conclusion["options"]] == [
        "Invest",
        "Decline",
    ]
    selected = next(
        option
        for option in conclusion["options"]
        if option["id"] == conclusion["selected_option_id"]
    )
    assert selected["label"] == "Invest"

    assert state["pinned_facts"]["key_metrics"][0]["value"] == "$500M+"
    assert state["pinned_facts"]["scenarios"]["bull"] == "2.4x on $120M"
    assert state["agent_run"]["report_id"] == "abc123"
    assert state["agent_run"]["mode"] == "studio"
    assert state["audit_records"][-1]["event"] == "agent_spine_applied"


def test_apply_agent_spine_snapshots_previous_state(studio_env):
    before = memo_editor_store.get_state("zainar-test")
    after = memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )
    assert after["revision"] > before["revision"]
    versions = memo_editor_store._versions_dir("zainar-test")
    assert any(versions.glob("*.yaml"))


def test_apply_agent_spine_without_extras_keeps_thesis_cards(studio_env):
    # First seed the studio state fully, then simulate a One-Click publish
    # (its spine has no studio_extras).
    memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )
    auto_spine = _investigation_spine()
    auto_spine.pop("studio_extras")
    auto_spine["shared_facts"]["recommendation_sentence"] = (
        "We recommend passing on this round."
    )
    state = memo_editor_store.apply_agent_spine(
        "zainar-test", auto_spine, {"report_id": "auto1", "mode": "auto"}
    )

    # Thesis cards survive untouched.
    assert [card["title"] for card in state["sections"]["investment_thesis"]["cards"]] == [
        "Contracted demand",
        "Network moat",
    ]
    # The agent stance appears as its own option and is selected; the
    # studio-seeded options stay.
    conclusion = state["sections"]["conclusion"]
    assert conclusion["selected_option_id"] == "agent_recommendation"
    labels = [option["label"] for option in conclusion["options"]]
    assert "Invest" in labels and "Agent recommendation" in labels
    assert state["agent_run"]["mode"] == "auto"


def test_apply_agent_spine_rejects_factless_spine(studio_env):
    with pytest.raises(ValueError):
        memo_editor_store.apply_agent_spine("zainar-test", {"nope": 1}, {})


# ---- rating normalization -------------------------------------------------


def test_normalize_rating_matrix():
    normalize = memo_studio_bridge.normalize_rating
    assert normalize({"agent_rating": "7/10"}) == "7/10"
    assert normalize({"agent_rating": "7"}) == "7/10"
    assert normalize({"agent_rating": 7}) == "7/10"
    assert normalize({"agent_rating": "10 / 10"}) == "10/10"
    assert normalize({"agent_rating": "0/10", "severity": "high"}) == "8/10"
    assert normalize({"agent_rating": "garbage", "severity": "low"}) == "3/10"
    assert normalize({"severity": "medium"}) == "5/10"
    assert normalize({}) == "5/10"


# ---- generate direction ---------------------------------------------------


def test_compose_spine_round_trip_honors_edits(studio_env):
    memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )
    state = memo_editor_store.get_state("zainar-test")
    risks = state["sections"]["risks_mitigations"]["cards"]
    # User edits: exclude one risk, promote the last to the top, pick the
    # other stance.
    memo_editor_store.patch_card(
        "zainar-test", "risks_mitigations", risks[2]["id"], {"included": False}
    )
    memo_editor_store.move_card(
        "zainar-test", "risks_mitigations", risks[3]["id"], "up"
    )
    state = memo_editor_store.get_state("zainar-test")
    conclusion = state["sections"]["conclusion"]
    decline = next(
        option for option in conclusion["options"] if option["label"] == "Decline"
    )
    memo_editor_store.select_conclusion("zainar-test", decline["id"])
    state = memo_editor_store.get_state("zainar-test")

    spine, pin_sheet, warnings = memo_studio_bridge.compose_spine(
        state, _investigation_spine(), provenance={"report_id": "abc123"}
    )

    facts = spine["shared_facts"]
    assert facts["recommendation_sentence"] == (
        "We recommend passing on this round."
    )
    # Excluded card gone (the "up" move swaps Regulatory past the excluded
    # Competitive card); user order preserved; 3 included → warning.
    assert [risk["summary"] for risk in facts["risks"]] == [
        "Customer concentration",
        "Execution slip",
        "Regulatory drag",
    ]
    assert facts["risks"][2]["rating"] == "3/10"
    assert any("risk cards" in warning for warning in warnings)
    # Pinned facts round-trip verbatim.
    assert facts["key_metrics"][0]["value"] == "$500M+"
    assert facts["scenarios"]["bear"] == "0.8x on $40M"
    assert facts["source_topics"]["S2"] == "Concentration"
    # Skeleton copied unchanged; base section notes survive.
    assert spine["package_skeleton"]["sources"][1]["id"] == "S2"
    assert spine["section_notes"]["company_overview"] == (
        "Note the carrier deployments."
    )
    assert "Pinned theses, in this order: 1) Contracted demand" in (
        spine["section_notes"]["investment_highlights"]
    )
    assert "studio_pin_sheet.md" in spine["section_notes"]["investment_risk"]
    assert spine["studio_provenance"]["report_id"] == "abc123"
    assert spine["studio_provenance"]["revision_id"] == state["revision_id"]
    # Pin sheet carries the human-reviewed content.
    assert "We recommend passing on this round." in pin_sheet
    assert "Contracted demand" in pin_sheet
    assert "Customer concentration" in pin_sheet


def test_compose_spine_errors(studio_env):
    memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )
    state = memo_editor_store.get_state("zainar-test")

    with pytest.raises(memo_studio_bridge.StudioComposeError):
        memo_studio_bridge.compose_spine(state, None)
    with pytest.raises(memo_studio_bridge.StudioComposeError):
        memo_studio_bridge.compose_spine(
            state, {"package_skeleton": {"sources": []}}
        )

    broken = memo_editor_store.get_state("zainar-test")
    broken["sections"]["conclusion"]["selected_option_id"] = "missing"
    with pytest.raises(memo_studio_bridge.StudioComposeError):
        memo_studio_bridge.compose_spine(broken, _investigation_spine())

    none_included = memo_editor_store.get_state("zainar-test")
    for card in none_included["sections"]["risks_mitigations"]["cards"]:
        card["included"] = False
    with pytest.raises(memo_studio_bridge.StudioComposeError):
        memo_studio_bridge.compose_spine(none_included, _investigation_spine())


def test_compose_spine_truncates_long_conclusion(studio_env):
    memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )
    state = memo_editor_store.get_state("zainar-test")
    conclusion = state["sections"]["conclusion"]
    selected = next(
        option
        for option in conclusion["options"]
        if option["id"] == conclusion["selected_option_id"]
    )
    selected["text"] = "We recommend " + "x" * 400

    spine, _sheet, warnings = memo_studio_bridge.compose_spine(
        state, _investigation_spine()
    )
    assert len(spine["shared_facts"]["recommendation_sentence"]) <= 300
    assert any("truncated" in warning for warning in warnings)


# ---- card add/remove ------------------------------------------------------


def test_add_and_delete_card(studio_env):
    memo_editor_store.apply_agent_spine(
        "zainar-test", _investigation_spine(), _provenance()
    )
    state = memo_editor_store.add_card(
        "zainar-test",
        "risks_mitigations",
        {
            "title": "Key-person dependency",
            "rating": "6",
            "likelihood": "Medium",
            "bullets": ["Five founders carry the IP."],
        },
    )
    cards = state["sections"]["risks_mitigations"]["cards"]
    assert cards[-1]["title"] == "Key-person dependency"
    assert cards[-1]["rank"] == len(cards)
    assert cards[-1]["agent_rating"] == "6"
    assert cards[-1]["bullets"][0]["text"] == "Five founders carry the IP."

    # The new card becomes a normalized pin at compose time.
    spine, _sheet, _warnings = memo_studio_bridge.compose_spine(
        memo_editor_store.get_state("zainar-test"), _investigation_spine()
    )
    added = [
        risk
        for risk in spine["shared_facts"]["risks"]
        if risk["summary"] == "Key-person dependency"
    ]
    assert added and added[0]["rating"] == "6/10"

    state = memo_editor_store.delete_card(
        "zainar-test", "risks_mitigations", cards[-1]["id"]
    )
    remaining = state["sections"]["risks_mitigations"]["cards"]
    assert all(card["title"] != "Key-person dependency" for card in remaining)
    assert [card["rank"] for card in remaining] == list(
        range(1, len(remaining) + 1)
    )
    with pytest.raises(ValueError):
        memo_editor_store.delete_card(
            "zainar-test", "risks_mitigations", "missing-card"
        )


def test_add_card_requires_title_and_card_section(studio_env):
    with pytest.raises(ValueError):
        memo_editor_store.add_card("zainar-test", "risks_mitigations", {})
    with pytest.raises(ValueError):
        memo_editor_store.add_card(
            "zainar-test", "conclusion", {"title": "Nope"}
        )
