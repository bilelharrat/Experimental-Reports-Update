"""Morning Brief — a dated, archived snapshot of the US market read.

Pulse renders live aggregates; this module freezes them. One build pass
composes indices, watchlist movers, the near-term events calendar, and
alerts fired in the last day into a JSON document archived under
``data/market_briefs/YYYY-MM-DD.json`` (UTC date, latest build of the day
wins). That gives the desk a browsable history — "what did the tape look
like Tuesday morning" — the way Hormuz appendices archive by date.

Composition only: every section comes from existing sources
(``live_quotes``, ``quote_workspace.fetch_calendar``, the desk store) and
sections degrade independently — a calendar outage still leaves a brief
with quotes and alerts.

The optional **written note** (``write_note``) is the one model-assisted
layer, and it comes in two lengths. The *short* note is a bilingual read
of the frozen payload and nothing else. The *long* note is the morning
brief proper: 1200-1800 words covering the tape, central banks,
geoeconomics and geopolitics, which means it has to read the news, so it
runs through ``ai_engine.grounded`` and stores the sources it used.

Either way the frozen numbers stay the source of truth — a model outage
leaves the brief intact, and rebuilding a brief drops the old note because
it described the previous tape. The note records which engine wrote it and
whether it was actually researched, so neither a fallback nor an
unsourced long note passes as a normal result.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server import ai_engine, desk_store, live_quotes

logger = logging.getLogger(__name__)

BRIEFS_ROOT = Path(__file__).resolve().parent.parent / "data" / "market_briefs"

# The long note researches the news behind the tape in two languages, which
# is a research call plus a structuring call over a long output.
LONG_NOTE_TIMEOUT_SEC = 420

# Gemini writes the brief — the configured Gemini model, 3.8 Flash — whatever
# engine the research desk is set to, and it is never handed to Claude. A
# failed Gemini run is left for the morning schedule to try again.
NOTE_ENGINE_POLICY = "gemini-only"

INDEX_TICKERS = ["SPY", "QQQ", "DIA", "IWM", "GLD", "USO", "TLT", "VIXY", "UUP"]
MAX_WATCHLIST = 24
MOVER_LIMIT = 6
CALENDAR_DAYS = 7
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_LOCK = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat().replace("+00:00", "Z")


def _watchlist_tickers() -> list[str]:
    """Pinned tickers from the synced desk prefs blob."""
    pinned = desk_store.load_prefs()["data"].get("bsh.marketPinnedTickers")
    if not isinstance(pinned, list):
        return []
    seen: list[str] = []
    for row in pinned:
        ticker = str(row or "").strip().upper()
        if ticker and ticker not in seen:
            seen.append(ticker)
    return seen[:MAX_WATCHLIST]


def _quote_rows(tickers: list[str]) -> list[dict]:
    if not tickers:
        return []
    payload = live_quotes.fetch_quotes(tickers)
    quotes = payload.get("quotes") or {}
    rows = []
    for ticker in tickers:
        quote = quotes.get(ticker)
        if not isinstance(quote, dict):
            continue
        rows.append(
            {
                "ticker": ticker,
                "last_price": quote.get("last_price"),
                "change_pct_1d": quote.get("change_pct_1d"),
                "currency": quote.get("currency"),
                "as_of": quote.get("as_of"),
            }
        )
    return rows


def _movers(rows: list[dict]) -> dict:
    scored = [
        row
        for row in rows
        if isinstance(row.get("change_pct_1d"), (int, float))
    ]
    ranked = sorted(scored, key=lambda row: row["change_pct_1d"], reverse=True)
    return {
        "gainers": ranked[:MOVER_LIMIT],
        "losers": ranked[::-1][:MOVER_LIMIT],
    }


def _calendar_events(tickers: list[str]) -> list[dict]:
    try:
        from server import quote_workspace

        payload = quote_workspace.fetch_calendar(tickers)
    except Exception as exc:
        logger.warning("Brief calendar unavailable: %s", exc)
        return []
    events = payload.get("events") or []
    horizon = (_now() + timedelta(days=CALENDAR_DAYS)).date().isoformat()
    today = _now().date().isoformat()
    kept = [
        event
        for event in events
        if isinstance(event, dict) and today <= str(event.get("date") or "") <= horizon
    ]
    kept.sort(key=lambda event: (str(event.get("date") or ""), str(event.get("ticker") or "")))
    return kept[:40]


def build_brief() -> dict:
    """Compose and archive today's brief. Network: quotes + calendar."""
    watchlist = _watchlist_tickers()
    index_rows = _quote_rows(INDEX_TICKERS)
    watch_rows = _quote_rows([t for t in watchlist if t not in INDEX_TICKERS])
    since = _iso(_now() - timedelta(days=1))
    brief = {
        "schema_version": 1,
        "date": _now().date().isoformat(),
        "generated_at": _iso(),
        "indices": index_rows,
        "watchlist": watch_rows,
        "movers": _movers(watch_rows or index_rows),
        "calendar": _calendar_events(watchlist),
        "alerts_last_day": desk_store.list_alert_events(since=since, limit=20),
    }
    _save_brief(brief)
    return brief


def _save_brief(brief: dict) -> None:
    with _LOCK:
        BRIEFS_ROOT.mkdir(parents=True, exist_ok=True)
        path = BRIEFS_ROOT / f"{brief['date']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(brief, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)


def list_briefs() -> list[str]:
    """Archived brief dates, newest first."""
    if not BRIEFS_ROOT.is_dir():
        return []
    dates = [
        path.stem
        for path in BRIEFS_ROOT.glob("*.json")
        if DATE_RE.match(path.stem)
    ]
    return sorted(dates, reverse=True)


# --- Written note (model-assisted) -------------------------------------------

# The headline is the brief's front page: what the desk reads when it reads
# nothing else. Left to itself the model wrote Title Case summaries of
# everything at once ("Tech Rallies on US-China AI Talks as Crude Unwinds
# Geopolitical Risk"). These ask for one driver and one number, in the
# sentence case financial front pages use, and give the second driver a line
# of its own — the dek — instead of a second clause.
HEADLINE_FIELDS: dict = {
    "headline_en": {
        "type": "string",
        "description": (
            "Front-page headline, 50-80 chars, sentence case, present tense, "
            "active verb. One driver and one number from the frozen tape, e.g. "
            "'Nasdaq jumps 2.5% as US-China chip talks revive the AI trade'. "
            "No colon, no trailing period, no Title Case."
        ),
    },
    "headline_zh": {
        "type": "string",
        "description": "Chinese headline, <= 28 characters, same driver and number.",
    },
    "dek_en": {
        "type": "string",
        "description": (
            "The standfirst under the headline: one sentence, 100-180 chars, "
            "carrying what the headline leaves out — the second driver, or what "
            "it means for positioning. Never repeats the headline's number."
        ),
    },
    "dek_zh": {
        "type": "string",
        "description": "Chinese standfirst, one sentence, <= 70 characters.",
    },
}
HEADLINE_REQUIRED = ["headline_en", "headline_zh", "dek_en", "dek_zh"]

HEADLINE_RULES = (
    "\nThe headline and dek:\n"
    "- The headline is what the desk reads if it reads nothing else: one "
    "driver, one number from the frozen tape, sentence case, present tense, "
    "an active verb, 50-80 characters.\n"
    "- Say what happened, not that something happened: 'Treasuries slide as "
    "hot CPI pushes rate-cut bets into 2027', not 'Markets react to "
    "inflation data'.\n"
    "- The dek is one sentence carrying the second driver or the so-what for "
    "positioning. It never restates the headline.\n"
    "- No colons, no questions, no Title Case, and none of 'amid', 'mixed "
    "signals', 'navigates' or 'in focus'."
)

NOTE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **HEADLINE_FIELDS,
        "bullets_en": {
            "type": "array",
            "minItems": 3,
            "maxItems": 8,
            "items": {"type": "string"},
            "description": (
                "Skimmable desk bullets: what moved and why it matters, what "
                "the watchlist tape says, what to watch into the next session. "
                "Each <= 160 chars. No hedging boilerplate, no invented data."
            ),
        },
        "bullets_zh": {
            "type": "array",
            "minItems": 3,
            "maxItems": 8,
            "items": {"type": "string"},
        },
    },
    "required": [*HEADLINE_REQUIRED, "bullets_en", "bullets_zh"],
}

LONG_NOTE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        **HEADLINE_FIELDS,
        "sections_en": {
            "type": "array",
            "minItems": 6,
            "maxItems": 9,
            "description": (
                "The full morning report: the regime, the news that moved it, "
                "central banks and policy, geoeconomics, geopolitics, the "
                "watchlist, alerts, and the week ahead. 1200-1800 words total."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "description": "Section heading, <= 60 chars."},
                    "body": {
                        "type": "string",
                        "description": (
                            "5-12 sentences of flowing desk prose. Name "
                            "countries, institutions, measures and dates "
                            "rather than gesturing at them."
                        ),
                    },
                },
                "required": ["title", "body"],
            },
        },
        "sections_zh": {
            "type": "array",
            "minItems": 6,
            "maxItems": 9,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["title", "body"],
            },
        },
    },
    "required": [*HEADLINE_REQUIRED, "sections_en", "sections_zh"],
}

NOTE_SYSTEM_PROMPT = (
    "You are the morning-note writer on a small equity research desk. You "
    "get a frozen snapshot of the US tape: index ETF moves, the analyst's "
    "watchlist gainers/losers, alerts that fired in the last day, and the "
    "coming week's earnings/macro calendar. Write the 30-second desk read.\n"
    "Rules:\n"
    "- Use ONLY the numbers provided. Never invent prices, levels, or news.\n"
    "- Lead with the regime (risk-on/off/mixed) implied by the index moves.\n"
    "- Call out the most informative watchlist moves and any fired alerts.\n"
    "- End with what to watch next (calendar items, tickers near triggers).\n"
    "- Terse desk voice. No greetings, no disclaimers.\n"
    "- Chinese fields are a natural rewrite for a bilingual desk, not a "
    "word-for-word translation."
) + HEADLINE_RULES

LONG_NOTE_SYSTEM_PROMPT = (
    "You are the morning-report writer on a small equity research desk. You "
    "write the long morning brief the analyst reads with coffee: the tape, "
    "and the geoeconomics and geopolitics driving it.\n"
    "You get a FROZEN snapshot of the US tape — index ETF moves, the "
    "analyst's watchlist gainers/losers, alerts that fired in the last day, "
    "and the coming week's earnings/macro calendar. You also research the "
    "world around those numbers using Google Search.\n"
    "Write 1200-1800 words across 6-9 titled sections. Suggested arc, adapt "
    "it to the day:\n"
    "1. The regime — risk-on/off/mixed, and the cross-asset picture the "
    "index, commodity, bond and volatility moves imply together.\n"
    "2. What moved it — the actual news behind the tape, researched and "
    "attributed, not inferred from the prices.\n"
    "3. Central banks and policy — rates, inflation prints, guidance, "
    "fiscal news, and the repricing each caused.\n"
    "4. Geoeconomics — trade policy and tariffs, sanctions and export "
    "controls, supply chains, energy and commodity flows, currencies and "
    "capital movement. Name the countries, the measures and the dates, and "
    "connect each to the assets it touches.\n"
    "5. Geopolitics — conflicts, elections, alliances, leadership changes "
    "and security developments. Say specifically which markets, sectors or "
    "commodities each one prices into, and through what mechanism.\n"
    "6. The watchlist — which moves are signal and which are noise, and the "
    "themes the tickers cluster into.\n"
    "7. Alerts — the desk's own tripwires, and what each implies for "
    "positioning or attention.\n"
    "8. The week ahead — calendar items ranked by likely impact, the "
    "geopolitical and geoeconomic dates alongside the earnings, and what "
    "would change the read.\n"
    "Rules you do not break:\n"
    "- The frozen numbers are authoritative. Never restate a price, level "
    "or percentage that contradicts them, and never invent a watchlist move "
    "or an alert you were not given.\n"
    "- Everything beyond those numbers must come from what you actually "
    "searched and read. Attribute it — who reported it and when. If you "
    "could not confirm something, say so rather than asserting it.\n"
    "- Keep research current: this brief is about today and the days around "
    "it, not about the general state of the world. Anchor claims to dates.\n"
    "- Separate fact from reading. Mark interpretation as interpretation "
    "('reads like', 'consistent with'), and keep it clearly apart from what "
    "the sources said.\n"
    "- Flowing desk prose, confident but honest about uncertainty. No "
    "greetings, no disclaimers, no markdown headers inside a body.\n"
    "- Chinese sections are a natural rewrite for a bilingual desk, not a "
    "word-for-word translation, and carry the same facts and judgments."
) + HEADLINE_RULES


def _fmt_move(row: dict) -> str:
    change = row.get("change_pct_1d")
    pct = f"{change:+.1f}%" if isinstance(change, (int, float)) else "n/a"
    return f"{row.get('ticker')} {pct}"


def _note_prompt(brief: dict) -> str:
    lines = [f"Snapshot date: {brief.get('date')} (frozen {brief.get('generated_at')})"]
    indices = brief.get("indices") or []
    if indices:
        lines.append("Index ETFs: " + ", ".join(_fmt_move(row) for row in indices))
    movers = brief.get("movers") or {}
    gainers = movers.get("gainers") or []
    losers = movers.get("losers") or []
    if gainers:
        lines.append("Watchlist gainers: " + ", ".join(_fmt_move(r) for r in gainers))
    if losers:
        lines.append("Watchlist losers: " + ", ".join(_fmt_move(r) for r in losers))
    alerts = brief.get("alerts_last_day") or []
    if alerts:
        lines.append("Alerts fired (last 24h):")
        for row in alerts[:10]:
            message = row.get("message") or f"{row.get('ticker')} {row.get('kind')}"
            lines.append(f"- {message}")
    calendar = brief.get("calendar") or []
    if calendar:
        lines.append("Calendar (next week):")
        lines.extend(
            f"- {event.get('date')} {event.get('ticker') or ''} "
            f"{event.get('kind') or event.get('title') or ''}".rstrip()
            for event in calendar[:12]
        )
    return "\n".join(lines)


def _clean_sections(rows: list | None) -> list[dict]:
    sections = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        body = str(row.get("body") or "").strip()
        if body:
            sections.append({"title": title, "body": body})
    return sections


_WRAPPING_QUOTES = {('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"), ("「", "」"), ("《", "》")}


def _clean_line(value: object, *, headline: bool = False) -> str:
    """One display line: whitespace collapsed and wrapping quotes dropped.

    A headline also loses its trailing full stop — front pages don't print
    one, and the model adds it about as often as it leaves it off.
    """
    text = " ".join(str(value or "").split())
    if len(text) > 1 and (text[0], text[-1]) in _WRAPPING_QUOTES:
        text = text[1:-1].strip()
    if headline:
        text = text.rstrip(".。").rstrip()
    return text


def write_note(date: str | None = None, length: str = "short") -> dict:
    """Generate the written note for an archived brief and persist it.

    ``length`` picks the format: ``short`` is the 30-second bullet read,
    ``long`` is a full 600-1000 word sectioned report. Raises
    ``ValueError`` when there is no archived brief to annotate and
    ``RuntimeError`` when the Gemini call fails — the caller decides how
    to surface each. The frozen numbers are never touched.
    """
    length = str(length or "short").strip().lower()
    if length not in {"short", "long"}:
        raise ValueError("length must be 'short' or 'long'")
    brief = load_brief(date)
    if brief is None:
        raise ValueError("No archived brief for that date — build one first")
    is_long = length == "long"
    if is_long:
        # The long note covers geoeconomics and geopolitics, which are not in
        # the frozen snapshot and cannot be inferred from index moves. It has
        # to read the news, so it goes through the grounded path; the short
        # note stays a cheap read of the numbers it was handed.
        data, meta, err = ai_engine.grounded(
            system_prompt=LONG_NOTE_SYSTEM_PROMPT,
            user_prompt=_note_prompt(brief),
            schema=LONG_NOTE_SCHEMA,
            name="morning_brief_note_long",
            gemini_timeout_sec=LONG_NOTE_TIMEOUT_SEC,
            policy_override=NOTE_ENGINE_POLICY,
        )
    else:
        data, meta, err = ai_engine.structured(
            system_prompt=NOTE_SYSTEM_PROMPT,
            user_prompt=_note_prompt(brief),
            schema=NOTE_SCHEMA,
            name="morning_brief_note",
            timeout_sec=180,
            thinking_level="low",
            policy_override=NOTE_ENGINE_POLICY,
        )
    if err is not None or not isinstance(data, dict):
        raise RuntimeError(err or "Empty note response")
    note = {
        "generated_at": _iso(),
        "length": length,
        "engine": meta.get("engine"),
        "model": meta.get("model"),
        "engine_fallback_reason": meta.get("fallback_reason"),
        # The long note makes claims about the world, so it carries what it
        # read. An empty list on a long note means it was written without
        # sources and the geopolitics in it is unverified.
        "sources": meta.get("sources") or [],
        "researched": bool(meta.get("grounded")),
        "headline_en": _clean_line(data.get("headline_en"), headline=True),
        "headline_zh": _clean_line(data.get("headline_zh"), headline=True),
        "dek_en": _clean_line(data.get("dek_en")),
        "dek_zh": _clean_line(data.get("dek_zh")),
    }
    if is_long:
        note["sections_en"] = _clean_sections(data.get("sections_en"))
        note["sections_zh"] = _clean_sections(data.get("sections_zh"))
    else:
        note["bullets_en"] = [
            str(row).strip() for row in data.get("bullets_en") or [] if str(row).strip()
        ]
        note["bullets_zh"] = [
            str(row).strip() for row in data.get("bullets_zh") or [] if str(row).strip()
        ]
    brief["note"] = note
    _save_brief(brief)
    return brief


def load_brief(date: str | None = None) -> dict | None:
    """One archived brief; latest when ``date`` is omitted."""
    if date is not None and not DATE_RE.match(str(date)):
        raise ValueError("date must be YYYY-MM-DD")
    target = str(date) if date else None
    if target is None:
        dates = list_briefs()
        if not dates:
            return None
        target = dates[0]
    path = BRIEFS_ROOT / f"{target}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


# ---- Morning schedule -------------------------------------------------------
#
# The brief is only useful if it is already written when the desk opens. Left
# to the buttons it is written when someone remembers, which means the analyst
# reads yesterday's tape or waits ninety seconds for a long note. This loop
# builds the brief and writes its note once each morning.

MORNING_STATE_FILE = "_morning_state.json"
MORNING_CHECK_SECONDS = 300
DEFAULT_MORNING_HOUR = 7
DEFAULT_MORNING_LENGTH = "long"
# A failed morning is tried again an hour later, three runs a day at most.
# One failure used to cost the whole day: a server that started before its
# Gemini key was added, with Claude past its weekly limit, never wrote the
# brief even after the key arrived.
MORNING_RETRY_SECONDS = 3600
MORNING_MAX_ATTEMPTS = 3

_MORNING_LOCK = threading.Lock()
_MORNING_LOOP_STARTED = False
# Set while a scheduled run is in flight. The long note takes ~90s, and the
# page has nothing to show for that time unless it can tell the difference
# between "no brief today" and "the brief is being written right now".
_MORNING_RUNNING = threading.Event()


def morning_enabled() -> bool:
    """``BSH_MORNING_BRIEF=0`` turns the schedule off."""
    raw = str(os.environ.get("BSH_MORNING_BRIEF") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def morning_hour() -> int:
    """Local hour to write the brief at (``BSH_MORNING_BRIEF_HOUR``, default 7)."""
    raw = str(os.environ.get("BSH_MORNING_BRIEF_HOUR") or "").strip()
    try:
        hour = int(raw)
    except ValueError:
        return DEFAULT_MORNING_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_MORNING_HOUR


def morning_length() -> str:
    """``short`` or ``long`` (``BSH_MORNING_BRIEF_LENGTH``, default long)."""
    raw = str(os.environ.get("BSH_MORNING_BRIEF_LENGTH") or "").strip().lower()
    return raw if raw in {"short", "long"} else DEFAULT_MORNING_LENGTH


def _morning_state_path() -> Path:
    return BRIEFS_ROOT / MORNING_STATE_FILE


def _read_morning_state() -> dict:
    try:
        payload = json.loads(_morning_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_morning_state(payload: dict) -> None:
    try:
        BRIEFS_ROOT.mkdir(parents=True, exist_ok=True)
        _morning_state_path().write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    except OSError:
        logger.warning("morning brief: could not record run state", exc_info=True)


def morning_due(now: datetime | None = None) -> bool:
    """True when today's brief should be written and has not been.

    Local time, because "morning" is the reader's morning.

    The presence of a note decides this, not the fact that a run happened:
    ``build_brief`` deliberately drops the note when the snapshot is rebuilt
    (it described the previous tape), so a "Build brief" click after the
    morning run leaves the desk with no brief for the rest of the day. Keying
    off the recorded run date alone meant the schedule saw its own completed
    run and refused to write another.

    A run that FAILED today holds the loop off for an hour, so a broken
    model or market feed is not retried every five minutes, and after
    ``MORNING_MAX_ATTEMPTS`` failed runs the day is left alone.
    """
    if not morning_enabled():
        return False
    current = now or datetime.now().astimezone()
    if current.hour < morning_hour():
        return False
    today = current.strftime("%Y-%m-%d")
    existing = load_brief(today)
    if isinstance(existing, dict) and existing.get("note"):
        return False
    state = _read_morning_state()
    if str(state.get("last_run_date") or "") == today and not state.get("ok"):
        retry_at = _next_retry_at(state, today)
        return retry_at is not None and current.astimezone() >= retry_at
    return True


def _attempts(state: dict) -> int:
    try:
        return max(1, int(state.get("attempts") or 1))
    except (TypeError, ValueError):
        return 1


def _next_retry_at(state: dict, today: str) -> datetime | None:
    """When a morning that failed ``today`` is tried again; None when it isn't."""
    if str(state.get("last_run_date") or "") != today or state.get("ok"):
        return None
    if _attempts(state) >= MORNING_MAX_ATTEMPTS:
        return None
    try:
        attempted_at = datetime.fromisoformat(str(state.get("attempted_at") or ""))
    except ValueError:
        # Recorded before retries existed: no time to space a retry from.
        return None
    return attempted_at.astimezone() + timedelta(seconds=MORNING_RETRY_SECONDS)


def run_morning_brief(now: datetime | None = None) -> dict | None:
    """Build today's brief and write its note. Returns the brief, or None.

    Never raises: this runs on a background thread, and a market-data or
    model outage must not take the loop down with it. The run is recorded
    either way so a failing morning is not retried every five minutes.
    """
    current = now or datetime.now().astimezone()
    today = current.strftime("%Y-%m-%d")
    length = morning_length()
    previous = _read_morning_state()
    attempt = 1
    if str(previous.get("last_run_date") or "") == today and not previous.get("ok"):
        attempt = _attempts(previous) + 1
    _MORNING_RUNNING.set()
    try:
        build_brief()
        brief = write_note(length=length)
        _write_morning_state(
            {
                "last_run_date": today,
                "length": length,
                "ok": True,
                "error": None,
                "attempts": attempt,
            }
        )
        logger.info("Morning brief written for %s (%s).", today, length)
        return brief
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Morning brief failed for %s (run %d of %d): %s",
            today,
            attempt,
            MORNING_MAX_ATTEMPTS,
            exc,
        )
        _write_morning_state(
            {
                "last_run_date": today,
                "length": length,
                "ok": False,
                "error": str(exc)[:300],
                "attempts": attempt,
                "attempted_at": current.isoformat(),
            }
        )
        return None
    finally:
        _MORNING_RUNNING.clear()


def morning_status(now: datetime | None = None) -> dict:
    """What the schedule is doing, for the Pulse page and diagnostics."""
    current = now or datetime.now().astimezone()
    state = _read_morning_state()
    retry_at = _next_retry_at(state, current.strftime("%Y-%m-%d"))
    return {
        "enabled": morning_enabled(),
        "hour": morning_hour(),
        "length": morning_length(),
        "running": _MORNING_RUNNING.is_set(),
        "last_run_date": state.get("last_run_date"),
        "last_run_ok": state.get("ok"),
        "last_error": state.get("error"),
        "attempts": state.get("attempts"),
        "next_retry_at": retry_at.isoformat() if retry_at else None,
        "due_now": morning_due(current),
    }


def _morning_loop() -> None:
    while True:
        try:
            if morning_due():
                run_morning_brief()
        except Exception:  # noqa: BLE001
            logger.exception("Morning brief loop iteration failed")
        time.sleep(MORNING_CHECK_SECONDS)


def start_morning_loop() -> bool:
    """Start the morning schedule (FastAPI startup hook). Idempotent.

    Off when ``BSH_MORNING_BRIEF=0`` or Gemini cannot run: the brief is
    Gemini's to write, so a Claude CLI alone does not start it.
    """
    global _MORNING_LOOP_STARTED
    if not morning_enabled() or not ai_engine.available(NOTE_ENGINE_POLICY):
        return False
    with _MORNING_LOCK:
        if _MORNING_LOOP_STARTED:
            return False
        _MORNING_LOOP_STARTED = True
    threading.Thread(
        target=_morning_loop, name="morning-brief-loop", daemon=True
    ).start()
    return True
