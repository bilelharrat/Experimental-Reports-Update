"""Deterministic envelope facts on the accepted English package.

What the model should never be trusted to write is stamped in Python
before the English DOCX and the Chinese stage: the day the memo was
written (never the raw run id), when each page was retrieved, honest
publication dates, the evidence cutoff, what the fact check found (the
provenance line), and the cover fields as {en, zh} slots so the Chinese
cover is translated instead of printing English.
"""
from __future__ import annotations

import json

import yaml

from server import deal_pipeline, memo_analysis, memo_structure, source_cache, storage

RUN_ID = "2026-09-20__101500"


def _registry(company: dict, *, translation: dict | None = None) -> None:
    storage.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (storage.DATA_DIR / "companies.yaml").write_text(yaml.safe_dump([company]), encoding="utf-8")
    if translation is not None:
        ext_dir = storage.DATA_DIR / "company_ext"
        ext_dir.mkdir(parents=True, exist_ok=True)
        (ext_dir / f"{company['id']}.yaml").write_text(
            yaml.safe_dump({"translation": {"language": "zh", **translation}}, allow_unicode=True),
            encoding="utf-8",
        )


ACME = {
    "id": "acme-ai",
    "name": "Acme AI",
    "status": "private",
    "hq": "San Francisco, CA",
    "sector": "Information Technology",
}


# ---- cover facts ---------------------------------------------------------------------------


def test_cover_fields_become_slots_with_the_registry_chinese_prefilled():
    _registry(ACME, translation={"sector": "信息技术", "hq": "加利福尼亚州旧金山"})
    package = {
        "run": {"run_id": RUN_ID, "as_of": RUN_ID},
        "company": {
            "name": "Acme AI",
            "descriptor": "Vision models for warehouses",
            "sector": "Information Technology",
            "hq": "San Francisco, CA",
        },
    }
    memo_analysis._stamp_cover_facts(
        package,
        company_id="acme-ai",
        run_date="2026-09-20",
        structure=memo_structure.active_structure("late", version="v2"),
    )
    company = package["company"]
    assert package["run"]["as_of"] == "2026-09-20"  # never the raw run id
    assert company["name"] == "Acme AI"  # a proper name stays as written
    assert company["descriptor"] == {"en": "Vision models for warehouses", "zh": ""}
    assert company["sector"] == {"en": "Information Technology", "zh": "信息技术"}
    assert "hq" not in company
    assert company["location"] == {"en": "San Francisco, CA", "zh": "加利福尼亚州旧金山"}
    assert company["stage"] == {"en": "Late stage", "zh": "后期"}
    # No round anywhere on file: the key stays absent (the renderer leaves
    # the row out) — never "No round on offer" by guess.
    assert "round" not in company


def test_the_registry_chinese_is_used_only_for_the_registry_english():
    _registry(ACME, translation={"sector": "信息技术", "hq": "加利福尼亚州旧金山"})
    package = {"company": {"name": "Acme AI", "sector": "Industrial AI software", "location": {"en": "SF", "zh": ""}}}
    memo_analysis._stamp_cover_facts(package, company_id="acme-ai", run_date=None, structure=None)
    assert package["company"]["sector"] == {"en": "Industrial AI software", "zh": ""}
    assert package["company"]["location"] == {"en": "SF", "zh": ""}
    assert "stage" not in package["company"]
    assert "as_of" not in package["run"]


def test_the_round_on_offer_comes_from_the_deal_pipeline_and_a_stated_round_is_kept():
    _registry(ACME)
    deal_pipeline.update_deal_pipeline("acme-ai", {"round": "Series C"})
    package = {"company": {"name": "Acme AI", "stage": "Growth-stage"}}
    memo_analysis._stamp_cover_facts(package, company_id="acme-ai", run_date=None, structure=None)
    assert package["company"]["round"] == {"en": "Series C", "zh": ""}
    assert package["company"]["stage"] == {"en": "Growth-stage", "zh": ""}  # the model's stage is kept

    stated = {"company": {"name": "Acme AI", "round": ""}}
    memo_analysis._stamp_cover_facts(stated, company_id="acme-ai", run_date=None, structure=None)
    assert stated["company"]["round"] == ""  # "no round on offer", as the package said

    _registry({**ACME, "status": "public", "ticker": "ACME"})
    public = {"company": {"name": "Acme AI"}}
    memo_analysis._stamp_cover_facts(public, company_id="acme-ai", run_date=None, structure=None)
    assert "round" not in public["company"]


# ---- source dates --------------------------------------------------------------------------


def _manifest(run_dir, rows):
    sources = run_dir / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    (sources / "manifest.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


def _pass_record(run_dir, pass_id, evidence):
    fast = run_dir / "analysis" / "fast"
    fast.mkdir(parents=True, exist_ok=True)
    (fast / f"{pass_id}.json").write_text(
        json.dumps({"pass_id": pass_id, "status": "ok", "data": {"supporting_evidence": evidence}}),
        encoding="utf-8",
    )


def test_source_dates_are_honest_and_retrieval_comes_from_the_run(tmp_path):
    _registry(ACME)
    run_dir = tmp_path / "run"
    _manifest(run_dir, [{"at": "2026-09-19T08:00:00+00:00", "url": "https://press.example.com/acme-raise?utm_source=x"}])
    source_cache.record_source(
        "acme-ai",
        kind="web_fetch",
        text="Acme AI's customer count reached 400 in August, the company said in a statement.",
        url="https://news.example.org/story",
        fetched_at="2026-09-18T10:00:00+00:00",
    )
    _pass_record(
        run_dir,
        "growth_bridge",
        [{"source": "Press", "source_class": "business press", "detail": "d", "as_of": "2026-09", "url": "https://press.example.com/acme-raise"}],
    )
    session = tmp_path / "session"
    session.mkdir()
    (session / "strategic_risks.yaml").write_text(
        yaml.safe_dump(
            {
                "risks": [
                    {
                        "title": "t",
                        "supporting_evidence": [
                            {"locator": "https://news.example.org/story", "confidence": "Medium", "source_class": "news"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    package = {
        "run": {"run_id": RUN_ID, "evidence_cutoff": "2026-09-20"},
        "sources": [
            # Dated the day the run read it: undated, with its retrieval.
            {"id": "S1", "title": "Acme raises", "class": "Press", "url": "https://press.example.com/acme-raise", "as_of": "2026-09-20"},
            # A dated URL path wins over the run date.
            {"id": "S2", "title": "Story", "class": "News", "url": "https://news.example.org/2026/08/14/story", "as_of": "2026-09-20"},
            # Retrieved per the company's source cache.
            {"id": "S3", "title": "Story", "class": "News", "url": "https://news.example.org/story", "as_of": "2026-08"},
            # The firm's own material keeps its date.
            {"id": "S4", "title": "BSH reference call (customer, 2026-09)", "class": "BSH reference call", "as_of": "2026-09-20"},
            "not a source",
        ],
    }
    memo_analysis._stamp_source_dates(
        package, run_dir, company_id="acme-ai", run_date="2026-09-20", session_dir=session
    )
    s1, s2, s3, s4, junk = package["sources"]
    assert s1["published_at"] == "undated" and s1["as_of"] == "2026-09-20"
    assert s1["retrieved_at"] == "2026-09-19"
    assert s1["evidence_source_class"] == "business press"
    assert s2["published_at"] == "2026-08-14" and "retrieved_at" not in s2
    assert s3["published_at"] == "2026-08" and s3["retrieved_at"] == "2026-09-18"
    assert s3["evidence_confidence"] == "medium" and s3["evidence_source_class"] == "news"
    assert s4["published_at"] == "2026-09-20"
    assert junk == "not a source"
    # The model's cutoff was the run date: derived from the dated,
    # non-internal sources instead.
    assert package["run"]["evidence_cutoff"] == "2026-08-14"


def test_a_stated_evidence_cutoff_is_kept(tmp_path):
    package = {
        "run": {"evidence_cutoff": "2026-06-30"},
        "sources": [{"id": "S1", "title": "t", "class": "News", "url": "https://a.example.com/2026/08/01/x", "as_of": "2026-08-01"}],
    }
    memo_analysis._stamp_source_dates(package, tmp_path, company_id=None, run_date="2026-09-20")
    assert package["run"]["evidence_cutoff"] == "2026-06-30"


# ---- what the checks found -----------------------------------------------------------------


def _fact_check(run_dir, payload):
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps(payload), encoding="utf-8")


def test_the_fact_check_line_counts_every_checked_figure(tmp_path):
    _fact_check(
        tmp_path,
        {
            "checked": 20,
            "status": "fail",
            "p0_count": 2,
            "unsupported": 2,
            "tiers": {
                "basis": "tiered",
                "verified": 9,
                "found_elsewhere": 3,
                "derived": 2,
                "company_reported": 2,
                "registry_only": 1,
                "not_traced": 3,
            },
        },
    )
    package: dict = {"run": {"checks": {"gates": {"quality": "passed"}}}}
    memo_analysis._stamp_fact_check_checks(package, tmp_path)
    checks = package["run"]["checks"]
    assert checks["fact_check"] == {
        "verified": 9,
        "found_elsewhere": 5,
        "derived": 2,
        "not_traced": 4,
        "thin_corpus": False,
    }
    assert sum(v for k, v in checks["fact_check"].items() if k != "thin_corpus") == 20
    # Unsupported figures ship as findings on the report: "warnings".
    assert checks["gates"] == {"quality": "passed", "fact_check": "warnings"}


def test_no_fact_check_line_without_a_check(tmp_path):
    package: dict = {"run": {}}
    memo_analysis._stamp_fact_check_checks(package, tmp_path)
    assert "checks" not in package["run"]
    _fact_check(tmp_path, {"checked": 0, "status": "pass"})
    memo_analysis._stamp_fact_check_checks(package, tmp_path)
    assert "checks" not in package["run"]


def test_the_prerender_pass_stamps_the_gates(tmp_path):
    path = tmp_path / "memo_package.json"
    path.write_text(json.dumps({"run": {"checks": {"gates": {"fact_check": "passed"}}}}), encoding="utf-8")
    memo_analysis._stamp_prerender_gates(path, ['Chinese parity gate empty_zh at s1: "x" — fix'])
    gates = json.loads(path.read_text(encoding="utf-8"))["run"]["checks"]["gates"]
    assert gates == {"fact_check": "passed", "quality": "passed", "chinese_parity": "warnings"}
    memo_analysis._stamp_prerender_gates(path, ["pre-render quality check failed: OSError: x"])
    assert json.loads(path.read_text(encoding="utf-8"))["run"]["checks"]["gates"] == gates


# ---- the whole stamp -----------------------------------------------------------------------


def test_the_envelope_stamp_localizes_calculation_input_names_and_never_raises(tmp_path, monkeypatch):
    package = {
        "calculations": [
            {"id": "C1", "inputs": [{"name": "post-money", "value": "$2.4B"}, {"name": {"en": "ARR", "zh": "年度经常性收入"}}, "x"]},
            "junk",
        ],
        "company": {"name": "Acme AI"},
    }

    def boom(*_args, **_kwargs):
        raise RuntimeError("source cache down")

    monkeypatch.setattr(memo_analysis, "_stamp_source_dates", boom)
    memo_analysis._stamp_envelope_facts(package, tmp_path / RUN_ID, company_id=None, run_id=RUN_ID)
    inputs = package["calculations"][0]["inputs"]
    assert inputs[0]["name"] == {"en": "post-money", "zh": ""}
    assert inputs[1]["name"] == {"en": "ARR", "zh": "年度经常性收入"}
    assert package["run"]["as_of"] == "2026-09-20"


# ---- the final fact check and its warnings (2026-09-23 round 3) -------------------------


def test_the_final_fact_check_relabels_inputs_and_reports_the_delivered_text(tmp_path, monkeypatch):
    """The gate's check ran on the candidate before its repairs; the record
    and the provenance line now come from the package as delivered, and an
    input no source carries is shown as our assumption and warned about."""
    from server import memo_fact_check

    run_dir = tmp_path / RUN_ID
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps({"status": "fail", "unsupported": 184}))
    package = {
        "calculations": [
            {"id": "C1", "inputs": [{"name": {"en": "Estimated ARR", "zh": ""}, "value": {"en": "$30M", "zh": ""}, "ref": "S2"}]}
        ],
        "sections": [],
    }
    seen = {}

    def fake_final_check(*, run_dir, package, company_id, research_dir=None, session_dir=None):
        seen["company"] = company_id
        entry = {"calc_id": "C1", "input_index": 0, "name": "Estimated ARR", "value": "$30M", "ref": "S2"}
        memo_fact_check.relabel_unsourced_calculation_inputs(package, [entry])
        result = memo_fact_check.FactCheckResult(checked=10, verified=6, unsupported=2)
        result.findings = [
            memo_fact_check.FactFinding(
                code="unsupported_figure", section_id="executive_summary", location="sections[0].blocks[1].text",
                figure="$1.5M", snippet="monthly burn of $1.5M", detail="not on file", headline=True,
            ),
            memo_fact_check.FactFinding(
                code="unsupported_figure", section_id="risks", location="sections[5].blocks[2].text",
                figure="12%", snippet="12% churn", detail="not on file",
            ),
        ]
        result.evidence_chars = 90_000
        return result, [entry]

    monkeypatch.setattr(memo_fact_check, "final_check", fake_final_check)
    memo_analysis._final_fact_check(package, run_dir, company_id="zainar-inc")
    assert seen["company"] == "zainar-inc"
    assert package["calculations"][0]["inputs"][0]["ref"] == "assumption"
    payload = json.loads((run_dir / "logs" / "fact_check.json").read_text())
    assert payload["unsupported"] == 2 and payload["unsupported_headline"] == 1
    assert [f["figure"] for f in payload["headline_findings"]] == ["$1.5M"]

    warnings = memo_analysis._RunWarnings()
    memo_analysis._fact_check_warning(run_dir, warnings)
    assert warnings.en == [
        "Calculations: 1 input cited to a source that does not carry the figure — shown as our assumption",
        "Fact check: 1 figure in the executive summary, key metrics or recommendation not found in any source on file",
    ]
    assert {item["code"] for item in warnings.items} == {"calculation_input_unsourced", "headline_figure_untraced"}
    assert all(item["gate"] == "fact_check" for item in warnings.items)

    # A second stamp (a resume) finds nothing left to relabel; the first
    # stamp's entry stands because the input still reads as an assumption.
    monkeypatch.setattr(
        memo_fact_check,
        "final_check",
        lambda **_kw: (memo_fact_check.FactCheckResult(checked=10, verified=10), []),
    )
    memo_analysis._final_fact_check(package, run_dir, company_id="zainar-inc")
    kept = json.loads((run_dir / "logs" / memo_fact_check.CALCULATION_INPUTS_FILENAME).read_text())
    assert [r["calc_id"] for r in kept["relabelled"]] == ["C1"]


def test_no_company_or_a_failed_check_leaves_the_last_report(tmp_path, monkeypatch):
    from server import memo_fact_check

    run_dir = tmp_path / RUN_ID
    (run_dir / "logs").mkdir(parents=True)
    before = {"status": "fail", "unsupported": 3}
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps(before))
    memo_analysis._final_fact_check({"sections": []}, run_dir, company_id=None)
    failed = memo_fact_check.FactCheckResult()
    failed.error = "RuntimeError: cache down"
    monkeypatch.setattr(memo_fact_check, "final_check", lambda **_kw: (failed, []))
    memo_analysis._final_fact_check({"sections": []}, run_dir, company_id="zainar-inc")
    assert json.loads((run_dir / "logs" / "fact_check.json").read_text()) == before
    warnings = memo_analysis._RunWarnings()
    memo_analysis._fact_check_warning(run_dir, warnings)
    assert not warnings


def test_the_ic_memo_reports_a_comparison_its_figures_contradict(tmp_path):
    md = tmp_path / "ic.md"
    md.write_text(
        "# Walk-away price\nAt a softer bar the same arithmetic gives about $597M — still below the "
        "August 2021 Series A post-money of $579.37M only by a whisker.\nThe price is $236M, well below $1.0B.\n",
        encoding="utf-8",
    )
    warnings = memo_analysis._RunWarnings()
    memo_analysis._ic_comparison_warning(md, warnings)
    assert warnings.en == ["Arithmetic: 1 comparison in the IC decision memo contradicted by its own figures"]
    assert warnings.items[0]["code"] == "comparison_error"
    assert warnings.items[0]["summary_en"].startswith("$597M is above $579.37M, not below it")
    empty = memo_analysis._RunWarnings()
    memo_analysis._ic_comparison_warning(None, empty)
    memo_analysis._ic_comparison_warning(tmp_path / "missing.md", empty)
    assert not empty
