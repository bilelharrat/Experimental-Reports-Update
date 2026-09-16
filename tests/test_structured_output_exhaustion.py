"""When the CLI runs out of structured-output retries.

2026-09-16: two calls in one run — market_sizing and executive_summary —
exited 1 with empty stderr after the CLI gave up on structured output.
The run reported "claude exited 1" and died with $14.60 spent. The schemas
involved are permissive (the English section schema is literally
`{"section": {"type": "object"}}`), so repeated validation failure means
the JSON never closed: the response was too big to finish.
"""
from __future__ import annotations

from server import claude_runner


def test_the_subtype_is_named_not_guessed():
    assert (
        claude_runner.MEMO_STRUCTURED_OUTPUT_EXHAUSTED
        == "error_max_structured_output_retries"
    )


def test_the_error_says_what_went_wrong_and_what_to_do():
    message = claude_runner._structured_output_exhausted_error(
        {
            "subtype": "error_max_structured_output_retries",
            "usage": {"output_tokens": 17189},
        }
    )
    assert message
    assert "17189" in message
    # It must not read as a model error — the ask was too large.
    assert "too large" in message
    assert "Split the ask" in message


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
    assert message and "structured-output retries" in message


def test_the_section_schema_is_permissive_enough_to_prove_the_diagnosis():
    """If this schema ever grows limits, the "JSON never closed" reading
    stops being the only explanation and this analysis needs redoing."""
    schema = claude_runner._MEMO_ENGLISH_SECTION_SCHEMA
    assert schema["properties"]["section"] == {
        "type": "object",
        "additionalProperties": True,
    }
