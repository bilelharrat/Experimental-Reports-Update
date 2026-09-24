"""Round 2 of the Reports improvements, memo_analysis / memo_prep /
memo_inputs side: the length loop that would have saved the ZaiNar
2026-09-23__023008 run (trim one subsection, keep the per-section repairs
that succeeded, deliver small overruns with a warning), the pause after
the English, the cost guard, the cancel-on-failure accounting, the voice
cleaner that rewrites only the lint-banned phrases, the startup recovery
that no longer wipes a delivered run's warnings, the placeholder-free
registry entry, the IC memo on Claude for a Gemini run, and the wiring of
the report-only gates (claims, consistency, red team, quality metrics).

Every model call is a fake; nothing here reads the real data/ folder.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest
import yaml

from server import (
    claude_runner,
    job_progress,
    memo_analysis,
    memo_docx_renderer,
    memo_engine,
    memo_fact_check,
    memo_inputs,
    memo_prep,
    memo_structure,
    storage,
)
from test_memo_analysis import (  # noqa: F401 — memo_env is a fixture
    _events,
    _make_memo_report,
    _memo_package,
    _write_memo_package,
    memo_env,
)

FIXTURES = Path(__file__).parent / "fixtures"
ZAINAR_V2_DRAFT = FIXTURES / "zainar_v2_draft.en.json"
ZAINAR_V1_PACKAGE = FIXTURES / "zainar_claude_v1.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _analysis_pass(**_kwargs):
    return {
        "summary": "A pass summary long enough to look like work.",
        "key_findings": [],
        "supporting_evidence": [],
        "disconfirming_evidence": [],
        "open_questions": [],
        "memo_uses": [],
    }, None


def _words(section: dict) -> int:
    return memo_docx_renderer.section_en_word_count(section)


def _shorten_en(node: dict, keep_words: int) -> bool:
    text = node.get("en") if isinstance(node, dict) else None
    if not isinstance(text, str):
        return False
    words = text.split()
    if len(words) <= keep_words:
        return False
    node["en"] = " ".join(words[:keep_words]).rstrip(",;:") + "."
    return True


def _cut_blocks_to(blocks: list, target: int) -> list:
    """What a real trim does: shorter table cells, fewer bullets, shorter
    paragraphs — never a heading, a table, a card or a row removed."""
    kept = json.loads(json.dumps(blocks))

    def over() -> bool:
        return _words({"blocks": kept}) > target

    for block in kept:
        if not over():
            return kept
        if block.get("type") == "table":
            for row in block.get("rows") or []:
                for cell in row:
                    _shorten_en(cell, 14)
    for block in kept:
        if not over():
            return kept
        if block.get("type") == "bullets":
            items = block.get("items") or []
            while len(items) > 2 and over():
                items.pop()
            for item in items:
                _shorten_en(item, 16)
    for block in reversed(kept):
        if not over():
            return kept
        if block.get("type") == "paragraph":
            _shorten_en(block.get("text"), 24)
    return kept


@pytest.fixture
def pipeline_env(memo_env, monkeypatch):
    """A fast-pipeline run with every paid call faked."""
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    monkeypatch.setenv("BSH_MEMO_FAST_ENGLISH_PACKAGE_RETRIES", "0")
    monkeypatch.delenv("BSH_MEMO_RENDER_PDF_PREVIEWS", raising=False)
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", _analysis_pass)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_company_type_classifier",
        lambda **_kw: {"type": "other", "source": "test"},
    )
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package_parallel",
        lambda **_kw: ({"memo_package": _memo_package()}, None),
    )
    report, run_dir = _make_memo_report(memo_env)
    job_progress.ProgressLog(memo_prep.stream_path(run_dir)).emit(
        "job_init", kind="memo", report_id=report["id"]
    )
    return report, run_dir


def _run_pipeline(report, run_dir, *, company_name="Generalist, Inc.", company_slug="generalist-inc"):
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    return memo_analysis._run_fast_memo_pipeline(
        report_id=report["id"],
        report=storage.get_report(report["id"]),
        run_dir=run_dir,
        stream=stream,
        company_name=company_name,
        company_slug=company_slug,
        run_id=str(report["run_id"]),
        memo_paths_abs=memo_analysis._memo_paths_abs(report),
        analysis_session_path=None,
        lessons_path=None,
    )


# ---- the regression set ------------------------------------------------------


def test_the_zainar_packages_on_disk_still_validate():
    """The Claude v1 memo renders as delivered; the Claude v2 draft fails
    exactly the three errors its run died on, and two of them are still
    blocking once small overruns are tolerated."""
    memo_docx_renderer.validate_package(_load(ZAINAR_V1_PACKAGE))
    assert memo_docx_renderer.english_package_validation_errors(
        _load(ZAINAR_V1_PACKAGE), editorial_risk_checks=False
    ) == []

    draft = _load(ZAINAR_V2_DRAFT)
    errors = memo_docx_renderer.english_package_validation_errors(
        draft, editorial_risk_checks=False
    )
    assert len(errors) == 3
    assert errors[0].startswith("sources[17].url is required")
    overruns = {item["section"]: item for item in memo_analysis._over_cap_sections(draft)}
    assert overruns["risks"]["words"] == 5269 and overruns["risks"]["cap"] == 5200
    assert overruns["company_team"]["words"] == 2918 and overruns["company_team"]["cap"] == 2470
    blocking = memo_analysis._blocking_validation_errors(errors, draft)
    assert len(blocking) == 2
    assert not any("section risks" in err for err in blocking)
    assert any("section company_team" in err for err in blocking)
    assert [item["section"] for item in memo_analysis._tolerated_overruns(errors, draft)] == ["risks"]


def test_word_budget_overrun_parses_the_renderer_message():
    draft = _load(ZAINAR_V2_DRAFT)
    errors = memo_docx_renderer.english_package_validation_errors(
        draft, editorial_risk_checks=False
    )
    risks = memo_analysis._word_budget_overrun(errors[2], draft)
    assert risks == {"section": "risks", "words": 5269, "cap": 5200, "target": 2600, "over_pct": 1.3}
    assert memo_analysis._word_budget_overrun(errors[0], draft) is None
    # An unparseable wording that still carries the marker falls back to
    # the package's own numbers.
    fallback = memo_analysis._word_budget_overrun(
        "section risks is past its -word hard cap", draft
    )
    assert fallback["section"] == "risks" and fallback["words"] == 5269


def test_length_warning_names_the_delivered_overruns(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    warnings = memo_analysis._RunWarnings()
    memo_analysis._length_warning(run_dir, warnings, _load(ZAINAR_V2_DRAFT))
    items = [item for item in warnings.items if item["gate"] == "length"]
    assert {item["section"] for item in items} == {"company_team", "risks"}
    assert all(item["code"] == "section_over_cap" for item in items)
    assert "5269 words against a 5200-word cap" in next(
        item["summary_en"] for item in items if item["section"] == "risks"
    )
    # Nothing over its cap: no warning.
    quiet = memo_analysis._RunWarnings()
    memo_analysis._length_warning(run_dir, quiet, _memo_package())
    assert not quiet


# ---- the ZaiNar replay: trim, keep the repairs that succeeded, accept ----


def _fake_trim(calls):
    def run_section_trim(run_dir, *, section_id, subsection_path, target_words, hard_cap_words, structure=None, progress=None, role="REPAIR", company_name=None, timeout_sec=600):
        calls.append({"section_id": section_id, "target": target_words, "cap": hard_cap_words, "role": role, "company_name": company_name})
        payload = json.loads(Path(subsection_path).read_text(encoding="utf-8"))
        before = _words(payload)
        payload["blocks"] = _cut_blocks_to(payload["blocks"], target_words)
        Path(subsection_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "words_before": before, "words_after": _words(payload), "cost_usd": 0.05, "error": None}

    return run_section_trim


def _fake_envelope_repair(calls):
    def run_memo_envelope_repair(*, run_dir, company_name, run_id, envelope, findings, progress=None, timeout_sec=900):
        calls.append(findings)
        fixed = json.loads(json.dumps(envelope))
        fixed["sources"][17]["url"] = "https://example.com/press/zainar-emerges"
        return {"envelope": fixed, "claude_cost_usd": 0.3}, None

    return run_memo_envelope_repair


def test_zainar_draft_is_accepted_after_one_trim_per_section(pipeline_env, monkeypatch):
    """The wave assembles company_team 18% and risks 1.3% over their caps
    and one source without a URL. One trim of the largest subsection per
    section brings both under cap; the envelope repair adds the URL; the
    run is accepted — no whole-package repair, no regeneration."""
    report, run_dir = pipeline_env
    draft = _load(ZAINAR_V2_DRAFT)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package",
        lambda **_kw: ({"analysis_artifacts": {}, "memo_package": json.loads(json.dumps(draft))}, None),
    )
    trims: list[dict] = []
    monkeypatch.setattr(claude_runner, "run_section_trim", _fake_trim(trims), raising=False)
    envelope_calls: list = []
    monkeypatch.setattr(claude_runner, "run_memo_envelope_repair", _fake_envelope_repair(envelope_calls))
    monkeypatch.setattr(
        claude_runner, "run_memo_section_repair",
        lambda **_kw: pytest.fail("no section needed a repair after the trims"),
    )
    monkeypatch.setattr(
        claude_runner, "run_memo_package_structure_repair",
        lambda **_kw: pytest.fail("the whole-package repair must not run"),
    )

    result = _run_pipeline(report, run_dir, company_name="ZaiNar, Inc.", company_slug="zainar-inc")

    assert result.get("ok") is True, result
    assert sorted(call["section_id"] for call in trims) == ["company_team", "risks"]
    assert all(call["role"] == "REPAIR" for call in trims)
    assert len(envelope_calls) == 1 and "sources[17].url" in envelope_calls[0][0]
    accepted = _load(run_dir / "logs" / "memo_package.en.json")
    assert memo_analysis._over_cap_sections(accepted) == []
    assert accepted["sources"][17]["url"].startswith("https://")
    stages = [e.get("stage") for e in _events(memo_prep.stream_path(run_dir)) if e.get("type") == "stage"]
    assert stages.count("memo_section_trimmed") == 2
    assert "memo_package_envelope_repair_shortcut" in stages
    assert "memo_package_sectional_repair_applied" in stages
    assert "memo_package_structure_repair_succeeded" in stages
    assert "memo_package_length_accepted" not in stages


def test_zainar_draft_is_accepted_when_the_risks_repair_is_too_large(pipeline_env, monkeypatch):
    """With every trim failing, the replay of the failed run: the envelope
    and company_team repairs succeed, the risks repair cannot fit its
    answer in one call. The successes are KEPT, and the one remaining
    error — risks 1.3% over its cap — is delivered with a length warning
    instead of failing the run."""
    report, run_dir = pipeline_env
    draft = _load(ZAINAR_V2_DRAFT)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package",
        lambda **_kw: ({"analysis_artifacts": {}, "memo_package": json.loads(json.dumps(draft))}, None),
    )
    monkeypatch.setattr(
        claude_runner, "run_section_trim",
        lambda *_a, **_k: {"ok": False, "words_before": 0, "words_after": 0, "cost_usd": 0.0, "error": "trim unavailable"},
    )
    envelope_calls: list = []
    monkeypatch.setattr(claude_runner, "run_memo_envelope_repair", _fake_envelope_repair(envelope_calls))
    section_calls: list[dict] = []

    def section_repair(**kwargs):
        section_calls.append(kwargs)
        if kwargs["section_id"] == "risks":
            return None, (
                "claude exited 1: the model never returned output matching the "
                "schema: its answer never parsed as JSON. The last attempt sent "
                "34,881 bytes in one tool call, so the ask is too big for one "
                "call — split what it must return."
            )
        section = json.loads(json.dumps(kwargs["section"]))
        section["blocks"] = _cut_blocks_to(section["blocks"], 2400)
        return {"section": section, "claude_cost_usd": 0.6}, None

    monkeypatch.setattr(claude_runner, "run_memo_section_repair", section_repair)
    monkeypatch.setattr(
        claude_runner, "run_memo_package_structure_repair",
        lambda **_kw: pytest.fail("the whole-package repair must not run"),
    )

    result = _run_pipeline(report, run_dir, company_name="ZaiNar, Inc.", company_slug="zainar-inc")

    assert result.get("ok") is True, result
    assert sorted(call["section_id"] for call in section_calls) == ["company_team", "risks"]
    # The per-section repair asks for edits, not a re-emitted section (I2).
    assert all(call.get("mode") == "edits" for call in section_calls)
    accepted = _load(run_dir / "logs" / "memo_package.en.json")
    overruns = memo_analysis._over_cap_sections(accepted)
    assert [item["section"] for item in overruns] == ["risks"]
    assert overruns[0]["words"] == 5269
    assert accepted["sources"][17]["url"].startswith("https://")
    events = _events(memo_prep.stream_path(run_dir))
    applied = next(e for e in events if e.get("stage") == "memo_package_sectional_repair_applied")
    assert applied["repaired"] == ["company_team"]
    assert applied["envelope_repaired"] is True
    assert applied["too_large"] == ["risks"]
    assert "risks" in applied["failed"]
    accepted_stage = next(e for e in events if e.get("stage") == "memo_package_length_accepted")
    assert [s["section"] for s in accepted_stage["sections"]] == ["risks"]
    recorded = _load(run_dir / "logs" / "length_warnings.json")
    assert recorded["sections"][0]["section"] == "risks"
    stages = [e.get("stage") for e in events if e.get("type") == "stage"]
    assert "memo_package_structure_repair_succeeded" in stages
    assert "memo_package_structure_repair_failed" not in stages


def test_a_large_overrun_still_fails_when_nothing_can_fix_it(pipeline_env, monkeypatch):
    """Today's behaviour for anything past the tolerance: company_team 18%
    over, no trim, every repair failing — the run fails as before."""
    report, run_dir = pipeline_env
    draft = _load(ZAINAR_V2_DRAFT)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package",
        lambda **_kw: ({"analysis_artifacts": {}, "memo_package": json.loads(json.dumps(draft))}, None),
    )
    monkeypatch.setattr(claude_runner, "run_section_trim", lambda *_a, **_k: {"ok": False, "error": "no"})
    monkeypatch.setattr(claude_runner, "run_memo_envelope_repair", lambda **_kw: (None, "envelope repair failed"))
    monkeypatch.setattr(claude_runner, "run_memo_section_repair", lambda **_kw: (None, "repair failed"))
    monkeypatch.setattr(claude_runner, "run_memo_package_structure_repair", lambda **_kw: (None, "timed out"))

    result = _run_pipeline(report, run_dir, company_name="ZaiNar, Inc.", company_slug="zainar-inc")

    assert result.get("ok") is False
    assert "renderer validation" in str(result.get("error"))


def test_repair_by_section_keeps_successes_and_names_too_large(tmp_path, monkeypatch):
    package = _load(ZAINAR_V2_DRAFT)
    findings = memo_docx_renderer.english_package_validation_errors(package, editorial_risk_checks=False)
    monkeypatch.setattr(claude_runner, "run_memo_envelope_repair", _fake_envelope_repair([]))

    def section_repair(**kwargs):
        if kwargs["section_id"] == "risks":
            return None, claude_runner.MemoStageError(
                "the answer did not fit in one call", code="output_too_large"
            )
        section = json.loads(json.dumps(kwargs["section"]))
        section["blocks"] = _cut_blocks_to(section["blocks"], 2400)
        return {"section": section}, None

    monkeypatch.setattr(claude_runner, "run_memo_section_repair", section_repair)
    progress = job_progress.ProgressLog(tmp_path / "stream.jsonl")
    outcome = memo_analysis._repair_package_by_section(
        run_dir=tmp_path, company_name="ZaiNar, Inc.", run_id="r", package=package,
        findings=findings, progress=progress, stream=progress,
    )
    assert outcome.repaired == ["company_team"]
    assert outcome.too_large == ["risks"]
    assert outcome.envelope_repaired is True
    assert outcome.unmapped == []
    # The input package is untouched; the outcome carries the successes.
    assert package["sources"][17].get("url") in (None, "")
    assert outcome.package["sources"][17]["url"].startswith("https://")
    by_id = {s["id"]: s for s in outcome.package["sections"]}
    assert _words(by_id["company_team"]) <= 2470
    assert _words(by_id["risks"]) == 5269
    events = _events(tmp_path / "stream.jsonl")
    failed = next(e for e in events if e.get("type") == "phase_timing" and e.get("phase") == "english_repair:risks" and e.get("status") == "failed")
    assert failed["error_code"] == "output_too_large"


def test_trim_rewrites_only_the_largest_subsection(tmp_path, monkeypatch):
    package = _load(ZAINAR_V2_DRAFT)
    trims: list[dict] = []
    monkeypatch.setattr(claude_runner, "run_section_trim", _fake_trim(trims), raising=False)
    progress = job_progress.ProgressLog(tmp_path / "stream.jsonl")
    trimmed: set[str] = set()
    done = memo_analysis._trim_oversized_sections(run_dir=tmp_path, package=package, progress=progress, trimmed=trimmed)
    assert sorted(done) == ["company_team", "risks"]
    assert trimmed == {"company_team", "risks"}
    assert memo_analysis._over_cap_sections(package) == []
    # Never twice for the same section in one attempt.
    assert memo_analysis._trim_oversized_sections(run_dir=tmp_path, package=package, progress=progress, trimmed=trimmed) == []
    structure = memo_structure.for_package(package)
    by_id = {s["id"]: s for s in package["sections"]}
    for section_id in ("company_team", "risks"):
        section_def = next(d for d in structure.sections if d.id == section_id)
        plan = claude_runner._section_piece_plan(tmp_path, section_id, section_def)
        # The re-assembled section still cuts cleanly into its subsections.
        assert claude_runner._split_section_draft(by_id[section_id], plan) is not None
    assert (tmp_path / "logs" / "english_units" / "trim" / "risks" / "01.json").exists()


def test_a_failed_trim_leaves_the_section_alone(tmp_path, monkeypatch):
    package = _load(ZAINAR_V2_DRAFT)
    monkeypatch.setattr(claude_runner, "run_section_trim", lambda *_a, **_k: {"ok": False, "error": "no"}, raising=False)
    progress = job_progress.ProgressLog(tmp_path / "stream.jsonl")
    before = json.dumps(package, sort_keys=True)
    assert memo_analysis._trim_oversized_sections(run_dir=tmp_path, package=package, progress=progress, trimmed=set()) == []
    assert json.dumps(package, sort_keys=True) == before
    stages = [e.get("stage") for e in _events(tmp_path / "stream.jsonl")]
    assert stages.count("memo_section_trim_failed") == 2


def test_surgical_quality_repair_tolerates_a_small_overrun(memo_env, monkeypatch):
    """A repaired package that is otherwise clean but a few percent over
    one cap is accepted by the surgical repair (it used to be thrown away
    and the package regenerated)."""
    report, run_dir = _make_memo_report(memo_env)
    draft = _load(ZAINAR_V2_DRAFT)
    draft["sources"][17]["url"] = "https://example.com/press"
    by_id = {s["id"]: s for s in draft["sections"]}
    by_id["company_team"]["blocks"] = _cut_blocks_to(by_id["company_team"]["blocks"], 2400)
    assert [i["section"] for i in memo_analysis._over_cap_sections(draft)] == ["risks"]
    monkeypatch.setattr(claude_runner, "run_memo_package_sectional_repair", lambda **_kw: (json.loads(json.dumps(draft)), None))
    monkeypatch.setattr(memo_analysis, "_memo_package_prerender_quality_findings", lambda *_a, **_k: [])
    monkeypatch.setattr(memo_analysis, "_memo_pin_check_repair_enabled", lambda: False)
    progress = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    repaired = memo_analysis._surgical_quality_repair(
        run_dir=run_dir, company_name="ZaiNar, Inc.", run_id="r", candidate=draft,
        findings=["banned phrase somewhere"], attempt=1, progress=progress,
    )
    assert isinstance(repaired, dict)
    assert memo_analysis._accepted_english_package is not None
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "memo_package.en.json").write_text(json.dumps(draft), encoding="utf-8")
    assert memo_analysis._accepted_english_package(run_dir) is not None


# ---- I14: cancel the side agents on every failure path ------------------------


class _FakeChaser:
    def __init__(self, cost=0.7):
        self.calls: list = []
        self.post_cancel_cost_usd = cost
        self.has_units = False

    def on_spine(self, _payload):
        return None

    def on_section(self, *_args, **_kwargs):
        return None

    def shutdown(self, cancel=False):
        self.calls.append(cancel)
        return {"cancelled": 1, "reaped": 0, "post_cancel_cost_usd": self.post_cancel_cost_usd}


def test_english_failure_cancels_the_chaser_and_counts_its_spend(memo_env, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_FAST_ENGLISH_PACKAGE_RETRIES", "0")
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", lambda **_kw: (None, "English package pass crashed"))
    monkeypatch.setattr(claude_runner, "is_transient_claude_error", lambda _m: False)
    report, run_dir = _make_memo_report(memo_env)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    chaser = _FakeChaser(cost=0.7)
    result = memo_analysis._run_fast_synthesis(
        run_dir=run_dir, stream=stream, company_name="Generalist, Inc.", company_slug="generalist-inc",
        run_id=str(report["run_id"]), memo_paths={k: str(v) for k, v in memo_analysis._memo_paths_abs(report).items()},
        research_dir=run_dir / "research", analysis_session_path=None, lessons_path=None, scope_check=None,
        warnings=[], zh_chaser=chaser, speculator=None, cost_usd=1.0, worker_duration_ms=0,
        started_at=memo_analysis._now_iso(), started_monotonic=0.0, report_id=report["id"],
    )
    assert result["ok"] is False
    assert chaser.calls == [True]
    assert result["cost_usd"] == pytest.approx(1.7)


def test_shutdown_side_agent_falls_back_without_the_cancel_argument():
    class Legacy:
        def __init__(self):
            self.stopped = False

        def shutdown(self):
            self.stopped = True

    legacy = Legacy()
    assert memo_analysis._shutdown_side_agent(legacy, cancel=True) == 0.0
    assert legacy.stopped is True
    assert memo_analysis._shutdown_side_agent(None) == 0.0
    assert memo_analysis._shutdown_side_agent(_FakeChaser(cost=0.3), cancel=True) == 0.3


# ---- I19: the voice cleaner rewrites only the banned phrases ------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Valuation Multiple Underwriting and Return Profile", "Valuation Multiple Underwriting and Return Profile"),
        (
            "Underwriting the $1.0B post-money valuation against public operating peers.",
            "Underwriting the $1.0B post-money valuation against public operating peers.",
        ),
        ("Insurance underwriters price the fleet risk.", "Insurance underwriters price the fleet risk."),
        ("We underwrite the licensing fallback here.", "We rely on the licensing fallback here."),
        ("BSH underwrites a 3x base case.", "BSH relies on a 3x base case."),
        ("We are underwriting a 2028 exit.", "We are relying on a 2028 exit."),
        ("we have underwritten the pipeline.", "we have relied on the pipeline."),
        ("The underwriting case for ZaiNar is thin.", "The investment case for ZaiNar is thin."),
        ("Underwriting posture: cautious.", "Investment posture: cautious."),
        ("our underwriting assumption is 18 months of runway.", "our investment assumption is 18 months of runway."),
    ],
)
def test_voice_cleaner_rewrites_only_the_lint_banned_phrases(text, expected):
    assert memo_analysis._rewrite_memo_package_voice_text(text) == expected


def test_voice_cleaner_leaves_the_gemini_v1_headings_readable():
    """The word-level rewrite produced 'Valuation Multiple investment case
    and Return Profile' and 'investment case the $1.0B post-money
    valuation' in the Gemini v1 ZaiNar memo; the originals now survive."""
    for original in (
        "Valuation Multiple Underwriting and Return Profile",
        "Underwriting the $1.0B post-money valuation against public operating peers",
    ):
        rewritten = memo_analysis._rewrite_memo_package_voice_text(original)
        assert rewritten == original
        assert "investment case the" not in rewritten
        assert "Multiple investment case" not in rewritten


# ---- I20: startup recovery keeps a delivered run's warnings -------------------


def _finished_run(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    package_path = _write_memo_package(run_dir)
    memo_paths_abs = memo_analysis._memo_paths_abs(report)
    memo_docx_renderer.render_memos(
        package_path,
        out_en=memo_paths_abs["en"],
        out_zh=memo_paths_abs["zh"],
        manifest_path=run_dir / "logs" / "run_manifest.md",
        inventory_path=run_dir / "logs" / "file_inventory.md",
    )
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir), truncate=True)
    stream.emit("job_init", kind="memo", report_id=report["id"], company_id="generalist-inc", run_id=report["run_id"])
    stream.emit("done", report_id=report["id"], memo_paths={k: str(v) for k, v in memo_paths_abs.items()}, cost_usd=3.5, duration_ms=1000)
    return report, run_dir


def test_recovery_leaves_a_delivered_run_with_warnings_alone(memo_env):
    report, _run_dir = _finished_run(memo_env)
    items = [memo_analysis._warning_item(gate="coverage", language="EN", summary_en="One pass missing", summary_zh="缺少一个分析", code="pass_missing")]
    storage.update_report(
        report["id"], status="complete_with_warnings", stage="Memo ready (quality warnings)",
        quality_warnings=["Coverage: one pass missing"], quality_warnings_zh=["覆盖：缺少一个分析"], quality_warning_items=items,
    )
    assert memo_analysis.recover_stale_reports() == 0
    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert updated["quality_warning_items"] == items
    assert updated["quality_warnings"] == ["Coverage: one pass missing"]


def test_recovery_refinalize_preserves_the_gates_it_does_not_recompute(memo_env):
    report, _run_dir = _finished_run(memo_env)
    coverage = memo_analysis._warning_item(gate="coverage", language="EN", summary_en="One pass missing", summary_zh="缺少一个分析", code="pass_missing")
    cost = memo_analysis._warning_item(gate="cost", language="EN", summary_en="Ceiling reached", summary_zh="达到上限", code="cost_ceiling")
    quality = memo_analysis._warning_item(gate="quality", language="EN", summary_en="banned phrase", summary_zh="禁用词", code="banned")
    parity = memo_analysis._warning_item(gate="chinese_parity", language="ZH", summary_en="parity", summary_zh="对照", code="parity")
    storage.update_report(
        report["id"], status="failed_during_analysis", failure_phase="resume", error="socket closed",
        quality_warnings=["Coverage: one pass missing", "Cost ceiling reached — skipped: IC memo", "Memo quality gate found 1 P0 finding. See x.", "Chinese parity check found 1 P0 finding"],
        quality_warnings_zh=["覆盖", "费用", "质量", "对照"],
        quality_warning_items=[coverage, quality, cost, parity],
    )
    assert memo_analysis.recover_stale_reports() == 1
    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert updated["error"] is None and updated["failure_phase"] is None
    assert updated["quality_warning_items"] == [coverage, cost]
    assert updated["quality_warnings"] == ["Coverage: one pass missing", "Cost ceiling reached — skipped: IC memo"]
    assert updated["quality_warnings_zh"] == ["覆盖", "费用"]
    assert updated["claude_cost_usd"] == 3.5


def test_recovery_refinalize_without_other_gates_is_a_clean_complete(memo_env):
    report, _run_dir = _finished_run(memo_env)
    quality = memo_analysis._warning_item(gate="quality", language="EN", summary_en="banned phrase", summary_zh="禁用词", code="banned")
    storage.update_report(
        report["id"], status="failed_during_analysis", failure_phase="resume", error="socket closed",
        quality_warnings=["Memo quality gate found 1 P0 finding."], quality_warnings_zh=["质量"], quality_warning_items=[quality],
    )
    assert memo_analysis.recover_stale_reports() == 1
    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete"
    assert updated["quality_warning_items"] is None
    assert updated["quality_warnings"] is None


def test_recovery_leaves_a_paused_run_alone(memo_env):
    report, _run_dir = _finished_run(memo_env)
    storage.update_report(report["id"], status=memo_analysis.PAUSED_AFTER_ENGLISH_STATUS)
    assert memo_analysis.recover_stale_reports() == 0
    assert storage.get_report(report["id"])["status"] == memo_analysis.PAUSED_AFTER_ENGLISH_STATUS


# ---- I21: the registry entry a run reads carries no placeholders --------------

ZAINAR_ENTRY = yaml.safe_load(
    """
id: zainar-inc
name: ZaiNar, Inc.
status: private
website: https://zainartech.com
latest_funding:
  round: Growth / stealth-exit round
  amount_usd: $100,000,000+
  date: '2026-02-19'
positioning:
  category: network-based positioning platform
  source_refs:
  - label: ZaiNar company record
    source_class: company
    as_of: '2026-02-19'
metrics:
- label: ARR
  value: ~$24M
  unit: USD
  as_of: '2026-06-13'
  confidence: low
  source_class: demo placeholder (v2 design mock)
  note: Placeholder from the v2 design mock; no document backs it.
  source_refs:
  - label: Demo placeholder (v2 design mock) — not evidence
    source_class: demo placeholder (v2 design mock)
- label: YoY Growth
  value: +180%
  as_of: '2026-06-13'
  confidence: low
  source_class: demo placeholder (v2 design mock)
  note: Placeholder from the v2 design mock; no document backs it.
- label: Valuation
  value: $1.0B+
  unit: USD
  as_of: '2026-02-19'
  confidence: high
  source_class: company
  source_refs:
  - label: Stealth-exit funding disclosure
    source_class: company
- label: TAM
  value: ~$45B
  unit: USD
  as_of: '2030'
  confidence: low
  source_class: demo placeholder (v2 design mock)
  note: Placeholder from the v2 design mock; no market model backs it.
competitors:
- id: nextnav
  name: NextNav
  status: Public
  source_refs:
  - label: Public market comp set
    source_class: public
"""
)


def test_filtered_registry_entry_strips_the_placeholder_metrics():
    entry, excluded = memo_inputs.filtered_registry_entry(ZAINAR_ENTRY)
    assert [m["label"] for m in entry["metrics"]] == ["Valuation"]
    assert len(excluded) == 3
    assert excluded[0].startswith("ARR (demo placeholder")
    assert entry["registry_note"] == "3 fields excluded: placeholders with no document"
    # Everything else is untouched, and the input is not mutated.
    assert entry["competitors"] == ZAINAR_ENTRY["competitors"]
    assert entry["latest_funding"] == ZAINAR_ENTRY["latest_funding"]
    assert entry["positioning"] == ZAINAR_ENTRY["positioning"]
    assert len(ZAINAR_ENTRY["metrics"]) == 4
    assert "$24M" not in yaml.safe_dump(entry)
    clean, none_excluded = memo_inputs.filtered_registry_entry({"id": "acme", "metrics": [{"label": "ARR", "value": "$1M", "source_class": "company"}]})
    assert none_excluded == [] and "registry_note" not in clean


def test_the_run_reads_a_placeholder_free_registry_entry(memo_env, tmp_path):
    memo_env.mkdir(parents=True, exist_ok=True)
    (memo_env / "companies.yaml").write_text(yaml.safe_dump([ZAINAR_ENTRY], allow_unicode=True), encoding="utf-8")
    run_dir = tmp_path / "run"
    staged = memo_inputs.stage_run_inputs("zainar-inc", tmp_path / "research", run_dir)
    assert len(staged["registry_placeholders_excluded"]) == 3
    path = run_dir / "logs" / memo_inputs.REGISTRY_ENTRY_FILENAME
    assert Path(staged["registry_entry"]) == path
    entries = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert [e["id"] for e in entries] == ["zainar-inc"]
    assert [m["label"] for m in entries[0]["metrics"]] == ["Valuation"]
    # The agents are pointed at the staged file; a run without one keeps
    # reading data/companies.yaml.
    assert memo_analysis._run_companies_yaml(run_dir) == path
    assert memo_analysis._run_companies_yaml(tmp_path / "other") == memo_prep.COMPANIES_FILE
    # The registry-entry extractors find the entry in the one-entry file.
    assert "ARR" not in (claude_runner._extract_company_registry_entry_yaml(path, "zainar-inc") or "")
    assert "Valuation" in memo_engine._registry_entry_text(path, "zainar-inc")


def test_staging_records_the_exclusions_on_the_run(memo_env):
    memo_env.mkdir(parents=True, exist_ok=True)
    (memo_env / "companies.yaml").write_text(yaml.safe_dump([ZAINAR_ENTRY], allow_unicode=True), encoding="utf-8")
    report, run_dir = _make_memo_report(memo_env)
    storage.update_report(report["id"], company_id="zainar-inc")
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    record = memo_analysis._stage_run_inputs(storage.get_report(report["id"]), run_dir, run_dir / "research", stream)
    assert record["registry_placeholders_excluded"] == 3
    assert record["registry_entry"].endswith("logs/registry_entry.yaml")
    events = _events(memo_prep.stream_path(run_dir))
    excluded = next(e for e in events if e.get("stage") == "memo_registry_placeholders_excluded")
    assert "3 registry field(s) excluded" in excluded["message"]


# ---- I17: the IC memo runs on Claude whatever wrote the LP memo ---------------


def test_ic_memo_runs_on_claude_for_a_gemini_run(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    memo_engine.register_run_engine(run_dir, "gemini")
    seen: dict = {}

    def fake_ic_memo(**kwargs):
        seen["engine"] = memo_engine.run_engine(kwargs["run_dir"])
        seen["companies_yaml_path"] = kwargs["companies_yaml_path"]
        return {"ok": False, "error": "stop here", "cost_usd": 0.0}

    monkeypatch.setattr(claude_runner, "run_internal_diligence_memo", fake_ic_memo)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    result = memo_analysis._run_internal_diligence_memo(
        report_id=report["id"], run_dir=run_dir, company_name="Generalist, Inc.", company_slug="generalist-inc",
        run_id=str(report["run_id"]), memo_paths_abs=memo_analysis._memo_paths_abs(report),
        internal_paths_abs=memo_analysis._internal_memo_paths_abs(report), stream=stream, result={},
        analysis_session_path=None, lessons_path=None, scope_check=None, warnings=[],
    )
    assert result["ok"] is False
    assert seen["engine"] == "claude"
    assert seen["companies_yaml_path"] == memo_prep.COMPANIES_FILE
    assert memo_engine.run_engine(run_dir) == "gemini"
    stages = [e.get("stage") for e in _events(memo_prep.stream_path(run_dir))]
    assert "internal_memo_engine" in stages
    memo_engine.clear_run_engine(run_dir)


# ---- I11: pause after the English ----------------------------------------------


def _english_first_env(pipeline_env, monkeypatch):
    report, run_dir = pipeline_env
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_english_package",
        lambda **_kw: ({"analysis_artifacts": {}, "memo_package": _memo_package(body_zh="")}, None),
    )
    return report, run_dir


def test_pause_after_english_stops_before_the_chinese_and_resumes(pipeline_env, monkeypatch):
    report, run_dir = _english_first_env(pipeline_env, monkeypatch)
    storage.update_report(report["id"], pause_after_english=True)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_bilingual_package_parallel",
        lambda **_kw: pytest.fail("the Chinese must not start on a paused run"),
    )

    memo_analysis._run(report["id"])

    paths = memo_analysis._memo_paths_abs(report)
    updated = storage.get_report(report["id"])
    assert updated["status"] == memo_analysis.PAUSED_AFTER_ENGLISH_STATUS
    assert updated["stage"] == memo_analysis.ENGLISH_PAUSED_STAGE
    assert updated["paused_after_english_at"]
    assert updated["failure_phase"] is None
    assert paths["en"].exists()
    assert (run_dir / "logs" / "memo_package.en.json").exists()
    events = _events(memo_prep.stream_path(run_dir))
    assert events[-1]["type"] == "done" and events[-1]["paused_after_english"] is True
    assert any(e.get("stage") == "memo_paused_after_english" for e in events)
    # A paused run is a deliberate terminal state for the startup sweep.
    assert memo_analysis.recover_stale_reports() == 0
    assert storage.get_report(report["id"])["status"] == memo_analysis.PAUSED_AFTER_ENGLISH_STATUS
    assert memo_analysis._chinese_retry_requested(updated, run_dir) is True

    # What the resume endpoint records before the worker starts.
    storage.update_report(report["id"], status="analyzing", resume_from_status=updated["status"])
    calls: list = []

    def translate(**kwargs):
        calls.append(kwargs)
        return {"memo_package": _memo_package(), "claude_cost_usd": 0.2}, None

    monkeypatch.setattr(claude_runner, "run_memo_fast_bilingual_package_parallel", translate)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", lambda **_kw: pytest.fail("the English is kept"))

    memo_analysis._resume(report["id"])

    final = storage.get_report(report["id"])
    assert final["status"] == "complete", final.get("quality_warnings")
    assert len(calls) == 1
    assert paths["zh"].exists()
    events = _events(memo_prep.stream_path(run_dir))
    assert events[0]["type"] == "job_init" and events[0]["continue_after_pause"] is True
    assert events[-1]["type"] == "done"


def test_chinese_retry_is_not_requested_once_the_chinese_exists(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    (run_dir / "logs").mkdir(exist_ok=True)
    (run_dir / "logs" / "memo_package.en.json").write_text("{}", encoding="utf-8")
    paused = {"status": "analyzing", "resume_from_status": memo_analysis.PAUSED_AFTER_ENGLISH_STATUS}
    assert memo_analysis._chinese_retry_requested(paused, run_dir) is True
    _write_memo_package(run_dir)
    assert memo_analysis._chinese_retry_requested(paused, run_dir) is False
    assert memo_analysis._chinese_retry_requested({"failure_phase": "chinese_package"}, run_dir) is True


def test_bootstrap_records_the_pause_and_the_ceiling_only_when_set(memo_env, monkeypatch):
    memo_env.mkdir(parents=True, exist_ok=True)
    (memo_env / "companies.yaml").write_text(
        yaml.safe_dump([{"id": "acme-ai", "name": "Acme AI", "status": "private"}]), encoding="utf-8"
    )
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    seen: dict = {}
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda report_id: seen.update(storage.get_report(report_id) or {}))
    memo_prep.bootstrap_memo_run("acme-ai", pause_after_english=True, cost_ceiling_usd="25")
    assert seen["pause_after_english"] is True
    assert seen["cost_ceiling_usd"] == 25.0
    seen.clear()
    memo_prep.bootstrap_memo_run("acme-ai")
    assert "pause_after_english" not in seen and "cost_ceiling_usd" not in seen
    with pytest.raises(ValueError, match="cost_ceiling_usd"):
        memo_prep.bootstrap_memo_run("acme-ai", cost_ceiling_usd=0)
    with pytest.raises(ValueError, match="cost_ceiling_usd"):
        memo_prep.bootstrap_memo_run("acme-ai", cost_ceiling_usd="lots")


# ---- I13: the cost guard ----------------------------------------------------


def test_cost_ceiling_precedence(monkeypatch):
    monkeypatch.delenv(memo_analysis.COST_CEILING_ENV, raising=False)
    assert memo_analysis._cost_ceiling_usd(None) == 60.0
    monkeypatch.setenv(memo_analysis.COST_CEILING_ENV, "12.5")
    assert memo_analysis._cost_ceiling_usd({}) == 12.5
    assert memo_analysis._cost_ceiling_usd({"cost_ceiling_usd": 3}) == 3.0
    assert memo_analysis._cost_ceiling_usd({"cost_ceiling_usd": "nope"}) == 12.5
    monkeypatch.setenv(memo_analysis.COST_CEILING_ENV, "garbage")
    assert memo_analysis._cost_ceiling_usd({}) == 60.0


def test_cost_guard_records_each_stop_and_warns_once(memo_env):
    report, run_dir = _make_memo_report(memo_env)
    storage.update_report(report["id"], cost_ceiling_usd=2.0)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    assert memo_analysis._cost_guard_stop(report_id=report["id"], run_dir=run_dir, cost_usd=1.99, phase="Chinese version", stream=stream) is None
    stop = memo_analysis._cost_guard_stop(report_id=report["id"], run_dir=run_dir, cost_usd=2.0, phase="Chinese version", stream=stream)
    assert stop["phase"] == "Chinese version" and stop["ceiling_usd"] == 2.0
    memo_analysis._cost_guard_stop(report_id=report["id"], run_dir=run_dir, cost_usd=2.0, phase="IC decision memo", stream=stream)
    assert [s["phase"] for s in memo_analysis._cost_guard_stops(run_dir)] == ["Chinese version", "IC decision memo"]
    warnings = memo_analysis._RunWarnings()
    memo_analysis._cost_warning(run_dir, warnings)
    assert len(warnings.items) == 1
    assert warnings.items[0]["gate"] == "cost" and warnings.items[0]["code"] == "cost_ceiling"
    assert "Chinese version, IC decision memo" in warnings.en[0]


def test_the_ceiling_delivers_the_english_alone_with_a_cost_warning(pipeline_env, monkeypatch):
    report, run_dir = _english_first_env(pipeline_env, monkeypatch)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_analysis_pass",
        lambda **_kw: ({**_analysis_pass()[0], "claude_cost_usd": 0.4}, None),
    )
    storage.update_report(report["id"], cost_ceiling_usd=1.0)
    monkeypatch.setattr(
        claude_runner, "run_memo_fast_bilingual_package_parallel",
        lambda **_kw: pytest.fail("the Chinese must not start past the ceiling"),
    )
    fake_metrics = types.ModuleType("server.memo_quality_metrics")
    fake_metrics.compute = lambda run_dir, package, report: {"words_total": 42, "traced_pct": 0.5}
    monkeypatch.setitem(sys.modules, "server.memo_quality_metrics", fake_metrics)

    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert updated["english_only"] is True
    assert updated["failure_phase"] == "chinese_package"
    gates = {item["gate"] for item in updated["quality_warning_items"]}
    assert {"cost", "chinese_package"} <= gates
    assert updated["quality_metrics"] == {"words_total": 42, "traced_pct": 0.5}
    assert (run_dir / "logs" / "quality_metrics.json").exists()
    assert (run_dir / "logs" / "cost_guard.json").exists()
    assert memo_analysis._memo_paths_abs(report)["en"].exists()
    events = _events(memo_prep.stream_path(run_dir))
    stops = [e for e in events if e.get("stage") == "memo_cost_ceiling"]
    assert [s["phase"] for s in stops][:2] == ["analysis artifacts", "Chinese version"]
    assert events[-1]["type"] == "done" and events[-1]["english_only"] is True


# ---- I12: the red team -------------------------------------------------------------


def test_red_team_challenges_ride_the_repair_and_the_rest_are_warnings(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    monkeypatch.setenv(memo_analysis.RED_TEAM_FLAG, "1")
    package = _memo_package(body_zh="")
    quoted = "deployment depth and valuation support are visible"
    challenges = [
        {"claim": quoted, "section_id": "executive_summary", "why": "no deployment evidence on file", "severity": "high"},
        {"claim": "carrier revenue is contracted", "section_id": "company_overview", "why": "MOUs only", "severity": "medium"},
    ]
    seen_call: dict = {}

    def red_team(run_dir, package, *, role="SPINE_CHECK", company_name=None, progress=None, **_kw):
        seen_call.update(role=role, company_name=company_name, progress=progress)
        return {"challenges": challenges, "cost_usd": 0.12, "error": None}

    monkeypatch.setattr(claude_runner, "run_memo_red_team", red_team)
    seen: dict = {}

    def fake_repair(**kwargs):
        seen["findings"] = kwargs["findings"]
        repaired = json.loads(json.dumps(kwargs["candidate"]))
        block = repaired["sections"][0]["blocks"][0]
        block["text"]["en"] = block["text"]["en"].replace(quoted, "deployment depth is not yet evidenced")
        return repaired

    monkeypatch.setattr(memo_analysis, "_surgical_quality_repair", fake_repair)
    progress = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    repaired, cost = memo_analysis._run_red_team_pass(
        run_dir=run_dir, company_name="Generalist, Inc.", run_id="r", package=package, attempt=2,
        progress=progress, stream=progress, report_id=report["id"], cost_so_far=1.0,
    )
    assert cost == 0.12
    assert seen_call == {"role": "SPINE_CHECK", "company_name": "Generalist, Inc.", "progress": progress}
    assert quoted not in json.dumps(repaired)
    assert seen["findings"][0].startswith("section executive_summary: red-team challenge")
    # The finding maps to its section, so the per-section repair takes it.
    assert claude_runner._section_for_validation_error(package, seen["findings"][0]) == "executive_summary"
    record = _load(run_dir / "logs" / "red_team.json")
    assert record["repaired"] is True
    assert [c["claim"] for c in record["unresolved"]] == ["carrier revenue is contracted"]
    warnings = memo_analysis._RunWarnings()
    memo_analysis._red_team_warning(run_dir, warnings)
    assert [i["gate"] for i in warnings.items] == ["red_team"]
    assert warnings.items[0]["section"] == "company_overview"
    assert warnings.items[0]["code"] == "red_team_challenge"


def test_red_team_is_off_with_the_switch_off_or_past_the_ceiling(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    package = _memo_package(body_zh="")
    progress = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    monkeypatch.setattr(claude_runner, "run_memo_red_team", lambda *_a, **_k: pytest.fail("off"))
    monkeypatch.setenv(memo_analysis.RED_TEAM_FLAG, "0")
    assert memo_analysis._run_red_team_pass(
        run_dir=run_dir, company_name="G", run_id="r", package=package, attempt=1,
        progress=progress, stream=progress, report_id=report["id"], cost_so_far=0.0,
    ) == (package, 0.0)
    # On, but the run is already at its ceiling: the pass is skipped.
    monkeypatch.setenv(memo_analysis.RED_TEAM_FLAG, "1")
    storage.update_report(report["id"], cost_ceiling_usd=1.0)
    assert memo_analysis._run_red_team_pass(
        run_dir=run_dir, company_name="G", run_id="r", package=package, attempt=1,
        progress=progress, stream=progress, report_id=report["id"], cost_so_far=1.5,
    ) == (package, 0.0)
    assert not (run_dir / "logs" / "red_team.json").exists()
    assert [s["phase"] for s in memo_analysis._cost_guard_stops(run_dir)] == ["red-team pass"]


# ---- I6 / I7: the fact-check gates are report-only -------------------------


def test_claims_and_consistency_gates_wire_the_fact_check(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    seen: dict = {}

    def check_quotes(run_dir, *, company_id=None):
        seen["company_id"] = company_id
        return {"checked": 3, "matched": 2, "unmatched": [{"quote": "ARR reached $24M", "url": "https://example.com/a", "claim": "ARR"}]}

    monkeypatch.setattr(memo_fact_check, "check_quotes", check_quotes)
    monkeypatch.setattr(
        memo_fact_check, "metric_conflicts",
        lambda package: [{"metric": "ARR", "values": ["$24M", "$18M"], "locations": ["executive_summary", "business_financials"]}],
        raising=False,
    )
    warnings = memo_analysis._RunWarnings()
    memo_analysis._claims_warning(run_dir, warnings, "generalist-inc")
    memo_analysis._consistency_warning(run_dir, warnings, _memo_package())
    assert seen["company_id"] == "generalist-inc"
    gates = [item["gate"] for item in warnings.items]
    assert gates == ["claims", "consistency"]
    assert warnings.items[0]["code"] == "quote_unmatched"
    assert "ARR reached $24M" in warnings.items[0]["summary_en"]
    assert warnings.items[1]["summary_en"].startswith("ARR: $24M, $18M")
    # Without the functions (or when they raise) nothing is added.
    monkeypatch.delattr(memo_fact_check, "check_quotes", raising=False)
    monkeypatch.setattr(memo_fact_check, "metric_conflicts", lambda package: 1 / 0, raising=False)
    quiet = memo_analysis._RunWarnings()
    memo_analysis._claims_warning(run_dir, quiet)
    memo_analysis._consistency_warning(run_dir, quiet, _memo_package())
    assert not quiet


def test_pin_warnings_are_recorded_and_reported(memo_env, monkeypatch):
    """The pin check's P1 warnings (base_case_not_echoed) land in
    logs/pin_warnings.json and ship as gate "pins"; the P0 gate is untouched."""
    from server import memo_pin_check

    report, run_dir = _make_memo_report(memo_env)
    monkeypatch.setattr(memo_analysis, "_memo_pin_check_enabled", lambda: True)
    monkeypatch.setattr(memo_analysis, "_memo_shared_facts_from_disk", lambda _run_dir: {"stage": "late"})
    warning = memo_pin_check.PinFinding(
        code="base_case_not_echoed", location="executive_summary paragraph 1",
        pin="Base case: 2.4x MOIC by 2030", detail="the executive summary states a different outcome", severity="P1",
    )
    result = memo_pin_check.PinCheckResult(findings=[], pins_checked=3, warnings=[warning])
    monkeypatch.setattr(memo_pin_check, "check_package_pins", lambda _c, _f: result)
    monkeypatch.setattr(memo_pin_check, "render_markdown_report", lambda *_a, **_k: "# pins\n")
    progress = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    assert memo_analysis._run_memo_pin_check(run_dir=run_dir, candidate=_memo_package(), progress=progress) == []
    recorded = _load(run_dir / "logs" / "pin_warnings.json")
    assert recorded[0]["code"] == "base_case_not_echoed"
    warnings = memo_analysis._RunWarnings()
    memo_analysis._pins_warning(run_dir, warnings)
    assert [i["gate"] for i in warnings.items] == ["pins"]
    assert warnings.items[0]["code"] == "base_case_not_echoed"
    assert warnings.items[0]["section"] == "executive_summary"
    assert warnings.items[0]["severity"] == "warning"


def test_quality_metrics_are_optional(memo_env, monkeypatch):
    report, run_dir = _make_memo_report(memo_env)
    monkeypatch.setitem(sys.modules, "server.memo_quality_metrics", None)
    assert memo_analysis._quality_metrics(run_dir, _memo_package(), {}) is None
    broken = types.ModuleType("server.memo_quality_metrics")
    broken.compute = lambda *_a: 1 / 0
    monkeypatch.setitem(sys.modules, "server.memo_quality_metrics", broken)
    assert memo_analysis._quality_metrics(run_dir, _memo_package(), {}) is None
