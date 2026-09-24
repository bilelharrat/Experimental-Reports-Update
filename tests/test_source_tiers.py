"""Source reliability tiers and honest source dates (server/source_tiers.py)."""
from __future__ import annotations

import pytest

from server import source_tiers as t


@pytest.mark.parametrize(
    "url, tier",
    [
        # A: regulators, filings, courts, exchanges, government registries
        ("https://www.sec.gov/Archives/edgar/data/1/x.htm", "A"),
        ("https://efts.sec.gov/LATEST/search-index?q=x", "A"),
        ("https://www.courtlistener.com/docket/123/openai-v-open-ai/", "A"),
        ("https://www.hkexnews.hk/listedco/x.pdf", "A"),
        ("https://www.gov.uk/government/organisations/companies-house", "A"),
        ("https://www.meti.go.jp/english/x", "A"),
        ("https://listingcenter.nasdaq.com/x", "A"),
        # B: the named tier-1 set, data vendors and recognised news hosts
        ("https://www.reuters.com/technology/x", "B"),
        ("https://www.bloomberg.com/news/articles/x", "B"),
        ("https://www.ft.com/content/x", "B"),
        ("https://www.wsj.com/tech/x", "B"),
        ("https://www.cnbc.com/2026/08/17/x.html", "B"),
        ("https://www.theinformation.com/articles/x", "B"),
        ("https://pitchbook.com/profiles/company/x", "B"),
        ("https://sacra.com/c/anthropic/", "B"),
        ("https://finance.yahoo.com/news/x.html", "B"),
        ("https://www.nasdaq.com/articles/x", "B"),
        # C: blogs, self-publishing, SEO aggregators, anything unknown
        ("https://medium.com/@someone/anthropic-ipo", "C"),
        ("https://analyst.substack.com/p/x", "C"),
        ("https://buildmvpfast.com/blog/anthropic-ipo", "C"),
        ("https://www.valueaddvc.com/x", "C"),
        ("https://www.linkedin.com/pulse/x", "C"),
        ("", "C"),
        ("not a url", "C"),
    ],
)
def test_tier_map(url, tier):
    assert t.tier_for_url(url) == tier


def test_company_domain_is_a_minus_on_any_subdomain():
    assert t.tier_for_url("https://www.anthropic.com/news/x", "anthropic.com") == "A-"
    assert t.tier_for_url("https://investors.acme.io/q2", "https://www.acme.io") == "A-"
    # the company's own page outranks nothing else: a regulator stays A
    assert t.tier_for_url("https://www.sec.gov/x", "acme.io") == "A"
    # and a lookalike domain is not the company's
    assert t.tier_for_url("https://notacme.io/x", "acme.io") == "C"


def test_display_domain():
    assert t.display_domain("https://www.CNBC.com/2026/08/17/x.html") == "cnbc.com"
    assert t.display_domain("https://analyst.substack.com/p/x") == "analyst.substack.com"
    assert t.display_domain("") == ""
    assert t.display_domain("nonsense") == ""


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026", "2026"),
        ("2026-08", "2026-08"),
        ("2026-08-17", "2026-08-17"),
        ("2026/8/7", "2026-08-07"),
        ("2026-08-17T10:05:00Z", "2026-08-17"),
        ("2026-02-30", None),
        ("2026-13", None),
        ("2026-07 – 2026-08", None),
        ("2026-Q2", None),
        ("Aug 2026", None),
        ("undated", None),
        ("1850", None),
        (None, None),
        ("", None),
    ],
)
def test_parse_partial_date(value, expected):
    assert t.parse_partial_date(value) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://www.cnbc.com/2026/08/17/anthropic-run-rate.html", "2026-08-17"),
        ("https://example.com/2026/08/anthropic", "2026-08"),
        ("https://example.com/news/anthropic-2026-08-13.html", "2026-08-13"),
        ("https://example.com/p/20260813/story", "2026-08-13"),
        ("https://example.com/news/anthropic-ipo-081326.html", "2026-08-13"),
        # after the run date, implausible year, or an ID that is no date
        ("https://example.com/2027/01/05/future", None),
        ("https://example.com/1998/01/05/old", None),
        ("https://example.com/item/123456", None),
        ("https://example.com/news/x-991326.html", None),
        # only the path counts, never the query
        ("https://example.com/x?date=2026-08-17", None),
    ],
)
def test_date_from_url(url, expected):
    assert t.date_from_url(url, not_after="2026-09-01") == expected


def test_a_web_source_dated_the_run_day_becomes_undated():
    source = {
        "id": "S11",
        "title": "VentureBeat — Anthropic revenue tied to two customers",
        "class": "Business press",
        "as_of": "2026-09-01",
    }
    out = t.normalize_source_dates(source, "2026-09-01__185114")
    assert out["published_at"] == "undated"
    assert out["as_of"] == "2026-09-01"  # the legacy field is left alone
    assert "retrieved_at" not in out
    # ...unless the URL's path carries the real date
    dated = dict(source, url="https://venturebeat.com/ai/2026/08/28/anthropic-two-customers/")
    assert t.normalize_source_dates(dated, "2026-09-01")["published_at"] == "2026-08-28"


def test_internal_material_keeps_its_run_date():
    for source in (
        {"id": "S25", "title": "BSH reconstruction", "class": "BSH primary diligence", "as_of": "2026-09-01"},
        {"id": "S23", "title": "Anthropic company registry entry", "class": "Internal record", "as_of": "2026-09-01"},
    ):
        assert t.normalize_source_dates(source, "2026-09-01")["published_at"] == "2026-09-01"
        assert t.is_internal_source(source)


def test_published_at_wins_over_the_legacy_alias_and_fields_normalize():
    source = {
        "id": "S1",
        "title": "Series H announcement",
        "class": "company-reported",
        "as_of": "2026-05-01",
        "published_at": "2026-05",
        "data_period": "2026-04",
        "retrieved_at": "2026-09-01T12:00:00Z",
    }
    out = t.normalize_source_dates(source, "2026-09-01")
    assert out["published_at"] == "2026-05"
    assert out["data_period"] == "2026-04"
    assert out["retrieved_at"] == "2026-09-01"
    # fetched_at (from the source cache) is what fills retrieved_at later
    bare = {"id": "S2", "title": "x", "class": "press", "as_of": "undated"}
    out = t.normalize_source_dates(bare, "2026-09-01", fetched_at="2026-08-30T08:00:00Z")
    assert out["published_at"] == "undated"
    assert out["retrieved_at"] == "2026-08-30"


def test_normalize_is_pure():
    source = {"id": "S1", "title": "x", "class": "press", "as_of": "2026-09-01"}
    t.normalize_source_dates(source, "2026-09-01")
    assert source == {"id": "S1", "title": "x", "class": "press", "as_of": "2026-09-01"}


def test_evidence_cutoff_is_the_latest_dated_public_source():
    sources = [
        {"id": "S1", "title": "a", "class": "press", "as_of": "2026-06-13"},
        {"id": "S2", "title": "b", "class": "press", "as_of": "2026-08"},
        # run-day date on a web source: undated, never the cutoff
        {"id": "S3", "title": "c", "class": "press", "as_of": "2026-09-01"},
        # internal material never sets the evidence ceiling
        {"id": "S4", "title": "BSH model", "class": "internal model", "as_of": "2026-09-01"},
        # a forward date is not evidence
        {"id": "S5", "title": "d", "class": "press", "as_of": "2026-10-01"},
        {"id": "S6", "title": "e", "class": "press", "data_period": "2026-08-20"},
    ]
    assert t.evidence_cutoff(sources, "2026-09-01") == "2026-08-20"
    assert t.evidence_cutoff([], "2026-09-01") is None
    assert t.evidence_cutoff(sources[2:5], "2026-09-01") is None


def test_agencies_and_energy_research_houses_are_not_tier_c():
    # IEA/IMF-style agency statistics are the record; Wood Mackenzie-style
    # research houses are named vendors, not SEO aggregators.
    assert t.tier_for_url("https://www.iea.org/reports/world-energy-outlook-2025") == "A"
    assert t.tier_for_url("https://www.imf.org/en/Publications/WEO") == "A"
    assert t.tier_for_url("https://www.woodmac.com/news/opinion/lng/") == "B"
