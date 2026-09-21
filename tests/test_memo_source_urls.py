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


# ---- the exemption has to be true -------------------------------------------
# Live on 2026-09-21 a RadixArk Gemini memo classed three public sources as
# "internal document" and passed — RadixArk has no research folder, no
# uploads, nothing private at all — because the rule's own error message
# named reclassifying as the way out. The pipeline now stamps whether the
# firm holds anything private on the company, and the exemption needs it.


def test_a_private_class_does_not_exempt_when_nothing_private_is_on_file(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(
        _source("internal document", title="Public Infrastructure Software Comparables Tracker"),
        "sources[0]",
        errors,
        private_material=False,
    )
    assert len(errors) == 1
    assert "holds nothing private" in errors[0]
    # It must not repeat the advice that caused this.
    assert "say so in its class" not in errors[0]


def test_a_private_class_still_exempts_when_the_firm_holds_private_material(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(
        _source("BSH primary diligence", title="Founder interview"),
        "sources[0]",
        errors,
        private_material=True,
    )
    assert errors == []


def test_an_unstamped_package_keeps_the_old_exemption(monkeypatch):
    """Stored packages and fixtures carry no stamp; they validate as before."""
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(_source("internal document"), "sources[0]", errors)
    assert errors == []


def test_private_material_ignores_the_web_digests(tmp_path, monkeypatch):
    """recent_news.md and known_sources.md are written by the pipeline from
    public pages, so a folder holding only those holds nothing private."""
    from server import memo_fact_check as fc

    for module, attr, value in (
        ("portfolio", "has_record", lambda _cid: False),
        ("transcripts", "all_transcripts", lambda: []),
        ("ic_room", "list_reference_calls", lambda _cid: {"items": []}),
    ):
        monkeypatch.setattr(f"server.{module}.{attr}", value)
    folder = tmp_path / "acme"
    folder.mkdir()
    (folder / "recent_news.md").write_text("news", encoding="utf-8")
    (folder / "known_sources.md").write_text("pages", encoding="utf-8")
    (folder / "index.yaml").write_text("files: []", encoding="utf-8")
    assert fc.private_material_on_file("acme", research_dir=folder) == []

    (folder / "Meeting_Notes.pdf").write_bytes(b"%PDF-1.4 notes")
    assert fc.private_material_on_file("acme", research_dir=folder) == [
        "research file: Meeting_Notes.pdf"
    ]


def test_the_stamp_reaches_the_package_validator(tmp_path, monkeypatch):
    """End to end through the package validator, not just the helper."""
    from server import memo_fact_check as fc

    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    monkeypatch.setattr(fc, "private_material_on_file", lambda *_a, **_k: [])
    package = {"run": {}, "sources": [_source("internal document")]}
    fc.stamp_private_material(package, company_id="acme")
    assert package["run"]["private_material_on_file"] is False
    errors = r.english_package_validation_errors(package)
    assert any("holds nothing private" in e for e in errors)
