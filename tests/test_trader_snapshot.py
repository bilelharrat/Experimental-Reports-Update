"""Tests for the public-company trader snapshot pipeline (Phase 2).

Covers the schema/prompt module, the API surface, and the SSE stream.
The Claude subprocess is mocked at the ``companies_ai_public`` level
so these tests run in <1s without spawning claude.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from server import companies_ai_public, storage
from server.main import app


COMPANY_ID = "amd"


@pytest.fixture
def tmp_storage(monkeypatch, tmp_path):
    """Redirect storage paths so each test has its own companies.yaml +
    trader-progress dir.
    """
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")
    return tmp_path


@pytest.fixture
def public_company(tmp_storage):
    """Seed a single public company so the routes have something to act
    on."""
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": COMPANY_ID,
            "name": "Advanced Micro Devices, Inc.",
            "ticker": "AMD",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
            "description": "Designs CPUs and GPUs.",
        },
    ])
    return storage.get_company(COMPANY_ID)


@pytest.fixture
def private_company(tmp_storage):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": "anduril",
            "name": "Anduril Industries",
            "status": "private",
            "company_type": "private",
        },
    ])
    return storage.get_company("anduril")


@pytest.fixture
def stub_generate(monkeypatch):
    """Replace companies_ai_public.generate_snapshot with a fast stub."""
    def fake_generate(*, company, progress=None):
        if progress is not None:
            progress.emit("claude_action", action="thinking",
                          text="pretending to think")
        return (
            {
                "price_card": {
                    "last_price": 174.22, "currency": "USD",
                    "as_of": "2026-05-13T15:59:00-04:00",
                    "change_pct_1d": 1.82, "change_pct_5d": 4.10,
                    "change_pct_30d": 12.41, "change_pct_ytd": 28.03,
                    "change_pct_1y": 47.55,
                    "vs_sector_30d_pct": 14.20, "vs_sp500_30d_pct": 9.80,
                },
                "momentum_card": {
                    "trend": "bullish",
                    "trend_en": "Bullish",
                    "trend_zh": "看涨",
                    "above_50dma": True, "above_200dma": True,
                    "ma_crossover_recent": None,
                    "breakout_signals": ["5-day high"],
                    "breakout_signals_en": ["5-day high"],
                    "breakout_signals_zh": ["创5日新高"],
                    "notable_levels": {"support": 162.0, "resistance": 178.5},
                },
                "sentiment_card": {
                    "analyst_consensus": "Buy",
                    "analyst_consensus_en": "Buy",
                    "analyst_consensus_zh": "买入",
                    "coverage_count": 51,
                    "rating_distribution": {
                        "strong_buy": 18, "buy": 20,
                        "hold": 12, "sell": 1, "strong_sell": 0,
                    },
                    "target_price": {"mean": 195.0, "high": 230.0, "low": 148.0},
                    "recent_rating_changes": [],
                },
                "heat_card": {
                    "rel_volume_20d": 1.4, "iv_30d_pct": 42.0,
                    "iv_percentile_1y": 78, "options_skew": "call_bid",
                    "news_flow_24h": 11,
                    "insider_activity_30d": {
                        "buys": 0, "sells": 2,
                        "net_share_count_change": -45000,
                    },
                    "short_interest_pct_float": 2.1,
                    "days_to_cover": 1.8,
                    "social_mentions_trend": "rising",
                },
                "catalysts": [
                    {
                        "date": "2026-07-30", "type": "earnings",
                        "title": "Q2 2026 earnings",
                        "title_en": "Q2 2026 earnings",
                        "title_zh": "2026年第二季度财报",
                        "summary": "After-hours; consensus EPS $1.28",
                        "summary_en": "After-hours; consensus EPS $1.28",
                        "summary_zh": "盘后发布；市场预期每股收益 1.28 美元。",
                        "est_impact": "high",
                    },
                ],
                "trader_news": [
                    {
                        "headline": "Q1 beat on data-center",
                        "headline_en": "Q1 beat on data-center",
                        "headline_zh": "第一季度数据中心业务超预期",
                        "date": "2026-05-07",
                        "summary": "Data-center +47% YoY",
                        "summary_en": "Data-center +47% YoY",
                        "summary_zh": "数据中心业务同比增长47%。",
                        "bias": "positive",
                        "source_url": "https://example.com/q1",
                    },
                ],
                "tech_movers": {
                    "updated_at": "2026-05-13T20:15:00Z",
                    "movers": [
                        {
                            "ticker": "NVDA",
                            "company_en": "NVIDIA",
                            "company_zh": "英伟达",
                            "change_pct_1d": 5.8,
                            "direction": "up",
                            "market_driver_en": "AI data-center demand read-through.",
                            "market_driver_zh": "AI 数据中心需求带来板块联动。",
                            "source_url": "https://example.com/nvda",
                        },
                    ],
                },
            },
            None,
        )

    monkeypatch.setattr(
        companies_ai_public, "generate_snapshot", fake_generate,
    )


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _disable_auth(monkeypatch):
    monkeypatch.delenv("BSH_RESEARCH_API_TOKEN", raising=False)


# ---- Schema sanity ------------------------------------------------------


def test_schema_has_trader_topics():
    """All top-level cards from the design doc are required and
    schema-typed.
    """
    schema = companies_ai_public.SCHEMA
    assert schema["type"] == "object"
    required = set(schema.get("required") or [])
    assert required == {
        "price_card", "momentum_card", "sentiment_card",
        "heat_card", "catalysts", "trader_news", "tech_movers",
    }
    # Spot-check: price_card has the per-window returns the trader UI expects.
    price_required = set(
        schema["properties"]["price_card"].get("required") or []
    )
    for k in (
        "last_price", "change_pct_1d", "change_pct_30d",
        "vs_sector_30d_pct", "vs_sp500_30d_pct",
    ):
        assert k in price_required


def test_schema_requires_bilingual_prose_fields():
    """Every prose field that the iOS app localizes must have paired
    `_en` / `_zh` siblings in the required list. The strict-mode
    generator needs them to land in the JSON or the snapshot is
    rejected.
    """
    props = companies_ai_public.SCHEMA["properties"]

    momentum_required = set(props["momentum_card"]["required"])
    assert {"trend_en", "trend_zh"} <= momentum_required
    assert {"breakout_signals_en", "breakout_signals_zh"} <= momentum_required

    sentiment_required = set(props["sentiment_card"]["required"])
    assert {"analyst_consensus_en", "analyst_consensus_zh"} <= sentiment_required
    rating_change_required = set(
        props["sentiment_card"]
        ["properties"]["recent_rating_changes"]
        ["items"]["required"]
    )
    for k in ("action_en", "action_zh", "from_en", "from_zh", "to_en", "to_zh"):
        assert k in rating_change_required, k

    catalyst_required = set(
        props["catalysts"]["items"]["required"]
    )
    for k in ("title_en", "title_zh", "summary_en", "summary_zh"):
        assert k in catalyst_required, k

    news_required = set(
        props["trader_news"]["items"]["required"]
    )
    for k in ("headline_en", "headline_zh", "summary_en", "summary_zh"):
        assert k in news_required, k


def test_system_prompt_instructs_bilingual_output():
    """A sanity guard so future prompt edits don't silently drop the
    bilingual instruction — the iOS app depends on `_en` / `_zh` being
    populated.
    """
    prompt = companies_ai_public.SYSTEM_PROMPT
    assert "BILINGUAL" in prompt
    assert "_en" in prompt and "_zh" in prompt
    # We name the four card-level localized fields explicitly so a
    # careless refactor that drops them is caught.
    for token in (
        "trend_en", "trend_zh",
        "analyst_consensus_en", "analyst_consensus_zh",
        "title_en", "title_zh",
        "headline_en", "headline_zh",
    ):
        assert token in prompt, token


def test_generate_snapshot_refuses_private_company(monkeypatch):
    """The public-snapshot path must not be reachable for private records;
    the API gates this too but ``generate_snapshot`` belt-and-suspenders.
    """
    out, err = companies_ai_public.generate_snapshot(
        company={"name": "Foo", "ticker": "", "status": "private"},
    )
    assert out is None
    assert "ticker" in (err or "").lower()


# ---- API: POST /trader/refresh ------------------------------------------


def _wait_for_done(company_id, *, timeout=3.0):
    """Poll the company record until trader_snapshot lands."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        c = storage.get_company(company_id)
        if c and c.get("trader_snapshot"):
            return c["trader_snapshot"]
        time.sleep(0.05)
    raise AssertionError("trader_snapshot did not land")


def test_refresh_public_company_writes_snapshot(
    public_company, stub_generate, client,
):
    resp = client.post(f"/api/companies/{COMPANY_ID}/trader/refresh")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert "/trader/refresh/stream" in body["stream_url"]

    snap = _wait_for_done(COMPANY_ID)
    assert snap["price_card"]["last_price"] == 174.22
    assert snap["momentum_card"]["trend"] == "bullish"
    assert snap["momentum_card"]["trend_zh"] == "看涨"
    assert snap["sentiment_card"]["analyst_consensus_zh"] == "买入"
    assert snap["catalysts"][0]["title_zh"]
    assert snap["catalysts"][0]["summary_zh"]
    assert snap["trader_news"][0]["headline_zh"]
    assert snap["trader_news"][0]["summary_zh"]
    assert snap["tech_movers"]["movers"][0]["ticker"] == "NVDA"
    assert snap["tech_movers"]["movers"][0]["market_driver_zh"]
    assert snap["refreshed_at"]
    assert snap["generation_duration_ms"] >= 0
    # The job worker stamps the bilingual contract on every snapshot so
    # the client knows it can render either language without another
    # refresh.
    assert snap["available_languages"] == ["en", "zh"]


def test_refresh_rejects_private_company(
    private_company, stub_generate, client,
):
    resp = client.post(f"/api/companies/anduril/trader/refresh")
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "company_type_not_public"


def test_refresh_404_for_unknown_company(tmp_storage, stub_generate, client):
    storage._write_yaml(storage.COMPANIES_FILE, [])
    resp = client.post("/api/companies/ghost/trader/refresh")
    assert resp.status_code == 404


def test_refresh_attaches_to_running_job(
    public_company, monkeypatch, client,
):
    """Two POSTs while a job is in flight should share one progress file
    instead of double-spawning a subprocess.
    """
    block = {"event": __import__("threading").Event()}

    def slow_generate(*, company, progress=None):
        progress.emit("stage", stage="working", message="waiting…")
        block["event"].wait(timeout=2.0)
        return ({"price_card": None, "momentum_card": None,
                 "sentiment_card": None, "heat_card": None,
                 "catalysts": [], "trader_news": [],
                 "tech_movers": {"updated_at": None, "movers": []}}, None)

    monkeypatch.setattr(
        companies_ai_public, "generate_snapshot", slow_generate,
    )

    r1 = client.post(f"/api/companies/{COMPANY_ID}/trader/refresh")
    assert r1.json()["status"] == "queued"
    # Give the worker a beat to write the job_init event so the second
    # call sees an in-flight job.
    time.sleep(0.1)
    r2 = client.post(f"/api/companies/{COMPANY_ID}/trader/refresh")
    assert r2.json()["status"] == "already_running"
    # Let the slow generate finish so the worker thread exits cleanly.
    block["event"].set()
