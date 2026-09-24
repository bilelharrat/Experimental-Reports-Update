"""Round 2, P1b: the run glossary (I5), quote-backed claims (I6) and the
red-team pass (I12). Fake runners only."""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner, memo_flags

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    return run_dir


# ---- the glossary ------------------------------------------------------------


def test_glossary_is_deterministic_and_leads_with_the_company(tmp_path):
    v2 = _load("zainar_v2_draft.en.json")
    terms = claude_runner.build_memo_glossary(v2)
    assert terms == claude_runner.build_memo_glossary(json.loads(json.dumps(v2)))
    assert terms[0] == {"en": "ZaiNar, Inc.", "zh": ""}
    ens = [t["en"] for t in terms]
    assert "Pass" in ens  # the verdict callout's vocabulary
    assert "Follow" not in ens  # "follow-on" in prose is not a verdict
    assert {"ARR", "MOIC", "IRR", "post-money"} <= set(ens)
    # Shouted labels are not acronyms.
    assert not {"TO", "BE", "BY", "IC"} & set(ens) or "IC" in ens
    assert "TO" not in ens and "BE" not in ens and "BY" not in ens
    assert len(terms) <= claude_runner.MEMO_GLOSSARY_MAX_TERMS
    assert all(t["zh"] == "" for t in terms)
    v1 = _load("zainar_v1_package.json")
    v1_terms = claude_runner.build_memo_glossary(v1)
    assert v1_terms[0]["en"] == "ZaiNar, Inc."
    assert "Steve Jurvetson" in [t["en"] for t in v1_terms]


def test_glossary_extend_and_freeze(tmp_path):
    run_dir = _run_dir(tmp_path)
    assert claude_runner.load_memo_glossary(run_dir) == []
    section = {
        "id": "executive_summary",
        "blocks": [
            {"type": "callout", "title": {"en": "Pass — 52/100", "zh": ""}, "body": {"en": "ARR and ARR again.", "zh": ""}},
        ],
    }
    terms = claude_runner.extend_memo_glossary(run_dir, section)
    assert [t["en"] for t in terms] == ["Pass", "ARR"]
    path = run_dir / "logs" / "glossary.json"
    assert json.loads(path.read_text(encoding="utf-8")) == terms
    # The first translation fixes the terms; blanks only.
    assert claude_runner.freeze_memo_glossary_zh(run_dir, [("Pass", "不建议投资"), ("ARR", ""), ("nope", "x")]) == 1
    # A later call cannot overwrite a frozen term, only fill a blank one.
    assert claude_runner.freeze_memo_glossary_zh(run_dir, [("Pass", "放弃"), ("ARR", "年度经常性收入")]) == 1
    frozen = claude_runner.load_memo_glossary(run_dir)
    assert frozen == [{"en": "Pass", "zh": "不建议投资"}, {"en": "ARR", "zh": "年度经常性收入"}]
    # Extending with more sections keeps every frozen term and adds new ones.
    more = {"sections": [section, {"id": "risks", "blocks": [{"type": "paragraph", "text": {"en": "MOIC, MOIC.", "zh": ""}}]}]}
    terms = claude_runner.extend_memo_glossary(run_dir, more)
    assert terms[:2] == frozen and terms[2] == {"en": "MOIC", "zh": ""}
    # The prompt block names the fixed terms and asks for the rest.
    block = claude_runner.memo_glossary_prompt_block(terms)
    assert "1. Pass → 不建议投资" in block
    assert "3. MOIC → (not yet fixed)" in block
    assert "`glossary_zh`" in block and "(3 items)" in block
    assert claude_runner.memo_glossary_prompt_block([]) == ""


def test_every_compact_translation_carries_the_glossary_and_freezes_its_answer(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    claude_runner.write_memo_glossary(run_dir, [{"en": "ARR", "zh": ""}, {"en": "Pass", "zh": "不建议投资"}])
    captured: list[dict] = []

    def fake_runner(**kw):
        captured.append(kw)
        count = kw["schema"]["properties"]["zh"]["minItems"]
        return {
            "zh": [f"中文{i}" for i in range(count)],
            "glossary_zh": ["年度经常性收入", "放弃"],
            "claude_cost_usd": 0.1,
            "claude_duration_ms": 5,
        }, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    unit_path = run_dir / "unit.json"
    unit_path.write_text(
        json.dumps({"blocks": [{"type": "paragraph", "text": {"en": "ARR grew.", "zh": ""}}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    unit, error = claude_runner._run_bilingual_unit(
        run_dir=run_dir, company_name="Z", run_id="r", unit_label="section x",
        unit_path=unit_path, progress=None, timeout_sec=60,
    )
    assert error is None and unit["blocks"][0]["text"]["zh"] == "中文0"
    kw = captured[0]
    assert "Use exactly these Chinese terms" in kw["prompt"]
    assert "1. ARR → (not yet fixed)" in kw["prompt"]
    assert "2. Pass → 不建议投资" in kw["prompt"]
    glossary_schema = kw["schema"]["properties"]["glossary_zh"]
    assert glossary_schema["minItems"] == glossary_schema["maxItems"] == 2
    assert "glossary_zh" not in kw["schema"]["required"]
    # The blank was fixed by this call; the frozen term survived the
    # model's different answer for it.
    assert claude_runner.load_memo_glossary(run_dir) == [
        {"en": "ARR", "zh": "年度经常性收入"},
        {"en": "Pass", "zh": "不建议投资"},
    ]


def test_no_glossary_leaves_the_compact_prompt_and_schema_alone(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    captured: dict = {}
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact",
        lambda **kw: (captured.update(kw) or ({"zh": ["中"]}, None)),
    )
    translations, error, _c, _d = claude_runner._run_zh_compact_call(
        run_dir=run_dir, company_name="Z", run_id="r", unit_label="u",
        slots=[{"en": "x", "zh": ""}], progress=None, timeout_sec=60,
    )
    assert error is None and translations == ["中"]
    assert captured["schema"] == claude_runner._memo_zh_compact_schema(1)
    assert "glossary_zh" not in captured["schema"]["properties"]
    # The style guide carries its own "### Glossary"; the run block is absent.
    assert "## Glossary (fixed Chinese terms)" not in captured["prompt"]


def test_the_full_unit_and_monolithic_prompts_carry_the_glossary(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    claude_runner.write_memo_glossary(run_dir, [{"en": "ARR", "zh": "年度经常性收入"}])
    prompts: list[str] = []
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact",
        lambda **kw: (prompts.append(kw["prompt"]) or ({"unit": {"a": 1}, "memo_package": {}}, None)),
    )
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "0")
    unit_path = run_dir / "u.json"
    unit_path.write_text("{}", encoding="utf-8")
    claude_runner._run_bilingual_unit(
        run_dir=run_dir, company_name="Z", run_id="r", unit_label="u",
        unit_path=unit_path, progress=None, timeout_sec=60,
    )
    claude_runner.run_memo_fast_bilingual_package(
        run_dir=run_dir, company_name="Z", run_id="r", english_package_path=unit_path,
    )
    assert all("1. ARR → 年度经常性收入" in p for p in prompts)
    assert "glossary_zh" in claude_runner._MEMO_BILINGUAL_UNIT_SCHEMA["properties"]


def test_the_chaser_grows_the_glossary_per_unit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner, "_run_bilingual_unit",
        lambda **kw: ({"blocks": [], "claude_cost_usd": 0.0, "claude_duration_ms": 0}, None),
    )
    chaser = claude_runner.BilingualChaser(run_dir=tmp_path, company_name="T", run_id="r")
    chaser.on_section("risks", {"id": "risks", "blocks": [{"type": "paragraph", "text": {"en": "MOIC and MOIC.", "zh": ""}}]})
    chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    assert [t["en"] for t in claude_runner.load_memo_glossary(tmp_path)] == ["MOIC"]


# ---- quote-backed claims ----------------------------------------------------------


def _pass_result(with_quote: bool) -> dict:
    finding = {
        "claim": "Series A post-money was $579.37M",
        "finding": "Filed price.",
        "evidence_class": "public filing",
        "implication": "Anchors the step-up.",
        "confidence": "high",
    }
    if with_quote:
        finding["evidence_quote"] = {
            "url": "https://example.com/filing",
            "quote": "post-money valuation of $579.37 million",
            "source_id": "S5",
        }
    return {
        "summary": "s",
        "key_findings": [finding],
        "supporting_evidence": [],
        "disconfirming_evidence": [],
        "remaining_evidence_limits": [],
        "investment_implications": [],
    }


def test_evidence_quote_is_optional_in_the_pass_schema():
    schema = claude_runner.MEMO_FAST_PASS_SCHEMA
    finding_schema = schema["properties"]["key_findings"]["items"]
    assert "evidence_quote" in finding_schema["properties"]
    assert "evidence_quote" not in finding_schema["required"]
    assert claude_runner._schema_errors(_pass_result(False), schema) == []
    assert claude_runner._schema_errors(_pass_result(True), schema) == []
    too_long = _pass_result(True)
    too_long["key_findings"][0]["evidence_quote"]["quote"] = "x" * 301
    assert claude_runner._schema_errors(too_long, schema)
    # null is accepted (a pass that says "none").
    none = _pass_result(False)
    none["key_findings"][0]["evidence_quote"] = None
    assert claude_runner._schema_errors(none, schema) == []


def test_quotes_are_recorded_once_per_run(tmp_path):
    run_dir = _run_dir(tmp_path)
    assert claude_runner.record_memo_evidence_quotes(run_dir, "p1", _pass_result(False)) == 0
    assert not (run_dir / "logs" / "evidence_quotes.json").exists()
    assert claude_runner.record_memo_evidence_quotes(run_dir, "p1", _pass_result(True)) == 1
    assert claude_runner.record_memo_evidence_quotes(run_dir, "p1", _pass_result(True)) == 0
    assert claude_runner.record_memo_evidence_quotes(run_dir, "p2", _pass_result(True)) == 1
    rows = claude_runner.load_memo_evidence_quotes(run_dir)
    assert rows == [
        {
            "claim": "Series A post-money was $579.37M",
            "url": "https://example.com/filing",
            "quote": "post-money valuation of $579.37 million",
            "pass_id": "p1",
            "source_id": "S5",
        },
        {**rows[0], "pass_id": "p2"},
    ]
    # Malformed quotes are skipped, never raise.
    broken = _pass_result(True)
    broken["key_findings"][0]["evidence_quote"] = {"url": "", "quote": "x"}
    assert claude_runner.record_memo_evidence_quotes(run_dir, "p3", broken) == 0
    assert claude_runner.record_memo_evidence_quotes(None, "p3", broken) == 0


def test_the_pass_records_its_quotes_and_asks_for_them(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    captured: dict = {}
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact",
        lambda **kw: (captured.update(kw) or (_pass_result(True), None)),
    )
    settings = tmp_path / "settings.md"
    settings.write_text("bg", encoding="utf-8")
    companies = tmp_path / "companies.yaml"
    companies.write_text("companies: []", encoding="utf-8")
    result, error = claude_runner.run_memo_fast_analysis_pass(
        run_dir=run_dir, company_name="Z", company_slug="z", run_id="r",
        pass_id="team", pass_label="Team", artifact_filename="team.md", focus="f",
        settings_path=settings, companies_yaml_path=companies, common_context="ctx",
    )
    assert error is None and result["key_findings"]
    assert "Quote your evidence" in captured["prompt"]
    assert captured["schema"] is claude_runner.MEMO_FAST_PASS_SCHEMA
    assert len(claude_runner.load_memo_evidence_quotes(run_dir)) == 1


# ---- the red team ----------------------------------------------------------------


def test_red_team_flag_defaults_on_and_the_conftest_pins_it_off(monkeypatch):
    assert memo_flags.DEFAULTS["BSH_MEMO_RED_TEAM"] is True
    # conftest pins every DEFAULTS entry to "0" for the historical baseline.
    assert claude_runner.memo_red_team_enabled() is False
    monkeypatch.setenv("BSH_MEMO_RED_TEAM", "1")
    assert claude_runner.memo_red_team_enabled() is True


def test_red_team_runs_one_cheap_call_and_normalises_its_answer(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    claude_runner.register_memo_run_quality(run_dir, "best")
    package = _load("zainar_v2_draft.en.json")
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {
            "challenges": [
                {"claim": "1.26x gross MOIC", "section_id": "executive_summary", "why": "No revenue base.", "severity": "high"},
                {"claim": "somewhere", "section_id": "not-a-section", "why": "w", "severity": "extreme"},
                {"claim": "", "section_id": "risks", "why": "dropped", "severity": "low"},
                "junk",
            ],
            "claude_cost_usd": 0.12,
        }, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    out = claude_runner.run_memo_red_team(run_dir, package)
    assert out["error"] is None and out["cost_usd"] == 0.12
    assert out["challenges"] == [
        {"claim": "1.26x gross MOIC", "section_id": "executive_summary", "why": "No revenue base.", "severity": "high"},
        {"claim": "somewhere", "section_id": "executive_summary", "why": "w", "severity": "medium"},
    ]
    assert captured["schema"] is claude_runner.MEMO_RED_TEAM_SCHEMA
    assert captured["role"] == "SPINE_CHECK"
    assert captured["model"] == "sonnet"  # the cheap tier on "best"
    assert captured["tools"] == "" and captured["allowed_tools"] == ""
    prompt = captured["prompt"]
    assert "ZaiNar, Inc." in prompt
    assert "`executive_summary`" in prompt and "`risks`" in prompt
    assert "### section `risks`" in prompt
    assert "- S1:" in prompt
    assert len(prompt) < claude_runner.MEMO_RED_TEAM_MAX_CHARS + 20_000


def test_red_team_failure_is_reported_not_raised(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", lambda **kw: (None, "boom"))
    out = claude_runner.run_memo_red_team(run_dir, _load("zainar_v1_package.json"))
    assert out == {"challenges": [], "cost_usd": 0.0, "error": "boom"}
    assert claude_runner.run_memo_red_team(run_dir, None)["error"] == "no package to challenge"
