"""Tests for the compact (Chinese-only) translation path."""
from __future__ import annotations

import json
from pathlib import Path

from server import claude_runner


def _unit() -> dict:
    return {
        "id": "financial_forecast_valuation",
        "blocks": [
            {"type": "paragraph", "text": {"en": "First paragraph.", "zh": ""}},
            {
                "type": "table",
                "title": {"en": "Scenario Analysis", "zh": ""},
                "headers": [
                    {"en": "Scenario", "zh": ""},
                    {"en": "Return", "zh": "已填"},
                ],
                "rows": [
                    [
                        {"en": "Bear", "zh": ""},
                        "0.8x",
                        {"en": "Growth slows to +80%.", "zh": ""},
                    ]
                ],
            },
        ],
    }


def _write_unit(tmp_path: Path, unit: dict) -> Path:
    path = tmp_path / "unit.en.json"
    path.write_text(json.dumps(unit, ensure_ascii=False), encoding="utf-8")
    return path


def test_collect_blank_zh_slots_order_and_skips():
    slots: list[dict] = []
    claude_runner._collect_blank_zh_slots(_unit(), slots)
    # Plain strings ("0.8x") and already-filled zh ("已填") are skipped;
    # order follows the document.
    assert [slot["en"] for slot in slots] == [
        "First paragraph.",
        "Scenario Analysis",
        "Scenario",
        "Bear",
        "Growth slows to +80%.",
    ]


def test_compact_translates_and_fills_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        count = kw["schema"]["properties"]["zh"]["minItems"]
        return {
            "zh": [f"中文{i}" for i in range(count)],
            "claude_cost_usd": 0.11,
            "claude_duration_ms": 900,
        }, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    unit_path = _write_unit(tmp_path, _unit())
    unit, error = claude_runner._run_bilingual_unit(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        unit_label="section financial_forecast_valuation",
        unit_path=unit_path,
        progress=None,
        timeout_sec=600,
    )
    assert error is None
    schema = captured["schema"]
    assert schema["properties"]["zh"]["minItems"] == 5
    assert schema["properties"]["zh"]["maxItems"] == 5
    prompt = captured["prompt"]
    # Numbered English list, plus the fixed number/date conventions.
    assert "1. First paragraph." in prompt
    assert "5. Growth slows to +80%." in prompt
    assert "$24M" in prompt and "42x" in prompt and "2026 年 2 月 19 日" in prompt
    assert "Do not return the English" in prompt
    # Filled in document order; untouched values preserved.
    assert unit["blocks"][0]["text"]["zh"] == "中文0"
    assert unit["blocks"][1]["title"]["zh"] == "中文1"
    assert unit["blocks"][1]["headers"][0]["zh"] == "中文2"
    assert unit["blocks"][1]["headers"][1]["zh"] == "已填"
    assert unit["blocks"][1]["rows"][0][1] == "0.8x"
    assert unit["blocks"][1]["rows"][0][2]["zh"] == "中文4"
    assert unit["claude_cost_usd"] == 0.11
    assert unit["claude_duration_ms"] == 900


def test_compact_gap_fill_sends_only_blanks(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    unit = _unit()
    # Pre-fill all but one string, as after a chase merge.
    unit["blocks"][0]["text"]["zh"] = "第一段。"
    unit["blocks"][1]["title"]["zh"] = "情景分析"
    unit["blocks"][1]["headers"][0]["zh"] = "情景"
    unit["blocks"][1]["rows"][0][0]["zh"] = "悲观"
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"zh": ["增速放缓至 +80%。"]}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    result, error = claude_runner._run_bilingual_unit(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        unit_label="section financial_forecast_valuation",
        unit_path=_write_unit(tmp_path, unit),
        progress=None,
        timeout_sec=600,
    )
    assert error is None
    assert captured["schema"]["properties"]["zh"]["minItems"] == 1
    assert "Growth slows to +80%." in captured["prompt"]
    assert "First paragraph." not in captured["prompt"].split("English strings:")[1]
    assert result["blocks"][1]["rows"][0][2]["zh"] == "增速放缓至 +80%。"


def test_compact_no_blanks_makes_no_call(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    unit = {"id": "x", "blocks": [{"text": {"en": "Done.", "zh": "完成。"}}]}

    def forbidden(**_kw):
        raise AssertionError("no translation call needed")

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", forbidden
    )
    result, error = claude_runner._run_bilingual_unit(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        unit_label="section x",
        unit_path=_write_unit(tmp_path, unit),
        progress=None,
        timeout_sec=600,
    )
    assert error is None
    assert result["claude_cost_usd"] == 0.0


def test_compact_splits_large_units(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    monkeypatch.setenv("BSH_MEMO_ZH_SPLIT_CHARS", "4000")
    unit = {
        "id": "big",
        "blocks": [
            {"text": {"en": f"Sentence number {i}. " + "x" * 700, "zh": ""}}
            for i in range(8)
        ],
    }
    calls: list[dict] = []

    def fake_runner(**kw):
        calls.append(kw)
        count = kw["schema"]["properties"]["zh"]["minItems"]
        return {
            "zh": [f"译文{i}" for i in range(count)],
            "claude_cost_usd": 0.05,
            "claude_duration_ms": 700,
        }, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    result, error = claude_runner._run_bilingual_unit(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        unit_label="section big",
        unit_path=_write_unit(tmp_path, unit),
        progress=None,
        timeout_sec=600,
    )
    assert error is None
    assert len(calls) == 2
    counts = sorted(
        kw["schema"]["properties"]["zh"]["minItems"] for kw in calls
    )
    assert sum(counts) == 8
    assert "(part 1/2)" in calls[0]["prompt"] or "(part 1/2)" in calls[1]["prompt"]
    # Every slot filled; costs summed, duration is the slower half.
    assert all(b["text"]["zh"] for b in result["blocks"])
    assert result["claude_cost_usd"] == 0.1
    assert result["claude_duration_ms"] == 700


def test_compact_failure_falls_back_to_full_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_ZH_COMPACT", "1")
    calls: list[dict] = []

    def fake_runner(**kw):
        calls.append(kw)
        if "minItems" in str(kw["schema"]):
            return None, "compact exploded"
        filled = _unit()
        for slot in _walk(filled):
            slot["zh"] = slot["zh"] or "中文"
        return {"unit": filled, "claude_cost_usd": 0.3}, None

    def _walk(v):
        out: list[dict] = []
        claude_runner._collect_blank_zh_slots(v, out)
        return out

    events: list[dict] = []

    class _Progress:
        def emit(self, type_, **fields):
            events.append({"type": type_, **fields})

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    unit, error = claude_runner._run_bilingual_unit(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        unit_label="section financial_forecast_valuation",
        unit_path=_write_unit(tmp_path, _unit()),
        progress=_Progress(),
        timeout_sec=600,
    )
    assert error is None
    # Two calls: the failed compact one, then the legacy full-unit one.
    assert len(calls) == 2
    assert calls[1]["schema"] is claude_runner._MEMO_BILINGUAL_UNIT_SCHEMA
    assert any(
        e.get("stage") == "memo_zh_compact_fallback" for e in events
    )
    assert unit["claude_cost_usd"] == 0.3


def test_flag_off_uses_legacy_with_style_note(tmp_path, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ZH_COMPACT", raising=False)
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {"unit": _unit(), "claude_cost_usd": 0.3}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_runner
    )
    unit, error = claude_runner._run_bilingual_unit(
        run_dir=tmp_path,
        company_name="G",
        run_id="r1",
        unit_label="section financial_forecast_valuation",
        unit_path=_write_unit(tmp_path, _unit()),
        progress=None,
        timeout_sec=600,
    )
    assert error is None
    assert captured["schema"] is claude_runner._MEMO_BILINGUAL_UNIT_SCHEMA
    # The number/date conventions now ride along on the legacy prompt too.
    assert "$24M" in captured["prompt"]
    assert "2026 年 2 月 19 日" in captured["prompt"]


def test_split_chars_knob_clamps(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ZH_SPLIT_CHARS", raising=False)
    assert claude_runner._memo_zh_split_chars() == 20_000
    monkeypatch.setenv("BSH_MEMO_ZH_SPLIT_CHARS", "100")
    assert claude_runner._memo_zh_split_chars() == 4_000
    monkeypatch.setenv("BSH_MEMO_ZH_SPLIT_CHARS", "junk")
    assert claude_runner._memo_zh_split_chars() == 20_000
