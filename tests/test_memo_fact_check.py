"""Tests for the deterministic memo fact check.

The check must be right in both directions: a figure carried by a source
in another spelling is supported (no false alarm), and a figure carried
by nothing on file is reported (no false comfort). Every case here is a
figure a real memo states, against a corpus a real research folder holds.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import claude_runner, memo_fact_check as fc, research_store, source_cache

COMPANY = "generalist-inc"


@pytest.fixture(autouse=True)
def _roots(tmp_path, monkeypatch):
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", tmp_path / "research")
    monkeypatch.delenv("BSH_MEMO_FACT_CHECK_REPAIR", raising=False)
    return tmp_path


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


def _package(paragraphs: dict[str, list[str]], *, sources=None, calculations=None, tables=None) -> dict:
    sections = []
    for section_id, texts in paragraphs.items():
        blocks = [{"type": "heading", "level": 2, "text": _loc("1. Heading with 999 in it")}]
        blocks += [{"type": "paragraph", "text": _loc(text)} for text in texts]
        for table in (tables or {}).get(section_id, []):
            blocks.append(table)
        sections.append({"id": section_id, "title": _loc(section_id.replace("_", " ").title()), "blocks": blocks})
    return {
        "schema_version": 1,
        "company": {"name": "Generalist, Inc."},
        "sections": sections,
        "sources": sources
        or [
            {"id": "S1", "title": _loc("Gartner IT Services Databook"), "class": "third-party market data", "treatment": _loc("Used as is."), "as_of": "2026-01-01", "url": "https://gartner.com/databook"},
        ],
        "calculations": calculations or [],
    }


# ---- extraction -------------------------------------------------------------


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Revenue reached $2.6B, up 24%.", [("$2.6B", 2.6e9, "amount"), ("24%", 24.0, "pct")]),
        ("USD 24 million of ARR and €3.5m of grants", [("USD 24 million", 24e6, "amount"), ("€3.5m", 3.5e6, "amount")]),
        ("a $500M+ book, 95+ patents, 1,200 employees, 12 countries", [("$500M", 5e8, "amount"), ("95+", 95.0, "amount"), ("1,200", 1200.0, "amount"), ("12", 12.0, "amount")]),
        ("entry at 1.5x–2.0x, exit $20–25M, margin 20-25%", [("1.5x", 1.5, "mult"), ("2.0x", 2.0, "mult"), ("$20M", 20e6, "amount"), ("$25M", 25e6, "amount"), ("20%", 20.0, "pct"), ("25%", 25.0, "pct")]),
        ("50 bps of yield; 40 basis points; 3 percentage points", [("50 bps", 0.5, "pct"), ("40 basis points", 0.4, "pct"), ("3 percentage points", 3.0, "pct")]),
        ("~$279B of commitments and c.$108.5B of guarantees", [("$279B", 279e9, "amount"), ("$108.5B", 108.5e9, "amount")]),
        ("13 × $200B = $2.6T", [("$200B", 200e9, "amount"), ("$2.6T", 2.6e12, "amount")]),
        ("over 30 customers and 24 months of runway", [("30", 30.0, "amount"), ("24", 24.0, "amount")]),
        ("30 paying enterprise customers", [("30", 30.0, "amount")]),
    ],
)
def test_extracts_the_figures_a_memo_states(text, expected):
    got = [(f.raw, f.value, f.klass) for f in fc.extract_figures(text)]
    assert got == expected


@pytest.mark.parametrize(
    "text",
    [
        "Q3 2026 and FY24 and FY2026E",
        "the 10-K, the S-1 and an 8-K",
        "top 10 customers; past 12 months; page 12; item 7",
        "2024-2026 and 2024–2026E",
        "24/7 support; Series B; rated 7/10",
        "see [S12] and [C3, S4] for the 2,400 figure",  # the citation digits vanish; 2,400 stays below
        "a 2x2 matrix",
        "https://example.com/2026/500M-deal",
        "ISO 27001 certified; SOC 2",
    ],
)
def test_skips_identifiers_years_and_windows(text):
    figures = [f.raw for f in fc.extract_figures(text)]
    assert figures in ([], ["2,400"]), figures


def test_citation_tokens_never_become_figures():
    figures = fc.extract_figures("ARR of $10M [S12] grew 40% [C3, S4].")
    assert [f.raw for f in figures] == ["$10M", "40%"]


# ---- value matching ---------------------------------------------------------


@pytest.mark.parametrize(
    "memo, source, supported",
    [
        ("$2.6B", "$2,580 million", True),          # rounding, cross spelling
        ("$2.6B", "2.58bn", True),
        ("$2.6B", "$2.7B", False),
        ("$500M", "$500,000,000", True),
        ("$500M", "$450M", False),                    # the fact-lottery pair stays distinct
        ("$500M", "$497M", True),                     # rounds to 500 at two significant digits
        ("$1B", "$1.04B", True),
        ("$1B", "$1.06B", False),
        ("24%", "24 percent", True),
        ("24%", "24.3%", True),
        ("24%", "25%", False),
        ("1.5x", "1.52x", True),
        ("1.5x", "1.6x", False),
        ("30 customers", "customer count: 30", True),
        ("30 customers", "31 customers", False),
        ("95+ patents", "95 patents", True),
        ("1,200 employees", "headcount 1200", True),
        ("50 bps", "0.5%", True),
        ("$24m", "24 million dollars", True),
        ("24 months", "24m", False),                  # a scale is not a noun
    ],
)
def test_source_text_supports_figure(memo, source, supported):
    figure = fc.extract_figures(memo)[0]
    assert fc.TextIndex.of(source).supports(figure) is supported


def test_significant_digit_bounds():
    assert fc._significant("500") == (2, 3)
    assert fc._significant("2.58") == (3, 3)
    assert fc._significant("1") == (2, 2)
    assert fc._significant("0.5") == (2, 2)
    assert fc._significant("1,200") == (2, 4)


# ---- the check --------------------------------------------------------------


def _corpus(*texts: str, evidence: bool = True) -> fc.Corpus:
    corpus = fc.Corpus()
    for index, text in enumerate(texts):
        corpus.add(f"text {index}", text, evidence=evidence)
    return corpus.finish()


def test_calculation_notes_derive_only_their_results():
    package = _package(
        {"executive_summary": ["Market of $2.6T [C1]; implied 1.5x [C1]; base of $200B; 13 partners."]},
        calculations=[{"id": "C1", "formula": "13 × $200B = $2.6T; $2.6T ÷ $1.75T = 1.5x", "result": "1.5x"}],
    )
    result = fc.check_package(package, _corpus("nothing numeric " * 200))
    assert result.derived == 2  # $2.6T and 1.5x follow an "="
    # The input is not laundered by the note, and "13 partners" is a count the memo asserts.
    assert sorted(f.figure for f in result.findings) == ["$200B", "13"]


def test_buckets_supported_derived_verified_unsupported():
    package = _package(
        {
            "executive_summary": [
                "ARR reached $10M [S1], growing 40%.",          # verified (S1 text), supported (corpus)
                "Implied EV/ARR of 12x [C1].",                    # derived
                "Headcount is 1,200 across 14 countries.",        # 1,200 supported; 14 unsupported
            ]
        },
        calculations=[{"id": "C1", "formula": "$120M ÷ $10M = 12x", "result": "12x"}],
    )
    corpus = _corpus("Company ARR: $10.0M as of June; growth 40 percent; 1200 staff.")
    result = fc.check_package(package, corpus, source_texts={"S1": "Gartner: ARR $10M for the vendor."})
    # $10M is an INPUT of C1, not something C1 derives, so it is verified by S1 rather than "derived".
    assert (result.checked, result.verified, result.supported, result.derived, result.unsupported) == (5, 1, 2, 1, 1)
    assert result.coverage_pct == 80
    # "40%" shares its sentence's [S1] citation and S1 does not carry it: a P1 note, not a P0.
    assert [f.code for f in result.findings] == ["citation_mismatch", "unsupported_figure"]
    finding = result.unsupported_findings[0]
    assert finding.code == "unsupported_figure"
    assert finding.figure == "14"
    assert finding.section_id == "executive_summary"
    assert finding.location.startswith("sections[0].blocks[3]")
    assert "14 countries" in finding.snippet
    assert result.status == "warn"  # thin corpus: reported, not enforced
    assert result.thin_corpus is True


def test_citation_mismatch_is_a_note_not_a_repair():
    package = _package({"risks": ["Churn ran at 8% [S1] last year."]})
    corpus = _corpus("Board deck: churn 8% in FY25. " * 100)
    result = fc.check_package(package, corpus, source_texts={"S1": "Gartner says nothing about churn."})
    assert result.unsupported == 0 and result.supported == 1
    assert [f.code for f in result.findings] == ["citation_mismatch"]
    assert result.findings[0].severity == "P1"
    assert result.summary_lines() == []


def test_unverifiable_citation_counts_but_does_not_flag():
    package = _package({"risks": ["Churn ran at 8% [S1] last year."]})
    corpus = _corpus("churn 8%" + " filler" * 400)
    result = fc.check_package(package, corpus, source_texts={})
    assert result.unverifiable_citations == 1
    assert result.findings == []


def test_table_cells_and_bullets_are_checked_headings_are_not():
    table = {
        "type": "table",
        "headers": [_loc("Metric"), _loc("2026")],
        "rows": [[_loc("Gross margin"), _loc("61%")], [_loc("Customers"), _loc("2,400")]],
    }
    package = _package(
        {"financials": ["Bullets follow."]},
        tables={"financials": [table, {"type": "bullets", "items": [_loc("Runway of 18 months.")]}]},
    )
    corpus = _corpus("gross margin 61%; 2,400 customers; runway eighteen months")
    result = fc.check_package(package, corpus)
    assert result.checked == 3
    assert [f.figure for f in result.findings] == ["18"]
    assert "rows[1]" not in result.findings[0].location


def test_repair_policy_auto_off_and_on(monkeypatch):
    package = _package({"risks": ["Churn ran at 9% last year."]})
    rich = _corpus("churn 8% " * 20_000)  # > 50,000 chars, does not carry 9%
    result = fc.check_package(package, rich)
    assert result.repair_feed is False  # auto: 0% traceable, the corpus is short
    assert "traceable" in result.repair_feed_reason
    package2 = _package({"risks": ["Churn ran at 8% last year, ARR $10M, headcount 1,200; 9% net."]})
    rich2 = _corpus("churn 8% ARR $10M headcount 1,200 " * 4_000)
    result2 = fc.check_package(package2, rich2)
    assert result2.repair_feed is True
    assert result2.status == "fail"
    lines = result2.summary_lines()
    assert len(lines) == 1
    assert lines[0].startswith('fact check unsupported_figure in section risks: "')
    assert "9%" in lines[0]
    monkeypatch.setenv("BSH_MEMO_FACT_CHECK_REPAIR", "0")
    assert fc.check_package(package2, rich2).repair_feed is False
    monkeypatch.setenv("BSH_MEMO_FACT_CHECK_REPAIR", "1")
    forced = fc.check_package(package, rich)
    assert forced.repair_feed is True
    thin = fc.check_package(package, _corpus("tiny"))
    assert thin.repair_feed is False and "thin" in thin.repair_feed_reason


def test_summary_lines_route_to_their_section(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_FACT_CHECK_REPAIR", "1")
    package = _package({"executive_summary": ["Fine."], "investment_risk": ["Churn 9% [S1]."]})
    result = fc.check_package(package, _corpus("x" * 5_000))
    line = result.summary_lines()[0]
    assert claude_runner._section_for_validation_error(package, line) == "investment_risk"
    assert claude_runner._is_envelope_repair_finding(package, line) is False


def test_fed_findings_are_capped(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_FACT_CHECK_REPAIR", "1")
    texts = [f"Metric {n} is {n + 11}% now." for n in range(30)]
    package = _package({"risks": texts})
    result = fc.check_package(package, _corpus("nothing numeric here " * 300))
    assert result.unsupported == 30
    assert len(result.summary_lines()) == fc.MAX_FED_FINDINGS


def test_to_dict_and_markdown_report(monkeypatch):
    package = _package({"risks": ["Churn 9%."]})
    result = fc.check_package(package, _corpus("x" * 5_000))
    payload = result.to_dict()
    assert payload["status"] == "warn"
    assert payload["p0_count"] == 1 and payload["finding_count"] == 1
    assert payload["findings"][0]["code"] == "unsupported_figure"
    assert payload["findings"][0]["suggestion"].startswith("the figure 9% appears in none")
    report = fc.render_markdown_report(result, attempt=2)
    assert "# Memo fact check" in report and "Attempt: 2" in report and "9%" in report
    assert fc.render_markdown_report(fc.FactCheckResult()).count("None.") == 1


def test_non_dict_package_is_an_error():
    result = fc.check_package(["nope"], _corpus("x"))
    assert result.error and result.status == "error"


# ---- corpus assembly ------------------------------------------------------------


def test_build_corpus_reads_ledger_docs_cache_and_run_sources(tmp_path, monkeypatch):
    research = research_store.RESEARCH_ROOT / COMPANY
    research.mkdir(parents=True)
    (research / claude_runner.MEMO_FACT_LEDGER_FILENAME).write_text("- 2026-06-13: $500M+ book; 95+ patents.", encoding="utf-8")
    (research / "notes.md").write_text("Analyst notes: 40% margin.", encoding="utf-8")
    (research / "known_sources.md").write_text("- digest line 77%", encoding="utf-8")  # digest of the cache: skipped
    (research / "x.progress.jsonl").write_text("{}", encoding="utf-8")
    source_cache.record_source(COMPANY, kind="web_fetch", text="Reuters: ARR $10M. " * 5, url="https://reuters.com/a")
    run_dir = tmp_path / "memos" / COMPANY / "run"
    source_cache.record_run_source(COMPANY, run_dir, tool="WebFetch", text="Bloomberg: 1,200 staff. " * 5, url="https://bloomberg.com/b", run_id="run")
    # A run source evicted from the company cache is still read from the run copy.
    source_cache.record_source(COMPANY, kind="web_fetch", text="Bloomberg edited: 1,300 staff. " * 5, url="https://bloomberg.com/b")
    monkeypatch.setattr(fc.numbers_lint, "_corpus", lambda cid: (["Transcript: churn 8%."], ["transcript: call"]))
    corpus = fc.build_corpus(COMPANY, run_dir=run_dir, research_dir=research)
    labels = [label for label, _ in corpus.texts]
    assert "research file: fact_ledger.md" in labels
    assert "research file: notes.md" in labels
    assert not any("known_sources" in label for label in labels)
    assert any(label.startswith("cached source") and "reuters" in label for label in labels)
    assert any(label.startswith("run source") and "bloomberg" in label for label in labels)
    assert "firm record: transcript: call" in labels
    for memo in ["$500M", "95+ patents", "40%", "$10M", "1,200 employees", "1,300 employees", "8%"]:
        assert corpus.index.supports(fc.extract_figures(memo)[0]), memo
    assert corpus.evidence_chars > 100
    assert corpus.thin is True


def test_check_memo_run_uses_cited_source_text(tmp_path, monkeypatch):
    monkeypatch.setattr(fc.numbers_lint, "_corpus", lambda cid: ([], []))
    source_cache.record_source(COMPANY, kind="web_fetch", text="Gartner databook: market $45B by 2030. " * 4, url="https://gartner.com/databook")
    package = _package({"market": ["The market reaches $45B by 2030 [S1]; the SAM is $9B."]})
    run_dir = tmp_path / "memos" / COMPANY / "run"
    result = fc.check_memo_run(run_dir=run_dir, package=package, company_id=COMPANY, research_dir=research_store.RESEARCH_ROOT / COMPANY)
    assert result.verified == 1
    assert [f.figure for f in result.findings] == ["$9B"]


def test_check_memo_run_never_raises(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(fc, "build_corpus", boom)
    result = fc.check_memo_run(run_dir=tmp_path, package={"sections": []}, company_id=COMPANY)
    assert result.error == "RuntimeError: disk on fire"
    assert result.to_dict()["status"] == "error"


# ---- URL attachment -------------------------------------------------------------


def test_attach_source_urls_from_artifacts_then_cache(tmp_path):
    run_dir = tmp_path / "memos" / COMPANY / "run"
    fast = run_dir / "analysis" / "fast"
    fast.mkdir(parents=True)
    (fast / "market_sizing.json").write_text(
        json.dumps(
            {
                "supporting_evidence": [
                    {"source": "Gartner IT Services Databook 2026", "source_class": "third-party", "detail": "x", "as_of": "2026", "url": "https://gartner.com/it-services-databook"},
                    {"source": "Private deck", "source_class": "company", "detail": "y", "as_of": "2026", "url": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    source_cache.record_source(COMPANY, kind="web_fetch", text="IDC forecast text " * 10, url="https://idc.com/digital-engineering-forecast", title="IDC Worldwide Digital Engineering Forecast")
    package = _package(
        {"market": ["x"]},
        sources=[
            {"id": "S1", "title": _loc("Gartner IT Services Databook"), "class": "third-party market data", "treatment": _loc("t"), "as_of": "2026-01-01"},
            {"id": "S2", "title": _loc("IDC Digital Engineering Forecast"), "class": "independent secondary", "treatment": _loc("t"), "as_of": "2026-01-01"},
            {"id": "S3", "title": _loc("Founder interview"), "class": "BSH primary diligence", "treatment": _loc("t"), "as_of": "2026-01-01"},
            {"id": "S4", "title": _loc("Already linked"), "class": "press", "treatment": _loc("t"), "as_of": "2026-01-01", "url": "https://keep.me/x"},
        ],
    )
    notes = fc.attach_source_urls(package, company_id=COMPANY, run_dir=run_dir)
    by_id = {s["id"]: s.get("url") for s in package["sources"]}
    assert by_id["S1"] == "https://gartner.com/it-services-databook"
    assert by_id["S2"] == "https://idc.com/digital-engineering-forecast"
    assert by_id["S3"] is None
    assert by_id["S4"] == "https://keep.me/x"
    assert len(notes) == 2 and notes[0].startswith("S1 ← https://gartner.com")
    assert fc.attach_source_urls({"sources": "nope"}, company_id=COMPANY, run_dir=run_dir) == []


def test_attach_source_urls_refuses_weak_matches(tmp_path):
    source_cache.record_source(COMPANY, kind="web_fetch", text="text " * 20, url="https://example.com/annual-report-2026", title="Annual report 2026")
    package = _package({"m": ["x"]}, sources=[{"id": "S1", "title": _loc("Market report"), "class": "third-party", "treatment": _loc("t"), "as_of": "2026"}])
    assert fc.attach_source_urls(package, company_id=COMPANY, run_dir=None) == []
    assert package["sources"][0].get("url") is None


# ---- company-level card ---------------------------------------------------------


def test_check_company_payload_shape(tmp_path, monkeypatch):
    from server import comps

    monkeypatch.setattr(fc.numbers_lint, "_corpus", lambda cid: ([], []))
    package = _package({"exec": ["ARR $10M and 9 customers and 14% churn."]})
    path = tmp_path / "memos" / COMPANY / "run" / "logs" / "memo_package.en.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(package), encoding="utf-8")
    monkeypatch.setattr(comps, "_latest_memo_package", lambda cid, reports=None: (path, package))
    research = research_store.RESEARCH_ROOT / COMPANY
    research.mkdir(parents=True)
    (research / claude_runner.MEMO_FACT_LEDGER_FILENAME).write_text("- ARR $10M", encoding="utf-8")
    payload = fc.check_company(COMPANY)
    assert payload["memo_package"] == str(path)
    assert (payload["checked"], payload["supported"], payload["unsupported"]) == (2, 1, 1)
    assert payload["findings"][0]["number"] == "14%"
    assert payload["findings"][0]["section"] == "Exec"
    assert "looked_for" in payload["findings"][0]
    assert payload["thin_corpus"] is True
    monkeypatch.setattr(comps, "_latest_memo_package", lambda cid, reports=None: (None, None))
    assert fc.check_company(COMPANY)["note"] == "No memo package on record"
