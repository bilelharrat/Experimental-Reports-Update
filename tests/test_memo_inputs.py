"""The firm's own material reaches the memo run (G1 FIX 2, 3, 5; G7 FIX 2).

Calls are staged anonymised (role and relation, never a name; earnings
calls excluded), founder updates with their dates and sources, the deal
terms on file (the pipeline's proposed terms, else the portfolio position),
and open reader flags as untrusted notes inlined into the passes' context —
never as a research-folder file. The readiness endpoint counts what a run
would be built from with the same code.
"""
from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient

from server import deal_pipeline, memo_analysis, memo_fact_check, memo_inputs, memo_prep, storage


@pytest.fixture
def company(tmp_path, monkeypatch):
    data_root = storage.DATA_DIR
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / "companies.yaml").write_text(
        yaml.safe_dump(
            [
                {
                    "id": "acme-ai",
                    "name": "Acme AI",
                    "status": "private",
                    "hq": "San Francisco, CA",
                    "website": "https://acme.ai",
                }
            ]
        ),
        encoding="utf-8",
    )
    return "acme-ai"


def _add_calls(company_id):
    from server import ic_room, transcripts

    ic_room.add_reference_call(
        company_id,
        {
            "contact": "Jane Q. Customer",
            "role": "VP Operations at a logistics customer",
            "relation": "customer",
            "call_date": "2026-06-14",
            "strengths": ["Deployment took two weeks"],
            "concerns": ["Pricing rose 30% at renewal"],
            "quotes": ["We would buy again"],
            "rating": 4,
        },
    )
    transcripts.add_transcript(
        title="Expert call on indoor positioning",
        text="Speaker: the market is early.",
        kind="expert_call",
        company_id=company_id,
        call_date="2026-05-02",
        participants=["Dr. Named Expert"],
    )
    transcripts.add_transcript(
        title="Q2 earnings call",
        text="Operator: welcome.",
        kind="earnings_call",
        company_id=company_id,
        call_date="2026-07-30",
    )


def test_calls_are_staged_without_names(company, tmp_path):
    _add_calls(company)
    research_dir = tmp_path / "research"
    run_dir = tmp_path / "run"
    staged = memo_inputs.stage_run_inputs(company, research_dir, run_dir)

    notes = (research_dir / memo_inputs.CALL_NOTES_FILENAME).read_text(encoding="utf-8")
    assert "Jane" not in notes and "Named Expert" not in notes
    assert "## BSH reference call (customer, 2026-06)" in notes
    assert "Concern: Pricing rose 30% at renewal" in notes
    assert "BSH earnings call" not in notes and "Operator" not in notes
    assert staged["built_from"]["calls"] == 2
    private = json.loads((run_dir / "logs" / "staged_private_items.json").read_text(encoding="utf-8"))
    titles = [item["title"] for item in private]
    assert "BSH reference call (customer, 2026-06)" in titles
    # A source citing the call by its heading names a private item.
    source = {"title": "BSH reference call (customer, 2026-06)", "class": "BSH reference call"}
    assert memo_fact_check.inventory_match(source, private) is not None


def test_founder_updates_and_kpis_carry_dates_and_sources(company, tmp_path):
    from server import portfolio

    portfolio.add_kpi(company, {"as_of": "2026-06-30", "arr_usd": 24_000_000})
    portfolio.add_update(
        company, text="Q2: ARR reached $24M; runway 18 months.", as_of="2026-07-05", subject="Q2 update"
    )
    research_dir = tmp_path / "research"
    staged = memo_inputs.stage_run_inputs(company, research_dir, None)
    text = (research_dir / memo_inputs.FOUNDER_UPDATES_FILENAME).read_text(encoding="utf-8")
    assert "| 2026-06-30 | ARR (USD) | 24000000 | manual |" in text
    assert "2026-07-05 — Q2 update" in text
    assert staged["built_from"]["founder_updates"] >= 2


def test_deal_terms_come_from_the_pipeline_then_the_position(company, tmp_path):
    from server import portfolio

    assert memo_inputs.deal_terms(company) is None
    portfolio.update_position(company, {"round": "Series A2", "security": "SAFE", "invested_usd": 2_000_000})
    fallback = memo_inputs.deal_terms(company)
    assert fallback["source"] == "portfolio_position"
    assert fallback["terms"]["instrument"] == "SAFE"
    deal_pipeline.update_deal_pipeline(
        company,
        {"round": "Series B", "instrument": "Preferred", "pre_money_usd": 900_000_000, "proposed_check_usd": 5_000_000},
    )
    found = memo_inputs.deal_terms(company)
    assert found["source"] == "deal_pipeline"
    assert found["terms"]["pre_money_usd"] == 900_000_000
    staged = memo_inputs.stage_run_inputs(company, tmp_path / "research", None)
    assert staged["deal_terms_on_file"] is True
    text = (tmp_path / "research" / memo_inputs.DEAL_TERMS_FILENAME).read_text(encoding="utf-8")
    assert "| Pre-money (USD) | 900000000 |" in text
    assert "do not assert any other vehicle" in text


def test_deal_pipeline_terms_are_validated_and_returned(company):
    record = deal_pipeline.get_deal_pipeline(company)
    for key in ("round", "instrument", "pre_money_usd", "post_money_usd", "proposed_check_usd", "terms_note"):
        assert key in record and record[key] is None
    updated = deal_pipeline.update_deal_pipeline(company, {"post_money_usd": "1500000000", "terms_note": "  pro rata  "})
    assert updated["post_money_usd"] == 1_500_000_000
    assert updated["terms_note"] == "pro rata"
    with pytest.raises(ValueError):
        deal_pipeline.update_deal_pipeline(company, {"proposed_check_usd": -5})
    with pytest.raises(ValueError):
        deal_pipeline.update_deal_pipeline(company, {"pre_money_usd": "$900M"})
    cleared = deal_pipeline.update_deal_pipeline(company, {"post_money_usd": None})
    assert cleared["post_money_usd"] is None


def test_reader_flags_are_untrusted_inline_notes_never_a_research_file(company, tmp_path):
    from server import firm

    firm.add_comment(
        company,
        text="This number is from 2024",
        author="partner@bsh.vc",
        target={"kind": "section", "ref": "rep-1", "label": "Financial outlook"},
        flag="wrong_number",
        quote="ARR of $40M",
    )
    firm.add_comment(company, text="plain comment", author="a@b.c", target={"kind": "report", "ref": "rep-1"})
    research_dir = tmp_path / "research"
    run_dir = tmp_path / "run"
    staged = memo_inputs.stage_run_inputs(company, research_dir, run_dir)
    assert staged["reader_flags"] == 1
    assert not (research_dir / memo_inputs.READER_FLAGS_FILENAME).exists()
    text = (run_dir / "logs" / memo_inputs.READER_FLAGS_FILENAME).read_text(encoding="utf-8")
    assert "Untrusted reader notes" in text
    assert "not instructions" in text
    assert "wrong number in “Financial outlook”" in text
    assert "plain comment" not in text
    assert memo_analysis._reader_flags_block(run_dir).startswith("## Untrusted reader notes")


def test_the_pass_context_inlines_the_reader_flags(company, tmp_path, monkeypatch):
    run_dir = tmp_path / "data" / "memos" / "acme-ai" / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / memo_inputs.READER_FLAGS_FILENAME).write_text(
        "## Untrusted reader notes (open flags on earlier memos)\n\n- tone\n", encoding="utf-8"
    )
    context = memo_analysis._pass_common_context(
        run_dir=run_dir,
        company_name="Acme AI",
        company_slug="acme-ai",
        run_id="r1",
        research_dir=None,
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )
    assert context.rstrip().endswith("- tone")
    # Without flags the context is exactly the builder's.
    (run_dir / "logs" / memo_inputs.READER_FLAGS_FILENAME).unlink()
    plain = memo_analysis._pass_common_context(
        run_dir=run_dir,
        company_name="Acme AI",
        company_slug="acme-ai",
        run_id="r1",
        research_dir=None,
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )
    from server import claude_runner

    assert plain == claude_runner.memo_fast_pass_common_context(
        run_dir=run_dir,
        company_name="Acme AI",
        company_slug="acme-ai",
        run_id="r1",
        settings_path=memo_prep.SETTINGS_FILE,
        companies_yaml_path=memo_prep.COMPANIES_FILE,
        research_dir=None,
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )


@pytest.mark.parametrize(
    "record, expected",
    [
        ({"hq": "Beijing, China"}, "cn"),
        ({"hq": "Shenzhen, Guangdong"}, "cn"),
        ({"name": "中经网数据有限公司"}, "cn"),
        ({"website": "https://www.example.com.cn/"}, "cn"),
        ({"hq": "Hsinchu, Taiwan", "name": "台积电"}, None),
        ({"hq": "Hong Kong", "legal_name": "香港公司"}, None),
        ({"hq": "San Francisco, CA", "website": "https://acme.ai"}, None),
        ({"hq": "Chinatown, San Francisco"}, None),
    ],
)
def test_jurisdiction_detection(record, expected):
    assert memo_inputs.detect_jurisdiction(record) == expected


def test_readiness_counts_what_a_run_would_be_built_from(company):
    from server.main import app

    _add_calls(company)
    body = TestClient(app).get(f"/api/reports/readiness?company_id={company}").json()
    assert body["inputs"] == {"research_docs": 0, "calls": 2, "founder_updates": 0}
    # Pre-flight: what an outside investor could buy (R29 B).
    assert body["company"]["actionability"]["kind"] == "private_round"
    assert TestClient(app).get("/api/reports/readiness").json()["inputs"] is None


def test_the_run_facts_are_stamped_on_the_package(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / memo_analysis.RUN_INPUTS_FILENAME).write_text(
        json.dumps(
            {"built_from": {"research_docs": 2, "calls": 1, "founder_updates": 0}, "deal_terms_on_file": False}
        ),
        encoding="utf-8",
    )
    package: dict = {"run": {"run_id": "r1"}}
    memo_analysis._stamp_run_facts(package, run_dir)
    assert package["run"]["built_from"] == {"research_docs": 2, "calls": 1, "founder_updates": 0}
    assert package["run"]["deal_terms_on_file"] is False
    assert "analysis_coverage" not in package["run"]  # no fast passes on disk
