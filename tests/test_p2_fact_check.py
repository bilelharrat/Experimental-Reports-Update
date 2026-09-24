"""Fact check round 2: the enforcement floor for unsupported headline
figures (I8), same-metric contradictions within one memo (I7), and the
evidence-quote check against the cached source text (I6)."""
from __future__ import annotations

import json

import pytest

from server import memo_fact_check as fc, research_store, source_cache

COMPANY = "zainar-inc"


@pytest.fixture(autouse=True)
def _roots(tmp_path, monkeypatch):
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", tmp_path / "research")
    monkeypatch.delenv("BSH_MEMO_FACT_CHECK_REPAIR", raising=False)


def _loc(en: str) -> dict:
    return {"en": en, "zh": ""}


def _corpus(text: str) -> fc.Corpus:
    corpus = fc.Corpus()
    corpus.add("evidence", text)
    return corpus.finish()


def _gemini_v1_shape() -> dict:
    """The Gemini standard-v1 memo's shape: an executive summary and a key
    metrics table stating a runway no source carries, and a long body
    whose figures the corpus mostly does not have (coverage < 60%)."""
    body = [
        f"Metric {n} reached {n + 11}% in the period." for n in range(12)
    ]
    return {
        "sections": [
            {
                "id": "executive_summary",
                "blocks": [
                    {"type": "paragraph", "text": _loc("With 52 employees burning $15M a year, the $10M primary cash infusion provides only 8 to 10 months of operational runway.")},
                    {
                        "type": "table",
                        "component": "key_metrics_snapshot",
                        "headers": [_loc("Metric"), _loc("Value")],
                        "rows": [[_loc("Estimated annual burn"), _loc("$12M to $18M (estimated)")]],
                    },
                ],
            },
            {"id": "company_overview", "blocks": [{"type": "paragraph", "text": _loc(" ".join(body))}]},
        ]
    }


def test_headline_floor_enforces_below_the_coverage_threshold():
    package = _gemini_v1_shape()
    corpus = _corpus("52 employees; $10M extension round. " * 4_000)  # rich, but no runway figure
    result = fc.check_package(package, corpus)
    assert result.coverage_pct is not None and result.coverage_pct < fc.AUTO_ENFORCE_MIN_COVERAGE
    headline = result.unsupported_headline_findings
    assert headline and all(f.headline for f in headline)
    assert {f.section_id for f in headline} == {"executive_summary"}
    assert {f.figure for f in headline} >= {"$15M", "$12M", "$18M"}
    assert result.repair_feed is True
    assert result.repair_feed_reason.startswith("headline floor:")
    assert "regardless of coverage" in result.repair_feed_reason
    # Headline figures are fed first.
    lines = result.summary_lines()
    assert lines and lines[0].startswith("fact check unsupported_figure in section executive_summary")
    assert result.to_dict()["unsupported_headline"] == len(headline)
    assert result.to_dict()["findings"][0]["headline"] is True


def test_headline_floor_respects_off_switch_and_thin_corpus(monkeypatch):
    package = _gemini_v1_shape()
    rich = _corpus("52 employees; $10M extension round. " * 4_000)
    monkeypatch.setenv("BSH_MEMO_FACT_CHECK_REPAIR", "0")
    assert fc.check_package(package, rich).repair_feed is False
    monkeypatch.delenv("BSH_MEMO_FACT_CHECK_REPAIR")
    thin = fc.check_package(package, _corpus("tiny"))
    assert thin.repair_feed is False and "thin" in thin.repair_feed_reason


def test_body_only_unsupported_figures_keep_the_old_auto_policy():
    package = {"sections": [{"id": "investment_risk", "blocks": [{"type": "paragraph", "text": _loc("Churn ran at 9% last year.")}]}]}
    result = fc.check_package(package, _corpus("churn 8% " * 20_000))
    assert result.unsupported == 1 and result.unsupported_headline_findings == []
    assert result.repair_feed is False and "traceable" in result.repair_feed_reason
    ok, reason = fc.should_enforce(_corpus("x " * 30_000), 10)
    assert ok is False and "traceable" in reason
    ok, reason = fc.should_enforce(_corpus("x " * 30_000), 10, headline_unsupported=2)
    assert ok is True and "2 unsupported figures" in reason


def test_headline_section_rule():
    assert fc.headline_section("executive_summary")
    assert fc.headline_section("investment_decision")
    assert fc.headline_section("company_overview", "key_metrics_snapshot")
    assert fc.headline_section("company_overview", ["board", "key_metrics_snapshot"])
    assert not fc.headline_section("company_overview")
    assert not fc.headline_section("investment_risk", "risk_register")


# ---- metric conflicts ---------------------------------------------------------------


def _package(blocks_by_section: dict[str, list]) -> dict:
    return {
        "company": {"name": "ZaiNar, Inc."},
        "sections": [{"id": sid, "blocks": blocks} for sid, blocks in blocks_by_section.items()],
    }


def test_metric_conflicts_flags_the_same_metric_with_two_values():
    package = _package({
        "executive_summary": [{"type": "paragraph", "text": _loc("NextNav (NASDAQ: NN) reports a net loss of $189.3M in 2025 on $3.98M revenue.")}],
        "valuation": [{"type": "paragraph", "text": _loc("NextNav sustains a -$111.9M net loss against $4.02M in trailing revenue [S7].")}],
    })
    conflicts = fc.metric_conflicts(package)
    assert len(conflicts) == 1
    conflict = conflicts[0]
    assert conflict["metric"] == "net loss (nextnav)"
    assert conflict["values"] == ["$189.3M", "$111.9M"]
    assert conflict["sections"] == ["executive_summary", "valuation"]
    assert len(conflict["locations"]) == 2 and all(loc.startswith("sections[") for loc in conflict["locations"])


def test_metric_conflicts_ignores_repeated_columns_scenarios_and_years():
    package = _package({
        "valuation": [
            {
                "type": "table",
                "headers": [_loc("Case"), _loc("ARR")],
                "rows": [[_loc("Bear"), _loc("$35M ARR")], [_loc("Base"), _loc("$120M ARR")], [_loc("Bull"), _loc("$250M ARR")]],
            },
            {
                "type": "table",
                "headers": [_loc("Metric"), _loc("Value")],
                "rows": [[_loc("Net loss"), _loc("$189.3M")], [_loc("Net loss"), _loc("$189.3M")], [_loc("Net loss"), _loc("$189M")]],
            },
            {"type": "paragraph", "text": _loc("Revenue was $3.5M in 2024 and $4.0M in 2025.")},
            {"type": "paragraph", "text": _loc("Gross margin is 75% while net margin is 40%.")},
        ],
    })
    assert fc.metric_conflicts(package) == []


def test_metric_conflicts_accepts_paths_and_never_raises(tmp_path):
    package = _package({
        "a": [{"type": "paragraph", "text": _loc("Headcount is 52 employees today.")}],
        "b": [{"type": "paragraph", "text": _loc("The company employs 200 employees.")}],
    })
    path = tmp_path / "memo_package.json"
    path.write_text(json.dumps(package), encoding="utf-8")
    assert [c["values"] for c in fc.metric_conflicts(path)] == [["52", "200"]]
    assert fc.metric_conflicts(tmp_path / "missing.json") == []
    assert fc.metric_conflicts(tmp_path / "missing.docx") == []
    assert fc.metric_conflicts(None) == []
    assert fc.metric_conflicts("not a package") == []


# ---- evidence quotes ------------------------------------------------------------------


def _run(tmp_path, quotes) -> "Path":  # noqa: F821 - annotation only
    run_dir = tmp_path / "memos" / COMPANY / f"2026-09-23__010203__{COMPANY}__memo-run"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs" / "evidence_quotes.json").write_text(json.dumps(quotes), encoding="utf-8")
    return run_dir


def test_check_quotes_matches_normalised_substrings_against_the_cache(tmp_path):
    quotes = [
        {"claim": "Company raised $10M", "url": "https://www.theinformation.com/a?utm_source=x", "quote": "ZaiNar raised a  $10M “insider” extension — its first outside price", "pass_id": "financials"},
        {"claim": "Runway", "url": "https://www.theinformation.com/a", "quote": "eight to ten months of runway", "pass_id": "financials"},
        {"claim": "No cache", "url": "https://example.com/nowhere", "quote": "anything at all here", "pass_id": "market"},
        {"claim": "Too short", "url": "https://www.theinformation.com/a", "quote": "raised", "pass_id": "x"},
        "junk",
    ]
    run_dir = _run(tmp_path, quotes)
    # The run's frozen source carries the first quote (with different quotes and spacing).
    source_cache.record_run_source(
        COMPANY, run_dir, tool="WebFetch",
        text="Report: ZaiNar raised a $10M 'insider' extension - its first outside price in years. " * 3,
        url="https://www.theinformation.com/a", run_id="run",
    )
    result = fc.check_quotes(run_dir)
    assert result["checked"] == 3 and result["matched"] == 1
    unmatched = {row["claim"]: row["reason"] for row in result["unmatched"]}
    # Only a cached page that lacks the quote is suspicious; a page never
    # cached cannot be checked and is listed apart.
    assert unmatched == {"Runway": "quote not found in the cached page text"}
    assert [row["claim"] for row in result["uncached"]] == ["No cache"]
    assert all(set(row) >= {"claim", "url", "quote", "pass_id", "reason"} for row in result["unmatched"])


def test_check_quotes_falls_back_to_the_company_cache_and_never_raises(tmp_path):
    run_dir = _run(tmp_path, [{"claim": "c", "url": "https://gartner.com/databook", "quote": "market $45B by 2030", "pass_id": "market"}])
    source_cache.record_source(COMPANY, kind="web_fetch", text="Gartner databook: market $45B by 2030. " * 4, url="https://gartner.com/databook")
    assert fc.check_quotes(run_dir)["matched"] == 1
    assert fc.check_quotes(run_dir, company_id="someone-else")["matched"] == 0
    empty = {"checked": 0, "matched": 0, "unmatched": [], "uncached": []}
    assert fc.check_quotes(tmp_path / "no-such-run") == empty
    (run_dir / "logs" / "evidence_quotes.json").write_text("{not json", encoding="utf-8")
    assert fc.check_quotes(run_dir) == empty


def test_an_elided_quote_matches_when_every_fragment_appears_in_order(tmp_path):
    # Live 2026-09-23: all six of Claude's "absent" quotes elided words with
    # "..." — every fragment was on the page.
    page = ("This funding accelerates deployment with carrier and enterprise partners "
            "globally, and we expect to announce major carrier and enterprise partnerships "
            "in the coming weeks. Our team is growing.")
    run_dir = _run(tmp_path, [
        {"claim": "ok", "url": "https://example.com/pr", "quote": "This funding accelerates deployment with carrier and enterprise partners globally... announce major carrier and enterprise partnerships", "pass_id": "p"},
        {"claim": "wrong order", "url": "https://example.com/pr", "quote": "announce major carrier and enterprise partnerships... This funding accelerates deployment", "pass_id": "p"},
    ])
    source_cache.record_run_source(COMPANY, run_dir, tool="WebFetch", text=page, url="https://example.com/pr", run_id="run")
    result = fc.check_quotes(run_dir)
    assert result["matched"] == 1
    assert [row["claim"] for row in result["unmatched"]] == ["wrong order"]
    # a short lead fragment ("ZaiNar...") does not block the match
    assert fc._elided_quote_in(
        fc.normalize_quote("ZaiNar... today announced the opening of its Tokyo office"),
        fc.normalize_quote("ZaiNar, the physical AI company, today announced the opening of its Tokyo office."),
    )


def test_normalize_quote():
    assert fc.normalize_quote("  “Hello”—World\u00a0 x ") == "'hello'-world x"
    assert fc.normalize_quote('a "b" c') == fc.normalize_quote("a ‘b’ c") == "a 'b' c"


# ---- scraped tables and calculation-input provenance (2026-09-23 round 3) -----------------


def test_figures_one_cell_per_line_are_read():
    """A scraped comps table puts one cell per line; the "glued identifier"
    filter read the newline as glue (and "$" matched before it), and the
    multiple pattern read the next line's number as a dimension — so every
    multiple in multiples.vc's tables was invisible to the check."""
    table = "People & Technology\n$545M\n$77M\n$489M\n1.2x\nAssetWatch\nPlejd\n$95M\n$32M\n11.7x\n9.3x"
    assert [f.raw for f in fc.extract_figures(table)] == [
        "$545M", "$77M", "$489M", "1.2x", "$95M", "$32M", "11.7x", "9.3x",
    ]
    # What the filters are for is unchanged.
    for identifier in ("FY24 revenue", "Q3 2025", "S-1 filing", "10-K", "H1 2026", "a 2x 4 board"):
        assert fc.extract_figures(identifier) == [], identifier


def _calc_package(inputs: list[dict]) -> dict:
    return {
        "sections": [],
        "calculations": [{"id": "C1", "inputs": inputs, "formula": "x = y", "result": "y"}],
    }


def test_a_calculation_input_no_source_carries_is_relabelled_as_an_assumption():
    """ZaiNar 2026-09-23 (Gemini v2): "Estimated Baseline Contracted Revenue
    = $30M [S2]" where S2 is a paywalled headline — every valuation figure
    was computed from it. $30M occurs elsewhere in the corpus, attached to
    something else, so it is not "in context" for the input's own words."""
    corpus = _corpus(
        "Tracxn: raised $10M on Feb 19, 2026. " + "filler words here. " * 60
        + "Another startup, Acme Robotics, raised $30M in a Series B led by Foo. " + "more filler. " * 60
    )
    package = _calc_package(
        [
            {"name": _loc("Estimated Baseline Contracted Revenue"), "value": _loc("$30M"), "ref": "S2"},
            {"name": _loc("Primary capital raised"), "value": _loc("$10,000,000"), "ref": "S2"},
            {"name": _loc("Exit multiple"), "value": _loc("10.0x"), "ref": "assumption"},
            {"name": _loc("Entry"), "value": _loc("$1.0B"), "ref": "S1"},
        ]
    )
    sources = {"S1": "valued at $1.0B after the round", "S2": "Startup earns $1 billion valuation"}
    found = fc.unsourced_calculation_inputs(package, corpus, sources)
    # $10,000,000 is carried in context ("raised $10M"); an assumption is
    # never listed; $1.0B is in its cited source.
    assert [(f["calc_id"], f["input_index"], f["value"]) for f in found] == [("C1", 0, "$30M")]
    assert fc.relabel_unsourced_calculation_inputs(package, found) == 1
    assert package["calculations"][0]["inputs"][0]["ref"] == "assumption"
    assert package["calculations"][0]["inputs"][1]["ref"] == "S2"
    # A second pass over the relabelled package finds nothing.
    assert fc.unsourced_calculation_inputs(package, corpus, sources) == []


def test_an_input_a_table_states_under_a_scale_heading_is_sourced():
    """D2 cited MarketsandMarkets for "Indoor location, 2026 = $18.3B"; the
    page states it as "Market Size Base Year (Billions) ~USD 18.31"."""
    page = "Indoor Location Market Market Size Base Year (Billions) ~USD 18.31 (2026) Revenue Forecast"
    corpus = _corpus(page + " filler." * 300)
    package = _calc_package([{"name": _loc("Indoor location, 2026"), "value": _loc("$18.3B"), "ref": "S9"}])
    assert fc.unsourced_calculation_inputs(package, corpus, {"S9": "a different page " * 200}) == []


def test_comparisons_their_own_figures_contradict():
    """Two live errors (ZaiNar 2026-09-23): Claude's IC memo called $597M
    "still below" $579.37M, and D2 put $1B "in the top fifth" of $315M-$1.4B."""
    errors = fc.comparison_errors(
        "= about $597M — still below the August 2021 Series A post-money of $579.37M only by a whisker."
    )
    assert [e["kind"] for e in errors] == ["comparison"]
    assert errors[0]["detail"] == "$597M is above $579.37M, not below it"
    band = fc.comparison_errors("Fair value range: $315M - $1.4B, our estimate. The $1B+ mark sits in the top fifth of that band.")
    assert [e["kind"] for e in band] == ["band"] and "63%" in band[0]["detail"]
    for fine in (
        # "under"/"over" qualifying the second figure, deltas, and right comparisons.
        "NextNav trades at an estimated enterprise value of $2.36B on under $4.0M of operating revenue.",
        "Qualcomm bought Skyhook for $179M in April 2022, about 82% below the current private mark.",
        "The $1.0B entry valuation sits $165M above the upper bound and nearly doubles the $505M midpoint.",
        "The walk-away price is $414M, well below the $1.0B entry mark.",
        "Revenue reached $12M, above the $10M plan.",
        "A $1.3B price sits in the upper half of the $315M to $1.4B range.",
    ):
        assert fc.comparison_errors(fine) == [], fine


def test_a_wrong_comparison_is_fed_to_the_repair_even_without_enforcement():
    package = {
        "sections": [
            {
                "id": "valuation",
                "blocks": [{"type": "paragraph", "text": {"en": "Revenue reached $8M, above the $10M plan.", "zh": ""}}],
            }
        ]
    }
    result = fc.check_package(package, _corpus("Revenue reached $8M against a $10M plan. " + "x " * 1500))
    assert [f.code for f in result.comparison_findings] == ["comparison_error"]
    assert not result.repair_feed or result.unsupported == 0
    lines = result.summary_lines()
    assert len(lines) == 1 and lines[0].startswith("fact check comparison_error in section valuation:")
    assert result.to_dict()["comparison_findings"][0]["suggestion"].startswith("$8M is below $10M")


@pytest.mark.parametrize(
    "text",
    [
        "about $597M — still below the August 2021 Series A post-money of $579.37M.",
        "$1B sits in the top fifth of $315M–$1.4B.",
        "$1B sits in the top fifth of $315M-$1.4B.",
        "Between $315M and $1.4B, $1B sits in the top fifth.",
        "Our fair value range is $315M to $1.4B. This is our own estimate. The $1B+ mark sits in the top fifth of the band.",
    ],
)
def test_wrong_comparisons_are_caught(text):
    assert fc.comparison_errors(text)


@pytest.mark.parametrize(
    "text",
    [
        # a shared-scale range, read whole
        "Of the $1.2–$1.5B range, $1.25B sits in the bottom fifth.",
        # the band's subject is in its own clause, and negation counts
        "Comps trade at $315M–$1.4B. Revenue was $50M. Growth puts the company in the top third of its peers.",
        "The range is $315M–$1.4B. Our $300M bid is not in the top fifth.",
        # the second figure belongs to another clause or another comparison
        "Revenue of $10M is above plan, with $12M expected next year.",
        "The company burned $10M over the last 12 months vs $12M the year before.",
        "Revenue grew to $10M under the new CEO, from $6M in 2023.",
        "We invest $5M over 3 years in a $40M round.",
        # a difference, not a subject
        "The $1.0B entry sits $165M above the $835M upper bound.",
        "We priced the round $50M above the $400M post-money.",
        # a part of the first figure
        "Revenue was $10M, less than $3M of it recurring.",
        "Customer A paid $5M, more than half of the $8M total.",
        # different currencies, negative figures
        "NT$3B is below $100M of US revenue.",
        "EBITDA improved to −$5M, above −$10M last year.",
        "EBITDA improved to ($5M), above ($10M) last year.",
        # a table row: the cell before is not the band's subject
        "$1B+ mark | A new priced round, struck inside the lower half of the $315M to $1.4B range",
    ],
)
def test_ordinary_prose_is_not_a_wrong_comparison(text):
    assert fc.comparison_errors(text) == []


def test_extraction_keeps_ranges_after_words_multiples_before_years_and_skips_long_digit_runs():
    assert [f.raw for f in fc.extract_figures("revenue of 20-25M")] == ["20M", "25M"]
    assert [f.raw for f in fc.extract_figures("trades at 12x 2025E EBITDA")] == ["12x"]
    assert fc.extract_figures("a 2x 4 grid") == []
    assert [f.raw for f in fc.extract_figures("$315M-$1.4B")] == ["$315M", "$1.4B"]
    assert fc.extract_figures("S-1 and 10-K") == []
    import time

    started = time.monotonic()
    assert [f.raw for f in fc.extract_figures("id " + "7" * 16000 + " raised $5M")] == ["$5M"]
    assert time.monotonic() - started < 1.0


def test_calc_input_provenance_edge_cases():
    corpus = fc.Corpus(texts=[("page", "ARR reached $5 million last year, with $30 average revenue per user.")])
    package = {
        "calculations": [
            {
                "id": "C1",
                "inputs": [
                    {"name": "Estimated baseline revenue", "value": "$30M", "ref": "S2"},
                    # derived in another note as well: never relabelled
                    {"name": "Implied enterprise value", "value": "$400M", "ref": "C2, S3"},
                    {"name": "TAM (2026)", "value": "$18.3B", "ref": "S9"},
                ],
            }
        ]
    }
    texts = {
        "S2": "Paywalled headline with no figures.",
        "S3": "Revenue of $40M.",
        "S9": "Market Size Base Year (Billions) ~USD 18.31 (2026) growing to 30.1 by 2031",
    }
    found = fc.unsourced_calculation_inputs(package, corpus, texts)
    # A scale word near another figure is not a heading: $30 is not $30M.
    assert [row["name"] for row in found] == ["Estimated baseline revenue"]
    # No source texts at all: no crash (nothing can be matched to a source).
    assert "Estimated baseline revenue" in [
        row["name"] for row in fc.unsourced_calculation_inputs(package, corpus, None)
    ]
