"""Round 2, P1b: repair as edits (I2), the subsection trim (I1) and the
typed repair errors.

Fixtures: the live ZaiNar packages copied from data/ (the Claude v1
finished memo and the Claude v2 draft whose `risks` repair died on
2026-09-23 because its re-emitted answer, 34,881 bytes, did not fit one
tool call). Every model call is a fake runner; nothing here reads data/.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from server import claude_runner, memo_docx_renderer, memo_structure

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def v2_draft() -> dict:
    return _load("zainar_v2_draft.en.json")


@pytest.fixture
def v1_package() -> dict:
    return _load("zainar_v1_package.json")


def _section(package: dict, section_id: str) -> dict:
    return next(s for s in package["sections"] if s["id"] == section_id)


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "memo-run"
    (run_dir / "logs").mkdir(parents=True)
    return run_dir


# ---- the fixtures still validate as they did live ----------------------------


def test_fixtures_validate_as_they_did_live(v1_package, v2_draft):
    assert memo_docx_renderer.english_package_validation_errors(
        v1_package, editorial_risk_checks=False
    ) == []
    errors = memo_docx_renderer.english_package_validation_errors(
        v2_draft, editorial_risk_checks=False
    )
    assert len(errors) == 3
    assert errors[0].startswith("sources[17].url is required")
    assert "section company_team runs 2918 English words" in errors[1]
    assert "section risks runs 5269 English words" in errors[2]


def test_an_empty_edits_answer_changes_nothing(v1_package, v2_draft):
    for package in (v1_package, v2_draft):
        patched, report = claude_runner.apply_memo_package_edits(package, {"edits": []})
        assert patched == package
        assert patched is not package
        assert report == {"applied": 0, "rejected": [], "dropped": 0, "sources_replaced": False}


# ---- the applier ------------------------------------------------------------


def test_edits_address_paragraphs_items_cells_and_callouts(v2_draft):
    risks = _section(v2_draft, "risks")
    # The risk cards carry no header row; the key-metrics table does.
    table_index = next(
        i for i, b in enumerate(risks["blocks"]) if b["type"] == "table" and b.get("headers")
    ) if any(b["type"] == "table" and b.get("headers") for b in risks["blocks"]) else None
    if table_index is None:
        team = _section(v2_draft, "company_team")
        team_table = next(i for i, b in enumerate(team["blocks"]) if b["type"] == "table" and b.get("headers"))
        risks["blocks"].append(json.loads(json.dumps(team["blocks"][team_table])))
        table_index = len(risks["blocks"]) - 1
    paragraph_index = next(i for i, b in enumerate(risks["blocks"]) if b["type"] == "paragraph")
    bullets_index = next(i for i, b in enumerate(risks["blocks"]) if b["type"] == "bullets")
    summary = _section(v2_draft, "executive_summary")
    callout_index = next(i for i, b in enumerate(summary["blocks"]) if b["type"] == "callout")
    # Give the header a Chinese half so the blanking rule is visible.
    risks["blocks"][table_index]["headers"][0]["zh"] = "旧"
    payload = {
        "edits": [
            {"section_id": "risks", "block_index": paragraph_index, "en": "Shorter paragraph."},
            {"section_id": "risks", "block_index": bullets_index, "item_index": 0, "en": "Shorter bullet."},
            {"section_id": "risks", "block_index": table_index, "row": 0, "col": 1, "en": "Shorter cell."},
            {"section_id": "risks", "block_index": table_index, "row": -1, "col": 0, "en": "Header."},
            {"section_id": "risks", "block_index": table_index, "field": "title", "en": "Table title."},
            {"section_id": "executive_summary", "block_index": callout_index, "en": "Callout body."},
            {"section_id": "executive_summary", "block_index": callout_index, "field": "title", "en": "Callout title."},
            {"section_id": "executive_summary", "block_index": callout_index, "item_index": 1, "en": "Callout item."},
        ]
    }
    patched, report = claude_runner.apply_memo_package_edits(v2_draft, payload)
    assert report["rejected"] == []
    assert report["applied"] == 8
    new_risks = _section(patched, "risks")
    assert new_risks["blocks"][paragraph_index]["text"] == {"en": "Shorter paragraph.", "zh": ""}
    assert new_risks["blocks"][bullets_index]["items"][0]["en"] == "Shorter bullet."
    table = new_risks["blocks"][table_index]
    assert table["rows"][0][1]["en"] == "Shorter cell."
    # The English changed, so the stale Chinese is blanked for the chase.
    assert table["headers"][0] == {"en": "Header.", "zh": ""}
    assert table["title"]["en"] == "Table title."
    new_callout = _section(patched, "executive_summary")["blocks"][callout_index]
    assert new_callout["body"]["en"] == "Callout body."
    assert new_callout["title"]["en"] == "Callout title."
    assert new_callout["items"][1]["en"] == "Callout item."
    # The original is untouched (pure), and the untouched blocks are equal.
    assert _section(v2_draft, "risks")["blocks"][paragraph_index]["text"]["en"] != "Shorter paragraph."
    assert new_risks["blocks"][paragraph_index + 1] == risks["blocks"][paragraph_index + 1]


def test_bad_addresses_are_rejected_never_crash(v2_draft):
    risks = _section(v2_draft, "risks")
    table_index = next(i for i, b in enumerate(risks["blocks"]) if b["type"] == "table")
    bullets_index = next(i for i, b in enumerate(risks["blocks"]) if b["type"] == "bullets")
    payload = {
        "edits": [
            {"section_id": "nope", "block_index": 0, "en": "x"},
            {"section_id": "risks", "block_index": 999, "en": "x"},
            {"section_id": "risks", "block_index": -1, "en": "x"},
            {"section_id": "risks", "block_index": table_index, "row": 999, "col": 0, "en": "x"},
            {"section_id": "risks", "block_index": table_index, "row": 0, "col": 99, "en": "x"},
            {"section_id": "risks", "block_index": table_index, "row": 0, "en": "x"},
            {"section_id": "risks", "block_index": bullets_index, "item_index": 99, "en": "x"},
            {"section_id": "risks", "block_index": bullets_index, "en": "x"},
            {"section_id": "risks", "block_index": 0, "en": ""},
            {"section_id": "risks", "block_index": 0, "field": "nothing_here", "en": "x"},
            "not an object",
        ],
        "drop_blocks": [
            {"section_id": "risks", "block_index": 999},
            {"section_id": "missing", "block_index": 0},
        ],
        "sources": [{"title": "no id"}],
    }
    patched, report = claude_runner.apply_memo_package_edits(v2_draft, payload)
    assert report["applied"] == 0 and report["dropped"] == 0
    assert report["sources_replaced"] is False
    assert len(report["rejected"]) == 14
    assert patched == v2_draft


def test_drop_blocks_and_sources_replacement(v2_draft):
    risks = _section(v2_draft, "risks")
    before = len(risks["blocks"])
    paragraph_indexes = [i for i, b in enumerate(risks["blocks"]) if b["type"] == "paragraph"]
    kept_after_drop = risks["blocks"][paragraph_indexes[1] + 1]
    new_sources = [dict(s) for s in v2_draft["sources"]]
    new_sources[17]["url"] = "https://www.theinformation.com/articles/zainar"
    payload = {
        "edits": [
            # Edits address ORIGINAL indexes even when blocks are dropped.
            {"section_id": "risks", "block_index": paragraph_indexes[1] + 1, "field": "text", "en": "kept and edited"}
            if kept_after_drop["type"] in ("paragraph", "heading")
            else {"section_id": "risks", "block_index": paragraph_indexes[0], "en": "edited"},
        ],
        "drop_blocks": [
            {"section_id": "risks", "block_index": paragraph_indexes[1]},
            {"section_id": "risks", "block_index": paragraph_indexes[1]},  # duplicate: dropped once
            {"section_id": "risks", "block_index": paragraph_indexes[0]},
        ],
        "sources": new_sources,
    }
    patched, report = claude_runner.apply_memo_package_edits(v2_draft, payload)
    assert report["dropped"] == 2
    assert report["sources_replaced"] is True
    assert len(_section(patched, "risks")["blocks"]) == before - 2
    assert patched["sources"][17]["url"].startswith("https://")
    # The dropped paragraphs are gone and the rest kept their order.
    remaining = [b for b in _section(patched, "risks")["blocks"] if b["type"] == "paragraph"]
    assert len(remaining) == len(paragraph_indexes) - 2


def test_refuses_to_empty_a_section(v2_draft):
    summary = _section(v2_draft, "executive_summary")
    payload = {
        "edits": [],
        "drop_blocks": [
            {"section_id": "executive_summary", "block_index": i}
            for i in range(len(summary["blocks"]))
        ],
    }
    patched, report = claude_runner.apply_memo_package_edits(v2_draft, payload)
    assert report["dropped"] == 0
    assert any("refusing to empty" in r for r in report["rejected"])
    assert len(_section(patched, "executive_summary")["blocks"]) == len(summary["blocks"])


# ---- which blocks a finding points at -----------------------------------------


def test_quoted_findings_pin_blocks_and_cap_findings_take_the_section(v2_draft):
    risks = _section(v2_draft, "risks")
    paragraph_index = next(i for i, b in enumerate(risks["blocks"]) if b["type"] == "paragraph")
    snippet = risks["blocks"][paragraph_index]["text"]["en"][:40]
    pinned = claude_runner.blocks_for_findings(
        risks, [f'quality gate sell_side_voice at paragraph: "{snippet}..." — rewrite']
    )
    assert pinned == [paragraph_index]
    whole = claude_runner.blocks_for_findings(
        risks,
        [
            "section risks runs 5269 English words against its 2600-word "
            "target and its 5200-word hard cap — cut commentary"
        ],
    )
    assert whole == list(range(len(risks["blocks"])))


def test_addressed_lines_carry_every_string_with_its_address(v2_draft):
    team = _section(v2_draft, "company_team")
    lines = claude_runner.addressed_block_lines("company_team", team["blocks"])
    text = "\n".join(lines)
    table_index = next(i for i, b in enumerate(team["blocks"]) if b["type"] == "table")
    assert f"[company_team #{table_index} table] title:" in text
    assert "row 0 col 1 (" in text
    assert "header col 0:" in text
    assert "[company_team #0 heading] text (" in text
    risks = _section(v2_draft, "risks")
    risk_lines = claude_runner.addressed_block_lines("risks", risks["blocks"])
    assert any(line.startswith("[risks #") and " bullets]" in line for line in risk_lines)
    assert any(line.startswith("  item 0 (") for line in risk_lines)
    # Word counts guide the trim.
    assert "words):" in text


# ---- the section repair in edits mode ---------------------------------------------


def test_section_repair_defaults_to_edits_mode_and_applies_them(tmp_path, monkeypatch, v2_draft):
    run_dir = _run_dir(tmp_path)
    risks = _section(v2_draft, "risks")
    paragraph_index = next(i for i, b in enumerate(risks["blocks"]) if b["type"] == "paragraph")
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {
            "edits": [
                {"section_id": "risks", "block_index": paragraph_index, "en": "Tight."},
                {"section_id": "risks", "block_index": 9999, "en": "ignored"},
            ],
            "drop_blocks": [],
            "claude_cost_usd": 0.21,
            "claude_duration_ms": 1200,
        }, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    structure = memo_structure.for_package(v2_draft)
    finding = (
        "section risks runs 5269 English words against its 2600-word target "
        "and its 5200-word hard cap — cut commentary"
    )
    result, error = claude_runner.run_memo_section_repair(
        run_dir=run_dir,
        company_name="ZaiNar, Inc.",
        run_id="r1",
        section=risks,
        section_id="risks",
        findings=[finding],
        structure=structure,
    )
    assert error is None
    assert captured["schema"] is claude_runner.MEMO_REPAIR_EDITS_SCHEMA
    assert captured["role"] == "REPAIR"
    prompt = captured["prompt"]
    assert "returning edits, not the section" in prompt
    assert finding in prompt
    assert f"[risks #{paragraph_index} paragraph]" in prompt
    # The risk section carries the risk-card contract.
    assert "Risk Register Format Contract" in prompt
    assert result["section"]["id"] == "risks"
    assert result["section"]["blocks"][paragraph_index]["text"]["en"] == "Tight."
    assert result["edits_applied"] == 1
    assert len(result["edits_rejected"]) == 1
    assert result["claude_cost_usd"] == 0.21
    # The input section was not mutated.
    assert risks["blocks"][paragraph_index]["text"]["en"] != "Tight."


def test_section_repair_with_no_applicable_edits_is_a_typed_error(tmp_path, monkeypatch, v2_draft):
    run_dir = _run_dir(tmp_path)
    monkeypatch.setattr(
        claude_runner,
        "_run_memo_local_json_artifact",
        lambda **kw: ({"edits": [{"section_id": "risks", "block_index": 9999, "en": "x"}]}, None),
    )
    result, error = claude_runner.run_memo_section_repair(
        run_dir=run_dir,
        company_name="Z",
        run_id="r1",
        section=_section(v2_draft, "risks"),
        section_id="risks",
        findings=["something"],
    )
    assert result is None
    assert claude_runner.repair_error_code(error) == "no_edits"
    assert "out of range" in error


def test_the_size_failure_is_distinguishable(tmp_path, monkeypatch, v2_draft):
    """The exact live failure: the CLI's size complaint must come back
    with code output_too_large, through the section repair AND the
    per-section fan-out."""
    run_dir = _run_dir(tmp_path)
    live = (
        "claude exited 1: the model never returned output matching the "
        "schema: its answer never parsed as JSON. The last attempt sent "
        "34,881 bytes in one tool call, so the ask is too big for one call "
        "— split what it must return."
    )
    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", lambda **kw: (None, live))
    assert claude_runner.is_output_too_large(live)
    assert claude_runner.repair_error_code(live) == "output_too_large"
    assert claude_runner.repair_error_code("claude exited 1: something else") is None
    assert claude_runner.repair_error_code(None) is None
    for mode in ("edits", "full"):
        result, error = claude_runner.run_memo_section_repair(
            run_dir=run_dir,
            company_name="Z",
            run_id="r1",
            section=_section(v2_draft, "risks"),
            section_id="risks",
            findings=["section risks runs 5269 English words against its 5200-word hard cap"],
            mode=mode,
        )
        assert result is None
        assert isinstance(error, claude_runner.MemoStageError)
        assert error.code == claude_runner.REPAIR_ERROR_OUTPUT_TOO_LARGE
        assert str(error) == live  # still the plain message for logs
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=run_dir,
        company_name="Z",
        run_id="r1",
        package=v2_draft,
        findings=["section risks runs 5269 English words against its 5200-word hard cap"],
    )
    assert repaired is None
    assert claude_runner.repair_error_code(error) == "output_too_large"
    assert error.startswith("risks: ")


def test_sectional_repair_passes_mode_and_overlays_sources(tmp_path, monkeypatch, v2_draft):
    run_dir = _run_dir(tmp_path)
    seen_modes: list[str] = []
    new_sources = [dict(s) for s in v2_draft["sources"]]
    new_sources[17]["url"] = "https://example.com/the-information"

    def fake_section_repair(**kw):
        seen_modes.append(kw["mode"])
        section = json.loads(json.dumps(kw["section"]))
        return {"section": section, "sources": new_sources, "claude_cost_usd": 0.1}, None

    monkeypatch.setattr(claude_runner, "run_memo_section_repair", fake_section_repair)
    repaired, error = claude_runner.run_memo_package_sectional_repair(
        run_dir=run_dir,
        company_name="Z",
        run_id="r1",
        package=v2_draft,
        findings=["section risks runs 5269 English words against its 5200-word hard cap"],
        mode="full",
    )
    assert error is None
    assert seen_modes == ["full"]
    assert repaired["sources"][17]["url"] == "https://example.com/the-information"
    assert v2_draft["sources"][17].get("url") is None  # input untouched


def test_whole_package_repair_in_edits_mode(tmp_path, monkeypatch, v2_draft):
    run_dir = _run_dir(tmp_path)
    package_path = run_dir / "logs" / "memo_package.en.invalid.json"
    package_path.write_text(json.dumps(v2_draft), encoding="utf-8")
    captured: dict = {}
    team = _section(v2_draft, "company_team")
    paragraph_index = next(i for i, b in enumerate(team["blocks"]) if b["type"] == "paragraph")
    new_sources = [dict(s) for s in v2_draft["sources"]]
    new_sources[17]["url"] = "https://example.com/fixed"

    def fake_runner(**kw):
        captured.update(kw)
        return {
            "edits": [{"section_id": "company_team", "block_index": paragraph_index, "en": "Cut."}],
            "sources": new_sources,
            "claude_cost_usd": 0.5,
        }, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    errors = memo_docx_renderer.english_package_validation_errors(
        v2_draft, editorial_risk_checks=False
    )
    result, error = claude_runner.run_memo_package_structure_repair(
        run_dir=run_dir,
        company_name="ZaiNar, Inc.",
        run_id="r1",
        package_path=package_path,
        validation_errors=errors,
        mode="edits",
    )
    assert error is None
    assert captured["schema"] is claude_runner.MEMO_REPAIR_EDITS_SCHEMA
    prompt = captured["prompt"]
    # Only the sections the errors name are listed, plus the sources.
    assert "### section `company_team`" in prompt
    assert "### section `risks`" in prompt
    assert "### section `thesis_market`" not in prompt
    assert "The sources list" in prompt
    package = result["memo_package"]
    assert _section(package, "company_team")["blocks"][paragraph_index]["text"]["en"] == "Cut."
    assert package["sources"][17]["url"] == "https://example.com/fixed"
    assert result["sources_replaced"] is True
    assert result["claude_cost_usd"] == 0.5
    # The sources error is gone; the two word-cap overruns remain (one
    # paragraph is not 2,900 words).
    remaining = memo_docx_renderer.english_package_validation_errors(
        package, editorial_risk_checks=False
    )
    assert all("hard cap" in e for e in remaining)


def test_whole_package_repair_full_mode_is_unchanged(tmp_path, monkeypatch, v2_draft):
    run_dir = _run_dir(tmp_path)
    package_path = run_dir / "logs" / "memo_package.en.invalid.json"
    package_path.write_text(json.dumps(v2_draft), encoding="utf-8")
    captured: dict = {}
    monkeypatch.setattr(
        claude_runner,
        "_run_memo_local_json_artifact",
        lambda **kw: (captured.update(kw) or ({"memo_package": v2_draft}, None)),
    )
    result, error = claude_runner.run_memo_package_structure_repair(
        run_dir=run_dir,
        company_name="Z",
        run_id="r1",
        package_path=package_path,
        validation_errors=["sources[17].url is required"],
    )
    assert error is None
    assert captured["schema"] is claude_runner.MEMO_FAST_BILINGUAL_PACKAGE_SCHEMA
    assert str(package_path) in captured["prompt"]
    assert result["memo_package"] is v2_draft


# ---- the subsection trim ----------------------------------------------------------


def _pieces(run_dir: Path, section_id: str, sizes: list[int]) -> Path:
    pieces_dir = claude_runner.memo_section_pieces_dir(run_dir, section_id)
    pieces_dir.mkdir(parents=True, exist_ok=True)
    for number, words in enumerate(sizes, start=1):
        blocks = [
            {"type": "heading", "level": 2, "text": {"en": f"{number}. Part {number}", "zh": ""}},
            {"type": "paragraph", "text": {"en": " ".join(["word"] * words) + " [S1]", "zh": ""}},
        ]
        (pieces_dir / f"{number:02d}.json").write_text(
            json.dumps({"piece": number, "blocks": blocks}), encoding="utf-8"
        )
    (pieces_dir / "notes.txt").write_text("not a piece", encoding="utf-8")
    return pieces_dir


def test_subsection_word_counts_lists_pieces_in_order(tmp_path):
    run_dir = _run_dir(tmp_path)
    pieces_dir = _pieces(run_dir, "risks", [50, 300, 120])
    rows = claude_runner.subsection_word_counts(pieces_dir)
    assert [p.name for p, _ in rows] == ["01.json", "02.json", "03.json"]
    assert [w for _, w in rows] == [54, 304, 124]  # heading words + [S1]
    assert max(rows, key=lambda row: row[1])[0].name == "02.json"
    assert claude_runner.subsection_word_counts(tmp_path / "missing") == []


def test_section_trim_rewrites_the_file_when_shorter(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    pieces_dir = _pieces(run_dir, "risks", [50, 300])
    target = pieces_dir / "02.json"
    captured: dict = {}

    def fake_runner(**kw):
        captured.update(kw)
        return {
            "blocks": [
                {"type": "heading", "level": 2, "text": {"en": "2. Part 2", "zh": ""}},
                {"type": "paragraph", "text": {"en": "short now [S1]", "zh": ""}},
            ],
            "claude_cost_usd": 0.07,
        }, None

    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", fake_runner)
    out = claude_runner.run_section_trim(
        run_dir,
        section_id="risks",
        subsection_path=target,
        target_words=150,
        hard_cap_words=5200,
        structure=memo_structure.LATE,
        progress=None,
    )
    assert out["ok"] is True
    assert out["words_before"] == 304 and out["words_after"] == 6
    assert out["cost_usd"] == 0.07 and out["error"] is None
    assert "citations_dropped" not in out
    assert captured["schema"] is claude_runner._MEMO_SECTION_TRIM_SCHEMA
    assert captured["role"] == "REPAIR"
    assert "no more than 150 words" in captured["prompt"]
    assert "5200-word hard cap" in captured["prompt"]
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written["piece"] == 2
    assert written["blocks"][1]["text"]["en"] == "short now [S1]"
    # The other piece is untouched.
    assert claude_runner.subsection_word_counts(pieces_dir)[0][1] == 54


def test_section_trim_keeps_the_file_on_a_bad_answer(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    pieces_dir = _pieces(run_dir, "risks", [300])
    target = pieces_dir / "01.json"
    original = target.read_text(encoding="utf-8")
    answers = iter(
        [
            # Wrong heading.
            ({"blocks": [{"type": "heading", "text": {"en": "Other", "zh": ""}}]}, None),
            # Longer than before.
            (
                {
                    "blocks": [
                        {"type": "heading", "text": {"en": "1. Part 1", "zh": ""}},
                        {"type": "paragraph", "text": {"en": " ".join(["w"] * 400), "zh": ""}},
                    ]
                },
                None,
            ),
            # The size failure, typed.
            (None, "claude exited 1: ... so the ask is too big for one call — split what it must return."),
        ]
    )
    monkeypatch.setattr(claude_runner, "_run_memo_local_json_artifact", lambda **kw: next(answers))
    for expected in ("heading", "did not shorten", "too big"):
        out = claude_runner.run_section_trim(
            run_dir,
            section_id="risks",
            subsection_path=target,
            target_words=100,
            hard_cap_words=5200,
            structure=None,
            progress=None,
        )
        assert out["ok"] is False
        assert expected in str(out["error"])
        assert out["words_after"] == out["words_before"] == 304
        assert target.read_text(encoding="utf-8") == original
    assert claude_runner.repair_error_code(out["error"]) == "output_too_large"


def test_section_trim_is_a_no_op_under_target(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    target = _pieces(run_dir, "risks", [20]) / "01.json"
    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", lambda **kw: pytest.fail("no call needed")
    )
    out = claude_runner.run_section_trim(
        run_dir, section_id="risks", subsection_path=target, target_words=100,
        hard_cap_words=200, structure=None, progress=None,
    )
    assert out == {"ok": True, "words_before": 24, "words_after": 24, "cost_usd": 0.0, "error": None}


def test_section_trim_reports_dropped_citations(tmp_path, monkeypatch):
    run_dir = _run_dir(tmp_path)
    target = _pieces(run_dir, "risks", [200]) / "01.json"
    monkeypatch.setattr(
        claude_runner,
        "_run_memo_local_json_artifact",
        lambda **kw: (
            {"blocks": [
                {"type": "heading", "text": {"en": "1. Part 1", "zh": ""}},
                {"type": "paragraph", "text": {"en": "no citation left", "zh": ""}},
            ]},
            None,
        ),
    )
    out = claude_runner.run_section_trim(
        run_dir, section_id="risks", subsection_path=target, target_words=10,
        hard_cap_words=200, structure=None, progress=None,
    )
    assert out["ok"] is True
    assert out["citations_dropped"] == ["S1"]
