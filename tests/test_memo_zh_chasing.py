"""Unit tests for the speculative Chinese chasing machinery (Stage 3)."""
from __future__ import annotations

import json
import threading

from server import claude_runner


def _loc(en: str, zh: str = "") -> dict:
    return {"en": en, "zh": zh}


def _chaser(tmp_path, **kwargs) -> claude_runner.BilingualChaser:
    return claude_runner.BilingualChaser(
        run_dir=tmp_path,
        company_name="Test Co",
        run_id="run-1",
        **kwargs,
    )


def _section(section_id: str, body_en: str = "Alpha.") -> dict:
    return {
        "id": section_id,
        "title": _loc(f"{section_id} title"),
        "blocks": [{"type": "paragraph", "text": _loc(body_en)}],
    }


def _fill_unit(unit: dict) -> dict:
    def fill(node):
        if isinstance(node, dict):
            if "en" in node and "zh" in node and not node["zh"]:
                node["zh"] = f"中文:{node['en']}"
            for value in node.values():
                fill(value)
        elif isinstance(node, list):
            for value in node:
                fill(value)

    fill(unit)
    return unit


def test_chaser_submits_snapshot_files(tmp_path, monkeypatch):
    """The chase unit must read the section as it was at hook time —
    later repairs mutate the live object and must not leak in."""
    release = threading.Event()
    read_payloads: list[dict] = []

    def fake_unit(*, unit_path, **kwargs):
        release.wait(timeout=5)
        payload = json.loads(unit_path.read_text(encoding="utf-8"))
        read_payloads.append(payload)
        unit = _fill_unit(json.loads(json.dumps(payload)))
        unit["claude_cost_usd"] = 0.1
        unit["claude_duration_ms"] = 10
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    chaser = _chaser(tmp_path)
    section = _section("executive_summary")
    chaser.on_section("executive_summary", section)
    # Simulate a later surgical repair rewriting the live English object.
    section["blocks"][0]["text"]["en"] = "REPAIRED."
    release.set()
    outcome = chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    assert read_payloads[0]["blocks"][0]["text"]["en"] == "Alpha."
    assert "executive_summary" in outcome["units"]
    snapshot = (
        tmp_path / "logs" / "bilingual_units" / "chase"
        / "executive_summary.en.json"
    )
    assert snapshot.exists()


def test_chaser_collect_and_merge_adopts_zh(tmp_path, monkeypatch):
    def fake_unit(*, unit_path, **kwargs):
        unit = _fill_unit(json.loads(unit_path.read_text(encoding="utf-8")))
        unit["claude_cost_usd"] = 0.25
        unit["claude_duration_ms"] = 100
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    chaser = _chaser(tmp_path)
    package = {
        "company": {"descriptor": _loc("Automation systems")},
        "sources": [{"title": _loc("Data room")}],
        "sections": [_section("executive_summary"), _section("investment_risk")],
    }
    chaser.on_spine(
        {"package_skeleton": {k: v for k, v in package.items() if k != "sections"}}
    )
    for section in package["sections"]:
        chaser.on_section(section["id"], section)
    outcome = chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    assert sorted(outcome["units"]) == [
        "envelope",
        "executive_summary",
        "investment_risk",
    ]
    assert outcome["cost_usd"] == 0.75

    stats = chaser.merge_into(package, outcome["units"])
    assert stats["blank_after"] == 0
    assert stats["adopted"] == stats["blank_before"]
    assert package["company"]["descriptor"]["zh"] == "中文:Automation systems"
    assert package["sections"][0]["blocks"][0]["text"]["zh"] == "中文:Alpha."


def test_chaser_stale_english_dropped_then_left_blank(tmp_path, monkeypatch):
    def fake_unit(*, unit_path, **kwargs):
        unit = _fill_unit(json.loads(unit_path.read_text(encoding="utf-8")))
        unit["claude_cost_usd"] = 0.1
        unit["claude_duration_ms"] = 10
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    chaser = _chaser(tmp_path)
    section = _section("executive_summary")
    chaser.on_section("executive_summary", section)
    outcome = chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    # A repair changed the English after the chase snapshot.
    section["blocks"][0]["text"]["en"] = "Rewritten sentence."
    stats = chaser.merge_into({"sections": [section]}, outcome["units"])
    # Title adopted (en unchanged), body dropped (en drifted) → still blank.
    assert section["title"]["zh"] == "中文:executive_summary title"
    assert section["blocks"][0]["text"]["zh"] == ""
    assert stats["blank_after"] == 1


def test_chaser_join_timeout_marks_unit_missed(tmp_path, monkeypatch):
    release = threading.Event()

    def slow_unit(**kwargs):
        release.wait(timeout=5)
        return None, "too late anyway"

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", slow_unit)
    chaser = _chaser(tmp_path)
    chaser.on_section("executive_summary", _section("executive_summary"))
    outcome = chaser.collect(join_timeout_sec=0.05)
    assert outcome["missed"] == ["executive_summary"]
    assert outcome["units"] == {}
    release.set()
    chaser.shutdown()


def test_chaser_hook_exceptions_do_not_propagate(tmp_path):
    chaser = _chaser(tmp_path)
    # A payload json.dumps cannot serialize raises inside _submit; the hook
    # must swallow it (the English pass can never be sunk by the chaser).
    chaser.on_spine({"package_skeleton": {"company": object()}})
    chaser.on_section("executive_summary", {"id": "x", "bad": object()})
    assert not chaser.has_units
    chaser.shutdown()


def test_chaser_unmatched_section_unit_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr(
        claude_runner,
        "_run_bilingual_unit",
        lambda **kwargs: (
            _fill_unit(
                json.loads(kwargs["unit_path"].read_text(encoding="utf-8"))
            ),
            None,
        ),
    )
    chaser = _chaser(tmp_path)
    chaser.on_section("executive_summary", _section("executive_summary"))
    outcome = chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    package = {"sections": [_section("investment_risk")]}
    stats = chaser.merge_into(package, outcome["units"])
    assert stats["dropped_units"] == 1
    assert package["sections"][0]["blocks"][0]["text"]["zh"] == ""


def test_chaser_duplicate_submissions_are_ignored(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_unit(*, unit_label, unit_path, **kwargs):
        calls.append(unit_label)
        return (
            _fill_unit(json.loads(unit_path.read_text(encoding="utf-8"))),
            None,
        )

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    chaser = _chaser(tmp_path)
    section = _section("executive_summary")
    chaser.on_section("executive_summary", section)
    chaser.on_section("executive_summary", section)
    chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    assert len(calls) == 1


def test_chase_env_knobs_parse_and_clamp(monkeypatch):
    monkeypatch.delenv("BSH_MEMO_ZH_CHASE_WORKERS", raising=False)
    assert claude_runner._memo_zh_chase_workers() == 4
    monkeypatch.setenv("BSH_MEMO_ZH_CHASE_WORKERS", "99")
    assert claude_runner._memo_zh_chase_workers() == 6
    monkeypatch.setenv("BSH_MEMO_ZH_CHASE_WORKERS", "garbage")
    assert claude_runner._memo_zh_chase_workers() == 4
    monkeypatch.delenv("BSH_MEMO_ZH_CHASE_JOIN_TIMEOUT_SEC", raising=False)
    assert claude_runner._memo_zh_chase_join_timeout_sec() == 900.0
    monkeypatch.setenv("BSH_MEMO_ZH_CHASE_JOIN_TIMEOUT_SEC", "60")
    assert claude_runner._memo_zh_chase_join_timeout_sec() == 60.0

    from server import memo_analysis

    monkeypatch.delenv("BSH_MEMO_ZH_CHASING", raising=False)
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    assert memo_analysis._memo_zh_chasing_enabled() is False
    monkeypatch.setenv("BSH_MEMO_ZH_CHASING", "1")
    assert memo_analysis._memo_zh_chasing_enabled() is True
    # Chasing without the parallel English path has nothing to chase.
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    assert memo_analysis._memo_zh_chasing_enabled() is False


class _RecordingStream:
    def __init__(self):
        self.events: list[dict] = []
        self._lock = threading.Lock()

    def emit(self, type_, **fields):
        with self._lock:
            self.events.append({"type": type_, **fields})

    def snapshot(self, type_, phase=None):
        with self._lock:
            return [
                e
                for e in self.events
                if e["type"] == type_ and (phase is None or e.get("phase") == phase)
            ]


def test_chase_terminal_events_emit_at_unit_completion(tmp_path, monkeypatch):
    """The finished row must appear when the translation completes — not
    minutes later at the Phase-4 join (the 920s-wall-for-75s-work bug)."""

    def fake_unit(*, unit_path, **kwargs):
        unit = _fill_unit(json.loads(unit_path.read_text(encoding="utf-8")))
        unit["claude_cost_usd"] = 0.1
        unit["claude_duration_ms"] = 10
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", fake_unit)
    stream = _RecordingStream()
    chaser = _chaser(tmp_path, stream=stream)
    chaser.on_section("executive_summary", _section("executive_summary"))

    # The terminal events must arrive WITHOUT calling collect().
    deadline = 5.0
    import time as _time

    waited = 0.0
    while not stream.snapshot("thread_finished") and waited < deadline:
        _time.sleep(0.02)
        waited += 0.02
    finished_rows = stream.snapshot(
        "phase_timing", phase="zh_chase:executive_summary"
    )
    assert any(e["status"] == "finished" for e in finished_rows), (
        "unit completion must emit its terminal events before the join"
    )
    done_row = [e for e in finished_rows if e["status"] == "finished"][0]
    assert done_row["duration_ms"] < 5000, "row must show real runtime"

    outcome = chaser.collect(join_timeout_sec=5)
    chaser.shutdown()
    assert "executive_summary" in outcome["units"]
    # collect() must not re-emit the terminal events.
    finished_after = [
        e
        for e in stream.snapshot(
            "phase_timing", phase="zh_chase:executive_summary"
        )
        if e["status"] == "finished"
    ]
    assert len(finished_after) == 1


def test_chase_abandoned_unit_never_double_emits(tmp_path, monkeypatch):
    release = threading.Event()

    def slow_unit(*, unit_path, **kwargs):
        release.wait(timeout=5)
        unit = _fill_unit(json.loads(unit_path.read_text(encoding="utf-8")))
        return unit, None

    monkeypatch.setattr(claude_runner, "_run_bilingual_unit", slow_unit)
    stream = _RecordingStream()
    chaser = _chaser(tmp_path, stream=stream)
    chaser.on_section("executive_summary", _section("executive_summary"))
    outcome = chaser.collect(join_timeout_sec=0.05)
    assert outcome["missed"] == ["executive_summary"]
    failed_rows = [
        e
        for e in stream.snapshot(
            "phase_timing", phase="zh_chase:executive_summary"
        )
        if e["status"] == "failed"
    ]
    assert len(failed_rows) == 1

    # Let the worker finish late; it must stay silent.
    release.set()
    chaser._futures["executive_summary"].result(timeout=5)
    chaser.shutdown()
    rows = stream.snapshot("phase_timing", phase="zh_chase:executive_summary")
    terminal = [e for e in rows if e["status"] in ("finished", "failed")]
    assert len(terminal) == 1 and terminal[0]["status"] == "failed"


# The real cell text from the Databricks Gemini run of 2026-09-19: Gemini put
# the English back in the zh half of nine scorecard cells.
_ENGLISH_IN_ZH = (
    "Massive and expanding data and AI software TAM driven by enterprise "
    "cloud modernization and agentic AI pipelines."
)


def test_english_left_in_the_zh_half_still_counts_as_untranslated():
    """Asking whether a Chinese slot is FILLED was never the same question as
    whether it is TRANSLATED. Live on 2026-09-19 nine scorecard cells shipped
    in English because the slot was not blank, so every gap-fill skipped them
    and only the rendered-document gate noticed — too late to act on."""
    node = {"en": _ENGLISH_IN_ZH, "zh": _ENGLISH_IN_ZH}
    assert claude_runner._zh_untranslated(node) is True
    assert claude_runner._has_blank_zh({"cell": node}) is True
    assert claude_runner._count_blank_zh({"cell": node}) == 1


def test_a_short_non_chinese_zh_half_is_left_alone():
    """A zh half that is a number, a ticker or a proper noun carries no CJK
    either and is already correct — the rule must not chase those."""
    for zh in ("27.1x", "Databricks", "$7B", "2026-09-19", "IPO"):
        node = {"en": zh, "zh": zh}
        assert claude_runner._zh_untranslated(node) is False, zh


def test_a_translated_cell_is_not_chased():
    node = {"en": _ENGLISH_IN_ZH, "zh": "企业云现代化与智能体式 AI 流水线驱动的数据与 AI 软件市场空间庞大且持续扩张。"}
    assert claude_runner._zh_untranslated(node) is False
    assert claude_runner._count_blank_zh({"cell": node}) == 0


def test_adoption_replaces_an_english_filled_zh_half():
    """The chase merge adopted only into a blank slot, so a cell Gemini had
    filled with English could never be corrected by a later translation."""
    source = {"cell": {"en": _ENGLISH_IN_ZH, "zh": _ENGLISH_IN_ZH}}
    translated = {"cell": {"en": _ENGLISH_IN_ZH, "zh": "企业云现代化驱动的数据与 AI 软件市场空间庞大。"}}
    claude_runner._adopt_zh_translations(source, translated)
    assert source["cell"]["zh"] == "企业云现代化驱动的数据与 AI 软件市场空间庞大。"
