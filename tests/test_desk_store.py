"""Market-desk durable state: prefs blob, alert engine, signal ledger, brief."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import alert_engine, desk_store, live_quotes, market_brief
from server.main import app


@pytest.fixture()
def client():
    return TestClient(app)


# --- Prefs blob --------------------------------------------------------------


def test_prefs_roundtrip(client):
    empty = client.get("/api/desk/prefs")
    assert empty.status_code == 200
    assert empty.json() == {"updated_at": None, "data": {}}

    payload = {
        "bsh.marketPinnedTickers": ["NVDA", "SPY"],
        "bsh.marketAlertRules": [
            {"id": "r1", "ticker": "NVDA", "kind": "price", "threshold": 100, "direction": "above"}
        ],
    }
    saved = client.put("/api/desk/prefs", json={"data": payload})
    assert saved.status_code == 200
    assert saved.json()["data"] == payload
    assert saved.json()["updated_at"]

    fetched = client.get("/api/desk/prefs").json()
    assert fetched["data"]["bsh.marketPinnedTickers"] == ["NVDA", "SPY"]
    assert desk_store.alert_rules()[0]["ticker"] == "NVDA"


def test_prefs_rejects_oversized_blob(client):
    huge = {"blob": "x" * (desk_store.MAX_PREFS_BYTES + 100)}
    response = client.put("/api/desk/prefs", json={"data": huge})
    assert response.status_code == 400


# --- Alert engine ------------------------------------------------------------


def _quotes(**by_ticker: dict) -> dict[str, dict]:
    return {ticker.upper(): quote for ticker, quote in by_ticker.items()}


def test_evaluate_rules_price_and_pct():
    rules = [
        {"id": "p1", "ticker": "NVDA", "kind": "price", "threshold": 150, "direction": "above"},
        {"id": "p2", "ticker": "NVDA", "kind": "price", "threshold": 100, "direction": "below"},
        {"id": "m1", "ticker": "TSM", "kind": "pct", "threshold": 3},
        {"id": "off", "ticker": "TSM", "kind": "pct", "threshold": 1, "enabled": False},
        {"id": "vol", "ticker": "TSM", "kind": "volume", "threshold": 2},
    ]
    quotes = _quotes(
        NVDA={"last_price": 180.5, "change_pct_1d": 1.0},
        TSM={"last_price": 140.0, "change_pct_1d": -3.1},
    )
    fired = alert_engine.evaluate_rules(rules, quotes)
    ids = {row["rule_id"] for row in fired}
    assert ids == {"p1", "m1"}
    move = next(row for row in fired if row["rule_id"] == "m1")
    assert "-3.10%" in move["message"]


def test_run_check_records_and_dedupes(monkeypatch):
    desk_store.save_prefs(
        {
            "bsh.marketAlertRules": [
                {"id": "r1", "ticker": "NVDA", "kind": "price", "threshold": 100, "direction": "above"}
            ]
        }
    )
    monkeypatch.setattr(
        live_quotes,
        "fetch_quotes",
        lambda tickers: {
            "generated_at": "2026-09-09T00:00:00Z",
            "quotes": {"NVDA": {"last_price": 180.5, "change_pct_1d": 2.0}},
            "missing": [],
        },
    )
    first = alert_engine.run_check()
    assert len(first["fired"]) == 1
    # Same rule, same day: history unchanged.
    second = alert_engine.run_check()
    assert second["fired"] == []
    events = desk_store.list_alert_events()
    assert len(events) == 1
    assert events[0]["ticker"] == "NVDA"


def test_alert_events_endpoints(client):
    posted = client.post(
        "/api/alerts/events",
        json={"events": [{"ticker": "SPY", "message": "gap", "dedupe_key": "browser:spy:1"}]},
    )
    assert posted.status_code == 200
    assert len(posted.json()["recorded"]) == 1
    # Duplicate dedupe_key is ignored.
    again = client.post(
        "/api/alerts/events",
        json={"events": [{"ticker": "SPY", "message": "gap", "dedupe_key": "browser:spy:1"}]},
    )
    assert again.json()["recorded"] == []
    listed = client.get("/api/alerts/events").json()["events"]
    assert [row["ticker"] for row in listed] == ["SPY"]


# --- Signal ledger -----------------------------------------------------------


def test_signal_ledger_roundtrip_and_scoring(client, monkeypatch):
    monkeypatch.setattr(
        live_quotes,
        "fetch_quotes",
        lambda tickers: {
            "quotes": {"NVDA": {"last_price": 110.0}},
            "generated_at": "x",
            "missing": [],
        },
    )
    created = client.post(
        "/api/signals/ledger",
        json={"ticker": "nvda", "direction": "bearish", "label": "AI capex rolling over"},
    )
    assert created.status_code == 200
    entry = created.json()["entry"]
    assert entry["ticker"] == "NVDA"
    assert entry["price_at_signal"] == 110.0

    # Same label same day: no duplicate row.
    dup = client.post(
        "/api/signals/ledger",
        json={"ticker": "NVDA", "direction": "bearish", "label": "AI capex rolling over"},
    )
    assert dup.json()["entry"]["id"] == entry["id"]

    monkeypatch.setattr(
        live_quotes,
        "fetch_quotes",
        lambda tickers: {
            "quotes": {"NVDA": {"last_price": 99.0}},
            "generated_at": "x",
            "missing": [],
        },
    )
    scored = client.get("/api/signals/ledger").json()["entries"]
    assert len(scored) == 1
    assert scored[0]["return_since_pct"] == pytest.approx(-10.0)
    # Bearish call on a -10% move scores positive.
    assert scored[0]["score_pct"] == pytest.approx(10.0)

    gone = client.delete(f"/api/signals/ledger/{entry['id']}")
    assert gone.status_code == 200
    assert client.get("/api/signals/ledger").json()["entries"] == []
    assert client.delete("/api/signals/ledger/nope").status_code == 404


def test_record_signal_requires_ticker():
    with pytest.raises(ValueError):
        desk_store.record_signal({"label": "no ticker"})


# --- Morning brief -----------------------------------------------------------


def test_brief_build_archive_and_fetch(client, monkeypatch):
    desk_store.save_prefs({"bsh.marketPinnedTickers": ["NVDA"]})
    desk_store.record_alert_events(
        [{"ticker": "NVDA", "message": "moved", "dedupe_key": "k1"}]
    )

    def fake_quotes(tickers):
        quotes = {}
        for ticker in tickers:
            quotes[ticker] = {
                "last_price": 100.0,
                "change_pct_1d": 2.0 if ticker == "NVDA" else -1.0,
                "currency": "USD",
                "as_of": "2026-09-09T13:30:00Z",
            }
        return {"generated_at": "x", "quotes": quotes, "missing": []}

    monkeypatch.setattr(live_quotes, "fetch_quotes", fake_quotes)
    monkeypatch.setattr(market_brief, "_calendar_events", lambda tickers: [
        {"ticker": "NVDA", "date": "2026-09-10", "kind": "earnings"}
    ])

    built = client.post("/api/market-brief/run")
    assert built.status_code == 200
    brief = built.json()
    assert brief["indices"][0]["ticker"] == "SPY"
    assert brief["watchlist"] == [
        {
            "ticker": "NVDA",
            "last_price": 100.0,
            "change_pct_1d": 2.0,
            "currency": "USD",
            "as_of": "2026-09-09T13:30:00Z",
        }
    ]
    assert brief["movers"]["gainers"][0]["ticker"] == "NVDA"
    assert brief["calendar"][0]["kind"] == "earnings"
    assert brief["alerts_last_day"][0]["ticker"] == "NVDA"

    archive = client.get("/api/market-brief/archive").json()
    assert archive["dates"] == [brief["date"]]
    latest = client.get("/api/market-brief").json()
    assert latest["date"] == brief["date"]
    by_date = client.get("/api/market-brief", params={"date": brief["date"]}).json()
    assert by_date["generated_at"] == brief["generated_at"]
    assert client.get("/api/market-brief", params={"date": "not-a-date"}).status_code == 400


def test_brief_404_when_empty(client):
    assert client.get("/api/market-brief").status_code == 404
    assert client.get("/api/market-brief/archive").json()["dates"] == []


def _archive_minimal_brief(monkeypatch):
    monkeypatch.setattr(
        live_quotes,
        "fetch_quotes",
        lambda tickers: {
            "generated_at": "x",
            "quotes": {t: {"last_price": 100.0, "change_pct_1d": -0.5} for t in tickers},
            "missing": [],
        },
    )
    monkeypatch.setattr(market_brief, "_calendar_events", lambda tickers: [])
    return market_brief.build_brief()


def test_brief_note_written_and_persisted(client, monkeypatch):
    brief = _archive_minimal_brief(monkeypatch)

    captured = {}

    def fake_structured(**kwargs):
        captured.update(kwargs)
        return (
            {
                "headline_en": "Risk-off drift; defensives bid",
                "headline_zh": "避险情绪主导，防御板块走强",
                "bullets_en": ["SPY -0.5% with breadth soft", "GLD bid", "Watch CPI"],
                "bullets_zh": ["SPY 下跌 0.5%，广度偏弱", "黄金走强", "关注 CPI"],
            },
            {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None},
            None,
        )

    monkeypatch.setattr(market_brief.ai_engine, "structured", fake_structured)

    response = client.post("/api/market-brief/note", json={})
    assert response.status_code == 200
    note = response.json()["note"]
    assert note["headline_en"].startswith("Risk-off")
    assert len(note["bullets_zh"]) == 3
    # Prompt was built from the frozen payload, numbers included.
    assert "SPY -0.5%" in captured["user_prompt"]

    # Note is persisted into the archived JSON.
    reloaded = client.get("/api/market-brief", params={"date": brief["date"]}).json()
    assert reloaded["note"]["headline_zh"] == "避险情绪主导，防御板块走强"
    # The engine that wrote the note is recorded, so a fallback stays visible.
    assert reloaded["note"]["engine"] == "gemini"
    assert reloaded["note"]["engine_fallback_reason"] is None

    # Rebuilding the brief drops the stale note.
    rebuilt = client.post("/api/market-brief/run").json()
    assert "note" not in rebuilt


def test_brief_long_note_uses_sections(client, monkeypatch):
    _archive_minimal_brief(monkeypatch)

    captured = {}

    def fake_structured(**kwargs):
        captured.update(kwargs)
        return (
            {
                "headline_en": "Mixed tape, defensives lead",
                "headline_zh": "盘面分化，防御领涨",
                "sections_en": [
                    {"title": "Regime", "body": "Risk appetite is soft across the board."},
                    {"title": "Watchlist", "body": "Losers cluster in rate-sensitive names."},
                    {"title": "Week ahead", "body": "Calendar is quiet; watch breadth."},
                ],
                "sections_zh": [
                    {"title": "市场基调", "body": "风险偏好整体偏弱。"},
                    {"title": "观察名单", "body": "利率敏感板块领跌。"},
                    {"title": "本周展望", "body": "日历清淡，关注广度。"},
                ],
            },
            {"engine": "gemini", "model": "gemini-3.8-flash", "fallback_reason": None},
            None,
        )

    monkeypatch.setattr(market_brief.ai_engine, "structured", fake_structured)

    response = client.post("/api/market-brief/note", json={"length": "long"})
    assert response.status_code == 200
    note = response.json()["note"]
    assert note["length"] == "long"
    assert [row["title"] for row in note["sections_en"]] == ["Regime", "Watchlist", "Week ahead"]
    assert "bullets_en" not in note
    # Long variant got the long prompt and schema.
    assert captured["name"] == "morning_brief_note_long"
    assert "600-1000 words" in captured["system_prompt"]

    # Persisted; and an invalid length is rejected.
    assert client.get("/api/market-brief").json()["note"]["length"] == "long"
    assert client.post("/api/market-brief/note", json={"length": "epic"}).status_code == 400


def test_brief_note_requires_archive_and_surfaces_engine_errors(client, monkeypatch):
    # No archived brief yet.
    assert client.post("/api/market-brief/note", json={}).status_code == 400

    _archive_minimal_brief(monkeypatch)
    monkeypatch.setattr(
        market_brief.ai_engine,
        "structured",
        lambda **kwargs: (None, {"engine": "gemini"}, "gemini HTTP 503 — unavailable"),
    )
    failed = client.post("/api/market-brief/note", json={})
    assert failed.status_code == 502
    assert "gemini HTTP 503" in failed.json()["detail"]
    # Failure leaves the archived numbers untouched.
    assert "note" not in client.get("/api/market-brief").json()


# --- Quote diagnostics -------------------------------------------------------


def test_quotes_diagnostics_reports_cache_state(client, monkeypatch):
    import json as jsonlib

    live_quotes.clear_cache()
    cnbc = {
        "FormattedQuoteResult": {
            "FormattedQuote": [
                {
                    "symbol": "KO",
                    "code": 0,
                    "last": "88.67",
                    "change_pct": "-1.10%",
                    "last_time": "2026-08-31T16:10:00.000-0400",
                }
            ]
        }
    }
    monkeypatch.setattr(
        live_quotes, "_http_get", lambda url, extra_headers=None: jsonlib.dumps(cnbc)
    )
    client.get("/api/quotes", params={"ticker": "KO"})
    stats = client.get("/api/diagnostics/quotes").json()
    tickers = [row["ticker"] for row in stats["cached_quotes"]]
    assert "KO" in tickers
    entry = next(row for row in stats["cached_quotes"] if row["ticker"] == "KO")
    assert entry["age_seconds"] >= 0
    assert stats["quote_ttl_seconds"] == live_quotes.QUOTE_TTL_SECONDS
    live_quotes.clear_cache()
