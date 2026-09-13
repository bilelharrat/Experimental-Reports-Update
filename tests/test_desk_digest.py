from __future__ import annotations

from server import desk_digest, desk_store


def test_what_changed_and_screener_shape(monkeypatch):
    monkeypatch.setattr(desk_store, "pinned_tickers", lambda: ["KO", "SPY"])
    monkeypatch.setattr(
        "server.live_quotes.fetch_quotes",
        lambda tickers: {
            "quotes": {
                "KO": {"name": "Coca-Cola", "change_pct_1d": -2.1},
                "SPY": {"name": "S&P 500", "change_pct_1d": 0.2},
            }
        },
    )
    monkeypatch.setattr(
        "server.live_quotes.fetch_news",
        lambda tickers, limit=40: {
            "items": [
                {
                    "id": "n1",
                    "title": "KO launches new product",
                    "ticker": "KO",
                    "published_at": "2099-01-01T00:00:00Z",
                }
            ]
        },
    )
    monkeypatch.setattr("server.storage.list_reports", lambda: [])
    monkeypatch.setattr("server.storage.list_companies", lambda: [])

    digest = desk_digest.build_what_changed(limit=10)
    assert digest["items"]
    kinds = {row["kind"] for row in digest["items"]}
    assert "mover" in kinds or "news" in kinds

    screener = desk_digest.build_desk_screener(limit=10)
    assert "items" in screener
    assert isinstance(screener["items"], list)
