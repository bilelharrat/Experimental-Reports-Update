"""Round 2: the optional v1 base-case pin (I24, a P1 warning in the pin
check, never a gate) and the run quality metrics (I10) with their reader
exposure."""
from __future__ import annotations

import json

from server import memo_pin_check, memo_prep, memo_quality_metrics as qm, memo_structure, report_reader


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


BASE_CASE = "Base case: $120M ARR by 2029 at a 10x exit returns 1.0x."


def _package(exec_text: str, finance_text: str) -> dict:
    return {
        "structure": {"stage": "late", "version": 1},
        "sections": [
            {"id": "executive_summary", "blocks": [{"type": "paragraph", "text": _loc(exec_text)}]},
            {"id": "financial_forecast_valuation", "blocks": [
                {"type": "table", "title": _loc("Scenarios"), "rows": [[_loc("Base"), _loc(finance_text)]]},
            ]},
        ],
    }


def test_base_case_pin_is_a_warning_not_a_gate():
    facts = {"base_case_outcome": BASE_CASE}
    echoed = memo_pin_check.check_package_pins(
        _package(f"We watch. {BASE_CASE} [S1]", "Base case: $120M ARR by 2029 at a 10x exit returns 1.0x"), facts
    )
    assert echoed.ok and echoed.warnings == [] and echoed.pins_checked == 1

    missing = memo_pin_check.check_package_pins(
        _package(f"We watch. {BASE_CASE}", "Base case: $150M ARR by 2029 returns 1.3x."), facts
    )
    assert missing.ok  # the gate is untouched
    assert missing.summary_lines() == []
    assert [w.code for w in missing.warnings] == ["base_case_not_echoed"]
    warning = missing.warnings[0]
    assert warning.severity == "P1" and warning.location == "financial_forecast_valuation"
    assert "scenarios" in warning.detail
    assert missing.warning_lines() == [
        f"pin check base_case_not_echoed in section financial_forecast_valuation: {warning.detail}"
    ]
    payload = missing.to_dict()
    assert payload["ok"] is True and payload["warnings"][0]["severity"] == "P1"
    assert payload["findings"] == []
    report = memo_pin_check.render_markdown_report(missing)
    assert "Warnings (report only): 1" in report and "base_case_not_echoed" in report

    both = memo_pin_check.check_package_pins(_package("We watch.", "Nothing pinned here."), facts)
    assert [w.location for w in both.warnings] == ["executive_summary", "financial_forecast_valuation"]


def test_base_case_pin_is_optional():
    result = memo_pin_check.check_package_pins(_package("We watch.", "Nothing."), {})
    assert result.ok and result.warnings == [] and result.pins_checked == 0
    assert memo_structure.SPINE_BASE_CASE_OUTCOME_FIELD == "base_case_outcome"
    assert "base_case_outcome" in memo_structure.SPINE_OPTIONAL_PIN_FIELDS
    # The pin finding's dict carries its severity; gate findings are P0.
    finding = memo_pin_check.PinFinding(code="x", location="y", pin="p", detail="d")
    assert finding.to_dict()["severity"] == "P0"


# ---- quality metrics ---------------------------------------------------------------


def _memo_package() -> dict:
    same = "The category is large and compounding above twenty percent a year but no report sizes the slice."
    return {
        "company": {"name": "ZaiNar, Inc."},
        "structure": {"stage": "late", "version": 1},
        "sections": [
            {"id": "executive_summary", "blocks": [
                {"type": "paragraph", "text": {"en": same + " We watch.", "zh": "我们观望。"}},
            ]},
            {"id": "company_overview", "blocks": [
                {"type": "paragraph", "text": {"en": same + " Another sentence with eight or more words follows here.", "zh": "business model — 7/10。另一句。"}},
                {"type": "paragraph", "text": {"en": "NextNav net loss was $189.3M in 2025.", "zh": "NextNav 2025 年净亏损 1.893 亿美元。"}},
                {"type": "paragraph", "text": {"en": "NextNav's net loss came to $111.9M.", "zh": "NextNav 净亏损 1.119 亿美元。"}},
                {"type": "paragraph", "text": {"en": "The phase-based sync is patented.", "zh": "分阶段同步已获专利。"}},
                {"type": "paragraph", "text": {"en": "phase-based again here.", "zh": "阶段式再次出现。"}},
            ]},
        ],
    }


def test_compute_is_pure_and_shaped_for_the_frontend(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps({
        "coverage_pct": 52.0,
        "findings": [
            {"code": "unsupported_figure", "section_id": "executive_summary", "headline": True},
            {"code": "unsupported_figure", "section_id": "company_overview", "headline": False},
            {"code": "citation_mismatch", "section_id": "executive_summary"},
        ],
    }), encoding="utf-8")
    (run_dir / "logs" / "glossary.json").write_text(json.dumps([{"en": "phase-based", "zh": "分阶段"}]), encoding="utf-8")

    metrics = qm.compute(run_dir, _memo_package(), {"id": "r1"})
    assert metrics["traced_pct"] == 52
    assert metrics["unsupported_headline_figures"] == 1
    assert 0 < metrics["repetition_index"] <= 1
    assert metrics["words_total"] == sum(metrics["words_by_section"].values()) > 0
    assert set(metrics["words_by_section"]) == {"executive_summary", "company_overview"}
    assert metrics["over_cap_sections"] == []  # late v1 has no word budgets
    assert metrics["metric_conflicts"] == 1
    assert metrics["zh_term_drift"] == 1
    assert metrics["untranslated_zh_lines"] == 1
    stored = json.loads((run_dir / "logs" / "quality_metrics.json").read_text(encoding="utf-8"))
    assert stored == metrics
    assert qm.load(run_dir) == metrics
    assert qm.load(tmp_path / "nowhere") is None


def test_compute_without_a_run_or_package_never_raises(tmp_path):
    empty = qm.compute(None, None, None, write=False)
    assert empty["traced_pct"] is None and empty["words_total"] is None
    assert empty["metric_conflicts"] == 0 and empty["over_cap_sections"] == []
    # An older fact check with no headline flag falls back to the section rule.
    fact_check = {"coverage_pct": "91", "findings": [{"code": "unsupported_figure", "section_id": "executive_summary"}]}
    metrics = qm.compute(None, {"sections": []}, {"memo_fact_check": fact_check}, write=False)
    assert metrics["traced_pct"] is None  # a string coverage is not a number
    assert metrics["unsupported_headline_figures"] == 1
    assert qm.repetition_index({"sections": []}) is None


def test_reader_exposes_quality_metrics_from_record_or_logs(tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    run_dir = data_root / "memos" / "zainar-inc" / "run"
    (run_dir / "logs").mkdir(parents=True)
    assert report_reader.quality_metrics({"id": "r"}) is None
    report = {"id": "r", "run_dir": "data/memos/zainar-inc/run", "status": "english_ready_paused", "kind": "memo"}
    assert report_reader.quality_metrics(report) is None
    (run_dir / "logs" / "quality_metrics.json").write_text(json.dumps({"traced_pct": 80}), encoding="utf-8")
    assert report_reader.quality_metrics(report) == {"traced_pct": 80}
    assert report_reader.quality_metrics({**report, "quality_metrics": {"traced_pct": 91}}) == {"traced_pct": 91}
    assert "english_ready_paused" in report_reader.READABLE_STATUSES
    assert report_reader._eligible({"kind": "memo", "status": "english_ready_paused"}) is memo_prep.is_memo_kind("memo")
