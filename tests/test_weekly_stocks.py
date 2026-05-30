from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from server import job_progress, weekly_stocks
from server.main import app


@pytest.fixture
def tmp_weekly(monkeypatch, tmp_path):
    monkeypatch.setattr(weekly_stocks, "WEEKLY_DIR", tmp_path)
    monkeypatch.setattr(weekly_stocks, "SUMMARY_PATH", tmp_path / "summary.json")
    monkeypatch.setattr(
        weekly_stocks,
        "PROGRESS_PATH",
        tmp_path / "weekly_summary.progress.jsonl",
    )
    monkeypatch.setattr(
        weekly_stocks,
        "DRAFT_PATH",
        tmp_path / "weekly_summary.draft.json",
    )
    yield tmp_path
    for t in threading.enumerate():
        if t.name == "weekly-stocks" and t.is_alive():
            t.join(timeout=5.0)
            assert not t.is_alive()


@pytest.fixture
def client():
    return TestClient(app)


def _sample_summary() -> dict:
    return {
        "week_label": "Test week",
        "week_label_en": "Test week",
        "week_label_zh": "测试周",
        "as_of": "2026-05-23T12:00:00Z",
        "market_pulse": "Momentum is concentrated in AI infrastructure.",
        "market_pulse_en": "Momentum is concentrated in AI infrastructure.",
        "market_pulse_zh": "动量集中在AI基础设施。",
        "benchmark_context": "Leaders beat the S&P 500 this week.",
        "benchmark_context_en": "Leaders beat the S&P 500 this week.",
        "benchmark_context_zh": "领涨股本周跑赢标普500。",
        "methodology": "Blended weekly price action, volume, catalysts, and durability.",
        "methodology_en": "Blended weekly price action, volume, catalysts, and durability.",
        "methodology_zh": "综合周内走势、成交量、催化剂和持续性。",
        "summary_cards": [
            {
                "label": "Top move",
                "label_en": "Top move",
                "label_zh": "最大涨幅",
                "value": "+24%",
                "note": "Leader",
                "note_en": "Leader",
                "note_zh": "领涨",
            },
            {
                "label": "Avg heat",
                "label_en": "Avg heat",
                "label_zh": "平均热度",
                "value": "88",
                "note": "Strong",
                "note_en": "Strong",
                "note_zh": "强势",
            },
            {
                "label": "Sectors",
                "label_en": "Sectors",
                "label_zh": "板块",
                "value": "3",
                "note": "Mixed",
                "note_en": "Mixed",
                "note_zh": "分散",
            },
            {
                "label": "Watch",
                "label_en": "Watch",
                "label_zh": "观察",
                "value": "2",
                "note": "Near misses",
                "note_en": "Near misses",
                "note_zh": "接近入选",
            },
        ],
        "sector_mix": [
            {
                "sector": "Technology",
                "sector_en": "Technology",
                "sector_zh": "科技",
                "count": 1,
            }
        ],
        "stocks": [
            {
                "rank": 1,
                "ticker": "TEST",
                "name": "Test Corp",
                "exchange": "NASDAQ",
                "sector": "Technology",
                "sector_en": "Technology",
                "sector_zh": "科技",
                "score": 94,
                "weekly_change_pct": 24.2,
                "relative_volume": 2.4,
                "relative_strength_pct": 18.1,
                "market_cap_usd": 12_000_000_000,
                "why_awesome": "It broke out on verified catalyst strength.",
                "why_awesome_en": "It broke out on verified catalyst strength.",
                "why_awesome_zh": "它在已验证催化剂推动下完成突破。",
                "setup": "Momentum setup with institutional volume.",
                "setup_en": "Momentum setup with institutional volume.",
                "setup_zh": "机构成交量支撑的动量机会。",
                "catalyst": "Fresh guidance raise.",
                "catalyst_en": "Fresh guidance raise.",
                "catalyst_zh": "最新上调指引。",
                "risk": "Move fades if volume normalizes.",
                "risk_en": "Move fades if volume normalizes.",
                "risk_zh": "若成交量回落，行情可能降温。",
                "tags": ["breakout", "volume"],
                "tags_en": ["breakout", "volume"],
                "tags_zh": ["突破", "放量"],
                "drivers": [
                    {
                        "label": "Price",
                        "label_en": "Price",
                        "label_zh": "价格",
                        "value": "+24%",
                        "score": 94,
                        "note": "Best move in sample.",
                        "note_en": "Best move in sample.",
                        "note_zh": "样本中涨幅最高。",
                    },
                    {
                        "label": "Volume",
                        "label_en": "Volume",
                        "label_zh": "成交量",
                        "value": "2.4x",
                        "score": 85,
                        "note": "Heavy participation.",
                        "note_en": "Heavy participation.",
                        "note_zh": "参与度明显上升。",
                    },
                    {
                        "label": "Catalyst",
                        "label_en": "Catalyst",
                        "label_zh": "催化剂",
                        "value": "Guide",
                        "score": 90,
                        "note": "Fresh news.",
                        "note_en": "Fresh news.",
                        "note_zh": "新消息驱动。",
                    },
                ],
                "sparkline": [
                    {"label": "Mon", "label_en": "Mon", "label_zh": "周一", "value": 20},
                    {"label": "Tue", "label_en": "Tue", "label_zh": "周二", "value": 35},
                    {"label": "Wed", "label_en": "Wed", "label_zh": "周三", "value": 55},
                    {"label": "Thu", "label_en": "Thu", "label_zh": "周四", "value": 70},
                    {"label": "Fri", "label_en": "Fri", "label_zh": "周五", "value": 95},
                ],
                "sources": [
                    {
                        "label": "Example",
                        "label_en": "Example",
                        "label_zh": "示例来源",
                        "url": "https://example.com",
                        "date": "2026-05-23",
                    }
                ],
            }
        ],
        "watchlist": [
            {
                "ticker": "WAIT",
                "name": "Wait Corp",
                "reason": "Near breakout.",
                "reason_en": "Near breakout.",
                "reason_zh": "接近突破。",
            }
        ],
        "sources": [
            {
                "label": "Example",
                "label_en": "Example",
                "label_zh": "示例来源",
                "url": "https://example.com",
                "date": "2026-05-23",
            }
        ],
    }


def _sample_scan() -> dict:
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    candidates = []
    for index, ticker in enumerate(tickers, start=1):
        candidates.append(
            {
                "rank": index,
                "ticker": ticker,
                "name": f"{ticker} Corp",
                "exchange": "NASDAQ",
                "sector": "Technology",
                "sector_en": "Technology",
                "sector_zh": "科技",
                "score_hint": 100 - index,
                "weekly_change_pct": 30 - index,
                "catalyst": "Fresh catalyst.",
                "catalyst_en": "Fresh catalyst.",
                "catalyst_zh": "新催化剂。",
                "reason": "Strong weekly setup.",
                "reason_en": "Strong weekly setup.",
                "reason_zh": "本周走势强劲。",
                "sources": [
                    {
                        "label": "Scan source",
                        "label_en": "Scan source",
                        "label_zh": "扫描来源",
                        "url": f"https://example.com/{ticker.lower()}",
                        "date": "2026-05-28",
                    }
                ],
            }
        )
    scan = _sample_summary()
    scan.pop("sector_mix")
    scan.pop("stocks")
    scan["candidates"] = candidates
    return scan


def _sample_stock(ticker: str, index: int) -> dict:
    stock = dict(_sample_summary()["stocks"][0])
    stock["ticker"] = ticker
    stock["name"] = f"{ticker} Corp"
    stock["score"] = 100 - index
    stock["weekly_change_pct"] = 30 - index
    stock["sources"] = [
        {
            "label": f"{ticker} source",
            "label_en": f"{ticker} source",
            "label_zh": f"{ticker} 来源",
            "url": f"https://example.com/detail/{ticker.lower()}",
            "date": "2026-05-28",
        }
    ]
    return stock


def test_weekly_stocks_refresh_persists_summary(tmp_weekly, monkeypatch, client):
    def fake_generate(progress=None):
        if progress:
            progress.emit("stage", stage="testing", message="Testing weekly flow")
        return weekly_stocks.save_summary(_sample_summary()), None

    monkeypatch.setattr(weekly_stocks, "generate_summary", fake_generate)

    resp = client.post("/api/weekly-stocks/refresh")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"

    deadline = time.monotonic() + 3.0
    body = None
    while time.monotonic() < deadline:
        body = client.get("/api/weekly-stocks").json()
        if body["summary"]:
            break
        time.sleep(0.05)

    assert body and body["summary"]["stocks"][0]["ticker"] == "TEST"
    assert body["summary"]["available_languages"] == ["en", "zh"]
    assert body["summary"]["stocks"][0]["why_awesome_zh"] == "它在已验证催化剂推动下完成突破。"
    assert "Research the hottest US-listed stocks" in body["prompt"]
    assert "研究本交易周最热门的美国上市股票" in body["prompt_zh"]


def test_weekly_refresh_supersedes_failed_structured_output_log(
    tmp_weekly, monkeypatch, client
):
    progress = job_progress.ProgressLog(weekly_stocks.progress_path())
    progress.emit(
        "job_init",
        kind="weekly_stocks",
        title="Weekly stock summary",
        subtitle="Hot stocks research",
    )
    progress.emit(
        "claude_action",
        action="tool_result",
        tool="StructuredOutput",
        is_error=True,
        preview="Output does not match required schema",
    )

    def fake_generate(progress=None):
        return weekly_stocks.save_summary(_sample_summary()), None

    monkeypatch.setattr(weekly_stocks, "generate_summary", fake_generate)

    resp = client.post("/api/weekly-stocks/refresh")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"


def test_weekly_refresh_clears_previous_terminal_stream(
    tmp_weekly, monkeypatch, client
):
    progress = job_progress.ProgressLog(weekly_stocks.progress_path())
    progress.emit("done", generated_at="old", summary={"week_label": "old"})

    def fake_generate(progress=None):
        summary = _sample_summary()
        summary["week_label"] = "Fresh week"
        return weekly_stocks.save_summary(summary), None

    monkeypatch.setattr(weekly_stocks, "generate_summary", fake_generate)

    resp = client.post("/api/weekly-stocks/refresh")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"

    deadline = time.monotonic() + 3.0
    progress_text = ""
    while time.monotonic() < deadline:
        progress_text = weekly_stocks.progress_path().read_text(encoding="utf-8")
        if "Fresh week" in progress_text:
            break
        time.sleep(0.05)

    assert "Fresh week" in progress_text
    assert '"week_label": "old"' not in progress_text


def test_weekly_stocks_response_includes_refresh_state(tmp_weekly, client):
    progress = job_progress.ProgressLog(weekly_stocks.progress_path())
    progress.emit(
        "job_init",
        kind="weekly_stocks",
        title="Weekly stock summary",
        subtitle="Hot stocks research",
    )
    progress.emit("error", error="research stalled")

    body = client.get("/api/weekly-stocks").json()

    assert body["refresh_state"]["kind"] == "weekly_stocks"
    assert body["refresh_state"]["terminal_type"] == "error"
    assert body["refresh_state"]["error"] == "research stalled"


def test_weekly_generate_summary_runs_phased_pipeline(tmp_weekly, monkeypatch):
    calls = []
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]

    def fake_run_web_research_json(**kwargs):
        calls.append(kwargs)
        name = kwargs["name"]
        if name == "weekly_scan":
            return _sample_scan(), None
        ticker = name.removeprefix("weekly_stock_").upper()
        assert ticker in tickers
        return _sample_stock(ticker, tickers.index(ticker) + 1), None

    monkeypatch.setattr(
        weekly_stocks.claude_runner,
        "run_web_research_json",
        fake_run_web_research_json,
    )
    progress = job_progress.ProgressLog(weekly_stocks.progress_path())

    summary, err = weekly_stocks.generate_summary(progress=progress)

    assert err is None
    assert summary["stocks"][0]["ticker"] == "AAA"
    assert len(summary["stocks"]) == 6
    assert calls[0]["name"] == "weekly_scan"
    assert calls[0]["timeout_sec"] <= 115
    assert all(call["timeout_sec"] <= 115 for call in calls[1:])

    progress_text = weekly_stocks.progress_path().read_text(encoding="utf-8")
    assert '"type": "candidates"' in progress_text
    assert '"type": "stock_started"' in progress_text
    assert '"type": "stock_done"' in progress_text
    assert '"type": "publish_done"' in progress_text

    draft = weekly_stocks.load_draft()
    assert draft["status"] == "complete"
    assert draft["completed_count"] == 6
