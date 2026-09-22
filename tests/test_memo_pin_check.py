"""Tests for the deterministic pin-echo checker."""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner, memo_analysis, memo_pin_check


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


def _shared_facts() -> dict:
    return {
        "recommendation_sentence": (
            "Recommendation: BSH commits to the round through the SPV."
        ),
        "key_metrics": [
            {"name": "ARR", "value": "$10M", "as_of": "2026-05-01"},
            {"name": "Headcount", "value": "70,000", "as_of": "2026-05-01"},
            {"name": "Gross margin", "value": "Not disclosed", "as_of": "-"},
        ],
        "scenarios": {
            "bear": "0.8x MOIC on $40M exit",
            "base": "1.5x on $75M",
            "bull": "2.4x on $120M",
        },
        "risks": [
            {
                "summary": "Customer concentration",
                "rating": "7/10",
                "likelihood": "Medium",
            },
            {
                "summary": "Execution slip",
                "rating": "6/10",
                "likelihood": "High",
            },
        ],
        "source_topics": {"S1": "Data room"},
    }


def _echoing_package() -> dict:
    return {
        "schema_version": 1,
        "company": {"name": "Generalist, Inc."},
        "run": {"run_id": "r1", "language": "en"},
        "sources": [],
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": _loc(
                            "Recommendation: BSH commits to the round "
                            "through the SPV."
                        ),
                    },
                    {
                        "type": "table",
                        "component": "key_metrics_snapshot",
                        "title": _loc("Key Metrics Snapshot"),
                        "rows": [
                            [_loc("ARR"), _loc("$10M")],
                            # Deliberately unformatted: the pin says
                            # "70,000" — the squashed comparison must
                            # still match.
                            [_loc("Headcount"), _loc("70000 employees")],
                        ],
                    },
                ],
            },
            {"id": "company_overview", "blocks": []},
            {"id": "investment_highlights", "blocks": []},
            {
                "id": "investment_risk",
                "blocks": [
                    {
                        "type": "heading",
                        "text": _loc("Risk 1: Customer concentration"),
                    },
                    {"type": "paragraph", "text": _loc("Rated 7/10.")},
                    {
                        "type": "heading",
                        "text": _loc("Risk 2: Execution slip"),
                    },
                    {"type": "paragraph", "text": _loc("Rated 6/10.")},
                ],
            },
            {
                "id": "financial_forecast_valuation",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": _loc(
                            "Bear 0.8x MOIC on a $40M exit; base 1.5x on "
                            "$75M; bull 2.4x on $120M."
                        ),
                    },
                ],
            },
        ],
    }


def test_clean_package_passes():
    result = memo_pin_check.check_package_pins(
        _echoing_package(), _shared_facts()
    )
    assert result.ok, [f.to_dict() for f in result.findings]
    # recommendation + 2 checkable metrics + 2 risk ratings + 3 scenarios
    assert result.pins_checked == 8
    # the "Not disclosed" metric value is uncheckable
    assert result.pins_skipped == 1


def test_decision_history_pin_is_enforced_only_when_present():
    history = (
        "BSH made the decision to pass on 2026-01-05 because the valuation "
        "was too rich."
    )
    facts = {**_shared_facts(), "decision_history_sentence": history}

    # Pin set but not echoed → flagged.
    result = memo_pin_check.check_package_pins(_echoing_package(), facts)
    codes = [f.code for f in result.findings]
    assert "decision_history_not_echoed" in codes

    # Pin echoed verbatim in the exec summary → clean.
    package = _echoing_package()
    package["sections"][0]["blocks"].append(
        {"type": "paragraph", "text": _loc(history)}
    )
    result = memo_pin_check.check_package_pins(package, facts)
    assert result.ok, [f.to_dict() for f in result.findings]
    assert result.pins_checked == 9  # recommendation + history + 7 others

    # No pin → no check (legacy spines and no-decision companies).
    result = memo_pin_check.check_package_pins(
        _echoing_package(), _shared_facts()
    )
    assert "decision_history_not_echoed" not in [
        f.code for f in result.findings
    ]


def test_reworded_recommendation_is_flagged():
    package = _echoing_package()
    package["sections"][0]["blocks"][0]["text"] = _loc(
        "Participation in the round is recommended."
    )
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    codes = [f.code for f in result.findings]
    assert codes == ["recommendation_not_echoed"]


def test_missing_metric_value_is_flagged():
    package = _echoing_package()
    package["sections"][0]["blocks"][1]["rows"] = [[_loc("ARR"), _loc("$10M")]]
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    codes = [f.code for f in result.findings]
    assert codes == ["metric_value_missing"]
    assert "70,000" in result.findings[0].pin


def test_prose_metric_value_matches_by_numbers():
    """Spines legally pack treatment prose into `value`; sections echo the
    numbers, not the sentence (live Run D observation). The checker must
    match on numeric tokens, not the verbatim string."""
    facts = _shared_facts()
    facts["key_metrics"].append(
        {
            "name": "Contracts and MOUs",
            "value": (
                "$450M+ at launch, revised to $500M+; conversion modeled "
                "at 10% to 20%"
            ),
            "as_of": "2026-06-01",
        }
    )
    package = _echoing_package()
    package["sections"][1]["blocks"] = [
        {
            "type": "paragraph",
            "text": _loc(
                "Disclosed contracts and MOUs of $450M+ were later revised "
                "to $500M+; we model conversion at 10% to 20%."
            ),
        }
    ]
    result = memo_pin_check.check_package_pins(package, facts)
    assert result.ok, [f.to_dict() for f in result.findings]
    # When the numbers are wholesale absent, it still flags.
    package["sections"][1]["blocks"] = []
    result = memo_pin_check.check_package_pins(package, facts)
    codes = [f.code for f in result.findings]
    assert codes == ["metric_value_missing"]
    assert "$450M" in result.findings[0].detail


def test_numberless_prose_metric_value_is_skipped():
    facts = _shared_facts()
    facts["key_metrics"].append(
        {
            "name": "Named references",
            "value": (
                "None disclosed; the award is a subsidy selection, modeled "
                "as pilot-stage evidence"
            ),
            "as_of": "2026-06-01",
        }
    )
    result = memo_pin_check.check_package_pins(_echoing_package(), facts)
    assert result.ok
    # "Not disclosed" plus the numberless prose value are both uncheckable.
    assert result.pins_skipped == 2


def test_metric_value_anywhere_in_package_counts():
    package = _echoing_package()
    package["sections"][0]["blocks"][1]["rows"] = [[_loc("ARR"), _loc("$10M")]]
    package["sections"][1]["blocks"] = [
        {"type": "paragraph", "text": _loc("The team grew to 70,000.")}
    ]
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    assert result.ok


def test_missing_risk_rating_and_weak_summary_are_flagged():
    package = _echoing_package()
    package["sections"][3]["blocks"] = [
        {"type": "heading", "text": _loc("Risk 1: Customer concentration")},
        {"type": "paragraph", "text": _loc("Rated 7/10.")},
        # Execution slip (6/10) dropped entirely.
    ]
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    codes = [f.code for f in result.findings]
    assert codes == ["risk_rating_missing"]

    # Same rating present but the pinned summary unrecognizable.
    package["sections"][3]["blocks"].append(
        {"type": "paragraph", "text": _loc("A second concern rated 6/10.")}
    )
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    codes = [f.code for f in result.findings]
    assert codes == ["risk_summary_weak"]


def test_missing_scenario_numbers_are_flagged():
    package = _echoing_package()
    package["sections"][4]["blocks"] = [
        {"type": "paragraph", "text": _loc("Bear 0.8x MOIC on a $40M exit.")}
    ]
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    codes = sorted(f.code for f in result.findings)
    assert codes == [
        "scenario_numbers_missing",
        "scenario_numbers_missing",
    ]
    pins = " ".join(f.pin for f in result.findings)
    assert "base" in pins and "bull" in pins


def test_summary_lines_map_to_owning_sections():
    package = _echoing_package()
    package["sections"][0]["blocks"][0]["text"] = _loc("Different opener.")
    package["sections"][3]["blocks"] = []
    result = memo_pin_check.check_package_pins(package, _shared_facts())
    lines = result.summary_lines()
    mapped = {
        claude_runner._section_for_validation_error(package, line)
        for line in lines
    }
    assert "executive_summary" in mapped
    assert "investment_risk" in mapped


def test_run_memo_pin_check_writes_report_and_emits(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_PIN_CHECK", raising=False)
    # server.main loads the machine-local .env into os.environ when any
    # test imports it; pin the repair flag so an armed .env (it is armed
    # since Round 4) cannot flip repair_feed under this test.
    monkeypatch.setenv("BSH_MEMO_PIN_CHECK_REPAIR", "0")
    run_dir = tmp_path / "memo-run"
    units = run_dir / "logs" / "english_units"
    units.mkdir(parents=True)
    (units / "spine.json").write_text(
        json.dumps({"shared_facts": _shared_facts()}), encoding="utf-8"
    )
    events: list[dict] = []

    class _Progress:
        def emit(self, type_, **fields):
            events.append({"type": type_, **fields})

    lines = memo_analysis._run_memo_pin_check(
        run_dir=run_dir,
        candidate=_echoing_package(),
        progress=_Progress(),
        attempt=1,
    )
    assert lines == []
    report = (run_dir / "logs" / "pin_check.md").read_text()
    assert "Pins checked: 8" in report
    assert events and events[0]["stage"] == "memo_pin_check"
    assert events[0]["pins_checked"] == 8
    assert events[0]["repair_feed"] is False


def test_run_memo_pin_check_disabled_or_no_spine(tmp_path, monkeypatch):
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)

    class _Progress:
        def emit(self, *a, **k):
            raise AssertionError("must not emit")

    # No spine on disk (monolithic path): silently skipped.
    monkeypatch.setenv("BSH_MEMO_PIN_CHECK", "1")
    assert (
        memo_analysis._run_memo_pin_check(
            run_dir=run_dir,
            candidate=_echoing_package(),
            progress=_Progress(),
        )
        == []
    )
    # Flag off: skipped even with a spine.
    units = run_dir / "logs" / "english_units"
    units.mkdir(parents=True)
    (units / "spine.json").write_text(
        json.dumps({"shared_facts": _shared_facts()}), encoding="utf-8"
    )
    monkeypatch.setenv("BSH_MEMO_PIN_CHECK", "0")
    assert (
        memo_analysis._run_memo_pin_check(
            run_dir=run_dir,
            candidate=_echoing_package(),
            progress=_Progress(),
        )
        == []
    )
    assert not (run_dir / "logs" / "pin_check.md").exists()
