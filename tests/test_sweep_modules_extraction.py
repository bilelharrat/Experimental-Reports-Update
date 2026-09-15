"""Deterministic extraction and matching: deck/update regexes, comps facts, numbers lint, transcripts, thesis fit."""
from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

from server import comps, intake_decks, numbers_lint, portfolio, storage, thesis_store, transcripts
from server.main import app

client = TestClient(app)


class _Slide:
    def __init__(self, n, text):
        self.slide_no, self.text, self.notes = n, text, ""


def _seed(**extra) -> None:
    storage._write_yaml(storage.COMPANIES_FILE, [{"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private", **extra}])


def _fields(text: str) -> dict:
    return {f["name"]: (f["usd"] if f["usd"] is not None else f["value"]) for f in portfolio.extract_update_fields(text)}


def test_money_regex_reads_full_digit_amounts():
    fields = {f["name"]: f for f in intake_decks.extract_fields([_Slide(1, "We are raising $5,000,000 on a $25,000,000 post-money valuation")])}
    assert fields["raise"]["usd"] == 5_000_000 and fields["post_money"]["usd"] == 25_000_000
    got = _fields("Cash in the bank: $4,200,000. Net burn was $310,000. ARR of $1,250,000.")
    assert got == {"arr": 1_250_000, "burn": 310_000, "cash": 4_200_000}


def test_update_regexes_pick_the_right_figure():
    assert _fields("Net burn dropped from $450K to $380K this month.") == {"burn": 380_000}
    assert _fields("We hired 5 people this month and are now 42 employees.") == {"headcount": "42"}
    assert _fields("Runway extended by 6 months to 24 months") == {"runway": "24"}
    assert _fields("Our product is used by 2,500 people daily; team of 14 people.") == {"headcount": "14"}
    assert _fields("Burn run-rate is $300K/month.") == {"burn": 300_000}
    assert _fields("Revenue model: SaaS at $49 per seat per month") == {}
    assert _fields("Praised by customers. Pricing starts at $99") == {}
    assert _fields("We have 10,000 employees") == {"headcount": "10000"}
    assert _fields("1,200,000 customers") == {"customers": "1200000"}


def test_cash_burn_is_not_cash_and_arr_stops_at_the_sentence():
    _seed()
    got = _fields("We closed the month with $2.1M ARR. Net cash burn was $210K; runway 18 months.")
    assert got["arr"] == 2_100_000 and got["burn"] == 210_000 and "cash" not in got
    out = portfolio.add_update("acme-ai", text="We closed the month with $2.1M ARR. Net cash burn was $210K.", as_of="2026-08-01")
    assert out["latest_kpi"]["arr_usd"] == 2_100_000 and "cash_usd" not in out["latest_kpi"]
    assert not [a for a in out["alerts"] if a["kind"] == "runway"]
    assert _fields("Operating cash burn of $320K, ending cash of $5.1M")["cash"] == 5_100_000
    assert _fields("We collected $400K in cash from customers. Burn $250K. Cash balance $1.5M.")["cash"] == 1_500_000


def _package(*texts: str) -> dict:
    return {"sections": [{"title": "Round", "blocks": [{"text": t} for t in texts]}]}


def test_comps_post_money_takes_the_valuation_not_the_round_size(monkeypatch):
    _seed()
    for text, expected in (
        ("The last priced round was the May 2026 Series H: $65 billion raised at $965 billion post-money, co-led by X.", 965e9),
        ("It raised $65 billion at a post-money valuation of $965 billion.", 965e9),
        ("raising a $15M Series A at a $75M post-money valuation", 75e6),
    ):
        monkeypatch.setattr(comps, "_latest_memo_package", lambda cid, t=text: (Path("memo.json"), _package(t)))
        facts = comps.private_facts("acme-ai")
        assert facts["post_money_usd"] == expected, text
        assert facts["sources"][0]["section"] == "Round"
    for round_text, expected in (
        ("Series H: $65 billion raised at $965 billion post-money", 965e9),
        ("raised $65 billion at a post-money valuation of $965 billion", 965e9),
        ("Series A at $450,000,000 post-money", 450e6),
        ("Series A at $60M post-money (Jan 2026)", 60e6),
    ):
        _seed(round=round_text)
        monkeypatch.setattr(comps, "_latest_memo_package", lambda cid: (None, None))
        assert comps.private_facts("acme-ai")["post_money_usd"] == expected, round_text


def test_comps_revenue_needs_an_annual_metric(monkeypatch):
    _seed()
    cases = (
        ("Second-quarter 2026 revenue exceeded $11.5 billion", None),
        ("ARR near $24M", 24e6),
        ("revenue lands near $55 to $66 billion", None),
        ("Annual recurring revenue reached $3.2 billion in June", 3.2e9),
        ("Annualized revenue of $5B a month", None),
        ("Monthly revenue run-rate of $9B", None),
    )
    for text, expected in cases:
        monkeypatch.setattr(comps, "_latest_memo_package", lambda cid, t=text: (Path("memo.json"), _package(t)))
        assert comps.private_facts("acme-ai")["revenue_usd"] == expected, text
    monkeypatch.setattr(comps, "_latest_memo_package", lambda cid: (Path("memo.json"), _package("$65 billion raised at $965 billion post-money. Second-quarter 2026 revenue exceeded $11.5 billion.")))
    monkeypatch.setattr(comps.live_quotes, "fetch_quotes", lambda tickers: {"quotes": {}})
    monkeypatch.setattr(comps.quote_workspace, "_fundamentals", lambda symbol: {})
    monkeypatch.setattr(comps, "_latest_annual_revenue", lambda symbol: None)
    body = comps.build_comps("acme-ai", refresh=True)
    assert body["private"]["post_money_usd"] == 965e9 and body["private"]["revenue_usd"] is None and body["private"]["implied_multiple"] is None


def test_numbers_lint_matches_whole_figures_only():
    def unsupported(memo: str, source: str) -> int:
        return numbers_lint.lint_blocks([("T", memo)], [source])["unsupported"]

    assert unsupported("$5M", "15 months") == 1
    assert unsupported("12%", "112%") == 1
    assert unsupported("3x", "13x") == 1
    assert unsupported("$5M", "runway of 5 months") == 1
    assert unsupported("$5M", "arr 5000000.0") == 0
    assert unsupported("$5M", "$5mm") == 0
    assert unsupported("$5M", "$5 million") == 0
    out = numbers_lint.lint_blocks(
        [("Traction", "ARR reached $5M and gross margin is 12% with 3x net retention.")],
        ["Founder update: runway of 15 months, churn 112% cohort, 13x oversubscribed"],
    )
    assert out["checked"] == 3 and out["supported"] == 0


def test_transcripts_keep_numbers_and_clock_times():
    plain = "Interviewer: How many enterprise customers signed last quarter?\n42\nInterviewer: When is the board meeting?\nExpert: We meet at 10:30 every Monday. LTV:CAC is 3:10."
    out = transcripts.normalize_text(plain)
    assert "\n42\n" in out and "10:30" in out and "3:10" in out
    srt = "1\n00:00:01,000 --> 00:00:04,000\nHost: Thanks for joining.\n\n2\n00:00:04,000 --> 00:00:09,000\nExpert: We have 7 customers.\n"
    out = transcripts.normalize_text(srt)
    assert out == "Host: Thanks for joining.\nExpert: We have 7 customers."
    out = transcripts.normalize_text("[00:12] Actually 4 to 5.\n(12:30) Bob: hello.\nSpeaker 1  0:03\nWe started.")
    assert "00:12" not in out and "12:30" not in out and "0:03" not in out and "Bob: hello." in out
    assert transcripts.normalize_text("Expert: See you at 9:15.") == "Expert: See you at 9:15."


def test_transcript_payload_types_are_validated():
    _seed()
    assert client.post("/api/transcripts", json={"title": "t", "text": "Speaker: hi", "participants": 5}).status_code == 400
    assert client.post("/api/transcripts", json={"title": "t", "text": "Speaker: hi", "company_id": ["a"]}).status_code == 400


def test_thesis_terms_match_whole_words_and_exact_stages():
    thesis = dict(thesis_store.DEFAULT_THESIS, sectors=["AI"], stages=["Pre-seed"], geographies=["US"], disqualifiers=["oil"])
    retail = thesis_store.score_company({"name": "Maple Retail", "description": "Point-of-sale for small business retail chains in Canada", "stage": "Seed"}, thesis=thesis)
    assert retail["score"] == 0 and retail["fit"] == "weak"
    assert "Stage outside thesis: seed" in retail["reasons"]
    soil = thesis_store.score_company({"name": "Soilwise", "description": "Soil sensors for farms in Kenya"}, thesis=thesis)
    assert soil["fit"] != "disqualified"
    contact = thesis_store.score_company({"name": "X", "description": "Contact us about our tools"}, thesis=thesis)
    assert "Geography not in thesis" in contact["reasons"]
    us = thesis_store.score_company({"name": "X", "description": "AI tools, US-based"}, thesis=thesis)
    assert "Geography fits: US" in us["reasons"] and "Sector matches thesis: AI" in us["reasons"]
    kw = dict(thesis_store.DEFAULT_THESIS, keywords=["C++", "agent", "health*"])
    hits = thesis_store.score_company({"name": "X", "description": "C++ agents for healthcare"}, thesis=kw)["reasons"][0]
    assert "C++" in hits and "agent" in hits and "health*" in hits


def test_stage_detection_uses_unambiguous_phrases_and_the_latest_stage():
    assert thesis_store._stage_of({}, "sequoia led a round in 2021; now raising its series b") == "series b"
    assert thesis_store._stage_of({}, "series and parallel circuits") is None
    assert thesis_store._stage_of({}, "seed round closed, series a next") == "series a"
    assert thesis_store._stage_of({"stage": "Pre-seed"}, "") == "pre-seed"
    assert thesis_store._stage_of({"round": "Seed / Series A"}, "") == "series a"
    assert thesis_store._stages_in("Seed / Series A", thesis_store.STAGE_ALIASES) == {"seed", "series a"}
    assert thesis_store._stages_in("pre-seed", thesis_store.STAGE_ALIASES) == {"pre-seed"}
