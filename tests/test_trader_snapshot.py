"""Tests for the public-company trader snapshot pipeline (Phase 2).

Covers the schema/prompt module, the API surface, and the SSE stream.
The Claude subprocess is mocked at the ``companies_ai_public`` level
so these tests run in <1s without spawning claude.
"""
from __future__ import annotations

from datetime import datetime, timezone
import time

import pytest
from fastapi.testclient import TestClient

from server import (
    api as server_api,
    companies_ai,
    companies_ai_public,
    company_translate,
    storage,
    trader_stats,
    trader_bilingual_fill,
)
from server.main import app


COMPANY_ID = "amd"


@pytest.fixture
def tmp_storage(monkeypatch, tmp_path):
    """Redirect storage paths so each test has its own companies.yaml +
    trader-progress dir.

    The trader-refresh endpoint spawns a `threading.Thread(daemon=True)`
    per request. If one of those workers outlives this fixture's
    teardown, it inherits the un-patched module-level paths and
    overwrites the real ``data/companies.yaml`` with whatever the test
    seeded into tmp_path. (See the 2026-05-13 incident: an entire
    company list got clobbered down to just ``amd``.) Guard with two
    nets:

    1. Join every ``trader-snapshot:*`` thread before reverting the
       monkeypatch. If any thread is still alive after 5s, fail loud.
    2. Snapshot the real file's mtime and assert it didn't move
       during the test. Catches anything that slips past the join
       (different thread name, future workflow, etc.).
    """
    import threading
    from pathlib import Path

    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    monkeypatch.setattr(storage, "COMPANIES_FILE", tmp_path / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", tmp_path / "threads")

    real_companies = (
        Path(__file__).resolve().parent.parent / "data" / "companies.yaml"
    )
    canary_mtime = (
        real_companies.stat().st_mtime if real_companies.exists() else None
    )

    try:
        yield tmp_path
    finally:
        for t in threading.enumerate():
            if (
                t.name.startswith("trader-snapshot:")
                or t.name == "company-regen-all"
            ) and t.is_alive():
                t.join(timeout=5.0)
                assert not t.is_alive(), (
                    f"background worker {t.name!r} did not finish "
                    "within 5s; refusing to tear down tmp_storage "
                    "because the daemon will write to the real "
                    "data/companies.yaml after monkeypatch reverts."
                )
        if canary_mtime is not None and real_companies.exists():
            new_mtime = real_companies.stat().st_mtime
            assert new_mtime == canary_mtime, (
                "Real data/companies.yaml was modified during the test "
                f"(mtime {canary_mtime} → {new_mtime}). A background "
                "thread must have outlived this fixture's teardown — "
                "investigate before re-running."
            )


def _stub_heat_card_v2() -> dict:
    """Hand-crafted Positioning Structure (heat_card v2) payload that
    exercises every required sub-object and confidence path. Used by
    the fake-generate stub and the round-trip / migration tests.
    """
    return {
        "anchored_vwaps": {
            "current_price": 446.4,
            "anchors": [
                {
                    "kind": "earnings",
                    "label_en": "Q1 earnings (May 5)",
                    "label_zh": "2026年一季度财报（5月5日）",
                    "date": "2026-05-05",
                    "price": 421.39,
                },
                {
                    "kind": "52w_high",
                    "label_en": "52-week high",
                    "label_zh": "52周高点",
                    "date": "2026-05-08",
                    "price": 469.22,
                },
            ],
            "confidence": "medium",
            "confidence_note_en":
                "Anchors derived from Yahoo Finance close prices.",
            "confidence_note_zh":
                "锚定价取自雅虎财经收盘价。",
        },
        "float_turnover_zones": {
            "zones": [
                {
                    "low": 412.0, "high": 425.0, "pct_float": 22.0,
                    "note_en": "Post-earnings accumulation.",
                    "note_zh": "财报后吸筹区。",
                },
            ],
            "confidence": "medium",
            "confidence_note_en":
                "Estimated from volume-weighted profile.",
            "confidence_note_zh":
                "基于成交量加权分布估算。",
        },
        "holder_mix": {
            "passive_pct": 35.0, "long_only_pct": 28.0,
            "hedge_fund_pct": 22.0, "retail_pct": 10.0,
            "insider_pct": 1.5, "strategic_pct": 3.5,
            "quality_label_en": "Passive anchor, HF overhang.",
            "quality_label_zh": "被动资金提供锚定，对冲基金存在抛压。",
            "confidence": "high",
            "confidence_note_en": "13F snapshot via Whalewisdom.",
            "confidence_note_zh": "13F数据，来源 Whalewisdom。",
        },
        "options_positioning": {
            "gamma_flip": None, "put_wall": None, "call_wall": None,
            "regime_en": None, "regime_zh": None,
            "confidence": "unavailable",
            "confidence_note_en":
                "SpotGamma pay-walled; CBOE OI not granular enough.",
            "confidence_note_zh":
                "SpotGamma 付费墙，CBOE 公开未结合约粒度不足。",
        },
        "short_pressure": {
            "si_pct_float": 2.2, "days_to_cover": 0.8,
            "borrow_rate_pct": 0.5, "trend": "falling",
            "note_en": "Low SI + low borrow → weak bearish conviction.",
            "note_zh": "空头持仓低 + 借券成本低 → 看空动能偏弱。",
            "confidence": "high",
            "confidence_note_en": "FINRA SI + Iborrow rate.",
            "confidence_note_zh": "FINRA 空头数据 + Iborrow 借券利率。",
        },
        "valuation": {
            "ev_revenue_current": 12.0, "ev_revenue_5y_percentile": 18,
            "fwd_ev_ebitda": 22.0, "peg": 1.4,
            "note_en":
                "EV/Rev at 18th percentile vs 5y — downside compressed.",
            "note_zh":
                "EV/营收处于5年18百分位，下行空间压缩。",
            "confidence": "high",
            "confidence_note_en": "YCharts + Macrotrends.",
            "confidence_note_zh": "数据来源 YCharts 与 Macrotrends。",
        },
        "revisions": {
            "eps_up_30d": 14, "eps_down_30d": 3,
            "eps_up_90d": 22, "eps_down_90d": 8,
            "direction": "up",
            "note_en": "+14 / −3 EPS revisions (30d) — momentum positive.",
            "note_zh": "近30天每股收益上修14次/下修3次，趋势偏正。",
            "confidence": "medium",
            "confidence_note_en": "Zacks aggregator.",
            "confidence_note_zh": "Zacks 汇总数据。",
        },
        "next_catalyst": {
            "label_en": "Q2 2026 earnings",
            "label_zh": "2026年第二季度财报",
            "date": "2026-07-30",
            "implied_move_pct": 11.0,
            "confidence": "high",
            "confidence_note_en": "ATM straddle around earnings.",
            "confidence_note_zh": "财报前后ATM跨式期权报价。",
        },
        "support_confidence": {
            "zones": [
                {
                    "low": 412.0, "high": 425.0,
                    "confidence": "high",
                    "reasons_en": [
                        "AVWAP from earnings", "22% float turnover",
                    ],
                    "reasons_zh": ["财报后VWAP", "22% 换手"],
                },
            ],
            "confidence": "medium",
            "confidence_note_en":
                "Weighted from float turnover + holder quality.",
            "confidence_note_zh":
                "综合换手区与持有人质量加权。",
        },
        "fragility": {
            "score": 55, "rating": "medium",
            "drivers_en": [
                "AI narrative ~55% of valuation",
                "HF ownership crowded",
            ],
            "drivers_zh": [
                "AI叙事约占估值55%",
                "对冲基金持仓拥挤",
            ],
            "confidence": "medium",
            "confidence_note_en": "Composite from sub-fields above.",
            "confidence_note_zh": "由上述子项综合得出。",
        },
        "repricing_risk": {
            "positive_pct": 35, "neutral_pct": 40, "negative_pct": 25,
            "note_en":
                "Earnings momentum tilts positive; gamma resistance caps upside.",
            "note_zh":
                "盈利动能偏正；伽马阻力限制了上行空间。",
            "confidence": "medium",
            "confidence_note_en": "Composite — see drivers above.",
            "confidence_note_zh": "综合判断，详见上方驱动项。",
        },
    }


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
    """Replace companies_ai_public.generate_snapshot with a fast stub.

    Also short-circuits the bilingual completeness pass to a no-op:
    the stubs above produce fully bilingual data, so the fill pass
    has nothing to do — but it would still iterate the snapshot and
    (if claude is on PATH) probe `is_available()` etc. Skipping it
    keeps the worker thread sub-millisecond, which keeps the 3-second
    `_wait_for_done` poll deterministic when the whole suite runs.
    """
    monkeypatch.setattr(
        trader_bilingual_fill, "ensure_bilingual_completeness",
        lambda snapshot: snapshot,
    )

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
                "heat_card": _stub_heat_card_v2(),
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
        "heat_card", "catalysts", "trader_news",
        "research_overview", "market_session", "tech_movers",
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

    overview = props["research_overview"]["properties"]
    business_required = set(
        overview["business_mix"]["properties"]["segments"]
        ["items"]["required"]
    )
    for k in ("name_en", "name_zh", "note_en", "note_zh"):
        assert k in business_required, k
    quality_required = set(
        overview["financial_quality"]["properties"]["metrics"]
        ["items"]["required"]
    )
    for k in ("label_en", "label_zh", "note_en", "note_zh"):
        assert k in quality_required, k
    scenario_required = set(
        overview["scenario_matrix"]["properties"]["scenarios"]
        ["items"]["required"]
    )
    for k in (
        "label_en", "label_zh", "key_driver_en", "key_driver_zh",
    ):
        assert k in scenario_required, k


def test_heat_card_v2_has_all_sections():
    """Positioning Structure v2 — eight high-signal fields plus three
    composites, each independently nullable, each carrying a
    declarative confidence enum + bilingual confidence note. See
    docs/heat-card-v2.md.
    """
    heat = companies_ai_public.SCHEMA["properties"]["heat_card"]
    assert heat["type"] == ["object", "null"]
    required = set(heat["required"])
    assert required == {
        "anchored_vwaps", "float_turnover_zones", "holder_mix",
        "options_positioning", "short_pressure", "valuation",
        "revisions", "next_catalyst",
        "support_confidence", "fragility", "repricing_risk",
    }
    # Every section that the model fills must carry confidence + note.
    for section in (
        "anchored_vwaps", "float_turnover_zones", "holder_mix",
        "options_positioning", "short_pressure", "valuation",
        "revisions", "next_catalyst",
        "support_confidence", "fragility", "repricing_risk",
    ):
        sec = heat["properties"][section]
        sec_required = set(sec["required"])
        assert {"confidence", "confidence_note_en", "confidence_note_zh"} <= sec_required, (
            f"{section} is missing the declarative confidence triple"
        )


def test_heat_card_v2_bilingual_inventory():
    """Each prose field in heat_card v2 must have paired `_en` / `_zh`
    siblings. Lock the inventory so a refactor that drops one is
    caught immediately.
    """
    heat_props = companies_ai_public.SCHEMA["properties"]["heat_card"]["properties"]

    anchor_item = (
        heat_props["anchored_vwaps"]["properties"]["anchors"]["items"]
    )
    assert {"label_en", "label_zh"} <= set(anchor_item["required"])

    zone_item = (
        heat_props["float_turnover_zones"]["properties"]["zones"]["items"]
    )
    assert {"note_en", "note_zh"} <= set(zone_item["required"])

    for section, fields in [
        ("holder_mix", {"quality_label_en", "quality_label_zh"}),
        ("options_positioning", {"regime_en", "regime_zh"}),
        ("short_pressure", {"note_en", "note_zh"}),
        ("valuation", {"note_en", "note_zh"}),
        ("revisions", {"note_en", "note_zh"}),
        ("next_catalyst", {"label_en", "label_zh"}),
        ("repricing_risk", {"note_en", "note_zh"}),
    ]:
        assert fields <= set(heat_props[section]["required"]), section

    # Composite arrays carry parallel _en / _zh array fields.
    sc_zone = (
        heat_props["support_confidence"]
        ["properties"]["zones"]["items"]
    )
    assert {"reasons_en", "reasons_zh"} <= set(sc_zone["required"])
    assert {"drivers_en", "drivers_zh"} <= set(
        heat_props["fragility"]["required"]
    )


def test_schema_version_constant_is_at_least_two():
    """The on-disk schema version must be bumped when heat_card breaks.
    """
    assert companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION >= 2


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


def _wait_for_progress_done(path, *, timeout=8.0):
    import json

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            events = [
                json.loads(line)
                for line in path.read_text().splitlines()
                if line.strip()
            ]
            for event in reversed(events):
                if event.get("type") in {"done", "error"}:
                    return event
        time.sleep(0.05)
    raise AssertionError("progress log did not terminate")


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


def test_refresh_sections_preserves_previous_data_on_failure(
    public_company, monkeypatch, client,
):
    existing = {
        "refreshed_at": "2026-06-16T12:00:00+00:00",
        "schema_version": 2,
        "price_card": {"last_price": 100, "currency": "USD"},
        "catalysts": [
            {
                "date": "2026-07-30",
                "type": "earnings",
                "title": "Old catalyst",
                "title_en": "Old catalyst",
                "title_zh": "旧催化剂",
                "summary": "Old summary.",
                "summary_en": "Old summary.",
                "summary_zh": "旧摘要。",
                "est_impact": "high",
            },
        ],
        "section_status": {
            "catalysts": {
                "section_id": "catalysts",
                "label": "Upcoming catalysts",
                "status": "fresh",
                "last_successful_at": "2026-06-16T12:00:00+00:00",
                "last_attempted_at": "2026-06-16T12:00:00+00:00",
                "last_error": None,
                "retryable": True,
                "source_run_id": "seed",
            },
        },
    }
    storage.update_company_snapshot(COMPANY_ID, existing)
    monkeypatch.setattr(
        trader_bilingual_fill,
        "ensure_bilingual_completeness",
        lambda snapshot: snapshot,
    )
    monkeypatch.setattr(companies_ai_public.claude_runner, "is_available", lambda: True)

    def fail_snapshot(**kwargs):
        assert kwargs["ticker"] == "AMD"
        return None, "stalled after 120s without output"

    monkeypatch.setattr(
        companies_ai_public.claude_runner,
        "run_public_company_snapshot",
        fail_snapshot,
    )

    resp = client.post(
        f"/api/companies/{COMPANY_ID}/trader/refresh-sections",
        json={
            "sections": ["catalysts"],
            "force": True,
            "preserve_existing_sections": True,
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["retried_sections"] == ["catalysts"]

    done = _wait_for_progress_done(
        storage.DATA_DIR / "_trader" / f"{COMPANY_ID}__snapshot.progress.jsonl"
    )
    assert done["type"] == "done"
    assert done["retry_scope"] == "sections"

    snap = storage.get_company(COMPANY_ID)["trader_snapshot"]
    assert snap["catalysts"][0]["title_en"] == "Old catalyst"
    catalyst_status = snap["section_status"]["catalysts"]
    assert catalyst_status["status"] == "stale"
    assert "stalled after 120s" in catalyst_status["last_error"]

    history = trader_stats.read_history(COMPANY_ID, limit=1)
    assert history[0]["retry_scope"] == "sections"
    assert history[0]["retried_sections"] == ["catalysts"]
    assert history[0]["failed_sections"][0]["section"] == "catalysts"


def test_refresh_sections_replaces_only_requested_section(
    public_company, monkeypatch, client,
):
    existing = {
        "refreshed_at": "2026-06-16T12:00:00+00:00",
        "schema_version": 2,
        "price_card": {"last_price": 100, "currency": "USD"},
        "catalysts": [
            {
                "date": "2026-07-30",
                "type": "earnings",
                "title": "Old catalyst",
                "title_en": "Old catalyst",
                "title_zh": "旧催化剂",
                "summary": "Old summary.",
                "summary_en": "Old summary.",
                "summary_zh": "旧摘要。",
                "est_impact": "medium",
            },
        ],
    }
    storage.update_company_snapshot(COMPANY_ID, existing)
    monkeypatch.setattr(
        trader_bilingual_fill,
        "ensure_bilingual_completeness",
        lambda snapshot: snapshot,
    )
    monkeypatch.setattr(companies_ai_public.claude_runner, "is_available", lambda: True)

    def generate_catalysts(**kwargs):
        return (
            {
                "catalysts": [
                    {
                        "date": "2026-08-01",
                        "type": "product",
                        "title": "New launch",
                        "title_en": "New launch",
                        "title_zh": "新产品发布",
                        "summary": "Fresh section retry result.",
                        "summary_en": "Fresh section retry result.",
                        "summary_zh": "部分重试的新结果。",
                        "est_impact": "high",
                    },
                ],
            },
            None,
        )

    monkeypatch.setattr(
        companies_ai_public.claude_runner,
        "run_public_company_snapshot",
        generate_catalysts,
    )

    resp = client.post(
        f"/api/companies/{COMPANY_ID}/trader/refresh-sections",
        json={
            "sections": ["catalysts"],
            "force": True,
            "preserve_existing_sections": True,
        },
    )
    assert resp.status_code == 200, resp.text
    _wait_for_progress_done(
        storage.DATA_DIR / "_trader" / f"{COMPANY_ID}__snapshot.progress.jsonl"
    )

    snap = storage.get_company(COMPANY_ID)["trader_snapshot"]
    assert snap["price_card"]["last_price"] == 100
    assert snap["catalysts"][0]["title_en"] == "New launch"
    assert snap["section_status"]["catalysts"]["status"] == "fresh"


def test_refresh_all_public_companies_writes_each_public_snapshot(
    tmp_storage, stub_generate, client,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": COMPANY_ID,
            "name": "Advanced Micro Devices, Inc.",
            "ticker": "AMD",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
        },
        {
            "id": "nvda",
            "name": "NVIDIA Corporation",
            "ticker": "NVDA",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
        },
        {
            "id": "anduril",
            "name": "Anduril Industries",
            "status": "private",
            "company_type": "private",
        },
    ])

    resp = client.post("/api/companies/trader/refresh-all?languages=en")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["languages_requested"] == ["en"]
    assert body["total_count"] == 2
    assert body["queued_count"] == 2
    assert body["company_ids"] == [COMPANY_ID, "nvda"]

    amd = _wait_for_done(COMPANY_ID)
    nvda = _wait_for_done("nvda")
    assert amd["price_card"]["last_price"] == 174.22
    assert nvda["price_card"]["last_price"] == 174.22
    assert storage.get_company("anduril").get("trader_snapshot") is None

    done = _wait_for_progress_done(
        storage.DATA_DIR / "_trader" / "__all_public_refresh.progress.jsonl"
    )
    assert done["type"] == "done"
    assert done["total_count"] == 2
    assert done["refreshed_count"] == 2
    assert done["skipped_count"] == 0
    assert done["failed_count"] == 0


def test_regen_all_refreshes_summaries_and_public_trader_views(
    tmp_storage, stub_generate, monkeypatch, client,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": COMPANY_ID,
            "name": "Advanced Micro Devices, Inc.",
            "ticker": "AMD",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
            "description": "Old AMD summary.",
        },
        {
            "id": "anduril",
            "name": "Anduril Industries",
            "status": "private",
            "company_type": "private",
            "description": "Old Anduril summary.",
        },
        {
            "id": "nvda",
            "name": "NVIDIA Corporation",
            "ticker": "NVDA",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
            "description": "Old NVIDIA summary.",
        },
    ])

    def fake_deep_search(
        query, *, force_refresh=False, progress=None, only_company_id=None
    ):
        assert force_refresh is True
        assert only_company_id is not None
        company = next(
            c for c in storage.list_companies()
            if c.get("id") == only_company_id
        )
        updated = storage.update_company(
            company["id"],
            description=f"Fresh summary for {query}.",
            recent_news=[
                {
                    "headline": f"{query} update",
                    "date": "2026-05-25",
                    "summary": "Fresh company news.",
                },
            ],
        )
        if progress is not None:
            progress.emit(
                "claude_action",
                action="thinking",
                text=f"search {query}",
            )
        return {
            "source": "claude_code",
            "matches": [updated],
            "cached_at": "2026-05-25T00:00:00+00:00",
        }

    def fake_translate(company):
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
                "recent_news": [
                    {
                        "headline": "ZH update",
                        "summary": "ZH Fresh company news.",
                    }
                ],
            },
        }

    monkeypatch.setattr(companies_ai, "deep_search", fake_deep_search)
    monkeypatch.setattr(company_translate, "translate_company", fake_translate)

    resp = client.post("/api/companies/regen-all")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["languages_requested"] == ["en", "zh"]
    assert body["total_count"] == 3
    assert body["public_trader_count"] == 2
    assert body["company_ids"] == [COMPANY_ID, "nvda", "anduril"]

    done = _wait_for_progress_done(
        storage.DATA_DIR / "_regen" / "__all_companies_regen.progress.jsonl"
    )
    assert done["type"] == "done"
    assert done["total_count"] == 3
    assert done["summary_refreshed_count"] == 3
    assert done["summary_failed_count"] == 0
    assert done["trader_refreshed_count"] == 2
    assert done["trader_failed_count"] == 0

    amd = storage.get_company(COMPANY_ID)
    anduril = storage.get_company("anduril")
    nvda = storage.get_company("nvda")
    assert amd["description"] == "Fresh summary for AMD."
    assert amd["translation"]["description"].startswith("ZH Fresh summary")
    assert amd["trader_snapshot"]["available_languages"] == ["en", "zh"]
    assert anduril["description"] == "Fresh summary for Anduril Industries."
    assert anduril["translation"]["description"].startswith("ZH Fresh summary")
    assert anduril.get("trader_snapshot") is None
    assert nvda["description"] == "Fresh summary for NVDA."
    assert nvda["translation"]["description"].startswith("ZH Fresh summary")
    assert nvda["trader_snapshot"]["available_languages"] == ["en", "zh"]


def test_regen_all_backs_off_until_reset_then_retries(
    tmp_storage, monkeypatch, client,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": "anduril",
            "name": "Anduril Industries",
            "status": "private",
            "company_type": "private",
            "description": "Old Anduril summary.",
        },
    ])
    monkeypatch.setenv("BSH_REGEN_BACKOFF_MAX_SLEEP_SECONDS", "0")
    calls = {"count": 0}

    def fake_deep_search(
        query, *, force_refresh=False, progress=None, only_company_id=None
    ):
        assert query == "Anduril Industries"
        assert force_refresh is True
        calls["count"] += 1
        if calls["count"] == 1:
            if progress is not None:
                progress.emit(
                    "claude_action",
                    action="thinking",
                    text=(
                        "You've hit your session limit · resets 2am "
                        "(America/Los_Angeles)"
                    ),
                )
            return {
                "source": "fallback",
                "matches": [],
                "reason": "claude exited 1",
            }
        updated = storage.update_company(
            "anduril",
            description="Fresh Anduril summary after reset.",
        )
        return {
            "source": "claude_code",
            "matches": [updated],
            "cached_at": "2026-05-25T00:00:00+00:00",
        }

    def fake_translate(company):
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
            },
        }

    monkeypatch.setattr(companies_ai, "deep_search", fake_deep_search)
    monkeypatch.setattr(company_translate, "translate_company", fake_translate)

    resp = client.post("/api/companies/regen-all")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"

    progress_path = (
        storage.DATA_DIR / "_regen" / "__all_companies_regen.progress.jsonl"
    )
    done = _wait_for_progress_done(progress_path)
    assert done["type"] == "done"
    assert done["summary_refreshed_count"] == 1
    assert done["summary_failed_count"] == 0
    assert calls["count"] == 2

    import json

    events = [
        json.loads(line)
        for line in progress_path.read_text().splitlines()
        if line.strip()
    ]
    assert any(
        event.get("type") == "stage" and event.get("stage") == "backing_off"
        for event in events
    )
    assert not any(event.get("type") == "error" for event in events)

    state = json.loads(
        (storage.DATA_DIR / "_regen" / "__all_companies_regen.state.json")
        .read_text()
    )
    assert state["status"] == "done"
    assert state["items"]["anduril"]["summary_status"] == "done"
    assert storage.get_company("anduril")["description"] == (
        "Fresh Anduril summary after reset."
    )


def test_regen_reset_parser_handles_wall_clock_boundary():
    reason = "You've hit your session limit · resets 2am (America/Los_Angeles)"

    before_reset = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
    assert server_api._parse_regen_reset_delay_seconds(
        reason, now=before_reset,
    ) == 3600

    just_after_reset = datetime(2026, 5, 26, 9, 1, tzinfo=timezone.utc)
    assert server_api._parse_regen_reset_delay_seconds(
        reason, now=just_after_reset,
    ) == 300


def test_regen_repair_rewrites_bad_next_day_backoff(tmp_storage):
    state = {
        "status": "backing_off",
        "backoff_kind": "provider_limit",
        "backoff_reason": (
            "You've hit your session limit · resets 2am "
            "(America/Los_Angeles)"
        ),
        "backoff_started_at": "2026-05-26T09:01:00+00:00",
        "backoff_until": "2026-05-27T08:59:59+00:00",
        "backoff_seconds": 86339,
    }

    assert server_api._repair_provider_limit_backoff(state) is True
    assert state["backoff_seconds"] == 300
    assert state["backoff_until"] == "2026-05-26T09:06:00+00:00"


def test_regen_all_proactively_backs_off_at_usage_window_guard(
    tmp_storage, monkeypatch, client,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": "anduril",
            "name": "Anduril Industries",
            "status": "private",
            "company_type": "private",
            "description": "Old Anduril summary.",
        },
        {
            "id": "stripe",
            "name": "Stripe",
            "status": "private",
            "company_type": "private",
            "description": "Old Stripe summary.",
        },
    ])
    # Timing contract (this test was flaky with a 1s window: processing ONE
    # company through the checkpoint-heavy loop can take >1s, which blows
    # past reset_at — the guard then legitimately restarts the window and
    # never emits a backoff). Make the window generous and force company 1
    # to definitely cross the threshold:
    #   threshold = 20s * 0.05 = 1s  <  company-1 time (sleep 1.2s)  <  reset 20s
    # so the guard MUST fire before company 2. The backoff sleep itself is
    # clamped to 0 and _clear_regen_backoff restarts the window after it.
    monkeypatch.setenv("BSH_REGEN_USAGE_WINDOW_SECONDS", "20")
    monkeypatch.setenv("BSH_REGEN_USAGE_WINDOW_PAUSE_FRACTION", "0.05")
    monkeypatch.setenv("BSH_REGEN_BACKOFF_MAX_SLEEP_SECONDS", "0")
    calls: list[str] = []

    def fake_deep_search(
        query, *, force_refresh=False, progress=None, only_company_id=None
    ):
        assert force_refresh is True
        calls.append(query)
        if len(calls) == 1:
            time.sleep(1.2)
        company = next(
            c for c in storage.list_companies()
            if c.get("id") == only_company_id
        )
        updated = storage.update_company(
            company["id"],
            description=f"Fresh summary for {query}.",
        )
        return {
            "source": "claude_code",
            "matches": [updated],
            "cached_at": "2026-05-25T00:00:00+00:00",
        }

    def fake_translate(company):
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
            },
        }

    monkeypatch.setattr(companies_ai, "deep_search", fake_deep_search)
    monkeypatch.setattr(company_translate, "translate_company", fake_translate)

    resp = client.post("/api/companies/regen-all")
    assert resp.status_code == 200, resp.text

    progress_path = (
        storage.DATA_DIR / "_regen" / "__all_companies_regen.progress.jsonl"
    )
    done = _wait_for_progress_done(progress_path)
    assert done["type"] == "done"
    assert done["summary_refreshed_count"] == 2
    assert calls == ["Anduril Industries", "Stripe"]

    import json

    events = [
        json.loads(line)
        for line in progress_path.read_text().splitlines()
        if line.strip()
    ]
    assert any(
        event.get("type") == "stage"
        and event.get("stage") == "backing_off"
        and event.get("backoff_kind") == "proactive_usage_window"
        for event in events
    )

    state = json.loads(
        (storage.DATA_DIR / "_regen" / "__all_companies_regen.state.json")
        .read_text()
    )
    assert state["status"] == "done"
    assert state["usage_window_seconds"] == 20.0
    assert state["usage_window_pause_fraction"] == 0.05


def test_regen_all_backs_off_when_trader_progress_reports_session_limit(
    tmp_storage, monkeypatch, client,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": COMPANY_ID,
            "name": "Advanced Micro Devices, Inc.",
            "ticker": "AMD",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
            "description": "Old AMD summary.",
        },
    ])
    monkeypatch.setenv("BSH_REGEN_BACKOFF_MAX_SLEEP_SECONDS", "0")
    generate_calls = {"count": 0}

    def fake_deep_search(
        query, *, force_refresh=False, progress=None, only_company_id=None
    ):
        updated = storage.update_company(
            COMPANY_ID,
            description=f"Fresh summary for {query}.",
        )
        return {
            "source": "claude_code",
            "matches": [updated],
            "cached_at": "2026-05-25T00:00:00+00:00",
        }

    def fake_translate(company):
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
            },
        }

    def fake_generate(*, company, progress=None):
        generate_calls["count"] += 1
        if generate_calls["count"] == 1:
            if progress is not None:
                progress.emit(
                    "claude_action",
                    action="thinking",
                    text=(
                        "You've hit your session limit · resets 2am "
                        "(America/Los_Angeles)"
                    ),
                )
            return None, "claude exited 1"
        return (
            {
                "price_card": None,
                "momentum_card": None,
                "sentiment_card": None,
                "heat_card": None,
                "catalysts": [],
                "trader_news": [],
                "research_overview": None,
                "market_session": None,
                "tech_movers": {"updated_at": None, "movers": []},
            },
            None,
        )

    monkeypatch.setattr(companies_ai, "deep_search", fake_deep_search)
    monkeypatch.setattr(company_translate, "translate_company", fake_translate)
    monkeypatch.setattr(companies_ai_public, "generate_snapshot", fake_generate)
    monkeypatch.setattr(
        trader_bilingual_fill,
        "ensure_bilingual_completeness",
        lambda snapshot: snapshot,
    )

    resp = client.post("/api/companies/regen-all")
    assert resp.status_code == 200, resp.text

    progress_path = (
        storage.DATA_DIR / "_regen" / "__all_companies_regen.progress.jsonl"
    )
    done = _wait_for_progress_done(progress_path)
    assert done["type"] == "done"
    assert done["trader_refreshed_count"] == 1
    assert done["trader_failed_count"] == 0
    assert generate_calls["count"] == 2

    import json

    events = [
        json.loads(line)
        for line in progress_path.read_text().splitlines()
        if line.strip()
    ]
    assert any(
        event.get("type") == "stage"
        and event.get("stage") == "backing_off"
        and event.get("backoff_kind") == "provider_limit"
        and event.get("phase") == "trader"
        for event in events
    )


def test_regen_all_resume_preserves_done_and_retries_recoverable_checkpoint(
    tmp_storage, stub_generate, monkeypatch, client,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": COMPANY_ID,
            "name": "Advanced Micro Devices, Inc.",
            "ticker": "AMD",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
            "description": "Already fresh AMD.",
            "trader_snapshot": {"available_languages": ["en", "zh"]},
        },
        {
            "id": "aapl",
            "name": "Apple Inc.",
            "ticker": "AAPL",
            "exchange": "NASDAQ",
            "status": "public",
            "company_type": "public",
            "description": "Old Apple summary.",
        },
    ])
    server_api._write_regen_checkpoint({
        "schema_version": 1,
        "status": "done_with_errors",
        "started_at": "2026-05-25T00:00:00+00:00",
        "updated_at": "2026-05-25T00:00:00+00:00",
        "completed_at": "2026-05-25T01:00:00+00:00",
        "force": False,
        "languages_requested": ["en", "zh"],
        "include_translations": True,
        "translation_mode": "all",
        "order": [COMPANY_ID, "aapl"],
        "items": {
            COMPANY_ID: {
                "company_id": COMPANY_ID,
                "company_name": "Advanced Micro Devices, Inc.",
                "ticker": "AMD",
                "company_type": "public",
                "summary_status": "done",
                "summary_source": "claude_code",
                "summary_refreshed_at": "2026-05-25T00:05:00+00:00",
                "trader_status": "done",
                "trader_refreshed_at": "2026-05-25T00:10:00+00:00",
            },
            "aapl": {
                "company_id": "aapl",
                "company_name": "Apple Inc.",
                "ticker": "AAPL",
                "company_type": "public",
                "summary_status": "done",
                "summary_source": "fallback",
                "summary_reason": "claude exited 1",
                "summary_refreshed_at": "2026-05-25T00:15:00+00:00",
                "trader_status": "error",
                "trader_error": "all snapshot sections failed: claude exited 1",
            },
        },
    })
    calls: list[str] = []

    def fake_deep_search(
        query, *, force_refresh=False, progress=None, only_company_id=None
    ):
        assert force_refresh is True
        calls.append(query)
        # Refresh queries by the stable key (ticker), not the AI name.
        assert query == "AAPL"
        assert only_company_id == "aapl"
        updated = storage.update_company(
            "aapl",
            description="Fresh Apple summary after resume.",
        )
        return {
            "source": "claude_code",
            "matches": [updated],
            "cached_at": "2026-05-25T00:00:00+00:00",
        }

    def fake_translate(company):
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
            },
        }

    monkeypatch.setattr(companies_ai, "deep_search", fake_deep_search)
    monkeypatch.setattr(company_translate, "translate_company", fake_translate)

    resp = client.post("/api/companies/regen-all")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "resumed"

    done = _wait_for_progress_done(
        storage.DATA_DIR / "_regen" / "__all_companies_regen.progress.jsonl"
    )
    assert done["type"] == "done"
    assert done["failed_count"] == 0
    assert calls == ["AAPL"]

    import json

    state = json.loads(
        (storage.DATA_DIR / "_regen" / "__all_companies_regen.state.json")
        .read_text()
    )
    assert state["status"] == "done"
    assert state["items"][COMPANY_ID]["summary_refreshed_at"] == (
        "2026-05-25T00:05:00+00:00"
    )
    assert state["items"][COMPANY_ID]["trader_refreshed_at"] == (
        "2026-05-25T00:10:00+00:00"
    )
    assert state["items"]["aapl"]["summary_status"] == "done"
    assert state["items"]["aapl"]["summary_source"] == "claude_code"
    assert state["items"]["aapl"]["trader_status"] == "done"
    assert storage.get_company(COMPANY_ID)["description"] == "Already fresh AMD."
    assert storage.get_company("aapl")["description"] == (
        "Fresh Apple summary after resume."
    )


def test_regen_all_startup_resume_uses_checkpoint(
    tmp_storage, monkeypatch,
):
    storage._write_yaml(storage.COMPANIES_FILE, [
        {
            "id": COMPANY_ID,
            "name": "Advanced Micro Devices, Inc.",
            "status": "private",
            "company_type": "private",
            "description": "Already fresh.",
        },
        {
            "id": "anduril",
            "name": "Anduril Industries",
            "status": "private",
            "company_type": "private",
            "description": "Old Anduril summary.",
        },
    ])
    server_api._write_regen_checkpoint({
        "schema_version": 1,
        "status": "running",
        "started_at": "2026-05-25T00:00:00+00:00",
        "updated_at": "2026-05-25T00:00:00+00:00",
        "completed_at": None,
        "force": False,
        "languages_requested": ["en", "zh"],
        "include_translations": True,
        "translation_mode": "all",
        "order": [COMPANY_ID, "anduril"],
        "items": {
            COMPANY_ID: {
                "company_id": COMPANY_ID,
                "company_name": "Advanced Micro Devices, Inc.",
                "ticker": "",
                "company_type": "private",
                "summary_status": "done",
                "summary_refreshed_at": "2026-05-25T00:00:00+00:00",
                "trader_status": "not_applicable",
            },
            "anduril": {
                "company_id": "anduril",
                "company_name": "Anduril Industries",
                "ticker": "",
                "company_type": "private",
                "summary_status": "pending",
                "trader_status": "not_applicable",
            },
        },
    })

    def fake_deep_search(
        query, *, force_refresh=False, progress=None, only_company_id=None
    ):
        assert query == "Anduril Industries"
        assert only_company_id == "anduril"
        updated = storage.update_company(
            "anduril",
            description="Fresh Anduril summary from startup resume.",
        )
        return {
            "source": "claude_code",
            "matches": [updated],
            "cached_at": "2026-05-25T00:00:00+00:00",
        }

    def fake_translate(company):
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
            },
        }

    monkeypatch.setattr(companies_ai, "deep_search", fake_deep_search)
    monkeypatch.setattr(company_translate, "translate_company", fake_translate)

    assert server_api.resume_regen_all_if_needed() is True
    done = _wait_for_progress_done(
        storage.DATA_DIR / "_regen" / "__all_companies_regen.progress.jsonl"
    )
    assert done["type"] == "done"
    assert done["summary_refreshed_count"] == 2
    assert storage.get_company(COMPANY_ID)["description"] == "Already fresh."
    assert storage.get_company("anduril")["description"] == (
        "Fresh Anduril summary from startup resume."
    )


def test_refresh_records_bilingual_query_params(
    public_company, stub_generate, client,
):
    """The iOS app posts `?languages=en,zh&include_translations=true&
    translation_mode=all`. Phase 1 records them on the response and on
    the job_init JSONL event so the client can render a translation-
    pending hint without re-fetching the company. The generator always
    produces both languages, so these inputs don't gate generation —
    yet.
    """
    resp = client.post(
        f"/api/companies/{COMPANY_ID}/trader/refresh"
        "?languages=en,zh&include_translations=true&translation_mode=all"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["languages_requested"] == ["en", "zh"]

    _wait_for_done(COMPANY_ID)

    # The progress log captured the request shape on job_init.
    import json
    path = (
        storage.DATA_DIR / "_trader" / f"{COMPANY_ID}__snapshot.progress.jsonl"
    )
    events = [
        json.loads(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    job_init = next(e for e in events if e.get("type") == "job_init")
    assert job_init["languages_requested"] == ["en", "zh"]
    assert job_init["include_translations"] is True
    assert job_init["translation_mode"] == "all"


def test_refresh_normalizes_languages_param(
    public_company, stub_generate, client,
):
    """Missing / garbage `languages` falls back to the bilingual
    default. Unknown codes are dropped silently — we never want a
    misconfigured client to land an empty `available_languages` on the
    job log.
    """
    resp = client.post(
        f"/api/companies/{COMPANY_ID}/trader/refresh?languages=fr,en,bogus"
    )
    assert resp.status_code == 200
    # Only `en` is recognized; we don't fail open to the bilingual
    # default in that case because the caller asked for a subset.
    assert resp.json()["languages_requested"] == ["en"]


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


def test_bilingual_snapshot_round_trips_through_storage(public_company):
    """A freshly generated bilingual snapshot must survive a YAML write
    + read cycle with every `_en` / `_zh` sibling intact.
    """
    snapshot = {
        "refreshed_at": "2026-05-13T20:15:00Z",
        "available_languages": ["en", "zh"],
        "price_card": {
            "last_price": 174.22, "currency": "USD", "as_of": None,
            "change_pct_1d": 1.82, "change_pct_5d": None,
            "change_pct_30d": None, "change_pct_ytd": None,
            "change_pct_1y": None, "vs_sector_30d_pct": None,
            "vs_sp500_30d_pct": None,
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
            "notable_levels": None,
        },
        "trader_news": [
            {
                "headline": "Q1 beat",
                "headline_en": "Q1 beat",
                "headline_zh": "第一季度超预期",
                "date": "2026-05-07",
                "summary": "Data-center +47% YoY",
                "summary_en": "Data-center +47% YoY",
                "summary_zh": "数据中心同比增长47%。",
                "bias": "positive",
                "source_url": "https://example.com/q1",
            },
        ],
    }

    storage.update_company_snapshot(COMPANY_ID, snapshot)
    reloaded = storage.get_company(COMPANY_ID)["trader_snapshot"]

    assert reloaded["available_languages"] == ["en", "zh"]
    assert reloaded["momentum_card"]["trend_zh"] == "看涨"
    assert reloaded["momentum_card"]["breakout_signals_zh"] == ["创5日新高"]
    assert reloaded["trader_news"][0]["headline_zh"] == "第一季度超预期"
    assert reloaded["trader_news"][0]["summary_zh"] == "数据中心同比增长47%。"
    # The legacy single-language fields must persist alongside so older
    # clients keep rendering until they migrate.
    assert reloaded["momentum_card"]["trend"] == "bullish"
    assert reloaded["trader_news"][0]["headline"] == "Q1 beat"


def test_legacy_snapshot_loads_without_bilingual_fields(public_company):
    """Snapshots written before the bilingual contract have only the
    single-language fields and no `available_languages` stamp. The
    storage layer must round-trip them as-is so existing companies
    keep working until their next refresh.
    """
    legacy = {
        "refreshed_at": "2026-04-01T10:00:00Z",
        "generation_duration_ms": 12345,
        "price_card": {
            "last_price": 160.0, "currency": "USD", "as_of": None,
            "change_pct_1d": 0.5, "change_pct_5d": None,
            "change_pct_30d": None, "change_pct_ytd": None,
            "change_pct_1y": None, "vs_sector_30d_pct": None,
            "vs_sp500_30d_pct": None,
        },
        "momentum_card": {
            "trend": "bullish",
            "above_50dma": True, "above_200dma": True,
            "ma_crossover_recent": None,
            "breakout_signals": ["5-day high"],
            "notable_levels": None,
        },
        "trader_news": [
            {
                "headline": "Legacy headline",
                "date": "2026-04-01",
                "summary": "Legacy summary",
                "bias": "positive",
                "source_url": "https://example.com/legacy",
            },
        ],
    }

    storage.update_company_snapshot(COMPANY_ID, legacy)
    reloaded = storage.get_company(COMPANY_ID)["trader_snapshot"]

    assert "available_languages" not in reloaded
    assert reloaded["momentum_card"]["trend"] == "bullish"
    assert "trend_zh" not in reloaded["momentum_card"]
    assert reloaded["trader_news"][0]["headline"] == "Legacy headline"
    assert "headline_zh" not in reloaded["trader_news"][0]


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


# ---- Schema version + migration ---------------------------------------


def test_migration_strips_v1_heat_card(public_company):
    """A snapshot written by the v1 code (rel_volume_20d etc. on
    heat_card, no schema_version) must be migrated to v2 — heat_card
    nulled out, schema_version stamped — so iOS/web don't decode the
    legacy shape through v2 paths.
    """
    legacy = {
        "refreshed_at": "2026-04-01T10:00:00Z",
        # No schema_version → v1 by convention.
        "price_card": None, "momentum_card": None,
        "sentiment_card": None,
        "heat_card": {
            "rel_volume_20d": 1.4,
            "iv_30d_pct": 42.0,
            "iv_percentile_1y": 78,
            "options_skew": "call_bid",
            "news_flow_24h": 11,
            "insider_activity_30d": {"buys": 0, "sells": 2,
                                     "net_share_count_change": -45000},
            "short_interest_pct_float": 2.1,
            "days_to_cover": 1.8,
            "social_mentions_trend": "rising",
        },
        "catalysts": [], "trader_news": [],
    }
    storage.update_company_snapshot(COMPANY_ID, legacy)

    n = storage.migrate_trader_snapshots(
        target_schema_version=companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION,
    )
    assert n == 1

    migrated = storage.get_company(COMPANY_ID)["trader_snapshot"]
    assert migrated["heat_card"] is None
    assert migrated["schema_version"] == \
        companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION
    # Sibling fields untouched.
    assert migrated["catalysts"] == []
    assert migrated["refreshed_at"] == "2026-04-01T10:00:00Z"


def test_migration_is_idempotent(public_company):
    storage.update_company_snapshot(COMPANY_ID, {
        "refreshed_at": "2026-04-01T10:00:00Z",
        "heat_card": {"rel_volume_20d": 1.4},
        "schema_version": 1,
    })
    target = companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION
    first = storage.migrate_trader_snapshots(target_schema_version=target)
    second = storage.migrate_trader_snapshots(target_schema_version=target)
    assert first == 1
    assert second == 0


def test_migration_leaves_current_snapshots_alone(public_company):
    """Snapshots that already match the current schema_version
    shouldn't be touched.
    """
    target = companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION
    storage.update_company_snapshot(COMPANY_ID, {
        "refreshed_at": "2026-05-13T20:15:00Z",
        "heat_card": _stub_heat_card_v2(),
        "schema_version": target,
    })
    n = storage.migrate_trader_snapshots(target_schema_version=target)
    assert n == 0
    snap = storage.get_company(COMPANY_ID)["trader_snapshot"]
    assert snap["heat_card"]["anchored_vwaps"]["current_price"] == 446.4


def test_done_event_stamps_schema_version(
    public_company, stub_generate, client,
):
    """A fresh refresh end-to-end must stamp schema_version on the
    saved snapshot AND echo it on the SSE `done` event.
    """
    resp = client.post(f"/api/companies/{COMPANY_ID}/trader/refresh")
    assert resp.status_code == 200
    snap = _wait_for_done(COMPANY_ID)
    target = companies_ai_public.TRADER_SNAPSHOT_SCHEMA_VERSION
    assert snap["schema_version"] == target

    import json
    path = (
        storage.DATA_DIR / "_trader" / f"{COMPANY_ID}__snapshot.progress.jsonl"
    )
    _wait_for_progress_done(path)
    events = [
        json.loads(line) for line in path.read_text().splitlines() if line
    ]
    done = next(e for e in events if e.get("type") == "done")
    assert done["schema_version"] == target


# ---- Force-refresh ----------------------------------------------------


def test_force_refresh_supersedes_in_flight_run(
    public_company, monkeypatch, client,
):
    """`?force=true` must bypass the `already_running` short-circuit
    and spawn a fresh worker even when a stale progress file exists.
    """
    import threading as _threading
    block = {"event": _threading.Event()}

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
    time.sleep(0.1)
    # Without `force`, this short-circuits.
    r2 = client.post(f"/api/companies/{COMPANY_ID}/trader/refresh")
    assert r2.json()["status"] == "already_running"
    # With `force=true`, the in-flight is superseded.
    r3 = client.post(
        f"/api/companies/{COMPANY_ID}/trader/refresh?force=true"
    )
    assert r3.json()["status"] == "force_queued"
    # Let the original generate finish so the worker thread exits.
    block["event"].set()
