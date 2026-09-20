"""The renderer's source-URL rule: a web-retrieved source must carry the
page it came from; private material says so in its class instead."""
from __future__ import annotations

import pytest

from server import memo_docx_renderer as r


def _loc(en: str) -> dict:
    return {"en": en, "zh": en}


def _source(cls: str, *, title: str = "Some source", url: str | None = None) -> dict:
    source = {"id": "S1", "title": _loc(title), "class": cls, "treatment": _loc("Weighed as is."), "as_of": "2026-01-01"}
    if url is not None:
        source["url"] = url
    return source


@pytest.mark.parametrize(
    "cls, title",
    [
        ("BSH primary diligence", "Founder interview"),
        ("internal model", "BSH returns model"),
        ("investor materials", "Series B deck"),
        ("investor/intermediary", "Banker CIM"),
        ("company-reported", "Management KPI pack"),
        ("company disclosure", "Board update"),
        ("company", "Data room export"),
        ("third-party market data", "Interview with a former customer"),
        ("public filings", "Transcript of the Q2 call"),
    ],
)
def test_private_material_may_omit_url(cls, title, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(_source(cls, title=title), "sources[0]", errors)
    assert errors == []


@pytest.mark.parametrize(
    "cls",
    [
        "independent secondary",
        "third-party market data",
        "public filings",
        "transaction_filing",
        "press reporting",
        "syndicated_market_research",
        "government / public announcement",
        "public comps",
        "industry_benchmarks",
        "third_party_analyst_estimate",
    ],
)
def test_web_retrieved_source_needs_url(cls, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(_source(cls, title="Market sizing report"), "sources[3]", errors)
    assert len(errors) == 1
    assert errors[0].startswith("sources[3].url is required")
    assert cls in errors[0]
    errors = []
    r._validate_source(_source(cls, title="Market sizing report", url="https://example.com/r"), "sources[3]", errors)
    assert errors == []


def test_url_rule_has_a_kill_switch(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SOURCE_URL_REQUIRED", "0")
    errors: list[str] = []
    r._validate_source(_source("independent secondary"), "sources[0]", errors)
    assert errors == []


def test_bad_url_still_rejected(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(_source("press reporting", url="www.example.com"), "sources[0]", errors)
    assert errors == ["sources[0].url must be an http(s) URL when present"]


def test_url_error_routes_to_the_envelope_repair():
    from server import claude_runner

    error = "sources[3].url is required: a source of class 'press reporting' is web-retrieved, so carry the page URL"
    package = {"sections": [{"id": "risks", "blocks": []}], "sources": []}
    assert claude_runner._section_for_validation_error(package, error) is None
    assert claude_runner._is_envelope_repair_finding(package, error) is True
