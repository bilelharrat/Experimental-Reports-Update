"""Risk-card wording is repaired, then warned — never a regeneration; the
private inventory is stamped report-only.

The renderer splits its risk-card checks (R11 FIX 1): the card SHAPE stays
blocking, the WORDING ("Why it matters" names an economic consequence,
"What we watch" is a signal, the declared rows) becomes a quality finding
that rides the surgical repair; whatever is left ships as a warning.

The run's private inventory is stamped under ``run.private_items_on_file``,
a key the renderer's source gate does not read: that gate tightens once
``run.private_inventory`` exists, and no writer prompt yet tells the model
to cite private documents by exact title or ``private_ref``.
"""
from __future__ import annotations

import json

import yaml

from server import claude_runner, job_progress, memo_analysis, memo_prep, storage
from test_memo_analysis import (  # noqa: F401 — memo_env is a fixture
    _events,
    _make_memo_report,
    _memo_package,
    memo_env,
)

_THIN_WHY = "Deployments still need on-site engineering work at every site we visited."


def _with_thin_why(package: dict) -> dict:
    """The fixture package with its first "Why it matters" row stripped of
    any economic consequence (the card still has its shape)."""
    for section in package["sections"]:
        for block in section.get("blocks") or []:
            if block.get("type") != "table" or block.get("layout") != "key_value":
                continue
            for row in block.get("rows") or []:
                if isinstance(row[0], dict) and row[0].get("en") == "Why it matters":
                    row[1] = {"en": _THIN_WHY, "zh": row[1].get("zh", "")}
                    return package
    raise AssertionError("fixture package has no risk card")


def _analysis_pass(**_kwargs):
    return {
        "summary": "A pass summary long enough to look like work.",
        "key_findings": [],
        "supporting_evidence": [],
        "disconfirming_evidence": [],
        "open_questions": [],
        "memo_uses": [],
    }, None


def _run_pipeline(memo_env, monkeypatch, *, english, repair):
    monkeypatch.setenv("BSH_MEMO_FAST_PIPELINE", "1")
    monkeypatch.setenv("BSH_MEMO_FAST_ENGLISH_PACKAGE_RETRIES", "1")
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    monkeypatch.delenv("BSH_MEMO_RENDER_PDF_PREVIEWS", raising=False)
    report, run_dir = _make_memo_report(memo_env)
    stream = job_progress.ProgressLog(memo_prep.stream_path(run_dir))
    stream.emit("job_init", kind="memo", report_id=report["id"])
    english_calls: list = []
    repair_calls: list = []

    def fake_english(**kwargs):
        english_calls.append(kwargs.get("validation_feedback"))
        return {"analysis_artifacts": {}, "memo_package": english()}, None

    def fake_repair(**kwargs):
        repair_calls.append(list(kwargs.get("validation_errors") or []))
        return repair()

    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", _analysis_pass)
    monkeypatch.setattr(claude_runner, "run_memo_fast_english_package", fake_english)
    monkeypatch.setattr(claude_runner, "run_memo_package_structure_repair", fake_repair)
    monkeypatch.setattr(
        claude_runner,
        "run_memo_fast_bilingual_package_parallel",
        lambda **_kwargs: ({"memo_package": _memo_package()}, None),
    )
    result = memo_analysis._run_fast_memo_pipeline(
        report_id=report["id"],
        report=storage.get_report(report["id"]),
        run_dir=run_dir,
        stream=stream,
        company_name="Generalist, Inc.",
        company_slug="generalist-inc",
        run_id=str(report["run_id"]),
        memo_paths_abs=memo_analysis._memo_paths_abs(report),
        analysis_session_path=None,
        lessons_path=None,
    )
    return result, run_dir, english_calls, repair_calls


def test_risk_card_wording_rides_the_repair_and_never_costs_a_regeneration(memo_env, monkeypatch):
    result, run_dir, english_calls, repair_calls = _run_pipeline(
        memo_env,
        monkeypatch,
        english=lambda: _with_thin_why(_memo_package(body_zh="")),
        repair=lambda: (None, "repair agent unavailable"),
    )
    assert result.get("ok") is True
    # One generation, one repair attempt, and no second English attempt
    # although a retry was allowed.
    assert len(english_calls) == 1
    assert len(repair_calls) == 1
    assert any("Why it matters must state an economic consequence" in f for f in repair_calls[0])
    events = _events(memo_prep.stream_path(run_dir))
    warned = [e for e in events if e.get("stage") == "memo_risk_card_wording_warning"]
    assert warned and "Why it matters" in warned[0]["findings"][0]
    assert not any(e.get("stage") == "memo_fast_english_package_validation_retry" for e in events)
    accepted = json.loads((run_dir / "logs" / "memo_package.en.json").read_text(encoding="utf-8"))
    assert _THIN_WHY in json.dumps(accepted)


def test_a_repair_that_clears_the_blocking_findings_is_kept_with_risk_wording_left(memo_env, monkeypatch):
    from test_memo_analysis import _SCAFFOLD_BODY_EN

    result, run_dir, english_calls, repair_calls = _run_pipeline(
        memo_env,
        monkeypatch,
        english=lambda: _with_thin_why(_memo_package(body_en=_SCAFFOLD_BODY_EN, body_zh="")),
        # Clears the scaffold label, keeps the thin "Why it matters".
        repair=lambda: ({"memo_package": _with_thin_why(_memo_package(body_zh=""))}, None),
    )
    assert result.get("ok") is True
    assert len(english_calls) == 1 and len(repair_calls) == 1
    assert any("scaffold_label" in f for f in repair_calls[0])
    events = _events(memo_prep.stream_path(run_dir))
    assert any(e.get("stage") == "memo_quality_surgical_repair_succeeded" for e in events)
    assert any(e.get("stage") == "memo_risk_card_wording_warning" for e in events)


def test_finalize_records_leftover_risk_card_wording_as_a_warning(memo_env, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_GENERATE_INTERNAL", "0")
    report, run_dir = _make_memo_report(memo_env)

    def fake_run_investment_memo(**_kwargs):
        (run_dir / "logs").mkdir(parents=True, exist_ok=True)
        (run_dir / "logs" / "memo_package.json").write_text(
            json.dumps(_with_thin_why(_memo_package()), ensure_ascii=False), encoding="utf-8"
        )
        return {"ok": True, "cost_usd": 1.0, "duration_ms": 1000}

    monkeypatch.setattr(claude_runner, "run_investment_memo", fake_run_investment_memo)
    memo_analysis._run(report["id"])

    updated = storage.get_report(report["id"])
    assert updated["status"] == "complete_with_warnings"
    assert "Risk cards: 1 wording finding left to fix" in updated["quality_warnings"]
    assert len(updated["quality_warnings_zh"]) == len(updated["quality_warnings"])
    items = [item for item in updated["quality_warning_items"] if item["gate"] == "risk_cards"]
    assert len(items) == 1
    assert items[0]["code"] == "risk_card_wording"
    assert items[0]["section"] == "investment_risk"
    assert items[0]["severity"] == "warning"
    # Resume must never read this warning as an English quality failure.
    for text in updated["quality_warnings"]:
        if text.startswith("Risk cards"):
            assert "quality gate" not in text.lower() and "memo quality" not in text.lower()


def test_retry_chinese_accepts_an_english_package_with_risk_card_wording(tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    package = _with_thin_why(_memo_package(body_zh=""))
    (run_dir / "logs" / "memo_package.en.json").write_text(
        json.dumps(package, ensure_ascii=False), encoding="utf-8"
    )
    assert memo_analysis._accepted_english_package(run_dir) == package


# ---- private inventory: report-only ------------------------------------------------------


class _Progress:
    def __init__(self) -> None:
        self.events: list = []

    def emit(self, *args, **kwargs) -> None:
        self.events.append((args, kwargs))


def test_the_private_inventory_is_stamped_report_only(memo_env, tmp_path):
    run_dir = tmp_path / "run"
    (run_dir / "logs").mkdir(parents=True)
    candidate = _memo_package(body_zh="")
    candidate.setdefault("run", {})["private_inventory"] = [{"id": "stale"}]
    memo_analysis._attach_memo_source_urls(
        run_dir=run_dir,
        candidate=candidate,
        company_id="generalist-inc",
        progress=_Progress(),
    )
    run = candidate["run"]
    assert run[memo_analysis.PRIVATE_ITEMS_KEY] == [
        {
            "id": "deck1",
            "kind": "research_document",
            "title": "Company investor materials",
            "ref": "investor_materials.pdf",
        }
    ]
    # The key the renderer's source gate reads is never stamped (and a
    # stale one is removed), so a URL-less private source keeps today's
    # private_material_on_file rule.
    assert "private_inventory" not in run
    assert run["private_material_on_file"] is True


def _private_company(memo_env, *, status="private"):
    memo_env.mkdir(parents=True, exist_ok=True)
    (memo_env / "companies.yaml").write_text(
        yaml.safe_dump([{"id": "generalist-inc", "name": "Generalist, Inc.", "status": status}]),
        encoding="utf-8",
    )


def _diligence_items(report, run_dir, package=None):
    warnings = memo_analysis._RunWarnings()
    memo_analysis._private_diligence_warning(report, run_dir, warnings, package)
    return warnings


def test_no_diligence_warning_for_a_private_company_with_nothing_on_file(memo_env):
    _private_company(memo_env)
    report, run_dir = _make_memo_report(memo_env)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    package = _memo_package()
    package.setdefault("run", {})[memo_analysis.PRIVATE_ITEMS_KEY] = []
    (run_dir / "logs" / "memo_package.en.json").write_text(json.dumps(package), encoding="utf-8")

    warnings = _diligence_items(report, run_dir)
    assert warnings.en == [memo_analysis.NO_DILIGENCE_WARNING[0]]
    assert warnings.zh == [memo_analysis.NO_DILIGENCE_WARNING[1]]
    assert warnings.items[0]["gate"] == "private_diligence"
    assert warnings.items[0]["code"] == "no_private_material"

    # Material on file, a stored package from before the stamp, or a public
    # company: no warning.
    package["run"][memo_analysis.PRIVATE_ITEMS_KEY] = [{"id": "deck1", "kind": "research_document", "title": "Deck", "ref": "d.pdf"}]
    assert not _diligence_items(report, run_dir, package)
    assert not _diligence_items(report, run_dir, {"run": {}})
    _private_company(memo_env, status="public")
    assert not _diligence_items(report, run_dir, {"run": {memo_analysis.PRIVATE_ITEMS_KEY: []}})


def test_no_diligence_warning_reads_the_older_key_on_stored_packages(memo_env):
    _private_company(memo_env)
    report, run_dir = _make_memo_report(memo_env)
    assert _diligence_items(report, run_dir, {"run": {"private_inventory": []}}).en == [
        memo_analysis.NO_DILIGENCE_WARNING[0]
    ]
