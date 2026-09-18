"""When the CLI runs out of structured-output retries.

2026-09-16, first reading: two calls exited 1 with empty stderr after the
CLI gave up on structured output, and the run died reporting only "claude
exited 1". The diagnosis written here was "the response was too big to
finish its JSON".

2026-09-16, second reading, from the transcripts: that was wrong. The
rejections the CLI recorded read

    Output does not match required schema:
    root: must have required property 'key_findings'

four times over — an object submitted without its required properties,
not a giant one cut short. And across 481 stored pass payloads the whole
JSON never exceeded 15,907 characters, while successful passes wrote a
MEDIAN of 15,905 output tokens and a maximum of 24,772. The pass that
died wrote 16,422. Size does not separate the failures from the
successes; what separates them is whether the model happened to submit a
complete object.

So the rule these tests hold to: report the rejection the CLI actually
gave, never a cause inferred from a token count.
"""
from __future__ import annotations

from server import claude_runner

REJECTION = (
    "Output does not match required schema: root: must have required "
    "property 'key_findings'"
)


def test_the_subtype_is_named_not_guessed():
    assert (
        claude_runner.MEMO_STRUCTURED_OUTPUT_EXHAUSTED
        == "error_max_structured_output_retries"
    )


def test_the_error_quotes_the_cli_rather_than_guessing():
    message = claude_runner._structured_output_exhausted_error(
        {
            "subtype": "error_max_structured_output_retries",
            "usage": {"output_tokens": 16422},
        },
        {"last_schema_rejection": REJECTION, "schema_rejection_count": 4},
    )
    assert message
    assert "must have required property 'key_findings'" in message
    assert "4 rejected attempt(s)" in message
    # the old story must not come back
    assert "too large" not in message
    assert "never completed" not in message


def test_without_a_recorded_rejection_it_admits_it_does_not_know():
    message = claude_runner._structured_output_exhausted_error(
        {
            "subtype": "error_max_structured_output_retries",
            "usage": {"output_tokens": 17189},
        }
    )
    assert message
    assert "17189" in message
    assert "recorded no rejection notice" in message
    assert "too large" not in message


def test_a_successful_result_is_not_mistaken_for_it():
    assert (
        claude_runner._structured_output_exhausted_error({"subtype": "success"})
        is None
    )
    assert claude_runner._structured_output_exhausted_error(None) is None
    assert claude_runner._structured_output_exhausted_error({}) is None


def test_the_message_survives_a_result_with_no_usage():
    message = claude_runner._structured_output_exhausted_error(
        {"subtype": "error_max_structured_output_retries"}
    )
    assert message and claude_runner.is_structured_output_failure(message)


# ---- recognising the failure downstream -------------------------------------


def test_callers_recognise_the_failure_by_a_stable_phrase():
    """The retry paths key off this, not off the CLI's subtype string.

    The subtype never appears in the message, so an earlier
    `MEMO_STRUCTURED_OUTPUT_EXHAUSTED in str(error)` check could never
    fire and the section retry it guarded was dead code.
    """
    assert claude_runner.MEMO_STRUCTURED_OUTPUT_EXHAUSTED not in (
        claude_runner._structured_output_exhausted_error(
            {"subtype": "error_max_structured_output_retries"}
        )
    )
    for state in ({}, {"last_schema_rejection": REJECTION}):
        message = claude_runner._structured_output_exhausted_error(
            {"subtype": "error_max_structured_output_retries"}, state
        )
        assert claude_runner.is_structured_output_failure(message)
    assert not claude_runner.is_structured_output_failure(None)
    assert not claude_runner.is_structured_output_failure("claude exited 1")


# ---- capturing the rejection from the stream --------------------------------


def test_a_rejection_tool_result_is_recorded():
    state: dict = {}
    claude_runner._note_schema_rejection(state, REJECTION)
    claude_runner._note_schema_rejection(state, REJECTION + " (again)")
    assert state["schema_rejection_count"] == 2
    assert state["last_schema_rejection"].endswith("(again)")


def test_ordinary_tool_results_are_not_recorded():
    state: dict = {}
    claude_runner._note_schema_rejection(state, "Web search results for ...")
    claude_runner._note_schema_rejection(state, None)
    claude_runner._note_schema_rejection(state, "")
    assert state == {}


def test_the_rejection_reaches_the_error_through_the_stream_handler():
    """End to end: a CLI rejection event, then the failure message."""
    state: dict = {}

    class _Progress:
        def emit(self, *_args, **_kwargs):
            pass

    event = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "content": [{"type": "text", "text": REJECTION}],
                }
            ]
        },
    }
    claude_runner._process_search_event(event, _Progress(), state)
    message = claude_runner._structured_output_exhausted_error(
        {"subtype": "error_max_structured_output_retries"}, state
    )
    assert "must have required property 'key_findings'" in message


# ---- the other rejection: a tool call too big to parse ----------------------
#
# 2026-09-16, the spine. Four attempts, each cut off mid-JSON:
#
#   InputValidationError: StructuredOutput was called with input that
#   could not be parsed as JSON.
#   You sent (first 200 of 33330 bytes): {"package_skeleton": ...
#
# 33,330 -> 31,264 -> 28,240 -> 27,850 bytes. The model kept shrinking and
# still never fit. THIS is a size failure, and it reads nothing like the
# passes' "must have required property". Both exist; they need opposite
# fixes, so the message must tell them apart.

UNPARSEABLE = (
    "<tool_use_error>InputValidationError: StructuredOutput was called "
    "with input that could not be parsed as JSON.\nYou sent (first 200 "
    'of 33330 bytes): {"package_skeleton": {"schema_version": 1'
)


def _unparseable(size):
    return UNPARSEABLE.replace("33330", str(size))


def test_an_unparseable_tool_call_is_recorded_with_its_size():
    state: dict = {}
    for size in (33330, 31264, 28240, 27850):
        claude_runner._note_schema_rejection(state, _unparseable(size))
    assert state["unparsed_input_bytes"] == [33330, 31264, 28240, 27850]
    assert state["schema_rejection_count"] == 4


def test_the_size_failure_says_split_the_ask():
    state: dict = {}
    for size in (33330, 31264, 28240, 27850):
        claude_runner._note_schema_rejection(state, _unparseable(size))
    message = claude_runner._structured_output_exhausted_error(
        {"subtype": "error_max_structured_output_retries"}, state
    )
    assert "27,850 bytes" in message
    assert "down from 33,330 across 4 attempts" in message
    assert "too big for one call" in message
    assert claude_runner.is_structured_output_failure(message)


def test_a_single_oversize_attempt_does_not_claim_it_shrank():
    state: dict = {}
    claude_runner._note_schema_rejection(state, _unparseable(20000))
    message = claude_runner._structured_output_exhausted_error(
        {"subtype": "error_max_structured_output_retries"}, state
    )
    assert "20,000 bytes" in message
    assert "down from" not in message


def test_size_evidence_outranks_a_trailing_schema_complaint():
    """The CLI's last word was a schema complaint about the wrapper it
    made from the unparseable input; the real cause is the size."""
    state: dict = {}
    claude_runner._note_schema_rejection(state, _unparseable(33330))
    claude_runner._note_schema_rejection(
        state,
        "Output does not match required schema: root: must have required "
        "property 'package_skeleton', root: must NOT have additional "
        "properties ('__unparsedToolInput' is not allowed)",
    )
    message = claude_runner._structured_output_exhausted_error(
        {"subtype": "error_max_structured_output_retries"}, state
    )
    assert "too big for one call" in message
    assert "__unparsedToolInput" not in message
