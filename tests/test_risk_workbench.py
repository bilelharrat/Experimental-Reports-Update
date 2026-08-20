from server.risk_workbench import (
    apply_framing,
    complete_risk,
    default_priorities,
    merge_task_evidence_into_risk,
    ordered_active_risks,
    packet_strategic_risk_lines,
    risk_score,
)


def test_complete_risk_fills_structured_workbench_fields():
    risk = complete_risk(
        {
            "title": "Can they convert pilots to production?",
            "decision_question": "Are named customers in production?",
            "why_it_matters": "Logos without production do not support the mark.",
            "severity": "high",
            "likelihood": "high",
        },
        {"name": "Generalist"},
        index=1,
    )
    assert risk["id"] == "risk-1"
    assert risk["bull_case_answer"]
    assert risk["bear_case_answer"]
    assert risk["key_questions"]
    assert risk["supporting_evidence"] == []
    assert risk["evidence_that_would_change_assessment"]
    assert risk["suggested_posture"] == "lead_risk"
    assert risk_score(risk) == 9


def test_default_priorities_keep_human_ranking():
    risks = [
        complete_risk(
            {"id": "risk-1", "title": "A", "severity": "high", "likelihood": "high"},
            {},
            index=1,
        ),
        complete_risk(
            {"id": "risk-2", "title": "B", "severity": "low", "likelihood": "low"},
            {},
            index=2,
        ),
    ]
    auto = default_priorities(risks)
    assert auto[0]["risk_id"] == "risk-1"
    human = default_priorities(
        risks,
        [
            {"risk_id": "risk-2", "rank": 1, "selected": True, "human_ranked": True},
            {"risk_id": "risk-1", "rank": 2, "selected": False, "human_ranked": True},
        ],
    )
    assert [row["risk_id"] for row in human] == ["risk-2", "risk-1"]
    assert human[0]["human_ranked"] is True


def test_apply_framing_rewrites_only_the_research_prompt():
    risk = complete_risk(
        {
            "id": "risk-1",
            "title": "Can they convert pilots to production?",
            "bull_case_answer": "Named production already exists.",
            "bear_case_answer": "The logos are still pilots.",
        },
        {"name": "Generalist"},
        index=1,
    )
    framed = apply_framing(risk, "competitive_moat", "Keep the same issue, tighter moat lens.")
    assert framed["id"] == "risk-1"
    assert framed["framing"] == "competitive_moat"
    assert framed["edited_by_human"] is True
    assert "moat" in framed["research_prompt"].lower()
    assert framed["bull_case_answer"] == "Named production already exists."


def test_packet_omits_dismissed_risks_and_keeps_bull_bear():
    risks = [
        complete_risk(
            {
                "id": "risk-1",
                "title": "Pilot conversion",
                "why_it_matters": "It gates the mark.",
                "bull_case_answer": "Production is already live.",
                "bear_case_answer": "Pilots never convert.",
            },
            {},
            index=1,
        ),
        complete_risk({"id": "risk-2", "title": "Noise", "why_it_matters": "Not material."}, {}, index=2),
    ]
    priorities = [
        {"risk_id": "risk-1", "rank": 1, "disposition": "lead_risk", "framing": "go_to_market"},
        {"risk_id": "risk-2", "rank": 2, "disposition": "dismissed", "rationale": "Not material."},
    ]
    active = ordered_active_risks(risks, priorities)
    assert [risk["id"] for risk in active] == ["risk-1"]
    packet = "\n".join(packet_strategic_risk_lines(risks, priorities))
    assert "Pilot conversion" in packet
    assert "Bull: Production is already live." in packet
    assert "Bear: Pilots never convert." in packet
    assert "Dismissed by analyst" in packet
    assert "Noise" not in packet.split("### Dismissed by analyst")[0]


def test_merge_task_evidence_updates_parent_risk_status():
    risk = complete_risk({"id": "risk-1", "title": "Pilot conversion"}, {}, index=1)
    merged = merge_task_evidence_into_risk(
        risk,
        {
            "status": "done",
            "supporting_evidence": [{"excerpt": "One line is live.", "source_class": "news"}],
            "contradicting_evidence": [
                {"excerpt": "The second site is a pilot.", "source_class": "third_party"}
            ],
            "remaining_evidence_limits": ["No utilization data."],
            "answer": "Mixed production evidence.",
        },
    )
    assert merged["status"] == "researched"
    assert merged["supporting_evidence"][0]["excerpt"] == "One line is live."
    assert merged["contradicting_evidence"][0]["source_class"] == "third_party"
    assert "No utilization data." in merged["missing_evidence"]
