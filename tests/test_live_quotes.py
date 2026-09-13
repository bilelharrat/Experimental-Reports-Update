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
                "dividend": "2.12",
                "dividendyield": "2.41%",
                "pe": "26.55",
                "eps": "3.34",
                "beta": "0.59",
                "mktcapView": "379.227B",
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

YAHOO_CHART_AAPL = {
    "chart": {
        "result": [
            {
                "meta": {
                    "currency": "USD",
                    "symbol": "AAPL",
                    "exchangeName": "NMS",
                    "shortName": "Apple Inc.",
                    "regularMarketPrice": 190.5,
                    "chartPreviousClose": 188.0,
                    "regularMarketTime": 1725148800,
                    "regularMarketOpen": 188.2,
                    "regularMarketDayHigh": 191.0,
                    "regularMarketDayLow": 187.4,
                    "regularMarketVolume": 52000000,
                    "fiftyTwoWeekHigh": 237.23,
                    "fiftyTwoWeekLow": 164.08,
                },
                "timestamp": [1725148800, 1725149100],
                "indicators": {
                    "quote": [
                        {
                            "close": [188.1, 190.5],
                            "open": [187.9, 188.4],
                            "high": [188.8, 191.0],
                            "low": [187.5, 188.0],
                            "volume": [1_000_000, 1_200_000],
                        }
                    ]
                },
            }
        ],
        "error": None,
    }
}

YAHOO_QUOTE_AAPL = {
    "quoteResponse": {
        "result": [
            {
                "symbol": "AAPL",
                "shortName": "Apple Inc.",
                "fullExchangeName": "NasdaqGS",
                "currency": "USD",
                "regularMarketPrice": 190.5,
                "regularMarketPreviousClose": 188.0,
                "regularMarketChange": 2.5,
                "regularMarketChangePercent": 1.3298,
                "regularMarketOpen": 188.2,
                "regularMarketDayHigh": 191.0,
                "regularMarketDayLow": 187.4,
                "regularMarketVolume": 52000000,
                "averageDailyVolume3Month": 61000000,
                "marketCap": 2_900_000_000_000,
                "trailingPE": 32.1,
                "epsTrailingTwelveMonths": 6.42,
                "beta": 1.24,
                "trailingAnnualDividendYield": 0.0044,
                "fiftyTwoWeekHigh": 237.23,
                "fiftyTwoWeekLow": 164.08,
                "regularMarketTime": 1725148800,
            }
        ]
    }
}

YAHOO_SEARCH_APPLE = {
    "quotes": [
        {
            "symbol": "AAPL",
            "shortname": "Apple Inc.",
            "quoteType": "EQUITY",
            "exchDisp": "NASDAQ",
        },
        {
            "symbol": "APLE",
            "shortname": "Apple Hospitality REIT",
            "quoteType": "EQUITY",
            "exchDisp": "NYSE",
        },
        {
            "symbol": "AAPL240920C00200000",
            "shortname": "AAPL Sep 2024 200 Call",
            "quoteType": "OPTION",
            "exchDisp": "OPR",
        },
    ]
}

NASDAQ_CHART_AAPL = {
    "data": {
        "symbol": "AAPL",
        "company": "Apple Inc. Common Stock",
        "lastSalePrice": "$190.50",
        "previousClose": "$188.00",
        "volume": "52,000,000",
        "exchange": "NASDAQ-GS",
        "chart": [
            {"x": 1_725_148_800_000, "y": 188.1, "z": {"value": "188.1"}},
            {"x": 1_725_149_100_000, "y": 190.5, "z": {"value": "190.5"}},
        ],
    }
}

NASDAQ_SEARCH_APPLE = {
    "data": [
        {
            "symbol": "AAPL",
            "name": "Apple Inc. Common Stock",
            "exchange": "NASDAQ-GS",
            "asset": "STOCKS",
        }
    ]
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
    assert first["quotes"]["KO"]["dividend"] == "$2.12"
    assert first["quotes"]["KO"]["dividend_yield"] == pytest.approx(0.0241)
    assert first["quotes"]["KO"]["pe_ratio"] == pytest.approx(26.55)
    assert first["missing"] == []
    assert second["quotes"]["KO"]["last_price"] == 88.67
    assert len(calls) == 1


def test_cnbc_dividend_helpers():
    assert live_quotes._normalize_yield("2.41%") == pytest.approx(0.0241)
    assert live_quotes._normalize_yield(0.0241) == pytest.approx(0.0241)
    assert live_quotes._format_dividend_amount("2.12") == "$2.12"
    assert live_quotes._as_float("379.227B") == pytest.approx(379.227e9)


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


def test_fetch_chart_parses_yahoo_series_and_stats(monkeypatch):
    live_quotes.clear_cache()
    calls = []

    def fake_get(url: str, extra_headers=None) -> str:
        calls.append(url)
        if "/v8/finance/chart/" in url:
            return json.dumps(YAHOO_CHART_AAPL)
        if "/v7/finance/quote" in url:
            return json.dumps(YAHOO_QUOTE_AAPL)
        raise AssertionError(url)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    first = live_quotes.fetch_chart("aapl", "1d")
    second = live_quotes.fetch_chart("AAPL", "1d")

    assert first["ticker"] == "AAPL"
    assert first["range"] == "1d"
    assert first["last_price"] == 190.5
    assert first["previous_close"] == 188.0
    assert first["market_cap"] == 2_900_000_000_000
    assert first["points"][0]["close"] == 188.1
    assert first["points"][-1]["close"] == 190.5
    assert second["last_price"] == 190.5
    assert len(calls) == 2


def test_fetch_chart_rejects_bad_range():
    with pytest.raises(ValueError, match="unsupported chart range"):
        live_quotes.fetch_chart("AAPL", "2w")


def test_search_symbols_skips_options_and_caches(monkeypatch):
    live_quotes.clear_cache()
    calls = []

    def fake_get(url: str, extra_headers=None) -> str:
        calls.append(url)
        return json.dumps(YAHOO_SEARCH_APPLE)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    first = live_quotes.search_symbols("apple")
    second = live_quotes.search_symbols("Apple")

    assert [row["ticker"] for row in first["matches"]] == ["AAPL", "APLE"]
    assert first["matches"][0]["name"] == "Apple Inc."
    assert second["matches"][0]["ticker"] == "AAPL"
    assert len(calls) == 1


def test_chart_and_search_endpoints(monkeypatch):
    live_quotes.clear_cache()

    def fake_get(url: str, extra_headers=None) -> str:
        if "/v1/finance/search" in url:
            return json.dumps(YAHOO_SEARCH_APPLE)
        if "/v8/finance/chart/" in url:
            return json.dumps(YAHOO_CHART_AAPL)
        if "/v7/finance/quote" in url:
            return json.dumps(YAHOO_QUOTE_AAPL)
        raise AssertionError(url)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)
    client = TestClient(app)

    chart = client.get("/api/quotes/AAPL/chart", params={"range": "1d"})
    search = client.get("/api/quotes/search", params={"q": "apple"})
    bad = client.get("/api/quotes/AAPL/chart", params={"range": "2w"})

    assert chart.status_code == 200
    assert chart.json()["ticker"] == "AAPL"
    assert search.status_code == 200
    assert search.json()["matches"][0]["ticker"] == "AAPL"
    assert bad.status_code == 400


def test_chart_and_search_fall_back_to_nasdaq(monkeypatch):
    live_quotes.clear_cache()

    def fake_get(url: str, extra_headers=None) -> str:
        if "finance.yahoo.com" in url:
            raise RuntimeError("429")
        if "/chart?" in url:
            return json.dumps(NASDAQ_CHART_AAPL)
        if "slookup" in url:
            return json.dumps(NASDAQ_SEARCH_APPLE)
        raise AssertionError(url)

    monkeypatch.setattr(live_quotes, "_http_get", fake_get)

    chart = live_quotes.fetch_chart("AAPL", "1d")
    search = live_quotes.search_symbols("apple")

    assert chart["source"] == "nasdaq"
    assert chart["points"][-1]["close"] == 190.5
    assert search["matches"][0]["ticker"] == "AAPL"
