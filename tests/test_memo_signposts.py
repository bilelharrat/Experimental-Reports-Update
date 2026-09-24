"""Signposts, phase 1 (R32): every memo's falsifiable "we watch" items in
one structured list, on every path, with a warning for a listed signpost
the memo never states. Nothing is rendered and no model is called."""
from __future__ import annotations

import json

import pytest

from memo_v2_fixture import late_v2_package
from server import claude_runner, memo_analysis, memo_signposts


def test_signposts_are_derived_from_the_risk_cards_and_the_monitoring_table():
    signposts = memo_signposts.extract(late_v2_package())
    assert [s["id"] for s in signposts] == [f"SP{n}" for n in range(1, 10)]
    first = signposts[0]
    assert first["origin"] == "risk_card"
    assert first["claim_en"] == "Quarterly revenue against the $118M 2026 plan."  # citation stripped
    assert first["claim_zh"].startswith("季度收入")
    assert first["links_to_risk"].startswith("Risk 1: The entry price already assumes")
    assert first["source_section"] == "investment_risk"
    assert first["kind"] == "metric"
    valuation = next(s for s in signposts if s["origin"] == "monitoring_table")
    assert valuation == {
        "id": "SP7",
        "claim_en": "Post-money valuation: ≤ $1.6B (now $2.4B)",
        "claim_zh": "投后估值：≤ $1.6B（当前 $2.4B）",
        "kind": "price",
        "metric": "Post-money valuation",
        "threshold": "≤ $1.6B",
        "direction": "below",
        "due_by": None,
        "links_to_risk": None,
        "source_section": "investment_decision",
        "origin": "monitoring_table",
    }


def test_the_writers_own_list_wins_and_is_normalised():
    package = late_v2_package()
    package["signposts"] = [
        {
            "id": "SP1",
            "claim_en": "Q3 2026 ARR at or above $40M",
            "kind": "nonsense",
            "source_section": "investment_decision",
        },
        "junk",
        {"claim_en": ""},
    ]
    (signpost,) = memo_signposts.extract(package)
    assert signpost["origin"] == "package"
    assert signpost["kind"] == "metric"
    assert signpost["direction"] == "above"
    assert signpost["due_by"] == "2026-Q3"
    assert memo_signposts.extract("not a package") == []


@pytest.mark.parametrize(
    "text, due",
    [
        ("Q3 2026 ARR", "2026-Q3"),
        ("2027 Q1 audit", "2027-Q1"),
        ("by 2026-09", "2026-09"),
        ("renewal in September 2026", "2026-09"),
        ("before the 2027 audit", "2027"),
        ("each quarter", None),
    ],
)
def test_due_dates_keep_their_written_precision(text, due):
    assert memo_signposts.due_by_of(text) == due


def test_listed_signposts_the_memo_never_states_are_flagged():
    package = late_v2_package()
    package["signposts"] = [
        {"id": "SP1", "claim_en": "Average revenue per MWh under management", "kind": "metric", "source_section": "investment_risk"},
        {"id": "SP2", "claim_en": "A second hyperscaler signs a data-centre contract", "kind": "event", "source_section": "investment_decision"},
    ]
    findings = memo_signposts.echo_findings(package)
    assert [f["id"] for f in findings] == ["SP2"]
    # Derived signposts come from the memo itself: nothing to check.
    assert memo_signposts.echo_findings(late_v2_package()) == []


def test_finalize_writes_the_runs_signposts_and_warns_for_unstated_ones(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    package = late_v2_package()
    package["signposts"] = [
        {"id": "SP1", "claim_en": "A second hyperscaler signs a data-centre contract", "kind": "event", "source_section": "investment_decision"}
    ]
    warnings = memo_analysis._RunWarnings()
    memo_analysis._record_signposts(run_dir, warnings, package)
    stored = json.loads((run_dir / "logs" / memo_analysis.SIGNPOSTS_FILENAME).read_text(encoding="utf-8"))
    assert [s["id"] for s in stored["signposts"]] == ["SP1"]
    assert warnings.en == ["Signposts: 1 listed signpost is not stated in the memo"]
    assert warnings.items[0]["gate"] == "signposts"
    clean = memo_analysis._RunWarnings()
    memo_analysis._record_signposts(run_dir, clean, late_v2_package())
    assert not clean
    assert len(json.loads((run_dir / "logs" / memo_analysis.SIGNPOSTS_FILENAME).read_text(encoding="utf-8"))["signposts"]) == 9


def test_both_package_schemas_offer_the_optional_list():
    for schema in (claude_runner.MEMO_FAST_ENGLISH_PACKAGE_SCHEMA, claude_runner.MEMO_FAST_BILINGUAL_PACKAGE_SCHEMA):
        package = schema["properties"]["memo_package"]
        assert package["additionalProperties"] is True
        assert package["properties"]["signposts"] is claude_runner.MEMO_SIGNPOSTS_SCHEMA
        assert "required" not in package
    good = [{"id": "SP1", "claim_en": "x", "kind": "event", "source_section": "investment_decision", "direction": None}]
    assert claude_runner._schema_errors(good, claude_runner.MEMO_SIGNPOSTS_SCHEMA) == []


def test_a_due_year_next_to_letters_is_still_a_due_date():
    # A \b between "1" and "E" never matched: "by 2027E" had no due date.
    assert memo_signposts.due_by_of("by FY2027") == "2027"
    assert memo_signposts.due_by_of("by 2027E") == "2027"
    assert memo_signposts.due_by_of("$20271M of revenue") is None
