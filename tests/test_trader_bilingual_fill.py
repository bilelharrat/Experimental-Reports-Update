"""Tests for the server-side bilingual completeness pass.

The translator is mocked so these tests run without spawning claude.
The point of the suite is to lock the *invariant*: after the pass
returns, every paired `_en` / `_zh` field is either both-filled or
both-empty — never half-populated.
"""
from __future__ import annotations

import pytest

from server import trader_bilingual_fill


# ---- Mock translator --------------------------------------------------


def _install_mock_translator(monkeypatch):
    """Replace the claude-backed translators with deterministic
    transformations so we can pin behavior without a real LLM call.
    """
    def fake_string(values, *, source, target):
        # EN→ZH: prefix with "ZH:"; ZH→EN: prefix with "EN:". Lets
        # tests assert the *direction* of the translation along with
        # the *fact* that translation happened.
        marker = "ZH:" if target == "zh" else "EN:"
        return [f"{marker}{v}" for v in values]

    def fake_array(values, *, source, target):
        marker = "ZH:" if target == "zh" else "EN:"
        return [[f"{marker}{s}" for s in arr] for arr in values]

    monkeypatch.setattr(
        trader_bilingual_fill, "_translate_strings", fake_string,
    )
    monkeypatch.setattr(
        trader_bilingual_fill, "_translate_arrays", fake_array,
    )


# ---- Tests ------------------------------------------------------------


def test_half_populated_pair_gets_filled(monkeypatch):
    _install_mock_translator(monkeypatch)
    snap = {
        "momentum_card": {
            "trend_en": "Bullish",
            "trend_zh": None,
        },
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    assert snap["momentum_card"]["trend_en"] == "Bullish"
    assert snap["momentum_card"]["trend_zh"] == "ZH:Bullish"


def test_zh_to_en_direction(monkeypatch):
    _install_mock_translator(monkeypatch)
    snap = {
        "sentiment_card": {
            "analyst_consensus_en": None,
            "analyst_consensus_zh": "买入",
        },
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    assert snap["sentiment_card"]["analyst_consensus_zh"] == "买入"
    assert snap["sentiment_card"]["analyst_consensus_en"] == "EN:买入"


def test_seeder_creates_missing_en_zh_keys_for_legacy_only_snapshot(
    monkeypatch,
):
    """A truly pre-bilingual snapshot has only `<base>` keys — no
    `_en` / `_zh` siblings exist at all. The seeder pass must create
    those keys (as None) so the legacy promotion logic can fire.
    """
    _install_mock_translator(monkeypatch)
    snap = {
        "momentum_card": {
            "trend": "bullish",  # no trend_en, no trend_zh
            "breakout_signals": ["5-day high"],
        },
        "catalysts": [
            {
                "title": "Q2 earnings",
                "summary": "After-hours",
                # No title_en/_zh, no summary_en/_zh.
            },
        ],
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    m = snap["momentum_card"]
    assert m["trend_en"] == "bullish"
    assert m["trend_zh"] == "ZH:bullish"
    assert m["breakout_signals_en"] == ["5-day high"]
    assert m["breakout_signals_zh"] == ["ZH:5-day high"]
    c = snap["catalysts"][0]
    assert c["title_en"] == "Q2 earnings"
    assert c["title_zh"] == "ZH:Q2 earnings"
    assert c["summary_en"] == "After-hours"
    assert c["summary_zh"] == "ZH:After-hours"


def test_legacy_only_promotes_to_en_then_translates_zh(monkeypatch):
    """A pre-bilingual snapshot has only the legacy `<base>` field
    populated. The pass treats that as English-canonical, copies it
    into `_en`, and translates to fill `_zh`.
    """
    _install_mock_translator(monkeypatch)
    snap = {
        "momentum_card": {
            "trend": "bullish",
            "trend_en": None,
            "trend_zh": None,
        },
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    assert snap["momentum_card"]["trend_en"] == "bullish"
    assert snap["momentum_card"]["trend_zh"] == "ZH:bullish"


def test_both_filled_pair_is_untouched(monkeypatch):
    _install_mock_translator(monkeypatch)
    snap = {
        "catalysts": [
            {
                "title_en": "Q2 earnings",
                "title_zh": "二季度财报",
                "summary_en": "After-hours",
                "summary_zh": "盘后发布",
            },
        ],
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    c = snap["catalysts"][0]
    assert c["title_en"] == "Q2 earnings"
    assert c["title_zh"] == "二季度财报"
    assert c["summary_en"] == "After-hours"
    assert c["summary_zh"] == "盘后发布"


def test_both_empty_pair_with_no_legacy_is_untouched(monkeypatch):
    """Genuinely-missing fact: both `_en` and `_zh` are null and there's
    no legacy fallback. The pass leaves both null rather than inventing
    content.
    """
    _install_mock_translator(monkeypatch)
    snap = {
        "trader_news": [
            {
                "headline_en": None,
                "headline_zh": None,
                "summary_en": None,
                "summary_zh": None,
            },
        ],
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    n = snap["trader_news"][0]
    assert n["headline_en"] is None
    assert n["headline_zh"] is None
    assert n["summary_en"] is None
    assert n["summary_zh"] is None


def test_array_pair_with_missing_zh_gets_filled(monkeypatch):
    _install_mock_translator(monkeypatch)
    snap = {
        "momentum_card": {
            "breakout_signals_en": ["5-day high", "channel break"],
            "breakout_signals_zh": [],  # empty array counts as unfilled
        },
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    m = snap["momentum_card"]
    assert m["breakout_signals_en"] == ["5-day high", "channel break"]
    assert m["breakout_signals_zh"] == ["ZH:5-day high", "ZH:channel break"]


def test_heat_card_v2_unavailable_section_gets_confidence_note_filled(
    monkeypatch,
):
    """Real-world shape: heat_card.options_positioning marked
    `unavailable` with only `confidence_note_en` filled. The pass must
    translate the note into `_zh`.
    """
    _install_mock_translator(monkeypatch)
    snap = {
        "heat_card": {
            "options_positioning": {
                "gamma_flip": None, "put_wall": None, "call_wall": None,
                "regime_en": None, "regime_zh": None,
                "confidence": "unavailable",
                "confidence_note_en": "SpotGamma pay-walled.",
                "confidence_note_zh": None,
            },
        },
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    opt = snap["heat_card"]["options_positioning"]
    assert opt["confidence_note_en"] == "SpotGamma pay-walled."
    assert opt["confidence_note_zh"] == "ZH:SpotGamma pay-walled."
    # regime pair is both-null with no legacy → left alone.
    assert opt["regime_en"] is None
    assert opt["regime_zh"] is None


def test_real_world_amd_shape(monkeypatch):
    """Mirrors the live AMD snapshot before the fill pass: every
    legacy field populated, every `_en` / `_zh` sibling null. After
    the pass, every pair should be both-filled.
    """
    _install_mock_translator(monkeypatch)
    snap = {
        "momentum_card": {
            "trend": "bullish",
            "trend_en": None, "trend_zh": None,
            "breakout_signals": ["52-week high", "post-earnings gap"],
            "breakout_signals_en": [],
            "breakout_signals_zh": [],
        },
        "sentiment_card": {
            "analyst_consensus": "Buy",
            "analyst_consensus_en": None,
            "analyst_consensus_zh": None,
            "recent_rating_changes": [
                {
                    "firm": "BofA",
                    "action": "Upgrade",
                    "action_en": None, "action_zh": None,
                    "from": "Hold", "from_en": None, "from_zh": None,
                    "to": "Buy", "to_en": None, "to_zh": None,
                },
            ],
        },
        "catalysts": [
            {
                "title": "Q2 2026 earnings",
                "title_en": None, "title_zh": None,
                "summary": "After-hours; consensus EPS $1.28",
                "summary_en": None, "summary_zh": None,
            },
        ],
        "trader_news": [
            {
                "headline": "Q1 beat on data-center",
                "headline_en": None, "headline_zh": None,
                "summary": "Data-center +47% YoY",
                "summary_en": None, "summary_zh": None,
            },
        ],
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)

    # No null pair survives the pass.
    def _walk_pairs(node):
        for parent, base in trader_bilingual_fill._iter_pairs(node):
            yield parent, base

    for parent, base in _walk_pairs(snap):
        en = parent.get(f"{base}_en")
        zh = parent.get(f"{base}_zh")
        en_filled = trader_bilingual_fill._is_filled(en)
        zh_filled = trader_bilingual_fill._is_filled(zh)
        # Either both filled or both empty — never half.
        assert en_filled == zh_filled, (
            f"{base!r}: en_filled={en_filled} zh_filled={zh_filled}"
        )
        # On this fixture every legacy field was populated, so every
        # pair should now be both-filled.
        assert en_filled, f"{base!r} should be filled via legacy promotion"


def test_translator_failure_leaves_zh_null_rather_than_poisoning_it(
    monkeypatch,
):
    """If the translator subprocess errors, the pass MUST leave the
    missing-side field as null — never copy the source-language text
    into it. (Earlier behavior copied English into `_zh` on failure,
    which made the UI think it had a Chinese translation when in fact
    the user would see English text labelled as Chinese. That was
    worse than null.)
    """
    def fail_strings(values, *, source, target):
        return [None] * len(values)

    def fail_arrays(values, *, source, target):
        return [None] * len(values)

    monkeypatch.setattr(
        trader_bilingual_fill, "_translate_strings", fail_strings,
    )
    monkeypatch.setattr(
        trader_bilingual_fill, "_translate_arrays", fail_arrays,
    )

    snap = {
        "momentum_card": {
            "trend_en": "Bullish", "trend_zh": None,
            "breakout_signals_en": ["channel break"],
            "breakout_signals_zh": [],
        },
    }
    trader_bilingual_fill.ensure_bilingual_completeness(snap)
    # _en untouched.
    assert snap["momentum_card"]["trend_en"] == "Bullish"
    assert snap["momentum_card"]["breakout_signals_en"] == ["channel break"]
    # _zh stays null/empty — NOT poisoned with the English source.
    assert snap["momentum_card"]["trend_zh"] is None
    assert snap["momentum_card"]["breakout_signals_zh"] == []
