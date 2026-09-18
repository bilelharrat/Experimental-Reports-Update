"""Gemini backend + engine-selection policy.

Every test stubs the HTTP layer: the suite never reaches the network and
never needs a real key.
"""
from __future__ import annotations

import json

import httpx
from pathlib import Path
import pytest

from server import ai_engine, gemini_runner

SCHEMA = {
    "type": "object",
    "properties": {"headline": {"type": "string"}},
    "required": ["headline"],
}


def _response(status: int, payload: dict | str) -> httpx.Response:
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com/x")
    if isinstance(payload, str):
        return httpx.Response(status, text=payload, request=request)
    return httpx.Response(status, json=payload, request=request)


def _envelope(text: str, *, grounding: dict | None = None) -> dict:
    candidate: dict = {
        "content": {"role": "model", "parts": [{"text": text}]},
        "finishReason": "STOP",
    }
    if grounding is not None:
        candidate["groundingMetadata"] = grounding
    return {"candidates": [candidate]}


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("BSH_GEMINI_MODEL", raising=False)
    monkeypatch.delenv("BSH_GEMINI_THINKING", raising=False)
    monkeypatch.delenv("BSH_AI_ENGINE", raising=False)


@pytest.fixture
def no_key(monkeypatch):
    for name in ("GEMINI_API_KEY", "BSH_GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _stub_post(monkeypatch, responses, calls=None):
    """Answer each POST from ``responses`` in order, recording request bodies."""
    queue = list(responses)

    def post(url, **kwargs):
        if calls is not None:
            calls.append({"url": url, "body": kwargs.get("json"), "headers": kwargs.get("headers")})
        result = queue.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(gemini_runner.httpx, "post", post)
    return queue


# ---- configuration --------------------------------------------------------


def test_is_available_follows_the_key(monkeypatch, no_key):
    assert gemini_runner.is_available() is False
    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    assert gemini_runner.is_available() is True


def test_missing_key_is_an_error_not_an_exception(no_key):
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None
    assert "GEMINI_API_KEY" in error


def test_thinking_level_rejects_unsupported_values(monkeypatch):
    monkeypatch.setenv("BSH_GEMINI_THINKING", "minimal")
    assert gemini_runner.default_thinking_level() == "low"
    monkeypatch.setenv("BSH_GEMINI_THINKING", "high")
    assert gemini_runner.default_thinking_level() == "high"


# ---- request shape --------------------------------------------------------


def test_request_matches_the_rest_contract(monkeypatch, key):
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(200, _envelope('{"headline": "hi"}'))], calls)

    data, error = gemini_runner.run_structured_prompt(
        system_prompt="You are a desk editor.",
        user_prompt="Write it.",
        schema=SCHEMA,
        name="desk_note",
    )

    assert error is None
    assert data == {"headline": "hi"}
    call = calls[0]
    assert call["url"].endswith("/models/gemini-3.8-flash:generateContent")
    assert call["headers"]["x-goog-api-key"] == "test-key"
    body = call["body"]
    assert body["systemInstruction"]["parts"][0]["text"] == "You are a desk editor."
    assert body["contents"][0]["parts"][0]["text"] == "Write it."
    assert body["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"] == SCHEMA
    assert "tools" not in body


GROUNDING = {
    "webSearchQueries": ["acme founders"],
    "groundingChunks": [
        {"web": {"uri": "https://example.com/a", "title": "Example"}},
        {"web": {"uri": "https://example.com/a", "title": "Duplicate"}},
        {"web": {"uri": "https://example.com/b", "title": ""}},
    ],
}


def _grounded_pair(research="Acme was founded by Dana Reeve.", structured='{"headline": "x"}'):
    """The two responses a grounded call now consumes: research, then structure."""
    return [
        _response(200, _envelope(research, grounding=GROUNDING)),
        _response(200, _envelope(structured)),
    ]


def test_a_grounded_call_researches_then_structures(monkeypatch, key):
    """One request asking for both a search and schema JSON measured 2
    grounded responses in 5 — the model treats a schema-carrying prompt as
    a formatting task. The research step must carry no schema at all."""
    calls: list[dict] = []
    _stub_post(monkeypatch, _grounded_pair(), calls)

    data, meta, error = gemini_runner.run_grounded_json(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="team"
    )

    assert error is None and data == {"headline": "x"}
    assert len(calls) == 2

    research, structure = calls[0]["body"], calls[1]["body"]
    # Step 1: searching, and no schema anywhere — not as responseSchema, and
    # not as schema text in the prompt.
    assert research["tools"] == [{"google_search": {}}]
    assert "responseSchema" not in research["generationConfig"]
    assert "headline" not in research["contents"][0]["parts"][0]["text"]
    # Step 2: schema-constrained, and no search tool to invent from.
    assert "tools" not in structure
    assert structure["generationConfig"]["responseSchema"] == SCHEMA
    # The research prose is what gets structured.
    assert "Dana Reeve" in structure["contents"][0]["parts"][0]["text"]

    # Sources come from the research step: duplicates collapse, a blank
    # title falls back to the URL.
    assert meta["sources"] == [
        {"title": "Example", "url": "https://example.com/a"},
        {"title": "https://example.com/b", "url": "https://example.com/b"},
    ]
    assert meta["queries"] == ["acme founders"]
    assert meta["engine"] == "gemini"
    assert meta["grounded"] is True


def test_a_failed_research_step_never_reaches_the_structure_step(monkeypatch, key):
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(403, {"error": {"message": "no key"}})], calls)
    data, _meta, error = gemini_runner.run_grounded_json(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="team"
    )
    assert data is None and "no key" in error
    assert len(calls) == 1


# ---- response handling ----------------------------------------------------


def test_thinking_parts_are_not_treated_as_output(monkeypatch, key):
    envelope = {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": "Let me think about this.", "thought": True},
                        {"text": '{"headline": "real"}'},
                    ]
                },
                "finishReason": "STOP",
            }
        ]
    }
    _stub_post(monkeypatch, [_response(200, envelope)])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "real"}


@pytest.mark.parametrize(
    "text",
    [
        '```json\n{"headline": "fenced"}\n```',
        'Here you go:\n{"headline": "fenced"}',
    ],
)
def test_fenced_and_prefixed_json_still_parse(monkeypatch, key, text):
    _stub_post(monkeypatch, [_response(200, _envelope(text))])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "fenced"}


def test_blocked_prompt_reports_the_block_reason(monkeypatch, key):
    _stub_post(monkeypatch, [_response(200, {"promptFeedback": {"blockReason": "SAFETY"}})])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None
    assert "prompt blocked (SAFETY)" in error


def test_truncated_response_is_reported_not_silently_empty(monkeypatch, key):
    envelope = {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}
    _stub_post(monkeypatch, [_response(200, envelope)])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None
    assert "output token limit" in error


def test_api_error_message_surfaces_without_the_key(monkeypatch, key):
    _stub_post(
        monkeypatch,
        [
            _response(
                403,
                {"error": {"status": "PERMISSION_DENIED", "message": "API key not valid"}},
            )
        ],
    )
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None
    assert "PERMISSION_DENIED" in error and "API key not valid" in error
    assert "test-key" not in error


# ---- retries and degradation ----------------------------------------------


def test_rate_limit_is_retried(monkeypatch, key):
    monkeypatch.setattr(gemini_runner.time, "sleep", lambda _s: None)
    _stub_post(
        monkeypatch,
        [
            _response(429, {"error": {"message": "quota"}}),
            _response(200, _envelope('{"headline": "after retry"}')),
        ],
    )
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "after retry"}


def test_client_error_is_not_retried(monkeypatch, key):
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(401, {"error": {"message": "bad key"}})], calls)
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None and "bad key" in error
    assert len(calls) == 1


def test_schema_rejection_retries_with_the_schema_in_the_prompt(monkeypatch, key):
    calls: list[dict] = []
    _stub_post(
        monkeypatch,
        [
            _response(400, {"error": {"message": "Invalid JSON schema"}}),
            _response(200, _envelope('{"headline": "recovered"}')),
        ],
        calls,
    )
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "recovered"}
    assert "responseSchema" in calls[0]["body"]["generationConfig"]
    # Second attempt drops the schema field and carries the schema as text —
    # but stays in JSON mode, which is what keeps the output parseable.
    assert "responseSchema" not in calls[1]["body"]["generationConfig"]
    assert calls[1]["body"]["generationConfig"]["responseMimeType"] == "application/json"
    assert json.dumps(SCHEMA, indent=2) in calls[1]["body"]["contents"][0]["parts"][0]["text"]


def test_timeout_is_an_error_not_a_raise(monkeypatch, key):
    monkeypatch.setattr(gemini_runner.time, "sleep", lambda _s: None)
    _stub_post(monkeypatch, [httpx.TimeoutException("slow")] * gemini_runner.MAX_ATTEMPTS)
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t", timeout_sec=5
    )
    assert data is None and "timed out after 5s" in error


# ---- engine policy --------------------------------------------------------


def test_default_policy_prefers_gemini(monkeypatch, key):
    _stub_post(monkeypatch, [_response(200, _envelope('{"headline": "g"}'))])
    monkeypatch.setattr(
        ai_engine.claude_runner,
        "run_structured_prompt",
        lambda **_kw: pytest.fail("Claude must not be called when Gemini succeeds"),
    )
    data, meta, error = ai_engine.structured(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "g"}
    assert meta["engine"] == "gemini"
    assert meta["fallback_reason"] is None


def test_gemini_failure_falls_back_to_claude_and_records_why(monkeypatch, key):
    _stub_post(monkeypatch, [_response(403, {"error": {"message": "key revoked"}})])
    monkeypatch.setattr(
        ai_engine.claude_runner,
        "run_structured_prompt",
        lambda **_kw: ({"headline": "c"}, None),
    )
    data, meta, error = ai_engine.structured(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "c"}
    assert meta["engine"] == "claude"
    assert "key revoked" in meta["fallback_reason"]


def test_missing_key_falls_back_to_claude(monkeypatch, no_key):
    monkeypatch.delenv("BSH_AI_ENGINE", raising=False)
    monkeypatch.setattr(
        ai_engine.claude_runner,
        "run_structured_prompt",
        lambda **_kw: ({"headline": "c"}, None),
    )
    data, meta, error = ai_engine.structured(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and meta["engine"] == "claude"
    assert meta["fallback_reason"] == "no Gemini API key configured"


def test_gemini_only_policy_does_not_spend_claude(monkeypatch, key):
    monkeypatch.setenv("BSH_AI_ENGINE", "gemini-only")
    _stub_post(monkeypatch, [_response(403, {"error": {"message": "nope"}})])
    monkeypatch.setattr(
        ai_engine.claude_runner,
        "run_structured_prompt",
        lambda **_kw: pytest.fail("gemini-only must not fall back"),
    )
    data, meta, error = ai_engine.structured(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None and error is not None
    assert meta["engine"] == "gemini"


def test_claude_policy_skips_gemini_entirely(monkeypatch, key):
    monkeypatch.setenv("BSH_AI_ENGINE", "claude")
    monkeypatch.setattr(
        gemini_runner.httpx,
        "post",
        lambda *_a, **_kw: pytest.fail("claude policy must not call Gemini"),
    )
    monkeypatch.setattr(
        ai_engine.claude_runner,
        "run_structured_prompt",
        lambda **_kw: ({"headline": "c"}, None),
    )
    data, meta, error = ai_engine.structured(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and meta["engine"] == "claude"
    assert meta["fallback_reason"] is None


def test_grounded_fallback_reports_no_sources(monkeypatch, key):
    _stub_post(monkeypatch, [_response(500, {"error": {"message": "boom"}})] * gemini_runner.MAX_ATTEMPTS)
    monkeypatch.setattr(gemini_runner.time, "sleep", lambda _s: None)
    monkeypatch.setattr(
        ai_engine.claude_runner,
        "run_web_research_json",
        lambda **_kw: ({"headline": "c"}, None),
    )
    data, meta, error = ai_engine.grounded(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and meta["engine"] == "claude"
    assert meta["sources"] == []
    assert "boom" in meta["fallback_reason"]


# ---- diagnostics ----------------------------------------------------------


def test_diagnostics_reports_engine_config_without_spending_a_call(monkeypatch, key):
    """The settings surface needs to answer 'is my key live?' without paying
    for a generation to find out."""
    from starlette.testclient import TestClient

    from server.main import app

    monkeypatch.setattr(
        gemini_runner.httpx,
        "post",
        lambda *_a, **_kw: pytest.fail("diagnostics must not call the model"),
    )
    monkeypatch.setenv("BSH_AI_ENGINE", "gemini")
    body = TestClient(app).get("/api/diagnostics").json()
    assert body["gemini_key_configured"] is True
    assert body["gemini_model"] == "gemini-3.8-flash"
    assert body["ai_engine_policy"] == "gemini"


def test_diagnostics_reports_a_missing_key(no_key):
    from starlette.testclient import TestClient

    from server.main import app

    body = TestClient(app).get("/api/diagnostics").json()
    assert body["gemini_key_configured"] is False


def test_a_bad_key_is_not_mistaken_for_a_schema_rejection(monkeypatch, key):
    """Both arrive as HTTP 400. Retrying an auth failure without the schema
    spends a second doomed call and logs the wrong reason."""
    calls: list[dict] = []
    _stub_post(
        monkeypatch,
        [_response(400, {"error": {"message": "API key not valid. Please pass a valid API key."}})],
        calls,
    )
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert data is None and "API key not valid" in error
    assert len(calls) == 1


def test_unsupported_schema_keywords_are_stripped_before_sending(monkeypatch, key):
    """`response_schema` 400s on keywords outside its OpenAPI subset rather
    than ignoring them, and our schemas carry `additionalProperties` because
    they were written for Claude."""
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(200, _envelope('{"headline": "x"}'))], calls)
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False, "properties": {}},
            }
        },
    }
    gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=schema, name="t"
    )
    sent = calls[0]["body"]["generationConfig"]["responseSchema"]
    assert "additionalProperties" not in sent
    assert "additionalProperties" not in sent["properties"]["rows"]["items"]
    # The shape itself survives.
    assert sent["properties"]["rows"]["type"] == "array"


# ---- engine availability --------------------------------------------------


def test_availability_does_not_depend_on_the_claude_cli(monkeypatch, key):
    """A Gemini key with no CLI installed is a working setup. The pre-Gemini
    check would have left background loops switched off."""
    monkeypatch.delenv("BSH_AI_ENGINE", raising=False)
    monkeypatch.setattr(ai_engine.claude_runner, "is_available", lambda: False)
    assert ai_engine.available() is True


def test_availability_is_false_when_nothing_can_run(monkeypatch, no_key):
    monkeypatch.delenv("BSH_AI_ENGINE", raising=False)
    monkeypatch.setattr(ai_engine.claude_runner, "is_available", lambda: False)
    assert ai_engine.available() is False


def test_claude_policy_availability_ignores_the_gemini_key(monkeypatch, key):
    monkeypatch.setenv("BSH_AI_ENGINE", "claude")
    monkeypatch.setattr(ai_engine.claude_runner, "is_available", lambda: False)
    assert ai_engine.available() is False


def test_an_ungrounded_answer_is_reported_as_ungrounded(monkeypatch, key):
    """The model may answer a grounded request from memory. That is recall,
    not research, and callers key `is_deep_audited` off this."""
    _stub_post(
        monkeypatch,
        [
            _response(200, _envelope("I already know this.")),
            _response(200, _envelope('{"headline": "x"}')),
        ],
    )
    data, meta, error = gemini_runner.run_grounded_json(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert error is None and data == {"headline": "x"}
    assert meta["grounded"] is False
    assert meta["sources"] == []


def test_a_searched_answer_is_reported_as_grounded(monkeypatch, key):
    _stub_post(monkeypatch, _grounded_pair())
    _data, meta, _error = gemini_runner.run_grounded_json(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert meta["grounded"] is True


def test_the_research_step_uses_the_level_that_searches(monkeypatch, key):
    calls: list[dict] = []
    _stub_post(monkeypatch, _grounded_pair(), calls)
    gemini_runner.run_grounded_json(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    research_cfg = calls[0]["body"]["generationConfig"]
    assert research_cfg["thinkingConfig"]["thinkingLevel"] == "medium"
    # The structure step has nothing to reason about, so it stays cheap.
    assert calls[1]["body"]["generationConfig"]["thinkingConfig"]["thinkingLevel"] == "low"


def test_union_types_are_collapsed_for_the_response_schema(monkeypatch, key):
    """`{"type": ["string", "null"]}` is ordinary JSON Schema and is how the
    Claude-era schemas here spell a nullable field, but response_schema's
    proto takes one type plus a nullable flag and 400s on the list."""
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(200, _envelope('{"headline": "x"}'))], calls)
    schema = {
        "type": "object",
        "properties": {
            "note": {"type": ["string", "null"]},
            "rows": {"type": "array", "items": {"type": ["integer", "null"]}},
            "plain": {"type": "string"},
        },
    }
    gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=schema, name="t"
    )
    sent = calls[0]["body"]["generationConfig"]["responseSchema"]
    assert sent["properties"]["note"] == {"type": "string", "nullable": True}
    assert sent["properties"]["rows"]["items"] == {"type": "integer", "nullable": True}
    # A field that was never a union is untouched.
    assert sent["properties"]["plain"] == {"type": "string"}


def test_a_free_form_object_schema_goes_in_the_prompt(monkeypatch, key):
    """`{"type": "object", "additionalProperties": true}` means "free-form",
    and the memo package body is exactly that. response_schema cannot express
    it, and stripping the keyword leaves an object with no permitted
    properties — which returned an empty investment memo on a live run."""
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(200, _envelope('{"memo_package": {"a": 1}}'))], calls)
    schema = {
        "type": "object",
        "properties": {"memo_package": {"type": "object", "additionalProperties": True}},
    }
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=schema, name="memo"
    )
    assert error is None and data == {"memo_package": {"a": 1}}
    body = calls[0]["body"]
    assert "responseSchema" not in body["generationConfig"]
    # The full schema, additionalProperties included, reaches the model as text.
    assert "additionalProperties" in body["contents"][0]["parts"][0]["text"]


def test_an_expressible_schema_still_uses_response_schema(monkeypatch, key):
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(200, _envelope('{"headline": "x"}'))], calls)
    gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="t"
    )
    assert "responseSchema" in calls[0]["body"]["generationConfig"]


def test_a_truncated_response_says_so_instead_of_a_parse_error(monkeypatch, key):
    """Truncated output still looks like output. Reporting the parse failure
    instead of the cause sent a live memo run chasing a JSON bug that was
    really an output-length limit."""
    envelope = {
        "candidates": [
            {
                "content": {"parts": [{"text": '{"memo": "half a document'}]},
                "finishReason": "MAX_TOKENS",
            }
        ]
    }
    _stub_post(monkeypatch, [_response(200, envelope)])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="memo English package"
    )
    assert data is None
    assert "output token limit" in error and "max_output_tokens" in error


# ---- JSON mode and malformed output ---------------------------------------


def test_json_mode_is_on_even_when_the_schema_travels_in_the_prompt(monkeypatch, key):
    """A free-form schema cannot be sent as responseSchema, but JSON mode
    (constrained decoding) still can — and it is what stops the model from
    emitting a stray quote or prose around the object. The Chinese memo
    package, which failed to parse on a live run, is exactly this call."""
    calls: list[dict] = []
    _stub_post(monkeypatch, [_response(200, _envelope('{"memo_package": {"a": 1}}'))], calls)
    schema = {"type": "object", "properties": {"memo_package": {"type": "object", "additionalProperties": True}}}
    gemini_runner.run_structured_prompt(system_prompt="s", user_prompt="u", schema=schema, name="zh")
    cfg = calls[0]["body"]["generationConfig"]
    assert cfg["responseMimeType"] == "application/json"
    assert "responseSchema" not in cfg


def test_the_research_step_of_a_grounded_call_stays_off_json_mode(monkeypatch, key):
    """A response constraint alongside google_search empties the grounding."""
    calls: list[dict] = []
    _stub_post(monkeypatch, _grounded_pair(), calls)
    gemini_runner.run_grounded_json(system_prompt="s", user_prompt="u", schema=SCHEMA, name="t")
    research_cfg = calls[0]["body"]["generationConfig"]
    assert "responseMimeType" not in research_cfg and "responseSchema" not in research_cfg
    # The structure step is an ordinary JSON call and gets both.
    assert calls[1]["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_an_unescaped_emphasis_quote_around_a_cjk_term_is_repaired(monkeypatch, key):
    text = '{"headline": "公司的"核心"竞争力在于渠道"}'
    _stub_post(monkeypatch, [_response(200, _envelope(text))])
    data, error = gemini_runner.run_structured_prompt(system_prompt="s", user_prompt="u", schema=SCHEMA, name="zh")
    assert error is None
    assert data == {"headline": '公司的"核心"竞争力在于渠道'}


def test_a_parse_failure_shows_how_the_output_ends(monkeypatch, key):
    """The head of a 60KB package never says whether it was cut off; the
    tail does. The live failure message showed only the head."""
    text = '{"memo_package": {"sections": [{"id": "executive_summary", "text": "' + "x" * 500
    _stub_post(monkeypatch, [_response(200, _envelope(text))])
    data, error = gemini_runner.run_structured_prompt(system_prompt="s", user_prompt="u", schema=SCHEMA, name="zh")
    assert data is None
    assert "ends:" in error and error.rstrip("'\"").endswith("x" * 40)
    assert "chars" in error


def test_a_raw_control_character_inside_a_string_is_accepted(monkeypatch, key):
    """The default decoder rejects a whole 27KB document over one literal tab
    in a Chinese paragraph — which is what a live section unit hit."""
    text = '{"headline": "第一行' + "\t" + '第二行"}'  # a real TAB inside the string
    assert "\t" in text and "\\t" not in text
    _stub_post(monkeypatch, [_response(200, _envelope(text))])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="zh"
    )
    assert error is None
    assert data == {"headline": "第一行\t第二行"}


def test_a_parse_failure_names_the_decoder_reason_and_keeps_the_raw_output(
    monkeypatch, key, tmp_path
):
    import re as _re
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    _stub_post(monkeypatch, [_response(200, _envelope('{"a": 1,, "b": 2}'))])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA,
        name="memo Chinese package (section x)",
    )
    assert data is None
    assert "Expecting" in error, error
    match = _re.search(r"raw output kept at (\S+?);", error)
    assert match, error
    assert Path(match.group(1)).read_text(encoding="utf-8") == '{"a": 1,, "b": 2}'


def test_a_stray_word_between_structural_tokens_is_removed(monkeypatch, key):
    """A 21KB Chinese unit read `…"}]  Feature ]},{…` at the decoder's failure
    position — one bare identifier between an array close and the next
    close. Retrying the unit reproduced it."""
    text = '{"rows":[[{"en":"a","zh":"甲"}]  Feature ],"next":{"en":"b","zh":"乙"}}'
    _stub_post(monkeypatch, [_response(200, _envelope(text))])
    data, error = gemini_runner.run_structured_prompt(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="zh"
    )
    assert error is None, error
    assert data == {"rows": [[{"en": "a", "zh": "甲"}]], "next": {"en": "b", "zh": "乙"}}


def test_the_stray_token_repair_never_touches_string_content(monkeypatch, key):
    """The decoder never stops inside a string, so words inside values are
    untouchable — and a genuinely broken document still fails honestly."""
    assert gemini_runner._strip_stray_tokens('{"a": "x ] Feature ] y"}') is None
    assert gemini_runner._strip_stray_tokens('{"a": [1, 2') is None



# ---- a dropped closing bracket ------------------------------------------------


def test_a_dropped_closing_bracket_is_restored_from_the_decoder_position():
    """Live (Koch, 2026-09-18): a 26KB risk section closed a table block with
    `}` while its rows array was still open — one `]` short, the rest of the
    document balanced — and the whole section was lost to it."""
    good = {
        "section": {
            "id": "investment_risk",
            "blocks": [
                {
                    "type": "table",
                    "rows": [
                        [{"en": "Risk Rating", "zh": "风险评分"}],
                        [{"en": "9/10", "zh": "9/10"}],
                    ],
                },
                {"type": "heading", "level": 3, "text": {"en": "Risk 2", "zh": "风险 2"}},
            ],
        }
    }
    text = json.dumps(good, ensure_ascii=False)
    dropped = text.replace('"9/10"}]]}', '"9/10"}]}', 1)  # the `]` closing rows
    assert dropped != text
    parsed, reason = gemini_runner._loads_object(dropped)
    assert reason is None
    assert parsed == good


def test_a_dropped_closing_brace_is_restored_too():
    """The structure-repair pass of the same run dropped a `}` before a `]`."""
    good = {"a": [{"b": 1}, {"c": [1, 2]}], "d": "x"}
    text = json.dumps(good)
    dropped = text.replace('"c": [1, 2]}]', '"c": [1, 2]]', 1)
    assert dropped != text
    parsed, reason = gemini_runner._loads_object(dropped)
    assert reason is None
    assert parsed == good


def test_brackets_inside_strings_do_not_mislead_the_repair():
    good = {"text": "a ] stray } pair [ of { brackets", "rows": [[1], [2]]}
    text = json.dumps(good)
    dropped = text.replace("[2]]}", "[2]}", 1)
    parsed, reason = gemini_runner._loads_object(dropped)
    assert reason is None
    assert parsed == good


def test_an_extra_closing_bracket_is_removed_when_that_is_the_edit_that_parses():
    """The structure-repair pass of the same run wrote one `]` too many
    after a table's rows. Inserting the owed `}` there reads fine for a
    while and then leaves the document a level off; deleting parses."""
    good = {"a": [[1], [2]], "b": {"c": "d"}}
    text = json.dumps(good)
    extra = text.replace('[[1], [2]]', '[[1], [2]]]', 1)
    assert extra != text
    parsed, reason = gemini_runner._loads_object(extra)
    assert reason is None
    assert parsed == good


def test_a_document_that_ends_early_is_not_mistaken_for_a_dropped_bracket():
    """Truncation is the output-limit case, reported as such — not patched."""
    parsed, reason = gemini_runner._loads_object('{"a": [1, 2')
    assert parsed is None
    assert reason
