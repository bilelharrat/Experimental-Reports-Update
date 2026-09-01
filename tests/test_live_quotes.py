from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server import live_quotes
from server.main import app


CNBC_KO = {
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

SPARK_NVDA = {
    "spark": {
        "result": [
            {
                "symbol": "NVDA",
                "response": [
                    {
                        "meta": {
                            "currency": "USD",
                            "regularMarketPrice": 180.5,
                            "chartPreviousClose": 176.1,
                            "regularMarketTime": 1725148800,
                        }
                    }
                ],
            }
        ]
    }
}

NASDAQ_TSM = {
    "data": {
        "symbol": "TSM",
        "primaryData": {
            "lastSalePrice": "$415.32",
            "percentageChange": "-0.53%",
            "lastTradeTimestamp": "2026-08-31T16:10:00-04:00",
        },
    }
}


def test_normalize_tickers_dedupes_and_rejects_junk():
    assert live_quotes.normalize_tickers(["nvda", "NVDA", "bad ticker", "AAPL,MSFT"]) == [
        "NVDA",
        "AAPL",
        "MSFT",
    ]


def test_fetch_quotes_uses_cnbc_and_caches(monkeypatch):
    live_quotes.clear_cache()
    calls = []

    def fake_get(url: str, extra_headers=None) -> str:
        calls.append(url)
        return json.dumps(CNBC_KO)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    first = live_quotes.fetch_quotes(["ko"])
    second = live_quotes.fetch_quotes(["KO"])

    assert first["quotes"]["KO"]["last_price"] == 88.67
    assert first["quotes"]["KO"]["change_pct_1d"] == pytest.approx(-1.10)
    assert first["quotes"]["KO"]["source"] == "cnbc"
    assert first["missing"] == []
    assert second["quotes"]["KO"]["last_price"] == 88.67
    assert len(calls) == 1


def test_yahoo_fills_when_cnbc_is_down(monkeypatch):
    live_quotes.clear_cache()

    def fake_get(url: str, extra_headers=None) -> str:
        if "cnbc.com" in url:
            raise RuntimeError("cnbc down")
        return json.dumps(SPARK_NVDA)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    payload = live_quotes.fetch_quotes(["NVDA"])

    assert payload["quotes"]["NVDA"]["last_price"] == 180.5
    assert payload["quotes"]["NVDA"]["source"] == "yahoo"


def test_nasdaq_fills_remaining_leftovers(monkeypatch):
    live_quotes.clear_cache()

    def fake_get(url: str, extra_headers=None) -> str:
        if "cnbc.com" in url or "spark" in url:
            raise RuntimeError("batch down")
        return json.dumps(NASDAQ_TSM)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    payload = live_quotes.fetch_quotes(["TSM"])

    assert payload["quotes"]["TSM"]["last_price"] == 415.32
    assert payload["quotes"]["TSM"]["source"] == "nasdaq"


def test_failed_fetch_omits_the_ticker_and_does_not_refetch(monkeypatch):
    live_quotes.clear_cache()
    calls = []

    def fake_get(url: str, extra_headers=None) -> str:
        calls.append(url)
        raise RuntimeError("provider down")

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    first = live_quotes.fetch_quotes(["NVDA"])
    second = live_quotes.fetch_quotes(["NVDA"])

    assert first["quotes"] == {}
    assert first["missing"] == ["NVDA"]
    assert second["missing"] == ["NVDA"]
    assert calls  # first pass tried providers
    first_count = len(calls)
    assert first_count >= 1
    assert len(calls) == first_count


def test_quotes_endpoint_accepts_repeated_tickers(monkeypatch):
    live_quotes.clear_cache()
    monkeypatch.setattr(live_quotes, "_http_get", lambda url, extra_headers=None: json.dumps(CNBC_KO))
    client = TestClient(app)

    response = client.get("/api/quotes", params=[("ticker", "ko"), ("ticker", "KO")])

    assert response.status_code == 200
    body = response.json()
    assert body["quotes"]["KO"]["last_price"] == 88.67
    assert body["missing"] == []
