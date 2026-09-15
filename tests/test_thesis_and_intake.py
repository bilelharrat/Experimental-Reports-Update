"""Thesis scoring, cap-model math, deck intake and comps — all explainable, nothing invented."""
from __future__ import annotations

import io

from starlette.testclient import TestClient

from server import cap_model, comps, intake_decks, storage, thesis_store
from server.main import app

client = TestClient(app)


def _seed(**extra) -> None:
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private",
          "industry": "AI infrastructure", "description": "Vector database for agents, Series A, Berlin", **extra}],
    )


def test_thesis_round_trips_and_scores_explainably():
    res = client.put("/api/thesis", json={
        "sectors": ["AI infrastructure", "developer tools"],
        "stages": ["Seed", "Series A"],
        "geographies": ["Berlin", "London"],
        "keywords": ["agents", "vector"],
        "disqualifiers": ["crypto"],
        "must_be_true": ["Founders have shipped infra before"],
    })
    assert res.status_code == 200
    thesis = res.json()
    assert thesis["sectors"] == ["AI infrastructure", "developer tools"]
    assert thesis["disqualifiers"] == ["crypto"]

    _seed()
    scored = client.post("/api/thesis/score", json={"company_id": "acme-ai"}).json()
    assert scored["fit"] == "strong"
    assert scored["score"] >= 90
    assert any("Sector matches" in r for r in scored["reasons"])
    assert any("Stage fits: series a" in r for r in scored["reasons"])
    assert scored["open_questions"] == ["Founders have shipped infra before"]

    killed = client.post("/api/thesis/score", json={"name": "CoinThing", "description": "crypto exchange"}).json()
    assert killed["fit"] == "disqualified" and killed["score"] == 0 and killed["disqualified_by"] == ["crypto"]


def test_empty_thesis_reports_unconfigured_not_a_score():
    thesis_store.save_thesis({"sectors": [], "stages": [], "geographies": [], "keywords": [], "disqualifiers": []})
    result = thesis_store.score_company({"name": "X", "description": "anything"})
    assert result["score"] is None and result["fit"] == "unconfigured"


def test_rollup_rows_carry_thesis_fit():
    thesis_store.save_thesis({"sectors": ["AI infrastructure"], "stages": [], "keywords": []})
    _seed()
    from server import tracking_dashboard

    row = tracking_dashboard.build_rollup(["acme-ai"])["companies"][0]
    assert row["thesis_fit"]["fit"] == "strong"


def test_cap_model_math_and_waterfall():
    _seed()
    res = client.put("/api/companies/acme-ai/cap-model", json={
        "pre_money_musd": 40, "new_money_musd": 10, "our_check_musd": 5,
        "option_pool_pct_post": 10, "exit_values_musd": [50, 200],
    })
    assert res.status_code == 200
    result = res.json()["result"]
    assert result["ready"] is True
    assert result["post_money_musd"] == 50
    assert result["round_ownership_pct"] == 20
    assert result["our_ownership_pct"] == 10
    assert result["existing_ownership_pct_after"] == 70
    low, high = result["waterfall"]
    # $50M exit: 1x preference ($5M) beats 10% as-converted ($5M) → equal, treated as converted.
    assert low["our_proceeds_musd"] == 5
    assert high["our_proceeds_musd"] == 20 and high["multiple_on_check"] == 4
    assert client.get("/api/companies/acme-ai/cap-model").json()["inputs"]["pre_money_musd"] == 40


def test_cap_model_without_inputs_is_not_ready():
    assert cap_model.compute({})["ready"] is False


class _Slide:
    def __init__(self, n, text):
        self.slide_no, self.text, self.notes = n, text, ""


def test_deck_fields_extract_with_page_refs():
    slides = [
        _Slide(1, "Acme AI\nVector database for agents"),
        _Slide(4, "Traction: ARR $2.4M growing 3x. 120 customers. 18 employees."),
        _Slide(9, "The round: raising $12M Series A at $60M post-money. Runway 24 months after close."),
    ]
    fields = {f["name"]: f for f in intake_decks.extract_fields(slides)}
    assert fields["round"]["value"] == "Series A" and fields["round"]["page"] == 9
    assert fields["raise"]["usd"] == 12_000_000
    assert fields["post_money"]["usd"] == 60_000_000
    assert fields["arr"]["usd"] == 2_400_000 and fields["arr"]["page"] == 4
    assert fields["customers"]["value"] == "120"
    assert fields["headcount"]["value"] == "18"
    assert fields["runway"]["value"] == "24"
    assert "raising $12M" in fields["raise"]["excerpt"]


def test_intake_endpoint_creates_company_and_files_deck(monkeypatch):
    storage._write_yaml(storage.COMPANIES_FILE, [])
    thesis_store.save_thesis({"sectors": ["AI"], "stages": ["Series A"], "keywords": ["agents"]})
    monkeypatch.setattr(
        intake_decks.deck_summary, "extract_slides",
        lambda path, kind, **kw: [_Slide(1, "Acme AI\nAgents for AI teams"), _Slide(3, "Raising $8M Series A")],
    )
    res = client.post(
        "/api/intake/decks",
        files={"file": ("acme_deck.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["company"]["name"] == "Acme AI"
    assert body["file"]["filename"] == "acme_deck.pdf"
    names = {f["name"] for f in body["extraction"]["fields"]}
    assert {"round", "raise"} <= names
    assert body["thesis"]["fit"] in {"strong", "partial"}
    assert storage.get_company(body["company"]["id"]) is not None


def test_comps_uses_only_stated_private_facts(monkeypatch):
    _seed(round="Series A at $60M post-money (Jan 2026)")
    monkeypatch.setattr(comps.live_quotes, "fetch_quotes", lambda tickers: {"quotes": {
        t: {"name": t, "last_price": 100.0, "change_pct_1d": 1.0, "market_cap": 50_000_000_000} for t in tickers}})
    monkeypatch.setattr(comps.quote_workspace, "_fundamentals", lambda symbol: {"revenue_growth": 0.25, "gross_margin": 0.7})
    monkeypatch.setattr(comps, "_latest_annual_revenue", lambda symbol: 5_000_000_000)
    monkeypatch.setattr(comps, "_latest_memo_package", lambda cid: (None, None))

    res = client.get("/api/companies/acme-ai/comps?refresh=true")
    assert res.status_code == 200
    body = res.json()
    assert body["peer_median_price_to_sales"] == 10.0
    assert body["private"]["post_money_usd"] == 60_000_000
    # No revenue on record → no implied multiple, no invented number.
    assert body["private"]["revenue_usd"] is None
    assert body["private"]["implied_multiple"] is None

    saved = client.put("/api/companies/acme-ai/comps/peers", json={"tickers": ["nvda", "AMD", "nvda"]}).json()
    assert saved["tickers"] == ["NVDA", "AMD"]


def test_intake_rejects_unsupported_decks_without_creating_a_company(monkeypatch):
    storage._write_yaml(storage.COMPANIES_FILE, [])
    monkeypatch.setattr(intake_decks.deck_summary, "extract_slides", lambda path, kind, **kw: [])

    docx = client.post(
        "/api/intake/decks",
        files={"file": ("pitch.docx", io.BytesIO(b"PK\x03\x04 fake"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert docx.status_code == 400, docx.text

    empty = client.post(
        "/api/intake/decks",
        files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
    )
    assert empty.status_code == 400, empty.text

    assert storage.list_companies() == []
