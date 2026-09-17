from __future__ import annotations

import json
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

    def fake_grounded(**kwargs):
        calls.append(kwargs)
        name = kwargs["name"]
        if name == "weekly_scan":
            return _sample_scan(), {"engine": "gemini", "grounded": True, "sources": [{"title": "x", "url": "https://e.com"}], "queries": ["q"], "fallback_reason": None}, None
        ticker = name.removeprefix("weekly_stock_").upper()
        assert ticker in tickers
        return _sample_stock(ticker, tickers.index(ticker) + 1), {"engine": "gemini", "grounded": True, "sources": [{"title": "x", "url": "https://e.com"}], "queries": ["q"], "fallback_reason": None}, None

    monkeypatch.setattr(weekly_stocks.ai_engine, "grounded", fake_grounded)
    progress = job_progress.ProgressLog(weekly_stocks.progress_path())

    summary, err = weekly_stocks.generate_summary(progress=progress)

    assert err is None
    assert summary["stocks"][0]["ticker"] == "AAA"
    assert len(summary["stocks"]) == 6
    assert calls[0]["name"] == "weekly_scan"
    # These run behind a refresh button, so both engines stay on a
    # UI-shaped cap rather than ai_engine's batch default.
    assert calls[0]["gemini_timeout_sec"] == weekly_stocks.SCAN_TIMEOUT_SEC
    assert calls[0]["claude_timeout_sec"] == weekly_stocks.SCAN_TIMEOUT_SEC
    assert all(
        call["gemini_timeout_sec"] == weekly_stocks.DETAIL_TIMEOUT_SEC
        for call in calls[1:]
    )

    progress_text = weekly_stocks.progress_path().read_text(encoding="utf-8")
    assert '"type": "candidates"' in progress_text
    assert '"type": "stock_started"' in progress_text
    assert '"type": "stock_done"' in progress_text
    assert '"type": "publish_done"' in progress_text

    draft = weekly_stocks.load_draft()
    assert draft["status"] == "complete"
    assert draft["completed_count"] == 6


def test_fill_missing_summary_zh_translates_english_narrative(monkeypatch):
    """The fast scan produces English-only narrative; the zh fields must be
    translated from it, not left on the generic stats template (the July 20
    miss: market_pulse_zh showed leaderboard stats while market_pulse_en
    carried the real market story)."""
    calls = []

    def fake_structured(**kwargs):
        calls.append(kwargs)
        payload = json.loads(
            kwargs["user_prompt"].split("INPUT:\n", 1)[1]
        )
        return (
            {key: f"中文：{value[:20]}" for key, value in payload.items()},
            {"engine": "gemini"},
            None,
        )

    monkeypatch.setattr(weekly_stocks.ai_engine, "structured", fake_structured)
    summary = {
        "week_label": "Week of July 20-24, 2026",
        "week_label_en": "Week of July 20-24, 2026",
        "week_label_zh": "Week of July 20-24, 2026",
        "market_pulse_en": "A choppy, risk-off tilt dominated the tape.",
        "market_pulse_zh": "本周动量由 PYPL 领衔。",
        "benchmark_context_en": "S&P 500 roughly flat on the open.",
        "benchmark_context_zh": "已发布标的本周平均表现为 +22.6%。",
        "methodology_en": "Phased scan plus per-stock verification.",
        "methodology_zh": "先进行市场扫描。",
        "stocks": [
            {
                "ticker": "PYPL",
                # Fallback card: English stitched into a Chinese template.
                "why_awesome_en": "PYPL screened hot: best-in-class relative strength this week.",
                "why_awesome_zh": "PYPL 进入本周热门名单：best-in-class relative strength versus a flat index this week.",
                "catalyst_en": "Top weekly S&P 500 gainer on a sharp re-rating into earnings.",
                "catalyst_zh": "Top weekly S&P 500 gainer on a sharp re-rating into earnings.",
                # Genuine Chinese — must NOT be retranslated.
                "setup_en": "Scan-qualified momentum setup awaiting deeper verification.",
                "setup_zh": "已通过周度扫描筛选，仍需更深入验证的动量机会。",
                "risk_en": "Thesis weakens without confirmation.",
                "risk_zh": "若后续数据无法确认催化剂，交易逻辑会走弱。",
            }
        ],
    }
    # The fast scan carried no _zh fields at all.
    scan = {"market_pulse": "A choppy, risk-off tilt dominated the tape."}

    weekly_stocks._fill_missing_summary_zh(summary, scan)

    assert len(calls) == 1
    assert summary["market_pulse_zh"].startswith("中文：A choppy")
    assert summary["benchmark_context_zh"].startswith("中文：S&P 500")
    assert summary["week_label_zh"].startswith("中文：Week of")
    stock = summary["stocks"][0]
    # English-contaminated stock fields were translated from English…
    assert stock["why_awesome_zh"].startswith("中文：PYPL screened hot")
    assert stock["catalyst_zh"].startswith("中文：Top weekly")
    # …while genuine Chinese stayed untouched.
    assert stock["setup_zh"] == "已通过周度扫描筛选，仍需更深入验证的动量机会。"
    assert stock["risk_zh"] == "若后续数据无法确认催化剂，交易逻辑会走弱。"


def test_fill_missing_summary_zh_keeps_scan_chinese_and_survives_failure(
    monkeypatch,
):
    summary = {
        "market_pulse_en": "English narrative.",
        "market_pulse_zh": "扫描给出的真实中文叙述。",
        "benchmark_context_en": "Benchmark narrative.",
        "benchmark_context_zh": "已发布标的本周平均表现为 +22.6%。",
    }
    scan = {"market_pulse_zh": "扫描给出的真实中文叙述。"}

    def failing_structured(**kwargs):
        return None, {"engine": "gemini"}, "no engine available"

    monkeypatch.setattr(weekly_stocks.ai_engine, "structured", failing_structured)
    weekly_stocks._fill_missing_summary_zh(summary, scan)

    # Scan-provided Chinese untouched; failed translation keeps the fallback
    # instead of blanking or raising.
    assert summary["market_pulse_zh"] == "扫描给出的真实中文叙述。"
    assert summary["benchmark_context_zh"] == "已发布标的本周平均表现为 +22.6%。"


def test_fallback_scan_is_flagged_and_carries_no_fabricated_data():
    """The fallback scan must never masquerade as live market data (the July
    review finding: fabricated SNOW +36.5% cards stamped with the current
    week's dates). It is a seed watchlist, flagged as such."""
    scan = weekly_stocks._fallback_scan("scan timed out")

    assert scan["is_fallback"] is True
    assert scan["scan_error"] == "scan timed out"
    for candidate in scan["candidates"]:
        assert candidate["weekly_change_pct"] is None
        assert "fallback" in candidate["sources"][0]["label"].lower()
    # The narrative must disclose the failure, not claim weekly momentum.
    assert "failed" in scan["market_pulse"].lower()


def test_fallback_stock_card_is_flagged_unverified():
    candidate = {
        "rank": 1,
        "ticker": "AAA",
        "name": "Alpha Inc.",
        "weekly_change_pct": 4.2,
    }
    stock = weekly_stocks._fallback_stock_from_candidate(candidate, "detail timeout")

    assert stock["is_fallback"] is True
    assert stock["sparkline_synthetic"] is True
    assert "unverified" in stock["why_awesome"].lower()


def test_assemble_summary_propagates_fallback_flags():
    scan = {"is_fallback": True, "week_label": "Week of July 28-31, 2026"}
    stocks = [
        weekly_stocks._fallback_stock_from_candidate(
            {"rank": i, "ticker": t, "name": t}
        )
        for i, t in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE"], start=1)
    ]
    summary = weekly_stocks._assemble_summary(scan, stocks, [])

    assert summary["scan_fallback"] is True
    assert summary["fallback_stock_count"] == 5


def test_detail_call_retries_once_on_transient_error(tmp_weekly, monkeypatch):
    tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]
    detail_attempts = {}

    def fake_grounded(**kwargs):
        name = kwargs["name"]
        if name == "weekly_scan":
            return _sample_scan(), {"engine": "gemini", "grounded": True, "sources": [{"title": "x", "url": "https://e.com"}], "queries": ["q"], "fallback_reason": None}, None
        ticker = name.removeprefix("weekly_stock_").upper()
        detail_attempts[ticker] = detail_attempts.get(ticker, 0) + 1
        if ticker == "AAA" and detail_attempts[ticker] == 1:
            return None, {"engine": "gemini"}, "Connection reset by peer"
        return _sample_stock(ticker, tickers.index(ticker) + 1), {"engine": "gemini", "grounded": True, "sources": [{"title": "x", "url": "https://e.com"}], "queries": ["q"], "fallback_reason": None}, None

    monkeypatch.setattr(weekly_stocks.ai_engine, "grounded", fake_grounded)
    assert weekly_stocks.claude_runner.is_transient_claude_error(
        "Connection reset by peer"
    )

    summary, err = weekly_stocks.generate_summary()

    assert err is None
    assert detail_attempts["AAA"] == 2
    aaa = next(s for s in summary["stocks"] if s["ticker"] == "AAA")
    assert not aaa.get("is_fallback")
    assert summary["scan_fallback"] is False
    assert summary["fallback_stock_count"] == 0


def test_an_ungrounded_scan_is_treated_as_a_failed_scan(tmp_weekly, monkeypatch):
    """"This week's movers" is a claim about the live market. A model that
    answered from memory would name stale movers with this week's
    confidence — worse than the static watchlist, which announces itself."""

    def ungrounded(**kwargs):
        meta = {"engine": "gemini", "grounded": False, "sources": [], "queries": []}
        if kwargs["name"] == "weekly_scan":
            return _sample_scan(), meta, None
        ticker = kwargs["name"].removeprefix("weekly_stock_").upper()
        return _sample_stock(ticker, 1), meta, None

    monkeypatch.setattr(weekly_stocks.ai_engine, "grounded", ungrounded)
    summary, err = weekly_stocks.generate_summary()

    assert err is None, "an ungrounded scan degrades, it does not error"
    # The dashboard is flagged unverified and seeded from the static
    # watchlist, exactly as it is when the scan errors outright.
    assert summary["scan_fallback"] is True
    draft = weekly_stocks.load_draft() or {}
    reasons = " ".join(str(e.get("error")) for e in (draft.get("errors") or []))
    assert "without searching" in reasons
