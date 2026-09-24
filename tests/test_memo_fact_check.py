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


def _write_fast_pass(fast_dir: Path, pass_id: str, data: dict | None, *, status: str = "ok") -> None:
    """The file ``memo_analysis._write_fast_pass_outputs`` writes: the pass
    output sits under ``data`` (null for a failed pass)."""
    fast_dir.mkdir(parents=True, exist_ok=True)
    (fast_dir / f"{pass_id}.json").write_text(
        json.dumps(
            {
                "pass_id": pass_id,
                "label": pass_id.replace("_", " ").title(),
                "artifact_filename": f"{pass_id}.md",
                "status": status,
                "error": None if data is not None else "timed out",
                "duration_ms": 1,
                "cost_usd": 0.0,
                "usage": {},
                "data": data,
            }
        ),
        encoding="utf-8",
    )


def test_attach_source_urls_from_artifacts_then_cache(tmp_path):
    run_dir = tmp_path / "memos" / COMPANY / "run"
    fast = run_dir / "analysis" / "fast"
    _write_fast_pass(
        fast,
        "market_sizing",
        {
            "summary": "s",
            "supporting_evidence": [
                {"source": "Gartner IT Services Databook 2026", "source_class": "third-party", "detail": "x", "as_of": "2026", "url": "https://gartner.com/it-services-databook"},
                {"source": "Private deck", "source_class": "company", "detail": "y", "as_of": "2026", "url": None},
            ],
        },
    )
    _write_fast_pass(fast, "competition", None, status="failed")  # a failed pass is skipped, not fatal
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
    # Report-only additions: the honest split and the reader-facing summary.
    assert payload["tiers"]["basis"] == "tiered"
    assert payload["summary"]["status"] == "not_checkable" and payload["summary"]["coverage_pct"] is None
    monkeypatch.setattr(comps, "_latest_memo_package", lambda cid, reports=None: (None, None))
    assert fc.check_company(COMPANY)["note"] == "No memo package on record"


# ---- strict matching behind the honest tiers (report only) ------------------------


@pytest.mark.parametrize(
    "source",
    [
        "The round closed on 30 June 2026.",
        "Filed June 30, 2026 with the regulator.",
        "Filed Jun. 30 with the regulator.",
        "see p. 30 of the deck",
        "page 30 of the deck",
        "ranked No. 30 on the list",
        "under § 30 of the act",
        "as reported earlier [30] and since",
        "a footnote^30 here",
        "dated 2026-06-30 in the filing",
        "signed on 06/30/2026 by both parties",
    ],
)
def test_strict_index_ignores_dates_pages_sections_and_footnotes(source):
    figure = fc.extract_figures("over 30 customers")[0]
    # The enforced (loose) match is unchanged: the repair still accepts it.
    assert fc.TextIndex.of(source).supports(figure) is True
    assert fc.TextIndex.of(source, strict=True).supports(figure) is False
    assert 30.0 in fc.corpus_values(source)["amount"]
    assert 30.0 not in fc.corpus_values(source, strict=True)["amount"]


@pytest.mark.parametrize(
    "source",
    ["customer count: 30", "30 customers signed", "we now serve 30 enterprises", "In June, 30 customers renewed."],
)
def test_strict_index_keeps_real_counts(source):
    figure = fc.extract_figures("over 30 customers")[0]
    assert fc.TextIndex.of(source, strict=True).supports(figure) is True


def test_loose_index_is_unchanged_by_the_strict_scan():
    """``TextIndex.of`` / ``corpus_values`` default to exactly the index the
    repair has always enforced against."""
    text = "Revenue $2,580 million in FY25; 30 June; 1,200 staff; margin 61%; 2026-06-30; [12] 7x."
    index = fc.TextIndex.of(text)
    assert {"30", "12", "2026", "06"} <= index.forms
    assert 30.0 in index.values["amount"] and 12.0 in index.values["amount"]
    assert 2026.0 not in index.values["amount"]  # years never counted
    assert fc.corpus_values(text) == index.values


def _tiered_corpus(*, filler: int = 2_500) -> fc.Corpus:
    corpus = fc.Corpus()
    corpus.company_hosts = {"acme.com"}
    corpus.company_tokens = {"acme"}
    corpus.add(
        "research file: analyst_notes.md",
        "Independent analyst note: revenue reached $12M last year. The round closed on 30 June 2026. "
        + "Background prose without figures. " * (filler // 34),
    )
    corpus.add(
        "cached source a1: https://www.acme.com/news/launch",
        "Acme says it serves 450 customers across hospitals.",
        tier="company",
    )
    corpus.add("registry entry", "id: acme\ntam: ~$45B\npipeline: $77M\n", evidence=False)
    corpus.add_tier_text("registry", "registry field: metrics[0]", "TAM ; ~$45B ; USD ; 2030")
    return corpus.finish()


def _tier_package() -> dict:
    return _package(
        {
            "executive_summary": [
                "Churn was 8% [S1].",
                "Acme serves 450 customers.",
            ],
            "market": [
                "Revenue reached $12M.",
                "The market is a $45B opportunity.",
                "A pipeline of $77M.",
                "Implied 3.0x [C1].",
                "Over 30 customers renewed.",
                "Headcount is 999 employees.",
            ],
        },
        sources=[
            {"id": "S1", "title": _loc("Industry churn survey"), "class": "independent secondary", "treatment": _loc("t"), "as_of": "2026", "url": "https://survey.example.org/churn"},
            {"id": "S2", "title": _loc("Acme newsroom"), "class": "company-reported", "treatment": _loc("t"), "as_of": "2026", "url": "https://acme.com/news/launch"},
        ],
        calculations=[{"id": "C1", "formula": "$36M ÷ $12M = 3.0x", "result": "3.0x"}],
    )


def test_honest_tiers_split_what_the_loose_match_calls_supported():
    corpus = _tiered_corpus()
    package = _tier_package()
    result = fc.check_package(package, corpus, source_texts={"S1": "Survey: median churn 8% across vendors."})

    # The enforced buckets are exactly what the loose check always gave.
    assert (result.checked, result.verified, result.supported, result.derived, result.unsupported) == (8, 1, 5, 1, 1)
    tiers = result.tiers
    assert tiers["basis"] == "tiered"
    assert tiers["verified"] == 1  # 8%: the cited independent survey carries it
    assert tiers["derived"] == 1  # 3.0x
    assert tiers["found_elsewhere"] == 1  # $12M in the analyst note
    assert tiers["in_context"] == 1  # "revenue" sits next to $12M there
    assert tiers["company_reported"] == 1  # 450 customers: only acme.com says so
    assert tiers["company_reported_headline"] == 1
    assert tiers["registry_only"] == 1  # $45B: only a registry field with source_refs
    # $77M rests on the registry dump alone, 30 on "30 June", 999 on nothing.
    assert tiers["not_traced"] == 3
    assert sum(tiers[k] for k in ("verified", "found_elsewhere", "derived", "company_reported", "registry_only", "not_traced")) == result.checked
    rows = {row["figure"]: row for row in result.figure_tiers}
    assert rows["450"]["tier"] == "company_reported" and rows["450"]["headline"] is True
    assert rows["$45B"]["tier"] == "registry_only"
    assert rows["$77M"]["tier"] == "not_traced" and rows["$77M"]["unsupported"] is False
    assert rows["30"]["tier"] == "not_traced"
    assert rows["999"]["unsupported"] is True
    payload = result.to_dict()
    assert payload["tiers"] == tiers and payload["figure_tiers"]
    # Enforcement never reads the tiers.
    assert payload["p0_count"] == 1 and payload["unsupported"] == 1
    report = fc.render_markdown_report(result)
    assert "What the figures rest on (report only, not enforced)" in report
    assert "headline figure 450" in report


def test_a_cited_company_page_is_company_reported_not_verified():
    corpus = _tiered_corpus()
    package = _package(
        {"executive_summary": ["Acme serves 450 customers [S2]."]},
        sources=_tier_package()["sources"],
    )
    result = fc.check_package(
        package,
        corpus,
        source_texts={"S2": "Acme says it serves 450 customers across hospitals."},
    )
    assert result.verified == 1  # the enforced bucket: the cited source carries it
    assert result.tiers["verified"] == 0
    assert result.tiers["company_reported"] == 1


def test_build_corpus_tags_company_pages_and_reads_only_sourced_registry_fields(tmp_path, monkeypatch):
    from server import storage

    monkeypatch.setattr(fc.numbers_lint, "_corpus", lambda cid: ([], []))
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [
            {
                "id": COMPANY,
                "name": "Generalist, Inc.",
                "website": "https://www.generalist.ai",
                "description": "Generalist builds robots; 70 pilots.",
                "metrics": [
                    {"label": "ARR", "value": "~$24M", "source_refs": [{"label": "Board deck", "source_class": "company"}]},
                    {"label": "Pipeline", "value": "$88M"},
                ],
            }
        ],
    )
    source_cache.record_source(COMPANY, kind="web_fetch", text="Generalist announces 40 customers. " * 3, url="https://news.generalist.ai/launch")
    source_cache.record_source(COMPANY, kind="web_fetch", text="Reuters: Generalist has 40 customers. " * 3, url="https://reuters.com/g")

    corpus = fc.build_corpus(COMPANY, research_dir=tmp_path / "none")

    tiers = {row["label"]: row["tier"] for row in corpus.describe()}
    assert tiers["registry entry"] == "context"
    assert any(label.endswith("news.generalist.ai/launch") and tier == "company" for label, tier in tiers.items())
    assert any("reuters.com" in label and tier == "independent" for label, tier in tiers.items())
    assert corpus.company_hosts == {"generalist.ai"}
    registry = corpus.tier_index["registry"]
    assert registry.supports(fc.extract_figures("$24M")[0])
    assert not registry.supports(fc.extract_figures("$88M")[0])  # no source_refs on that field
    assert corpus.index.supports(fc.extract_figures("$88M")[0])  # the loose corpus still reads the dump


def test_firm_record_rows_pair_the_company_record_explicitly():
    rows = fc._firm_record_rows(
        ["description text", "Series B", "file summary text", "matrix row"],
        ["company record", "file summary: deck.pdf", "evidence matrix"],
    )
    assert rows[:2] == [("company record", "description text"), ("company record", "Series B")]
    assert rows[2] == ("file summary: deck.pdf", "file summary text")
    assert fc._firm_record_rows(["a"], ["transcript: call"]) == [("transcript: call", "a")]


# ---- the reader-facing summary ------------------------------------------------------


def test_summarize_fact_check_tiered_and_thin():
    corpus = _tiered_corpus()
    result = fc.check_package(_tier_package(), corpus, source_texts={"S1": "Survey: median churn 8% across vendors."})
    summary = fc.summarize_fact_check(result.to_dict())
    assert summary["basis"] == "tiered"
    assert summary["status"] == "warn"  # unsupported but not enforced (auto, small corpus)
    assert (summary["checked"], summary["verified"], summary["found_elsewhere"], summary["derived"]) == (8, 1, 1, 1)
    assert (summary["company_reported"], summary["registry_only"], summary["not_traced"]) == (1, 1, 3)
    assert summary["in_context"] == 1 and summary["company_reported_headline"] == 1
    assert summary["unsupported"] == 1 and summary["p0_count"] == 1
    assert summary["coverage_pct"] == 50  # (1 + 1 + 1 + 1) of 8
    thin = fc.check_package(_tier_package(), _tiered_corpus(filler=0))
    thin_summary = fc.summarize_fact_check(thin.to_dict())
    assert thin_summary["thin_corpus"] is True
    assert thin_summary["status"] == "not_checkable"
    assert thin_summary["coverage_pct"] is None and thin_summary["p0_count"] == 0


def test_summarize_fact_check_legacy_missing_and_error():
    assert fc.summarize_fact_check(None)["status"] == "not_run"
    assert fc.summarize_fact_check({})["coverage_pct"] is None
    legacy = {
        "status": "warn", "checked": 10, "verified": 2, "supported": 5, "derived": 1,
        "unsupported": 2, "coverage_pct": 80, "thin_corpus": False, "p0_count": 2,
    }
    summary = fc.summarize_fact_check(legacy)
    assert summary["basis"] == "legacy"
    assert (summary["found_elsewhere"], summary["not_traced"], summary["coverage_pct"]) == (5, 2, 80)
    assert summary["company_reported"] is None and summary["registry_only"] is None
    assert fc.summarize_fact_check({**legacy, "thin_corpus": True})["coverage_pct"] is None
    errored = fc.summarize_fact_check(fc.FactCheckResult(error="RuntimeError: x").to_dict())
    assert errored["status"] == "error" and errored["coverage_pct"] is None
    assert fc.summarize_fact_check({"status": "skipped", "checked": 0})["status"] == "no_figures"


# ---- source URLs: Serena locators and the seen/unseen audit ------------------------


def _serena_session(tmp_path: Path) -> Path:
    import yaml

    session_dir = tmp_path / "serena_session"
    session_dir.mkdir(parents=True)
    artifacts = {
        "strategic_risks": {
            "risks": [
                {
                    "id": "risk-1",
                    "supporting_evidence": [
                        {
                            "file_id": None,
                            "filename": None,
                            "locator": "https://www.cnbc.com/2026/08/17/acme-says-annualized-revenue-climbed-to-65-billion.html",
                            "excerpt": "Acme told investors its annualized revenue run rate climbed to $65 billion.",
                            "source_class": "news",
                        }
                    ],
                    "contradicting_evidence": [
                        {"locator": "p.4", "excerpt": "Private file evidence.", "source_class": "research_file"},
                    ],
                }
            ]
        },
        "infographic_source_brief": {
            "claims": [
                {
                    "claim": "c",
                    "source_traces": [
                        {"title": "Mergermarket record IPO valuation target", "url": "https://ionanalytics.com/insights/mergermarket/record-ipo", "excerpt": "Skeptics contend the valuation prices in 2028 revenue."},
                    ],
                }
            ]
        },
        "series_news": {
            "source_traces": [
                {"title": "", "url": "https://acme.com/news/series-h", "excerpt": "Series H."},
                {"title": "", "url": "https://acme.com/news/series-g", "excerpt": "Series G."},
            ]
        },
    }
    (session_dir / "session.yaml").write_text(yaml.safe_dump({"id": "s1", "artifacts": artifacts}), encoding="utf-8")
    return session_dir


def test_serena_candidates_come_from_traces_and_risk_locators(tmp_path):
    rows = fc._serena_url_candidates(_serena_session(tmp_path))
    urls = {row["url"]: row for row in rows}
    assert "https://www.cnbc.com/2026/08/17/acme-says-annualized-revenue-climbed-to-65-billion.html" in urls
    assert urls["https://ionanalytics.com/insights/mergermarket/record-ipo"]["name"] == "Mergermarket record IPO valuation target"
    assert urls["https://ionanalytics.com/insights/mergermarket/record-ipo"]["excerpt"].startswith("Skeptics")
    assert all(row["url"].startswith("https://") for row in rows)  # "p.4" is a page, not a URL
    assert fc._serena_url_candidates(None) == []
    assert fc._serena_url_candidates(tmp_path / "missing") == []


def test_attach_source_urls_from_serena_locators_refuses_ties_and_reports(tmp_path):
    session_dir = _serena_session(tmp_path)
    run_dir = tmp_path / "memos" / COMPANY / "run"
    (run_dir / "logs").mkdir(parents=True)
    package = _package(
        {"m": ["x"]},
        sources=[
            {"id": "S1", "title": _loc("CNBC: Acme annualized revenue climbed to $65 billion"), "class": "press reporting", "treatment": _loc("t"), "as_of": "2026"},
            {"id": "S2", "title": _loc("Mergermarket: record IPO valuation target"), "class": "press reporting", "treatment": _loc("t"), "as_of": "2026"},
            {"id": "S3", "title": _loc("Acme news series"), "class": "company disclosure", "treatment": _loc("t"), "as_of": "2026"},
            {"id": "S4", "title": _loc("Unrelated market sizing study"), "class": "third-party", "treatment": _loc("t"), "as_of": "2026"},
        ],
    )
    notes = fc.attach_source_urls(package, company_id=COMPANY, run_dir=run_dir, session_dir=session_dir, attempt=2)
    by_id = {s["id"]: s.get("url") for s in package["sources"]}
    assert by_id["S1"].startswith("https://www.cnbc.com/2026/08/17/acme-says")
    assert by_id["S2"] == "https://ionanalytics.com/insights/mergermarket/record-ipo"
    assert by_id["S3"] is None  # series-h and series-g tie: a wrong link is worse than none
    assert by_id["S4"] is None
    assert [note.split(" ", 1)[0] for note in notes] == ["S1", "S2"]
    assert "matched Serena session locator" in notes[0]
    log = (run_dir / "logs" / "source_urls.md").read_text(encoding="utf-8")
    assert log.startswith("## URL check — attempt 2")
    # Both attached URLs were recorded by the session: nothing is unseen.
    assert package["run"]["source_url_status"]["unseen"] == {}
    assert "not attached S3" in log and "series-h" in log and "series-g" in log
    assert "excerpt: \"Acme told investors" in log


def test_attach_source_urls_finds_the_session_through_the_run_manifest(tmp_path, monkeypatch):
    from server import serena_analysis

    session_dir = _serena_session(tmp_path)
    monkeypatch.setattr(serena_analysis, "session_dir", lambda company_id, session_id: session_dir if session_id == "s1" else tmp_path / "nope")
    run_dir = tmp_path / "memos" / COMPANY / "run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "run_manifest.md").write_text(
        "# Investment Memo Run Manifest\n\n- run_id: run\n- analysis_session_id: s1\n", encoding="utf-8"
    )
    package = _package(
        {"m": ["x"]},
        sources=[{"id": "S1", "title": _loc("Mergermarket record IPO valuation target"), "class": "press", "treatment": _loc("t"), "as_of": "2026"}],
    )
    notes = fc.attach_source_urls(package, company_id=COMPANY, run_dir=run_dir, write_report=False)
    assert package["sources"][0]["url"] == "https://ionanalytics.com/insights/mergermarket/record-ipo"
    assert len(notes) == 1
    assert not (run_dir / "logs" / "source_urls.md").exists()


def test_audit_marks_urls_seen_or_unseen_and_flags_reused_homepages(tmp_path):
    session_dir = _serena_session(tmp_path)
    run_dir = tmp_path / "memos" / COMPANY / "run"
    source_cache.record_source(COMPANY, kind="web_fetch", text="Cached page text " * 5, url="https://www.cached.com/a")
    source_cache.record_source(
        COMPANY,
        kind="web_search",
        text="search results blob " * 5,
        query="acme",
        links=[{"title": "Listed only", "url": "https://listed.example.com/only"}],
    )
    source_cache.record_run_source(COMPANY, run_dir, tool="WebFetch", text="Run fetch text " * 5, url="https://run.example.com/b", run_id="run")
    _write_fast_pass(
        run_dir / "analysis" / "fast",
        "market",
        {"supporting_evidence": [{"source": "Artifact page", "source_class": "x", "detail": "d", "as_of": None, "url": "https://artifact.example.com/c"}]},
    )
    package = _package(
        {"m": ["x"]},
        sources=[
            {"id": "S1", "title": _loc("a"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "http://cached.com/a"},
            {"id": "S2", "title": _loc("b"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://run.example.com/b/"},
            {"id": "S3", "title": _loc("c"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://artifact.example.com/c"},
            {"id": "S4", "title": _loc("d"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://ionanalytics.com/insights/mergermarket/record-ipo"},
            {"id": "S5", "title": _loc("e"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://made-up.example.com/deep/link"},
            {"id": "S6", "title": _loc("f"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://zainartech.com"},
            {"id": "S7", "title": _loc("g"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://www.zainartech.com/"},
            {"id": "S8", "title": _loc("h"), "class": "BSH primary diligence", "treatment": _loc("t"), "as_of": "2026"},
            {"id": "S9", "title": _loc("i"), "class": "c", "treatment": _loc("t"), "as_of": "2026", "url": "https://listed.example.com/only"},
        ],
    )
    before = json.dumps(package, sort_keys=True)
    audit = fc.audit_source_urls(package, company_id=COMPANY, run_dir=run_dir, session_dir=session_dir)
    assert json.dumps(package, sort_keys=True) == before  # report only: nothing stripped or edited
    rows = {row["id"]: row for row in audit["sources"]}
    assert rows["S1"]["seen_in"] == ["source_cache"]
    assert rows["S2"]["seen_in"] == ["source_cache", "run_manifest"]
    assert rows["S3"]["seen_in"] == ["analysis_artifacts"]
    assert rows["S4"]["seen_in"] == ["serena_locators"]
    assert rows["S5"]["seen"] is False and rows["S5"]["seen_in"] == []
    assert rows["S9"]["seen"] is False and rows["S9"]["seen_in"] == ["search_results"]
    assert rows["S8"]["url"] is None and rows["S8"]["seen"] is None
    assert rows["S6"]["homepage_reused"] and rows["S7"]["homepage_reused"]
    assert audit["homepage_reused"] == [{"url": "https://zainartech.com", "ids": ["S6", "S7"]}]
    assert (audit["with_url"], audit["unseen"], audit["no_url"]) == (8, 4, 1)
    assert audit["unseen_ids"] == ["S5", "S6", "S7", "S9"]
    lines = fc._source_url_summary_lines(audit)
    assert any("bare homepage https://zainartech.com is cited by 2 sources" in line for line in lines)
    assert any(line.startswith("- S9 UNSEEN (listed by a search, never fetched)") for line in lines)
    status = fc.stamp_source_url_status(package, audit)
    assert package["run"]["source_url_status"] == status
    assert status["unseen"] == {
        "S5": "https://made-up.example.com/deep/link",
        "S6": "https://zainartech.com",
        "S7": "https://www.zainartech.com/",
        "S9": "https://listed.example.com/only",
    }
    assert set(status["homepage_reused"]) == {"S6", "S7"}


def test_check_memo_run_records_the_url_status(tmp_path, monkeypatch):
    monkeypatch.setattr(fc.numbers_lint, "_corpus", lambda cid: ([], []))
    package = _package({"market": ["The market reaches $45B by 2030 [S1]."]})
    run_dir = tmp_path / "memos" / COMPANY / "run"
    result = fc.check_memo_run(run_dir=run_dir, package=package, company_id=COMPANY, research_dir=tmp_path / "none")
    payload = result.to_dict()
    assert payload["source_urls"]["with_url"] == 1
    assert payload["source_urls"]["unseen_ids"] == ["S1"]
    assert fc.summarize_fact_check(payload)["urls"] == {"with_url": 1, "seen": 0, "unseen": 1, "homepage_reused": 0}
    assert "## Source URLs (report only)" in fc.render_markdown_report(result)


def test_in_context_needs_the_memo_metric_near_the_number_in_the_source():
    corpus = fc.Corpus()
    corpus.company_tokens = {"acme"}
    corpus.add(
        "research file: survey.md",
        "Acme survey: 61% of respondents prefer hosted tools. "
        "Separately, Acme pilots ran in 70 hospitals. " + "Unrelated background prose. " * 60
        + "By then the new office had reached 450 desks. " + "More unrelated prose. " * 40,
    )
    corpus = corpus.finish()
    package = _package(
        {"financials": ["Acme gross margin was 61%.", "Acme runs 70 hospitals today.", "The platform reached 450 customers."]}
    )
    result = fc.check_package(package, corpus)
    assert result.tiers["found_elsewhere"] == 3
    # "hospitals" sits next to 70 in the source. "Gross margin" is nowhere near
    # 61%; "reached" sits next to 450, but the memo's metric is customers; and
    # the company's own name never counts as context.
    assert result.tiers["in_context"] == 1


def test_a_broken_tally_never_changes_the_enforced_check(monkeypatch):
    package = _tier_package()
    expected = fc.check_package(package, _tiered_corpus(), source_texts={"S1": "Survey: median churn 8% across vendors."})

    def boom(*_a, **_k):
        raise RuntimeError("tally bug")

    monkeypatch.setattr(fc._HonestTally, "classify", boom)
    result = fc.check_package(package, _tiered_corpus(), source_texts={"S1": "Survey: median churn 8% across vendors."})
    assert result.error is None and result.tiers == {} and result.figure_tiers == []
    keys = ("checked", "verified", "supported", "derived", "unsupported", "unverifiable_citations", "repair_feed")
    assert {k: getattr(result, k) for k in keys} == {k: getattr(expected, k) for k in keys}
    assert [f.to_dict() for f in result.findings] == [f.to_dict() for f in expected.findings]
    assert fc.summarize_fact_check(result.to_dict())["basis"] == "legacy"
