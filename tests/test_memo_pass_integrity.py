"""Guards learned from the 2026-09-16 Anthropic run.

That run produced a valid-shaped memo from a pass that had answered
`summary: "test"`, and then died at render because one paragraph's Chinese
came back empty. Both failures were silent until they were expensive.
"""
from __future__ import annotations

from server import claude_runner, job_progress, memo_analysis


# ---- placeholder pass output -------------------------------------------


def test_the_live_placeholder_answer_is_caught():
    """Verbatim from analysis/fast/market_sizing.json on that run."""
    reason = memo_analysis._fast_pass_degenerate_reason(
        {
            "summary": "test",
            "key_findings": [
                {
                    "claim": "a",
                    "finding": "b",
                    "evidence_class": "c",
                    "implication": "d",
                    "confidence": "low",
                }
            ],
            "supporting_evidence": [{"source": "a", "detail": "c"}],
        }
    )
    assert reason and "test" in reason


def test_a_terse_pass_with_real_findings_is_kept():
    """Both ends must be empty. A short summary over real findings is
    terse, not broken, and throwing it away costs a whole pass."""
    assert (
        memo_analysis._fast_pass_degenerate_reason(
            {
                "summary": "Thin market.",
                "key_findings": [
                    {
                        "claim": "The adopted TAM is $420B on the Stratpace definition.",
                        "finding": "Three external estimates disagree on scope.",
                    }
                ],
            }
        )
        is None
    )


def test_a_pass_that_found_nothing_may_say_so():
    assert (
        memo_analysis._fast_pass_degenerate_reason(
            {
                "summary": (
                    "No independent sizing exists for this segment; every "
                    "figure traces back to the company's own deck."
                ),
                "key_findings": [],
            }
        )
        is None
    )


def test_placeholder_words_are_caught_even_at_length():
    assert memo_analysis._fast_pass_degenerate_reason(
        {"summary": "TODO.", "key_findings": []}
    )


def test_a_missing_result_is_left_to_the_error_path():
    assert memo_analysis._fast_pass_degenerate_reason(None) is None


# ---- per-pass effort floor ---------------------------------------------


def test_market_sizing_carries_an_effort_floor():
    """Its focus text is by far the longest and most procedural, and at
    medium effort it answered with placeholder text while the other seven
    passes were fine."""
    assert claude_runner.MEMO_PASS_EFFORT_FLOOR["market_sizing"] == "high"
    assert claude_runner._memo_pass_effort("market_sizing", "medium") == "high"
    assert claude_runner._memo_pass_effort("market_sizing", "low") == "high"
    assert claude_runner._memo_pass_effort("market_sizing", None) == "high"


def test_the_floor_never_lowers_a_higher_effort():
    assert claude_runner._memo_pass_effort("market_sizing", "xhigh") == "xhigh"
    assert claude_runner._memo_pass_effort("market_sizing", "max") == "max"


def test_other_passes_keep_the_tier_effort():
    for pass_id in ("growth_bridge", "team_governance", "valuation_exit"):
        assert claude_runner._memo_pass_effort(pass_id, "medium") == "medium"
        assert claude_runner._memo_pass_effort(pass_id, None) is None


def test_every_floored_pass_is_a_real_pass():
    ids = {spec.pass_id for spec in memo_analysis._FAST_MEMO_PASSES}
    assert set(claude_runner.MEMO_PASS_EFFORT_FLOOR) <= ids


# ---- blank Chinese at the last gate ------------------------------------


def _package_with_blank_zh(count: int) -> dict:
    blocks = [
        {"type": "paragraph", "text": {"en": f"English {i}.", "zh": ""}}
        for i in range(count)
    ]
    blocks.append({"type": "paragraph", "text": {"en": "Kept.", "zh": "保留。"}})
    return {"sections": [{"id": "company_team", "blocks": blocks}]}


def test_a_few_blank_translations_fall_back_to_english():
    package = _package_with_blank_zh(1)
    filled = memo_analysis._fill_sparse_zh_gaps(package)
    assert len(filled) == 1
    block = package["sections"][0]["blocks"][0]
    assert block["text"]["zh"] == block["text"]["en"]
    # An existing translation is never touched.
    assert package["sections"][0]["blocks"][-1]["text"]["zh"] == "保留。"


def test_a_broken_translation_wave_still_fails_the_run():
    """Many gaps are not a miss, they are a wave that did not run — filling
    them would ship an English document labelled Chinese."""
    package = _package_with_blank_zh(20)
    assert memo_analysis._fill_sparse_zh_gaps(package) == []
    assert package["sections"][0]["blocks"][0]["text"]["zh"] == ""


def test_nothing_to_fill_reports_nothing():
    package = {"sections": [{"blocks": [{"text": {"en": "a", "zh": "甲"}}]}]}
    assert memo_analysis._fill_sparse_zh_gaps(package) == []


def test_the_fallback_is_off_unless_a_caller_asks(tmp_path):
    """Only the gate that runs AFTER the monolithic Chinese repair may use
    it; everywhere else a blank zh must still drive re-translation."""
    import inspect

    sig = inspect.signature(memo_analysis._memo_package_render_validation_error)
    assert sig.parameters["allow_zh_fallback"].default is False


# ---- the CLI rejecting every structured answer -------------------------
#
# 2026-09-16: `alternative_explanations` died after four rejections, each
# "must have required property 'key_findings'", while the seven sibling
# passes on the same schema and prompt landed. A lost pass costs the memo
# a line of argument, so it gets one more attempt.


def _run_one_pass(tmp_path, attempts):
    """Drive _run_fast_memo_pass with a scripted sequence of answers."""
    calls = []

    def fake_pass(**_kwargs):
        calls.append(1)
        return attempts[len(calls) - 1]

    return calls, fake_pass


def _pass_result(tmp_path, monkeypatch, attempts):
    calls, fake_pass = _run_one_pass(tmp_path, attempts)
    monkeypatch.setattr(claude_runner, "run_memo_fast_analysis_pass", fake_pass)
    stream = job_progress.ProgressLog(tmp_path / "stream.jsonl")
    result = memo_analysis._run_fast_memo_pass(
        spec=memo_analysis._FastMemoPassSpec(
            pass_id="alternative_explanations",
            label="Alternative explanations",
            artifact_filename="disconfirming_evidence.md",
            focus="focus",
        ),
        run_dir=tmp_path,
        company_name="Anthropic",
        company_slug="anthropic-pbc",
        run_id="run",
        stream=stream,
        research_dir=None,
        lessons_path=None,
        scope_check=None,
        warnings=[],
    )
    return result, calls


def _good_payload():
    return {
        "summary": "A real summary of what the pass established, at length.",
        "key_findings": [
            {
                "claim": "The bear case rests on undisclosed margins.",
                "finding": "No gross margin has been disclosed for any period.",
                "evidence_class": "company-reported",
                "implication": "The downside cannot be bounded from filings.",
                "confidence": "medium",
            }
        ],
    }


def test_a_rejected_pass_is_run_again(tmp_path, monkeypatch):
    rejected = (
        None,
        "the model never returned output matching the schema (4 rejected "
        "attempt(s)); the CLI's last complaint was: Output does not match "
        "required schema: root: must have required property 'key_findings'",
    )
    result, calls = _pass_result(
        tmp_path, monkeypatch, [rejected, (_good_payload(), None)]
    )
    assert len(calls) == 2
    assert result.ok
    assert result.error is None


def test_a_pass_rejected_twice_fails_and_says_why(tmp_path, monkeypatch):
    rejected = (
        None,
        "the model never returned output matching the schema; the CLI's last "
        "complaint was: Output does not match required schema: root: must "
        "have required property 'key_findings'",
    )
    result, calls = _pass_result(tmp_path, monkeypatch, [rejected, rejected])
    assert len(calls) == 2
    assert not result.ok
    assert "must have required property" in result.error


def test_an_ordinary_failure_is_not_retried(tmp_path, monkeypatch):
    """Only the schema-rejection class earns a second run."""
    result, calls = _pass_result(
        tmp_path, monkeypatch, [(None, "claude exited 1: no such file")]
    )
    assert len(calls) == 1
    assert not result.ok


def test_a_pass_that_works_first_time_runs_once(tmp_path, monkeypatch):
    result, calls = _pass_result(
        tmp_path, monkeypatch, [(_good_payload(), None)]
    )
    assert len(calls) == 1
    assert result.ok


def test_the_pass_prompt_forbids_a_probe_answer():
    """Two passes in one live run returned summary "test" and had to be
    re-run from scratch; an earlier run returned summary "test" with
    findings "a"/"b" and got all the way into a rendered memo."""
    import inspect

    source = inspect.getsource(claude_runner.run_memo_fast_analysis_pass)
    assert "Your FIRST structured answer must be the real one" in source
    assert "placeholder or a probe" in source
