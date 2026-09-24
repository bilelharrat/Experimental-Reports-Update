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


def test_the_error_does_not_offer_reclassifying_when_nothing_private_is_on_file(monkeypatch):
    """Offering "say so in its class" to a company with nothing private is
    offering the loophole; the next check would catch it a round later."""
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    errors: list[str] = []
    r._validate_source(
        _source("syndicated market research", title="Worldwide AI Spending Guide"),
        "sources[0]",
        errors,
        private_material=False,
    )
    assert len(errors) == 1
    assert "say so in its class" not in errors[0]
    assert "cannot be an internal document" in errors[0]


# ---- the run's private inventory (G1) -------------------------------------------
# One package-wide boolean said "private material on file" for the fact
# ledger, the decision record and documents the run was never given. The
# inventory names what this run may actually read, item by item.


def _inventory_env(tmp_path):
    from server import claude_runner, research_store

    company = "acme"
    research = research_store.RESEARCH_ROOT / company
    deck = research_store.upload_file(company, filename="Series_B_deck.pdf", content_type="application/pdf", data=b"%PDF-1.4 deck")
    deck_analysis = research_store.upload_file(company, filename="deck_analysis.md", content_type="text/markdown", data=b"# deck analysis")
    research_store.update_record(company, deck_analysis["id"], analysis_of=deck["id"])
    calls = research_store.upload_file(company, filename="Customer_calls.docx", content_type=None, data=b"PK\x03\x04 calls")
    calls_analysis = research_store.upload_file(company, filename="calls_analysis.md", content_type="text/markdown", data=b"# calls analysis")
    research_store.update_record(company, calls_analysis["id"], analysis_of=calls["id"])
    kpis = research_store.upload_file(company, filename="KPI_pack.pdf", content_type="application/pdf", data=b"%PDF-1.4 kpis", label="Board KPI pack")
    for digest in ("fact_ledger.md", "decision_record.md", "recent_news.md", "known_sources.md"):
        (research / digest).write_text("- public fact", encoding="utf-8")
    (research / "partner_notes.md").write_text("Notes from the partner meeting.", encoding="utf-8")
    (research / "empty.md").write_text("", encoding="utf-8")
    run_dir = tmp_path / "memos" / company / "run"
    # The analyst gave this run the deck analysis only: the calls analysis
    # (and the raw calls behind it) are out.
    claude_runner.write_memo_evidence_selection(run_dir, [deck_analysis["id"]])
    record = {
        "id": company,
        "name": "Acme",
        "metrics": [
            {"label": "ARR", "value": "~$24M", "source_refs": [{"label": "BSH PRD reference package", "source_class": "BSH primary diligence"}]},
            {"label": "YoY Growth", "value": "+180%", "source_refs": [{"label": "Demo placeholder (v2 design mock) — not evidence", "source_class": "demo placeholder (v2 design mock)"}]},
            {"label": "NRR", "value": "120%", "source_refs": [{"label": "Demo record — not diligence", "source_class": "BSH diligence (demo)"}]},
            {"label": "Valuation", "value": "$1.0B+", "source_refs": [{"label": "Funding disclosure", "source_class": "company"}]},
        ],
    }
    return record, run_dir, {"deck": deck, "deck_analysis": deck_analysis, "calls": calls, "calls_analysis": calls_analysis, "kpis": kpis}


def test_private_inventory_lists_only_what_the_run_may_read(tmp_path):
    from server import memo_fact_check as fc

    record, run_dir, ids = _inventory_env(tmp_path)
    inventory = fc.private_inventory(run_dir, record)
    by_id = {item["id"]: item for item in inventory}
    assert all(set(item) == {"id", "kind", "title", "ref"} for item in inventory)
    # The deck reaches the run through its analysis, so both are listed.
    assert by_id[ids["deck_analysis"]["id"]]["kind"] == "research_analysis"
    distilled = by_id[f"{ids['deck_analysis']['id']}:{ids['deck']['id']}"]
    assert distilled["kind"] == "research_document" and "Series_B_deck.pdf" in distilled["title"]
    assert distilled["ref"] == ids["deck_analysis"]["stored_name"]
    assert ids["deck"]["id"] not in by_id  # the raw deck itself is not read
    # Deselected: the calls analysis and the raw calls behind it.
    assert ids["calls_analysis"]["id"] not in by_id and ids["calls"]["id"] not in by_id
    assert not any("calls" in item["title"].lower() for item in inventory)
    assert by_id[ids["kpis"]["id"]]["title"] == "Board KPI pack — KPI_pack.pdf"
    assert by_id["file:partner_notes.md"]["kind"] == "research_file"
    titles = " ".join(item["title"] for item in inventory)
    for digest in ("fact_ledger", "decision_record", "recent_news", "known_sources", "empty.md"):
        assert digest not in titles
    # Registry metrics tagged BSH diligence count; demo-labelled ones never do.
    registry = [item for item in inventory if item["kind"] == "registry_metric"]
    assert [item["id"] for item in registry] == ["registry:metrics[0]"]
    assert registry[0]["title"] == "BSH PRD reference package: ARR ~$24M"


def test_private_inventory_without_a_selection_offers_every_analysis(tmp_path):
    from server import memo_fact_check as fc

    record, _run_dir, ids = _inventory_env(tmp_path)
    inventory = fc.private_inventory(None, record)
    assert ids["calls_analysis"]["id"] in {item["id"] for item in inventory}
    assert fc.private_inventory(None, {"id": "nobody", "name": "Nobody"}) == []


def test_stamp_private_inventory_and_match_sources_against_it(tmp_path):
    from server import memo_fact_check as fc

    record, run_dir, ids = _inventory_env(tmp_path)
    inventory = fc.private_inventory(run_dir, record, extra_items=[{"id": "call:2026-06", "kind": "reference_call", "title": "BSH reference call (customer, 2026-06)", "ref": "call_notes.md#1"}])
    package = {"run": {"private_material_on_file": True}, "sources": []}
    stamped = fc.stamp_private_inventory(package, inventory)
    assert package["run"]["private_inventory"] == stamped
    assert package["run"]["private_material_on_file"] is True  # the old flag is left alone
    assert fc.stamp_private_inventory({}, inventory) == stamped

    def source(title, **extra):
        return {"id": "S1", "title": {"en": title, "zh": title}, "class": "company-reported", **extra}

    assert fc.inventory_match(source("Acme Series B deck (2026)"), inventory)["id"].endswith(ids["deck"]["id"])
    assert fc.inventory_match(source("Board KPI pack"), inventory)["id"] == ids["kpis"]["id"]
    assert fc.inventory_match(source("BSH reference call (customer, 2026-06)"), inventory)["id"] == "call:2026-06"
    assert fc.inventory_match(source("Anything", private_ref=ids["kpis"]["id"]), inventory)["id"] == ids["kpis"]["id"]
    assert fc.inventory_match(source("Anything", private_ref="call_notes.md#1"), inventory)["id"] == "call:2026-06"
    # Public pages that call themselves private do not match anything.
    assert fc.inventory_match(source("Public Infrastructure Software Comparables Tracker"), inventory) is None
    assert fc.inventory_match(source("Customer calls"), inventory) is None  # deselected
    assert fc.inventory_match(source("Deck"), inventory) is None  # one word never matches
    assert fc.inventory_match(source("Board KPI pack"), []) is None
