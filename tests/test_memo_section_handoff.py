"""One section agent, delivered as files instead of one giant response.

The executive summary outgrew what a single structured response can carry:
a live run wrote 17,189 output tokens and the JSON never closed, so every
token was lost. The section agent now writes each numbered subsection to
its own file and returns a receipt; the server assembles the section from
the files and re-asks only the pieces that did not arrive usable.
"""
from __future__ import annotations

import json

import pytest

from server import claude_runner, memo_structure

V2 = memo_structure.load_structure("late", 2)
EXEC_SUBSECTIONS = V2.section("executive_summary").subsections


def _pieces_dir(run_dir):
    return claude_runner._memo_section_pieces_dir(run_dir, "executive_summary")


def _piece_payload(number, *, heading=None, extra_blocks=1):
    sub = EXEC_SUBSECTIONS[number - 1]
    return {
        "piece": number,
        "blocks": [
            {
                "type": "heading",
                "level": 2,
                "text": {
                    "en": heading if heading is not None else f"{number}. {sub.en}",
                    "zh": f"{number}. {sub.zh}",
                },
            },
            *(
                {"type": "paragraph", "text": {"en": f"body {number}", "zh": ""}}
                for _ in range(extra_blocks)
            ),
        ],
    }


def _write_piece(run_dir, number, payload=None, *, raw=None):
    path = _pieces_dir(run_dir) / f"{number:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _manifest(numbers):
    return {
        "section_id": "executive_summary",
        "pieces": [{"piece": n, "file": f"{n:02d}.json"} for n in numbers],
        "claude_cost_usd": 0.5,
        "claude_duration_ms": 1000,
        "claude_usage": {"output_tokens": 10},
    }


def _run(tmp_path, section_id="executive_summary"):
    return claude_runner._run_english_section(
        run_dir=tmp_path,
        section_id=section_id,
        common_context="shared",
        shared_facts_block="facts",
        spine_path=tmp_path / "spine.json",
        add_dirs=[],
        progress=None,
        timeout_sec=10,
        structure=V2,
    )


# ---- which sections hand off ------------------------------------------------


def test_every_section_hands_off_by_default(monkeypatch):
    """Started as the executive summary alone, to learn on one section.

    Two live runs assembled it clean with no piece retries, and then the
    budgets went from 6,700 words to 16,000 — every section is now the
    size the executive summary was when it began truncating.
    """
    monkeypatch.delenv("BSH_MEMO_SECTION_HANDOFF", raising=False)
    assert claude_runner._memo_section_handoff_ids() == "all"
    for section_id in V2.section_ids:
        section = V2.section(section_id)
        assert claude_runner._section_handoff_enabled(section_id, section), (
            section_id
        )


def test_a_named_subset_still_works(monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    assert claude_runner._section_handoff_enabled(
        "executive_summary", V2.section("executive_summary")
    )
    assert not claude_runner._section_handoff_enabled(
        "market_industry", V2.section("market_industry")
    )


@pytest.mark.parametrize("value", ["off", "none", "0", " "])
def test_handoff_can_be_turned_off(monkeypatch, value):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", value)
    assert claude_runner._memo_section_handoff_ids() == frozenset()


def test_handoff_ids_are_configurable(monkeypatch):
    monkeypatch.setenv(
        "BSH_MEMO_SECTION_HANDOFF", "executive_summary, market_industry"
    )
    assert claude_runner._memo_section_handoff_ids() == frozenset(
        {"executive_summary", "market_industry"}
    )


def test_a_section_without_subsections_stays_inline():
    section = memo_structure.LATE.section("executive_summary")
    assert section.subsections == ()
    assert not claude_runner._section_handoff_enabled(
        "executive_summary", section
    )


# ---- per-piece validation ---------------------------------------------------


def test_a_good_piece_has_no_error(tmp_path):
    path = _write_piece(tmp_path, 1, _piece_payload(1))
    assert (
        claude_runner._section_piece_error(
            path, 1, f"1. {EXEC_SUBSECTIONS[0].en}"
        )
        is None
    )


def test_heading_comparison_forgives_trivia(tmp_path):
    heading = f"1. {EXEC_SUBSECTIONS[0].en}"
    path = _write_piece(
        tmp_path, 1, _piece_payload(1, heading=f"  1.  {heading[3:].upper()}:  ")
    )
    assert claude_runner._section_piece_error(path, 1, heading) is None


@pytest.mark.parametrize(
    "payload,raw,needle",
    [
        (None, None, "never written"),
        (None, "{not json", "not valid JSON"),
        ([1, 2, 3], None, "not a JSON object"),
        ({"piece": 1, "blocks": []}, None, "no non-empty `blocks`"),
        ({"piece": 1, "blocks": ["a string"]}, None, "block 0 is not a"),
        (
            {"piece": 1, "blocks": [{"type": "paragraph", "text": {"en": "x"}}]},
            None,
            "must open with its heading",
        ),
    ],
)
def test_unusable_pieces_are_named(tmp_path, payload, raw, needle):
    path = _pieces_dir(tmp_path) / "01.json"
    if payload is not None or raw is not None:
        _write_piece(tmp_path, 1, payload, raw=raw)
    error = claude_runner._section_piece_error(
        path, 1, f"1. {EXEC_SUBSECTIONS[0].en}"
    )
    assert error and needle in error


def test_a_wrong_heading_is_caught(tmp_path):
    path = _write_piece(tmp_path, 1, _piece_payload(1, heading="1. Something else"))
    error = claude_runner._section_piece_error(
        path, 1, f"1. {EXEC_SUBSECTIONS[0].en}"
    )
    assert error and "the scaffold fixes" in error


# ---- the happy path ---------------------------------------------------------


def test_pieces_are_assembled_in_order(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    calls = []

    def fake_artifact(**kwargs):
        calls.append(kwargs)
        for number in range(1, len(EXEC_SUBSECTIONS) + 1):
            _write_piece(tmp_path, number, _piece_payload(number))
        return _manifest(range(1, len(EXEC_SUBSECTIONS) + 1)), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path)

    assert error is None
    assert len(calls) == 1
    section = result["section"]
    assert section["id"] == "executive_summary"
    headings = [
        b["text"]["en"] for b in section["blocks"] if b["type"] == "heading"
    ]
    assert headings == [
        f"{n}. {sub.en}" for n, sub in enumerate(EXEC_SUBSECTIONS, start=1)
    ]
    # heading + one paragraph per subsection, nothing dropped or reordered
    assert len(section["blocks"]) == 2 * len(EXEC_SUBSECTIONS)
    assert result["claude_cost_usd"] == 0.5


def test_the_handoff_prompt_forbids_measuring_with_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    captured = {}

    def fake_artifact(**kwargs):
        captured["prompt"] = kwargs["prompt"]
        captured["tools"] = kwargs.get("allowed_tools")
        captured["schema"] = kwargs["schema"]
        for number in range(1, len(EXEC_SUBSECTIONS) + 1):
            _write_piece(tmp_path, number, _piece_payload(number))
        return _manifest(range(1, len(EXEC_SUBSECTIONS) + 1)), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    _run(tmp_path)

    prompt = captured["prompt"]
    # write once, never inspect: the damage in the live run was the shell
    # trim loop, not writing files
    assert "Write each file ONCE" in prompt
    assert "never measure it" in prompt
    assert "`wc`, `awk`, `jq`" in prompt
    # the section spec still travels with it — same agent, same brief
    assert "## Your section: `executive_summary`" in prompt
    assert "## Subsection scaffold" in prompt
    assert "Write" in captured["tools"]
    assert captured["schema"] is claude_runner._MEMO_ENGLISH_SECTION_MANIFEST_SCHEMA


def test_stale_pieces_from_a_previous_attempt_are_cleared(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    stale = _write_piece(tmp_path, 1, _piece_payload(1, extra_blocks=9))

    def fake_artifact(**kwargs):
        assert not stale.exists(), "the last attempt's files must be cleared"
        for number in range(1, len(EXEC_SUBSECTIONS) + 1):
            _write_piece(tmp_path, number, _piece_payload(number))
        return _manifest(range(1, len(EXEC_SUBSECTIONS) + 1)), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path)
    assert error is None
    assert len(result["section"]["blocks"]) == 2 * len(EXEC_SUBSECTIONS)


# ---- targeted retry ---------------------------------------------------------


def test_only_the_bad_piece_is_re_asked(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    prompts = []

    def fake_artifact(**kwargs):
        prompts.append(kwargs["prompt"])
        if len(prompts) == 1:
            for number in range(1, len(EXEC_SUBSECTIONS) + 1):
                _write_piece(tmp_path, number, _piece_payload(number))
            _write_piece(tmp_path, 3, None, raw='{"piece": 3, "blocks": [')
            return _manifest(range(1, len(EXEC_SUBSECTIONS) + 1)), None
        _write_piece(tmp_path, 3, _piece_payload(3))
        return _manifest([3]), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path)

    assert error is None
    assert len(prompts) == 2
    retry = prompts[1]
    assert "## Rewrite ONE subsection" in retry
    assert f'subsection 3 ("3. {EXEC_SUBSECTIONS[2].en}"' in retry
    assert "not valid JSON" in retry
    # the siblings stay where they are
    assert "do not rewrite them" in retry
    assert len(result["section"]["blocks"]) == 2 * len(EXEC_SUBSECTIONS)
    # the retry's cost is added to the drafting call's
    assert result["claude_cost_usd"] == 1.0


def test_a_piece_gives_up_after_three_retries(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    calls = []

    def fake_artifact(**kwargs):
        calls.append(kwargs["prompt"])
        for number in range(1, len(EXEC_SUBSECTIONS) + 1):
            if number != 2:
                _write_piece(tmp_path, number, _piece_payload(number))
        return _manifest([n for n in range(1, len(EXEC_SUBSECTIONS) + 1)]), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path)

    assert result is None
    assert "subsection 2 is still unusable after 3 retries" in error
    assert "never written" in error
    # the drafting call plus exactly three retries of the one bad piece
    assert len(calls) == 1 + claude_runner.MEMO_SECTION_PIECE_MAX_RETRIES


def test_pieces_on_disk_survive_a_failed_drafting_call(tmp_path, monkeypatch):
    """A truncated response does not unwrite the files already banked."""
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    calls = []

    def fake_artifact(**kwargs):
        calls.append(kwargs["prompt"])
        if len(calls) == 1:
            for number in range(1, len(EXEC_SUBSECTIONS)):
                _write_piece(tmp_path, number, _piece_payload(number))
            return None, claude_runner.MEMO_STRUCTURED_OUTPUT_EXHAUSTED
        _write_piece(
            tmp_path, len(EXEC_SUBSECTIONS), _piece_payload(len(EXEC_SUBSECTIONS))
        )
        return _manifest([len(EXEC_SUBSECTIONS)]), None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path)

    assert error is None
    assert len(calls) == 2
    assert len(result["section"]["blocks"]) == 2 * len(EXEC_SUBSECTIONS)


def test_a_drafting_call_that_wrote_nothing_fails_without_retries(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    calls = []

    def fake_artifact(**kwargs):
        calls.append(kwargs["prompt"])
        return None, "run cancelled"

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path)

    assert result is None
    assert error == "run cancelled"
    assert len(calls) == 1


# ---- the inline path is untouched -------------------------------------------


def test_other_sections_still_answer_inline(tmp_path, monkeypatch):
    monkeypatch.setenv("BSH_MEMO_SECTION_HANDOFF", "executive_summary")
    # market_industry is outside the named subset, so it answers inline
    captured = {}

    def fake_artifact(**kwargs):
        captured.update(kwargs)
        return {"section": {"id": "market_industry", "blocks": []}}, None

    monkeypatch.setattr(
        claude_runner, "_run_memo_local_json_artifact", fake_artifact
    )
    result, error = _run(tmp_path, section_id="market_industry")

    assert error is None
    assert result["section"]["id"] == "market_industry"
    assert "Return only JSON:" in captured["prompt"]
    assert "## How this section reaches us" not in captured["prompt"]
    assert captured["schema"] is claude_runner._MEMO_ENGLISH_SECTION_SCHEMA
    assert captured.get("allowed_tools") is None
