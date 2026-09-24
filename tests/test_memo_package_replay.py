"""Stored English-package attempts as regression fixtures (R11 FIX 5), and
the replay harness that measures the gate against everything on disk.

The fixtures are three real first attempts (AMD, OpenAI, CIeNET), copied
from data/memos/.../logs/memo_package.en.attempt-1.json and trimmed. Every
error they raise today is a known class — the source-URL rule they predate
and the risk-card wording checks R11 moves out of the gate — so a NEW gate
that fails good packages shows up here instead of in a live run.
"""
from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from docx import Document

from scripts import memo_package_replay as replay
from server import memo_docx_renderer

FIXTURES = Path(__file__).parent / "fixtures" / "memo_packages"
KNOWN_CLASSES = {
    "amd_attempt1": {"url": 7},
    "openai_attempt1": {"url": 3, "economic": 2},
    "cienet_attempt1": {"url": 7, "rows": 6},
}


def _load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _kind(message: str) -> str:
    if ".url is required" in message:
        return "url"
    if "economic consequence" in message:
        return "economic"
    if "two-cell rows" in message:
        return "rows"
    return message


@pytest.mark.parametrize("name", sorted(KNOWN_CLASSES))
def test_stored_attempts_fail_only_on_known_rules(name, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    package, _repairs = memo_docx_renderer.repair_package_structure(_load(name))
    errors = memo_docx_renderer.english_package_validation_errors(package)
    assert Counter(_kind(e) for e in errors) == KNOWN_CLASSES[name], errors


@pytest.mark.parametrize("name", sorted(KNOWN_CLASSES))
def test_stored_attempts_pass_once_triaged(name, monkeypatch):
    """With the source-URL rule off (they predate it) and the risk-card
    wording checks treated as quality findings, the real attempts pass —
    the triage R11 asks for keeps good packages."""
    monkeypatch.setenv("BSH_MEMO_SOURCE_URL_REQUIRED", "0")
    package, _repairs = memo_docx_renderer.repair_package_structure(_load(name))
    assert memo_docx_renderer.english_package_validation_errors(package, editorial_risk_checks=False) == []
    findings = memo_docx_renderer.risk_card_quality_findings(package)
    assert Counter(_kind(f) for f in findings) == {
        kind: count for kind, count in KNOWN_CLASSES[name].items() if kind != "url"
    }


@pytest.mark.parametrize("name", sorted(KNOWN_CLASSES))
def test_stored_attempts_render_english_first(name, tmp_path):
    package, _repairs = memo_docx_renderer.repair_package_structure(_load(name))
    out = tmp_path / "run" / "memo" / "en.docx"
    result = memo_docx_renderer.render_memo_locale(package, "en", out, strict_sources=False)
    assert result["ok"] and out.exists()
    assert not (tmp_path / "run" / "memo" / "zh.docx").exists()
    headings = [p.text for p in Document(out).paragraphs if p.style.name == "Heading 1"]
    assert headings[0] == "I. Executive Summary"
    assert any(h.endswith("Sources, Source Classes, and Fact Reference Index") for h in headings)


def _seed_data_dir(root: Path) -> Path:
    data = root / "data"
    for index, name in enumerate(sorted(KNOWN_CLASSES)):
        logs = data / "memos" / f"company-{index}" / f"2026-09-0{index + 1}__000000__company-{index}__memo-run" / "logs"
        logs.mkdir(parents=True)
        shutil.copy(FIXTURES / f"{name}.json", logs / "memo_package.en.attempt-1.json")
        (logs / "stream.jsonl").write_text('{"model": "claude-opus-5"}\n', encoding="utf-8")
    buffett = data / "memos" / "ko" / "2026-08-25__000922__ko__buffett-memo-run" / "logs"
    buffett.mkdir(parents=True)
    (buffett / "memo_package.json").write_text(json.dumps({"decision": "Pass", "markdown_en": "x"}), encoding="utf-8")
    return data


def _tree(root: Path) -> dict[str, float]:
    return {str(p.relative_to(root)): p.stat().st_mtime for p in root.rglob("*")}


def test_replay_reports_pass_rate_and_error_classes_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("BSH_MEMO_SOURCE_URL_REQUIRED", raising=False)
    data = _seed_data_dir(tmp_path)
    before = _tree(data)
    assert replay.main(["--data-dir", str(data), "--json", "--quiet"]) == 0
    payload = json.loads(capsys.readouterr().out)
    summary = payload["summary"]
    assert summary["overall"] == {"packages": 3, "pass": 0, "pass_rate": 0.0}
    assert summary["first_attempts"]["packages"] == 3
    assert summary["by_engine"] == {"claude": {"packages": 3, "pass": 0, "pass_rate": 0.0}}
    assert summary["skipped"] == 1  # the Buffett package
    top = summary["error_classes"][0]
    assert top["count"] == 17 and top["packages"] == 3 and top["class"].startswith("sources[*].url is required")
    assert _tree(data) == before  # read-only

    # the triage view: only the URL rule is left
    assert replay.main(["--data-dir", str(data), "--json", "--quiet", "--triage"]) == 0
    triaged = json.loads(capsys.readouterr().out)["summary"]
    assert [item["class"][:26] for item in triaged["error_classes"]] == ["sources[*].url is required"]
    assert _tree(data) == before


def test_replay_prints_a_readable_summary(tmp_path, capsys):
    data = _seed_data_dir(tmp_path)
    assert replay.main(["--data-dir", str(data)]) == 0
    out = capsys.readouterr().out
    assert "# Memo package replay" in out and "| run | file | engine |" in out
    assert "- first attempts: 0/3 (0%)" in out
    assert replay.main(["--data-dir", str(tmp_path / "nowhere")]) == 2


def test_error_class_blanks_locations_and_values():
    assert replay.error_class("sections[3].blocks[2].headers[0].en is required") == (
        "sections[*].blocks[*].headers[*].en is required"
    )
    assert replay.error_class(
        "investment_risk blocks[12]: row 'Likelihood' must not be empty"
    ) == "<section> blocks[*]: row '…' must not be empty"
