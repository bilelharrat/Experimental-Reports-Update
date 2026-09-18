"""Run Google Gemini as a structured-JSON backend for research jobs.

Why a second engine alongside ``claude_runner``:
- The Claude path shells out to the ``claude`` CLI, which spends the user's
  Claude Code subscription and serializes behind a subprocess. For the small,
  high-frequency research calls (a desk note, a company news sweep, a founder
  dossier) a metered HTTP call to Flash is cheaper and much faster.
- Gemini's ``google_search`` tool grounds an answer in live web results and
  hands back the source URIs it used, which is exactly what the founder
  dossier and the company news feed need. The Claude equivalent costs a
  full agentic CLI run with WebSearch enabled.

``run_structured_prompt`` deliberately mirrors
``claude_runner.run_structured_prompt``'s signature and ``(data, error)``
return contract, so a call site can switch engines without reshaping its
code. ``run_grounded_json`` is the grounded variant: same JSON contract plus
the grounding metadata (source URIs, the searches the model ran).

Config (all optional except the key):
- ``GEMINI_API_KEY`` / ``BSH_GEMINI_API_KEY`` — the key. No key means
  ``is_available()`` is False and every call returns an error, which is the
  signal callers use to fall back to Claude.
- ``BSH_GEMINI_MODEL`` — default ``gemini-3.8-flash``.
- ``BSH_GEMINI_THINKING`` — ``low`` | ``medium`` | ``high`` (Flash rejects
  ``minimal``). Default ``low``.
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
from pathlib import Path
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_THINKING = "low"
# Grounded calls get their own default, and it is not the cheapest one.
# Whether the model actually calls `google_search` turns out to depend on the
# thinking level, and not monotonically: measured against the live API on the
# founder-dossier prompt, `low` and `high` both answered from model memory
# with zero searches, while `medium` searched every time (13-16 queries,
# 19-32 sources). An ungrounded answer here is the failure this whole module
# exists to avoid — it reads as researched while being unsourced recall — so
# grounded calls default to the level that demonstrably searches.
DEFAULT_GROUNDED_THINKING = "medium"
THINKING_LEVELS = ("low", "medium", "high")

# Attempts for a call that failed in a way a retry can fix (rate limit, 5xx,
# connection reset). Kept small: these run inside user-facing requests.
MAX_ATTEMPTS = 3
RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})

# Whether the model calls `google_search` is its own decision and it is not
# reliable on a long, schema-carrying prompt: measured on the founder-dossier
# prompt for a well-known company, identical requests grounded 2 times in 5.
#
# Retrying does NOT fix it — resampling an ungrounded call up to three times
# measured the same 2/5, so the decision is sticky for a given prompt rather
# than random per call. The retry was removed again as pure cost. A short,
# unstructured question about the same company grounds reliably, so the fix
# is prompt shape, not repetition (see docs/architecture.md).
#
# What this module owes callers meanwhile is the truth about which they got:
# `meta["grounded"]` says whether any search actually ran, and callers must
# not present an ungrounded answer as research.

# A 400 can mean the schema was rejected OR that the key is bad, the model
# name is wrong, the prompt is malformed. Only the first is worth retrying
# without the schema; the rest would just spend a second doomed call and log
# a misleading reason.
_SCHEMA_REJECTION_HINTS = (
    "schema",
    "response_format",
    "responseformat",
    "response_mime",
    "responsemimetype",
    "response_json",
)

_JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)
# An unescaped ASCII quote used as inline emphasis inside a string value —
# most often around a CJK term ("核心"竞争力). Same repair as claude_runner,
# which learned it on the same bilingual packages.
_BAD_QUOTE_RE = re.compile(r'(?<=[^\s,:\[\]{}])"(?=[^\s,:\[\]{}])')


def _loads_object(text: str) -> tuple[dict | None, str | None]:
    """`json.loads` that accepts only an object, with the quote repair.

    Returns ``(object, None)`` or ``(None, decoder reason)``. ``strict=False``
    lets a raw tab or newline inside a string value through: the grammar
    forbids them, but a 27KB Chinese section came back with one, and the
    default decoder rejects the whole document over it.
    """
    reason: str | None = None
    candidates = [text, _BAD_QUOTE_RE.sub(r'\\"', text)]
    stripped = _strip_stray_tokens(text)
    if stripped is not None:
        candidates.append(stripped)
    closed = _repair_closers(text)
    if closed is not None:
        candidates.append(closed)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate, strict=False)
        except json.JSONDecodeError as exc:
            reason = reason or f"{exc.msg} at line {exc.lineno} column {exc.colno}"
            continue
        if isinstance(parsed, dict):
            return parsed, None
        reason = reason or f"top-level JSON is {type(parsed).__name__}, not an object"
    return None, reason


_STRUCTURAL_AFTER = "]},"


def _strip_stray_tokens(text: str, *, limit: int = 25) -> str | None:
    """Remove bare words the model dropped between structural tokens.

    A 21KB Chinese section unit failed with "Expecting ',' delimiter" at a
    spot that read ``…"}]  Feature ]},{"type":…`` — one stray identifier
    between an array close and the next close. The decoder's own position
    points straight at it, so the repair is surgical: at the reported
    position, skip spaces, take one bare identifier, and delete it only if
    the next non-space character is a structural close or comma. Anything
    inside a string never qualifies, because the decoder does not stop
    there. Returns the repaired text, or None if nothing of that shape sits
    at the failure position.
    """
    changed = False
    for _ in range(limit):
        try:
            json.loads(text, strict=False)
            return text if changed else None
        except json.JSONDecodeError as exc:
            if exc.msg not in ("Expecting ',' delimiter", "Expecting value", "Extra data"):
                return text if changed else None
            i = exc.pos
            j = i
            while j < len(text) and text[j] in " \t":
                j += 1
            k = j
            while k < len(text) and (text[k].isalnum() or text[k] in "_-"):
                k += 1
            m = k
            while m < len(text) and text[m] in " \t":
                m += 1
            if k > j and m < len(text) and text[m] in _STRUCTURAL_AFTER:
                text = text[:i] + text[m:]
                changed = True
                continue
            return text if changed else None
    return text if changed else None


def _innermost_open(text: str, end: int) -> str | None:
    """The unclosed container — ``[`` or ``{`` — the decoder is inside at
    ``end``. String-aware, so brackets inside values never count."""
    stack: list[str] = []
    in_string = False
    escaped = False
    for ch in text[:end]:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "[{":
            stack.append(ch)
        elif ch in "]}" and stack:
            stack.pop()
    return stack[-1] if stack else None


def _error_pos(text: str) -> int | None:
    """Where the decoder stops, or None when the text parses."""
    try:
        json.loads(text, strict=False)
    except json.JSONDecodeError as exc:
        return exc.pos
    return None


def _repair_closers(text: str, *, limit: int = 25) -> str | None:
    """Repair a closing bracket the model dropped or doubled mid-document.

    A 26KB risk section (Koch, Inc., 2026-09-18) closed a table block with
    ``}`` while its ``rows`` array was still open — one ``]`` short, every
    other bracket balanced — and the whole section was lost to it. The
    structure-repair pass of the same run wrote one ``]`` too many after a
    table's rows. Both read the same to the decoder: "Expecting ','
    delimiter" at a closer of the wrong kind for the innermost open
    container. Whether the owed closer is missing or the found one is
    surplus cannot be told at that spot, so both edits are tried and the
    one the decoder gets further past is kept — a full parse wins
    outright. Only that one character is ever touched, and nothing inside
    a string qualifies. A document that simply ends early is not this
    shape and is left to the output-limit handling. Returns the repaired
    text, or None if nothing of that shape sits at the failure position.
    """
    changed = False
    for _ in range(limit):
        try:
            json.loads(text, strict=False)
            return text if changed else None
        except json.JSONDecodeError as exc:
            if exc.msg != "Expecting ',' delimiter" or exc.pos >= len(text):
                return text if changed else None
            found = text[exc.pos]
            open_kind = _innermost_open(text, exc.pos)
            if found == "}" and open_kind == "[":
                owed = "]"
            elif found == "]" and open_kind == "{":
                owed = "}"
            else:
                return text if changed else None
            inserted = text[: exc.pos] + owed + text[exc.pos :]
            deleted = text[: exc.pos] + text[exc.pos + 1 :]
            progress = [(_error_pos(candidate), candidate) for candidate in (inserted, deleted)]
            for pos, candidate in progress:
                if pos is None:
                    return candidate
            text = max(progress, key=lambda item: item[0])[1]
            changed = True
    return text if changed else None


class GeminiUnavailableError(RuntimeError):
    """No API key configured."""


# ---- configuration --------------------------------------------------------


def api_key() -> str | None:
    for name in ("GEMINI_API_KEY", "BSH_GEMINI_API_KEY", "GOOGLE_API_KEY"):
        value = str(os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def is_available() -> bool:
    """True when a key is configured. Never logs or returns the key itself."""
    return api_key() is not None


def default_model() -> str:
    return str(os.environ.get("BSH_GEMINI_MODEL") or "").strip() or DEFAULT_MODEL


def default_thinking_level(*, grounded: bool = False) -> str:
    var = "BSH_GEMINI_GROUNDED_THINKING" if grounded else "BSH_GEMINI_THINKING"
    fallback = DEFAULT_GROUNDED_THINKING if grounded else DEFAULT_THINKING
    raw = str(os.environ.get(var) or "").strip().lower()
    return raw if raw in THINKING_LEVELS else fallback


# ---- response parsing -----------------------------------------------------


def _parse_json_payload(text: str) -> dict | None:
    """Parse a model response as one JSON object, tolerating stray prose.

    The schema-constrained path returns clean JSON; the degraded path (schema
    in the prompt instead of ``responseFormat``) sometimes wraps it in a
    fence or a sentence, so the fence and first-object fallbacks stay.
    """
    return _parse_json_payload_reason(text)[0]


def _parse_json_payload_reason(text: str) -> tuple[dict | None, str | None]:
    """Like ``_parse_json_payload`` but also says why parsing failed."""
    candidate = (text or "").strip()
    if not candidate:
        return None, "empty response"
    parsed, reason = _loads_object(candidate)
    if parsed is not None:
        return parsed, None
    fenced = _FENCE_RE.findall(candidate)
    if fenced:
        parsed, _ = _loads_object(max(fenced, key=len).strip())
        if parsed is not None:
            return parsed, None
    match = _JSON_OBJ_RE.search(candidate)
    if match:
        parsed, _ = _loads_object(match.group(0))
        if parsed is not None:
            return parsed, None
    return None, reason


def _dump_unparseable(name: str, text: str) -> str | None:
    """Keep the raw output of a failed parse on disk; return its path.

    A head-and-tail excerpt in the error is not enough to diagnose a 27KB
    document, and the model's output is gone once the error is returned.
    """
    import tempfile
    import time as _time

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)[:80]
    path = Path(tempfile.gettempdir()) / f"bsh_gemini_unparsed_{safe}_{int(_time.time())}.txt"
    try:
        path.write_text(text, encoding="utf-8")
    except OSError:
        return None
    return str(path)


def _looks_like_schema_rejection(error: str) -> bool:
    lowered = (error or "").lower()
    return any(hint in lowered for hint in _SCHEMA_REJECTION_HINTS)


def _candidate_text(payload: dict) -> str:
    """Concatenate the text parts of the first candidate.

    Thinking parts carry ``"thought": true`` and are skipped — only the
    answer parts are the model's output.
    """
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    content = first.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("thought"):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            chunks.append(text)
    return "".join(chunks).strip()


def _grounding_meta(payload: dict) -> dict:
    """Source URIs and executed searches from ``groundingMetadata``.

    Returns ``{"sources": [{"title", "url"}], "queries": [...]}`` — empty
    lists when the model answered without searching.
    """
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    meta = first.get("groundingMetadata") if isinstance(first, dict) else None
    if not isinstance(meta, dict):
        return {"sources": [], "queries": []}
    sources: list[dict] = []
    seen: set[str] = set()
    for chunk in meta.get("groundingChunks") or []:
        web = chunk.get("web") if isinstance(chunk, dict) else None
        if not isinstance(web, dict):
            continue
        uri = str(web.get("uri") or "").strip()
        if not uri or uri in seen:
            continue
        seen.add(uri)
        sources.append({"title": str(web.get("title") or "").strip() or uri, "url": uri})
    queries = [
        str(q).strip()
        for q in (meta.get("webSearchQueries") or [])
        if str(q or "").strip()
    ]
    return {"sources": sources, "queries": queries}


def _hit_output_limit(payload: dict) -> bool:
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    return isinstance(first, dict) and str(first.get("finishReason") or "") == "MAX_TOKENS"


def _blocked_reason(payload: dict) -> str | None:
    """A refusal/stop reason worth reporting instead of 'empty response'."""
    feedback = payload.get("promptFeedback")
    if isinstance(feedback, dict) and feedback.get("blockReason"):
        return f"prompt blocked ({feedback['blockReason']})"
    candidates = payload.get("candidates")
    first = candidates[0] if isinstance(candidates, list) and candidates else {}
    reason = str(first.get("finishReason") or "").strip() if isinstance(first, dict) else ""
    if reason and reason not in {"STOP", "MAX_TOKENS"}:
        return f"generation stopped ({reason})"
    if reason == "MAX_TOKENS":
        return "response hit the output token limit"
    return None


def _error_text(response: httpx.Response) -> str:
    """The API's own error message, without echoing the key back."""
    try:
        body = response.json()
    except ValueError:
        return (response.text or "")[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict):
        message = str(error.get("message") or "").strip()
        status = str(error.get("status") or "").strip()
        if message:
            return f"{status}: {message}" if status else message
    return json.dumps(body)[:300]


# ---- request construction -------------------------------------------------


# `response_schema` takes an OpenAPI-flavored subset of JSON Schema and hard
# 400s on keywords outside it rather than ignoring them — `additionalProperties`
# is the one our existing schemas carry, since they were written for Claude.
# Stripping them costs nothing (they constrain a response the model is already
# being told to produce) and saves a doomed round trip per call.
_UNSUPPORTED_SCHEMA_KEYS = frozenset(
    {
        "additionalProperties",
        "patternProperties",
        "$schema",
        "$id",
        "$ref",
        "definitions",
        "$defs",
        "const",
        "default",
        "examples",
    }
)


def _schema_is_expressible(value: Any) -> bool:
    """False when `response_schema` cannot carry this schema's meaning.

    `{"type": "object", "additionalProperties": true}` is how a schema says
    "a free-form object" — the memo package body is exactly that. The proto
    behind response_schema has no way to express it, and stripping the
    keyword (which it otherwise rejects outright) turns the field into an
    object with no permitted properties, so the model correctly returns an
    empty one. That silently emptied a whole investment memo. Schemas like
    this go in the prompt instead, where JSON Schema means what it says.
    """
    if isinstance(value, dict):
        if value.get("additionalProperties") is True:
            return False
        return all(_schema_is_expressible(v) for v in value.values())
    if isinstance(value, list):
        return all(_schema_is_expressible(item) for item in value)
    return True


def _sanitize_schema(value: Any) -> Any:
    """Rewrite a JSON Schema into the subset ``response_schema`` accepts.

    Two incompatibilities, both of which 400 rather than being ignored:
    keywords outside the subset, and union types. `{"type": ["string",
    "null"]}` is ordinary JSON Schema for a nullable field and is how the
    Claude-era schemas here spell one, but the proto behind response_schema
    takes a single type plus a `nullable` flag.
    """
    if isinstance(value, dict):
        out = {
            k: _sanitize_schema(v)
            for k, v in value.items()
            if k not in _UNSUPPORTED_SCHEMA_KEYS
        }
        declared = out.get("type")
        if isinstance(declared, list):
            concrete = [str(x) for x in declared if str(x).lower() != "null"]
            if len(concrete) < len(declared):
                out["nullable"] = True
            # More than one concrete type has no representation here; the
            # first is the closest single-type approximation.
            out["type"] = concrete[0] if concrete else "string"
        return out
    if isinstance(value, list):
        return [_sanitize_schema(item) for item in value]
    return value


def _schema_instructions(schema: dict) -> str:
    """The prompt-embedded schema contract, for the no-responseFormat path."""
    return (
        "\n\nOUTPUT REQUIREMENTS (these override anything contradictory above):\n"
        "- Respond with ONE JSON object that conforms to this schema:\n\n"
        f"```json\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n```\n\n"
        "- Output the JSON object ONLY. No prose, no commentary, no markdown "
        "fences. The first character of your response is `{` and the last "
        "is `}`.\n"
        "- Every required field must be present. Use null for fields you "
        "cannot fill in."
    )


def _build_body(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    thinking: str,
    grounded: bool,
    embed_schema: bool,
    temperature: float | None,
    max_output_tokens: int | None,
    json_mode: bool = True,
) -> dict:
    # An empty schema means the research step of a grounded call, which must
    # carry no schema text at all — that is what suppresses the web search.
    prompt = user_prompt + (_schema_instructions(schema) if (embed_schema and schema) else "")
    generation_config: dict[str, Any] = {"thinkingConfig": {"thinkingLevel": thinking}}
    if temperature is not None:
        generation_config["temperature"] = temperature
    if max_output_tokens is not None:
        generation_config["maxOutputTokens"] = max_output_tokens
    if json_mode:
        # JSON mode is constrained decoding: the model cannot emit a stray
        # quote, a trailing comma or prose around the object. It is set for
        # every JSON call, including the ones whose schema has to travel in
        # the prompt (free-form objects, which responseSchema cannot express)
        # — those were the calls producing unparseable output, and a memo
        # package in Chinese is exactly one. Grounded calls stay off it: a
        # response constraint alongside google_search empties the grounding.
        generation_config["responseMimeType"] = "application/json"
    if not embed_schema:
        # The long-standing v1beta pair. The newer `responseFormat.text` shape
        # exists on this endpoint too but takes an enum mime type, not the
        # string — a rejection of either lands on the embed-schema retry in
        # `_run`, so a shape change on Google's side degrades instead of
        # failing the call.
        generation_config["responseSchema"] = _sanitize_schema(schema)
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    if system_prompt:
        body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    if grounded:
        body["tools"] = [{"google_search": {}}]
    return body


def _post(body: dict, *, model: str, key: str, timeout_sec: int) -> tuple[dict | None, str | None, int | None]:
    """One POST with retries for transient failures.

    Returns ``(payload, error, status)``. ``status`` is the HTTP status of the
    last non-retryable failure, so the caller can tell a schema rejection
    (400) from a key or quota problem.
    """
    url = f"{API_BASE}/models/{model}:generateContent"
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    last_error = "unknown error"
    last_status: int | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=timeout_sec)
        except httpx.TimeoutException:
            last_error = f"gemini timed out after {timeout_sec}s"
            last_status = None
        except httpx.HTTPError as exc:
            last_error = f"gemini request failed: {exc}"
            last_status = None
        else:
            if response.status_code == 200:
                try:
                    return response.json(), None, 200
                except ValueError as exc:
                    return None, f"gemini returned non-JSON envelope: {exc}", 200
            last_status = response.status_code
            last_error = f"gemini HTTP {response.status_code} — {_error_text(response)}"
            if response.status_code not in RETRY_STATUS:
                return None, last_error, last_status
        if attempt < MAX_ATTEMPTS:
            # Full jitter: these calls run inside user-facing requests, so a
            # retry storm from parallel callers would make a 429 worse.
            delay = random.uniform(0, min(8.0, 2.0**attempt))
            logger.warning(
                "gemini_runner: attempt %d/%d failed (%s); retrying in %.1fs",
                attempt,
                MAX_ATTEMPTS,
                last_error,
                delay,
            )
            time.sleep(delay)
    return None, last_error, last_status


# ---- public entry points --------------------------------------------------


def _run(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str,
    timeout_sec: int,
    model: str | None,
    thinking_level: str | None,
    grounded: bool,
    temperature: float | None,
    max_output_tokens: int | None,
) -> tuple[dict | None, dict, str | None]:
    key = api_key()
    if key is None:
        return None, {}, (
            "Gemini API key not configured. Set GEMINI_API_KEY in .env "
            "(get one at https://aistudio.google.com/apikey)."
        )
    chosen_model = (model or default_model()).strip() or DEFAULT_MODEL
    thinking = (thinking_level or default_thinking_level(grounded=grounded)).strip().lower()
    if thinking not in THINKING_LEVELS:
        thinking = DEFAULT_GROUNDED_THINKING if grounded else DEFAULT_THINKING

    data, meta, error = _single_call(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        name=name,
        timeout_sec=timeout_sec,
        model=chosen_model,
        key=key,
        thinking=thinking,
        grounded=grounded,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    if error is None and grounded and not meta.get("grounded"):
        logger.warning(
            "gemini_runner: %s answered without searching — the result is "
            "model recall, not research, and must not be shown as sourced",
            name,
        )
    return data, meta, error


def _single_call(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str,
    timeout_sec: int,
    model: str,
    key: str,
    thinking: str,
    grounded: bool,
    temperature: float | None,
    max_output_tokens: int | None,
    want_text: bool = False,
) -> tuple[Any, dict, str | None]:
    """One request, including the schema-rejection degradation.

    ``want_text=True`` returns the model's raw text instead of parsed JSON —
    the research step of a grounded call asks for prose on purpose.
    """
    chosen_model = model
    # Grounded calls MUST carry the schema in the prompt rather than in
    # `responseSchema`. Setting a response schema alongside the
    # `google_search` tool makes the API return an empty `groundingMetadata`
    # — no chunks, no queries — so there is no way to tell a researched
    # answer from unsourced model recall, and every source URL is lost.
    # Verified against the live API: with the schema, chunks=0/queries=0;
    # without it, the same prompt returns real chunks and queries.
    embed_schema = grounded or want_text or not schema or not _schema_is_expressible(schema)
    for _ in range(2):
        body = _build_body(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            schema=schema,
            thinking=thinking,
            grounded=grounded,
            embed_schema=embed_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            json_mode=not grounded and not want_text,
        )
        payload, error, status = _post(
            body, model=chosen_model, key=key, timeout_sec=timeout_sec
        )
        if error is not None:
            # A 400 naming the schema is one the API would take without it
            # (a JSON Schema keyword it won't accept). Retry once with the
            # schema in the prompt instead of losing the call. A 400 about
            # anything else — a bad key above all — is not retried.
            if status == 400 and not embed_schema and _looks_like_schema_rejection(error):
                logger.warning(
                    "gemini_runner: %s rejected the response schema (%s); "
                    "retrying with the schema embedded in the prompt",
                    name,
                    error,
                )
                embed_schema = True
                continue
            return None, {}, f"{error} ({name})"
        break
    else:  # pragma: no cover - the loop always returns or breaks
        return None, {}, f"gemini exhausted schema fallbacks ({name})"

    payload = payload or {}
    meta = _grounding_meta(payload)
    meta["model"] = chosen_model
    meta["engine"] = "gemini"
    # A grounded request whose response reports no searches was answered from
    # model memory. It is not research, and callers must not present it as
    # though it were.
    meta["grounded"] = bool(grounded and (meta["sources"] or meta["queries"]))
    text = _candidate_text(payload)
    if not text:
        return None, meta, (_blocked_reason(payload) or "gemini returned an empty response") + f" ({name})"
    if want_text:
        return text, meta, None
    # A truncated response often still *looks* like output. Reporting the
    # parse failure instead of the cause sent a live memo run chasing a JSON
    # bug that was really an output-length limit.
    if _hit_output_limit(payload):
        return None, meta, (
            f"gemini response hit the output token limit before finishing "
            f"({name}); raise max_output_tokens"
        )
    parsed, reason = _parse_json_payload_reason(text)
    if parsed is None:
        dump = _dump_unparseable(name, text)
        return None, meta, (
            f"gemini output didn't parse as JSON (name={name}, {len(text)} chars): "
            f"{reason or 'unknown reason'}"
            + (f"; raw output kept at {dump}" if dump else "")
            + f"; starts: {text[:120]!r} … ends: {text[-120:]!r}"
        )
    return parsed, meta, None


def run_structured_prompt(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str = "structured_output",
    timeout_sec: int = 180,
    model: str | None = None,
    thinking_level: str | None = None,
    grounded: bool = False,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> tuple[dict | None, str | None]:
    """Text-in / structured-JSON-out, mirroring ``claude_runner`` s contract.

    Returns ``(data, error)`` — exactly one of the two is non-None. ``name``
    is a debug label that ends up in error messages.
    """
    data, _meta, error = _run(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        schema=schema,
        name=name,
        timeout_sec=timeout_sec,
        model=model,
        thinking_level=thinking_level,
        grounded=grounded,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    )
    return data, error


RESEARCH_INSTRUCTION = (
    "\n\nResearch this now using Google Search, then write your findings as "
    "plain prose. Be exhaustive: every fact you can source, with the numbers, "
    "dates and names attached, and say explicitly which points you could not "
    "confirm. Do not produce JSON, a table, or any structured format — prose "
    "only. This is the research step; formatting happens separately."
)

STRUCTURE_SYSTEM_PROMPT = (
    "You convert research notes into one JSON object. You add nothing: every "
    "value comes from the notes, and a field the notes do not support is "
    "omitted or null. Do not call tools. Output the JSON object only."
)


def _structure_research(
    *,
    research_text: str,
    system_prompt: str,
    schema: dict,
    name: str,
    timeout_sec: int,
    model: str,
    key: str,
    max_output_tokens: int | None,
) -> tuple[dict | None, str | None]:
    """Second step of a grounded call: research prose in, schema JSON out."""
    data, _meta, error = _single_call(
        system_prompt=STRUCTURE_SYSTEM_PROMPT,
        user_prompt=(
            f"Original task, for context:\n{system_prompt.strip()}\n\n"
            f"Research notes to convert:\n---\n{research_text}\n---"
        ),
        schema=schema,
        name=f"{name}_structure",
        timeout_sec=timeout_sec,
        model=model,
        key=key,
        thinking=DEFAULT_THINKING,
        grounded=False,
        temperature=None,
        max_output_tokens=max_output_tokens,
    )
    return data, error


def run_grounded_json(
    *,
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    name: str = "grounded_research",
    timeout_sec: int = 240,
    model: str | None = None,
    thinking_level: str | None = None,
    temperature: float | None = None,
    max_output_tokens: int | None = None,
) -> tuple[dict | None, dict, str | None]:
    """Grounded research call: Google Search on, structured JSON out.

    Returns ``(data, meta, error)`` where ``meta`` carries ``sources``
    (``[{"title", "url"}]``), ``queries`` (the searches the model ran),
    ``model`` and ``engine``. ``meta`` is populated even on a parse failure,
    so a caller can still report what was searched.
    so a caller can still report what was searched.

    This runs as TWO calls, and that is the whole point. Asking for schema
    JSON and a web search in one request measured 2 grounded responses in 5:
    the model reads a long schema-carrying prompt as a formatting task and
    answers from memory. The same prompt with no schema attached grounds
    every time. So step one researches in prose with the search tool and no
    schema, and step two — ungrounded, cheap, no tools — converts those
    notes to the schema. Two Flash calls beat one that silently invents.
    """
    key = api_key()
    if key is None:
        return None, {}, (
            "Gemini API key not configured. Set GEMINI_API_KEY in .env "
            "(get one at https://aistudio.google.com/apikey)."
        )
    chosen_model = (model or default_model()).strip() or DEFAULT_MODEL

    # Step 1 — research, grounded, with no schema anywhere near the prompt.
    research, meta, error = _single_call(
        system_prompt=system_prompt,
        user_prompt=user_prompt + RESEARCH_INSTRUCTION,
        schema={},
        name=f"{name}_research",
        timeout_sec=timeout_sec,
        model=chosen_model,
        key=key,
        thinking=(thinking_level or default_thinking_level(grounded=True)),
        grounded=True,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        want_text=True,
    )
    if error is not None:
        return None, meta, error
    research_text = str(research or "").strip()
    if not research_text:
        return None, meta, f"gemini research step returned nothing ({name})"
    if not meta.get("grounded"):
        logger.warning(
            "gemini_runner: %s researched without searching — the result is "
            "model recall, not research",
            name,
        )

    # Step 2 — structure. No tools and no search: nothing new can enter here.
    data, structure_error = _structure_research(
        research_text=research_text,
        system_prompt=system_prompt,
        schema=schema,
        name=name,
        timeout_sec=timeout_sec,
        model=chosen_model,
        key=key,
        max_output_tokens=max_output_tokens,
    )
    if structure_error is not None:
        return None, meta, structure_error
    return data, meta, None


def health_check(*, timeout_sec: int = 30) -> dict:
    """Cheap liveness probe for the settings/diagnostics surface."""
    if not is_available():
        return {"ok": False, "configured": False, "error": "No GEMINI_API_KEY configured"}
    started = time.monotonic()
    data, error = run_structured_prompt(
        system_prompt="You are a health check.",
        user_prompt="Reply with {\"ok\": true}.",
        schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        name="gemini_health_check",
        timeout_sec=timeout_sec,
    )
    return {
        "ok": error is None and bool((data or {}).get("ok")),
        "configured": True,
        "model": default_model(),
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "error": error,
    }
