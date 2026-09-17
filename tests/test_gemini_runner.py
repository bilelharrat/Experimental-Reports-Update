"""Gemini backend + engine-selection policy.

Every test stubs the HTTP layer: the suite never reaches the network and
never needs a real key.
"""
from __future__ import annotations

import json

import httpx
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


def test_grounded_calls_enable_google_search(monkeypatch, key):
    calls: list[dict] = []
    grounding = {
        "webSearchQueries": ["acme founders"],
        "groundingChunks": [
            {"web": {"uri": "https://example.com/a", "title": "Example"}},
            {"web": {"uri": "https://example.com/a", "title": "Duplicate"}},
            {"web": {"uri": "https://example.com/b", "title": ""}},
        ],
    }
    _stub_post(
        monkeypatch,
        [_response(200, _envelope('{"headline": "x"}', grounding=grounding))],
        calls,
    )

    data, meta, error = gemini_runner.run_grounded_json(
        system_prompt="s", user_prompt="u", schema=SCHEMA, name="team"
    )

    assert error is None and data == {"headline": "x"}
    assert calls[0]["body"]["tools"] == [{"google_search": {}}]
    # Duplicate URIs collapse; a blank title falls back to the URL.
    assert meta["sources"] == [
        {"title": "Example", "url": "https://example.com/a"},
        {"title": "https://example.com/b", "url": "https://example.com/b"},
    ]
    assert meta["queries"] == ["acme founders"]
    assert meta["engine"] == "gemini"


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
    # Second attempt drops the schema field and carries the schema as text.
    assert "responseSchema" not in calls[1]["body"]["generationConfig"]
    assert "responseMimeType" not in calls[1]["body"]["generationConfig"]
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
