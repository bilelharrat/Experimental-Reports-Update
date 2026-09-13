"""Live Yahoo news tape for the News tab."""
from __future__ import annotations

from server import live_quotes


def test_parse_yahoo_news_normalizes_rows():
    payload = {
        "news": [
            {
                "uuid": "abc",
                "title": "AMD jumps after AI chip deal",
                "publisher": "Reuters",
                "link": "https://example.com/a",
                "providerPublishTime": 1_700_000_000,
                "relatedTickers": ["AMD", "NVDA"],
            },
            {"title": "", "link": "https://example.com/b"},
        ]
    }
    rows = live_quotes._parse_yahoo_news(payload, fallback_ticker="SPY")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AMD"
    assert rows[0]["source"] == "Reuters"
    assert rows[0]["published_at"].endswith("Z")
    assert rows[0]["kind"] == "live_news"


def test_fetch_news_uses_cache(monkeypatch):
    calls: list[str] = []

    def fake_get_json(url, extra_headers=None):
        calls.append(url)
        return {
            "news": [
                {
                    "uuid": f"id-{len(calls)}",
                    "title": f"Story {len(calls)}",
                    "publisher": "Wire",
                    "link": f"https://example.com/{len(calls)}",
                    "providerPublishTime": 1_700_000_000 + len(calls),
                    "relatedTickers": ["SPY"],
                }
            ]
        }

    monkeypatch.setattr(live_quotes, "_http_get_json", fake_get_json)
    live_quotes.clear_cache()
    first = live_quotes.fetch_news(["SPY"], limit=10)
    first_calls = len(calls)
    assert first_calls >= 1
    second = live_quotes.fetch_news(["SPY"], limit=10)
    assert first["items"]
    assert second["items"][0]["id"] in {row["id"] for row in first["items"]}
    assert len(calls) == first_calls, "second call must hit cache"
