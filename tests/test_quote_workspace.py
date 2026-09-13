from __future__ import annotations

from fastapi.testclient import TestClient

from server import live_quotes, quote_workspace
from server.main import app


SUMMARY_NVDA = {
    "data": {
        "summaryData": {
            "Exchange": {"value": "NASDAQ"},
            "Sector": {"value": "Technology"},
            "Industry": {"value": "Semiconductors"},
            "OneYrTarget": {"value": "$200.00"},
            "PreviousClose": {"value": "$176.10"},
            "Beta": {"value": "1.68"},
            "Yield": {"value": "0.03%"},
        },
        "bidAsk": {"bidPrice": "179.90", "askPrice": "180.10"},
    }
}

FINANCIALS_NVDA = {
    "data": {
        "incomeStatementTable": {
            "headers": {"value2": "2025", "value3": "2024"},
            "rows": [
                {"value1": "Revenue", "value2": "130,497", "value3": "60,922"},
                {"value1": "Operating expenses", "value2": "", "value3": ""},
            ],
        },
        "balanceSheetTable": {"headers": {}, "rows": []},
        "cashFlowTable": {"headers": {}, "rows": []},
        "financialRatiosTable": {"headers": {}, "rows": []},
    }
}

OPTIONS_NVDA = {
    "data": {
        "lastTrade": "$180.00",
        "table": {
            "rows": [
                {
                    "expiryDate": "2026-09-18",
                    "strike": "170",
                    "c_Last": "14.2",
                    "c_Volume": "120",
                    "p_Last": "3.1",
                    "p_Volume": "80",
                },
                {
                    "expiryDate": "2026-09-18",
                    "strike": "180",
                    "c_Last": "8.4",
                    "c_Volume": "900",
                    "p_Last": "7.9",
                    "p_Volume": "400",
                },
                {
                    "expiryDate": "2026-09-18",
                    "strike": "400",
                    "c_Last": "0.1",
                    "c_Volume": "2",
                    "p_Last": "220",
                    "p_Volume": "1",
                },
            ]
        },
    }
}

SCREENER = {
    "data": {
        "table": {
            "rows": [
                {
                    "symbol": "AAA",
                    "name": "Alpha",
                    "lastsale": "$10.00",
                    "netchange": "1.00",
                    "pctchange": "11.11%",
                    "marketCap": "1,000,000",
                    "volume": "1000",
                },
                {
                    "symbol": "BBB",
                    "name": "Beta Co",
                    "lastsale": "$20.00",
                    "netchange": "-2.00",
                    "pctchange": "-9.09%",
                    "marketCap": "9,000,000",
                    "volume": "5000",
                },
                {
                    "symbol": "CCC",
                    "name": "Gamma",
                    "lastsale": "$5.00",
                    "netchange": "0.10",
                    "pctchange": "2.04%",
                    "marketCap": "500,000",
                    "volume": "200",
                },
            ]
        }
    }
}


def test_parse_summary_maps_nasdaq_labels():
    parsed = quote_workspace._parse_summary(SUMMARY_NVDA)
    assert parsed["exchange"] == "NASDAQ"
    assert parsed["one_year_target"] == "$200.00"
    assert parsed["bid"] == "179.90"
    assert parsed["beta"] == "1.68"


def test_parse_financials_keeps_period_headers_and_section_rows():
    parsed = quote_workspace._parse_financials(FINANCIALS_NVDA)
    assert parsed["income"]["headers"] == ["2025", "2024"]
    assert parsed["income"]["rows"][0]["label"] == "Revenue"
    assert parsed["income"]["rows"][0]["values"] == ["130,497", "60,922"]
    assert parsed["income"]["rows"][1]["section"] is True


def test_parse_options_keeps_strikes_near_last_price():
    parsed = quote_workspace._parse_options(OPTIONS_NVDA, 180.0)
    strikes = [row["strike"] for row in parsed["rows"]]
    assert 180.0 in strikes
    assert 170.0 in strikes
    assert 400.0 in strikes
    assert parsed["rows"][0]["strike"] <= parsed["rows"][-1]["strike"]


def test_compact_options_snapshot_uses_workspace_cache(monkeypatch):
    quote_workspace.clear_cache()
    payload = {
        "ticker": "NVDA",
        "summary": {"previous_close": "180"},
        "options": quote_workspace._parse_options(OPTIONS_NVDA, 180.0),
    }
    with quote_workspace.live_quotes._CACHE_LOCK:
        quote_workspace._WORKSPACE_CACHE["NVDA"] = (
            __import__("time").monotonic() + 60,
            payload,
        )

    def boom(*_a, **_k):
        raise AssertionError("should not hit network")

    monkeypatch.setattr(quote_workspace, "fetch_options_chain", boom)
    monkeypatch.setattr(quote_workspace.live_quotes, "fetch_quotes", boom)
    snap = quote_workspace.compact_options_snapshot("nvda", max_rows=2)
    assert snap["ticker"] == "NVDA"
    assert len(snap["rows"]) == 2
    assert snap["implied_vol_available"] is False
    text = quote_workspace.format_options_snapshot_for_prompt(snap)
    assert "Options premiums (NVDA" in text
    assert "call bid/ask/last" in text
    assert "180" in text


def test_format_options_snapshot_empty_rows():
    text = quote_workspace.format_options_snapshot_for_prompt(
        {
            "ticker": "QQQ",
            "last_trade": None,
            "underlying_last": 500.0,
            "rows": [],
        }
    )
    assert "no option chain rows" in text
    assert "QQQ" in text


def test_parse_screener_sorts_gainers_losers_and_large_cap():
    rows = quote_workspace._parse_screener(SCREENER)
    assert [row["ticker"] for row in rows] == ["AAA", "BBB", "CCC"]
    assert rows[0]["change_pct"] == 11.11
    assert rows[1]["market_cap"] == 9_000_000


def test_parse_earnings_estimates_next_print():
    payload = {
        "data": {
            "earningsSurpriseTable": {
                "rows": [
                    {
                        "fiscalQtrEnd": "Jul 2026",
                        "dateReported": "8/26/2026",
                        "eps": 2.22,
                        "consensusForecast": "2.09",
                        "percentageSurprise": "6.22",
                    }
                ]
            }
        }
    }
    parsed = quote_workspace._parse_earnings(payload)
    assert parsed["past"][0]["reported"] == "2026-08-26"
    assert parsed["next_date"] == "2026-11-25"
    assert parsed["next_estimated"] is True


def test_returns_from_points_compute_horizons():
    start = 1_704_067_200  # 2024-01-01-ish UTC
    points = [{"t": start + 86400 * day, "close": 100 + day * 0.1} for day in range(0, 400, 5)]
    # inject a drawdown mid-series
    points[40]["close"] = 80
    returns = quote_workspace._returns_from_points(points)
    assert returns["last"] == points[-1]["close"]
    assert returns["1m"] is not None
    assert returns["ytd"] is not None
    assert returns["1y"] is not None
    assert returns["drawdown_1y"] is not None
    assert returns["drawdown_1y"] < 0


def test_parse_calendar_day_filters_symbols():
    day = __import__("datetime").date(2026, 9, 10)
    rows = quote_workspace._parse_calendar_day(
        {
            "data": {
                "rows": [
                    {
                        "symbol": "NVDA",
                        "name": "NVIDIA",
                        "time": "time-after-hours",
                        "epsForecast": "1.2",
                        "marketCap": "1,000,000",
                    },
                    {"symbol": "!!!", "name": "bad"},
                ]
            }
        },
        day,
    )
    assert len(rows) == 1
    assert rows[0]["ticker"] == "NVDA"
    assert rows[0]["confirmed"] is True
    assert rows[0]["date"] == "2026-09-10"

def test_parse_screener_download_includes_sector_and_volume():
    payload = {
        "data": {
            "rows": [
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA",
                    "lastsale": "$200",
                    "netchange": "1",
                    "pctchange": "0.5%",
                    "volume": "1000000",
                    "marketCap": "1000000000",
                    "sector": "Technology",
                    "industry": "Semiconductors",
                }
            ]
        }
    }
    rows = quote_workspace._parse_screener(payload)
    assert rows[0]["sector"] == "Technology"
    assert rows[0]["volume"] == 1_000_000


def test_fetch_workspace_assembles_nasdaq_parts(monkeypatch):
    quote_workspace.clear_cache()
    calls = []

    def fake_get(url: str) -> dict:
        calls.append(url)
        if "company-profile" in url:
            return {
                "data": {
                    "Symbol": {"value": "NVDA"},
                    "CompanyName": {"value": "NVIDIA Corporation"},
                    "Sector": {"value": "Technology"},
                    "CompanyDescription": {"value": "Designs GPUs."},
                }
            }
        if "/summary" in url:
            return SUMMARY_NVDA
        if "/financials" in url:
            return FINANCIALS_NVDA
        if "targetprice" in url:
            return {
                "data": {
                    "consensusOverview": {
                        "priceTarget": "200",
                        "lowPriceTarget": "140",
                        "highPriceTarget": "250",
                        "buy": 40,
                        "hold": 8,
                        "sell": 1,
                    }
                }
            }
        if "earnings-forecast" in url:
            return {
                "data": {
                    "quarterlyForecast": {
                        "rows": [
                            {
                                "fiscalEnd": "2026-10",
                                "consensusEPSForecast": "1.10",
                                "highEPSForecast": "1.30",
                                "lowEPSForecast": "0.90",
                                "noOfEstimates": "32",
                            }
                        ]
                    }
                }
            }
        if "institutional-holdings" in url:
            return {
                "data": {
                    "ownershipSummary": {"SharesOutstandingPCT": {"value": "66%"}},
                    "holdingsTransactions": {
                        "table": {
                            "rows": [
                                {
                                    "ownerName": "Vanguard",
                                    "sharesHeld": "200M",
                                    "sharesChangePCT": "1.2%",
                                    "marketValue": "$40B",
                                }
                            ]
                        }
                    },
                }
            }
        if "insider-trades" in url:
            return {
                "data": {
                    "numberOfTrades": {
                        "rows": [{"insiderTrade": "Open Market Buys", "months3": "2", "months12": "9"}]
                    },
                    "transactionTable": {"table": {"rows": []}},
                }
            }
        if "option-chain" in url:
            return OPTIONS_NVDA
        if "earnings-surprise" in url:
            return {
                "data": {
                    "earningsSurpriseTable": {
                        "rows": [
                            {
                                "fiscalQtrEnd": "Jul 2026",
                                "dateReported": "8/26/2026",
                                "eps": 2.22,
                                "consensusForecast": "2.09",
                                "percentageSurprise": "6.22",
                            }
                        ]
                    }
                }
            }
        raise AssertionError(url)

    monkeypatch.setattr(quote_workspace, "_get", fake_get)

    first = quote_workspace.fetch_workspace("nvda")
    second = quote_workspace.fetch_workspace("NVDA")

    assert first["ticker"] == "NVDA"
    assert first["source"] == "nasdaq"
    assert first["profile"]["name"] == "NVIDIA Corporation"
    assert first["summary"]["one_year_target"] == "$200.00"
    assert first["financials"]["income"]["rows"][0]["label"] == "Revenue"
    assert first["analysis"]["target"] == 200.0
    assert first["analysis"]["buy"] == 40
    assert first["analysis"]["quarterly"][0]["consensus"] == 1.10
    assert first["holders"]["holders"][0]["owner"] == "Vanguard"
    assert first["insiders"]["summary"][0]["label"] == "Open Market Buys"
    assert first["options"]["rows"]
    assert first["earnings"]["past"][0]["eps"] == 2.22
    assert first["earnings"]["next_date"] == "2026-11-25"
    assert second["profile"]["name"] == first["profile"]["name"]
    assert any("company-profile" in url for url in calls)
    cached_calls = len(calls)
    quote_workspace.fetch_workspace("NVDA")
    assert len(calls) == cached_calls


def test_fetch_screeners_ranks_universe(monkeypatch):
    quote_workspace.clear_cache()
    monkeypatch.setattr(quote_workspace, "_get", lambda url: SCREENER)

    payload = quote_workspace.fetch_screeners()
    assert payload["gainers"][0]["ticker"] == "AAA"
    assert payload["losers"][0]["ticker"] == "BBB"
    assert payload["active"][0]["ticker"] == "BBB"
    assert len(payload["universe"]) == 3


def test_workspace_and_screener_endpoints(monkeypatch):
    quote_workspace.clear_cache()
    live_quotes.clear_cache()

    def fake_get(url: str) -> dict:
        if "screener/stocks" in url:
            return SCREENER
        if "company-profile" in url:
            return {"data": {"Symbol": "NVDA", "CompanyName": "NVIDIA Corporation"}}
        if "/summary" in url:
            return SUMMARY_NVDA
        if "/financials" in url:
            return FINANCIALS_NVDA
        if "targetprice" in url or "earnings-forecast" in url:
            return {"data": {}}
        if "institutional-holdings" in url:
            return {"data": {}}
        if "insider-trades" in url:
            return {"data": {}}
        if "option-chain" in url:
            return OPTIONS_NVDA
        if "earnings-surprise" in url:
            return {"data": {"earningsSurpriseTable": {"rows": []}}}
        raise AssertionError(url)

    monkeypatch.setattr(quote_workspace, "_get", fake_get)
    client = TestClient(app)

    workspace = client.get("/api/quotes/NVDA/workspace")
    screeners = client.get("/api/quotes/screeners")
    bad = client.get("/api/quotes/!!!/workspace")

    assert workspace.status_code == 200
    assert workspace.json()["ticker"] == "NVDA"
    assert screeners.status_code == 200
    assert screeners.json()["gainers"][0]["ticker"] == "AAA"
    assert bad.status_code == 400
