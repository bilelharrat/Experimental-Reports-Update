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
layer: a short bilingual narrative generated from the frozen payload via
``ai_engine.structured`` (Gemini Flash, Claude fallback) and stored back
into the archived JSON under ``note``. The numbers stay the source of
truth — a model outage leaves the brief intact, and rebuilding a brief
drops the old note because it described the previous tape. The note
records which engine wrote it, so a fallback is visible rather than
passing as a normal result.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server import ai_engine, desk_store, live_quotes

logger = logging.getLogger(__name__)

BRIEFS_ROOT = Path(__file__).resolve().parent.parent / "data" / "market_briefs"

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

NOTE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline_en": {
            "type": "string",
            "description": "One-line desk read of the tape, <= 90 chars.",
        },
        "headline_zh": {"type": "string"},
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
    "required": ["headline_en", "headline_zh", "bullets_en", "bullets_zh"],
}

LONG_NOTE_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "headline_en": {
            "type": "string",
            "description": "One-line desk read of the tape, <= 90 chars.",
        },
        "headline_zh": {"type": "string"},
        "sections_en": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
            "description": (
                "The full morning report. Suggested arc: market regime; index "
                "and cross-asset read; watchlist moves worth attention; alerts "
                "and what they imply; the week ahead. 600-1000 words total."
            ),
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "description": "Section heading, <= 60 chars."},
                    "body": {
                        "type": "string",
                        "description": "3-8 sentences of flowing desk prose.",
                    },
                },
                "required": ["title", "body"],
            },
        },
        "sections_zh": {
            "type": "array",
            "minItems": 3,
            "maxItems": 6,
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
    "required": ["headline_en", "headline_zh", "sections_en", "sections_zh"],
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
)

LONG_NOTE_SYSTEM_PROMPT = (
    "You are the morning-report writer on a small equity research desk. You "
    "get a frozen snapshot of the US tape: index ETF moves, the analyst's "
    "watchlist gainers/losers, alerts that fired in the last day, and the "
    "coming week's earnings/macro calendar. Write the full morning report "
    "the analyst reads with coffee — 600-1000 words across 3-6 titled "
    "sections.\n"
    "Rules:\n"
    "- Use ONLY the numbers provided. Never invent prices, levels, news, or "
    "causes. When interpreting, mark it as interpretation ('reads like', "
    "'consistent with') rather than asserting facts you weren't given.\n"
    "- Open with the regime (risk-on/off/mixed) and the cross-asset picture "
    "implied by the index/commodity/bond ETF moves.\n"
    "- Walk the watchlist: which moves are signal vs noise, clusters by "
    "theme where the tickers suggest one.\n"
    "- Treat fired alerts as the desk's own tripwires: what each implies "
    "for positioning or attention.\n"
    "- Close with the week ahead: calendar items ranked by likely impact "
    "and what would change the read.\n"
    "- Flowing desk prose, confident but honest about uncertainty. No "
    "greetings, no disclaimers.\n"
    "- Chinese sections are a natural rewrite for a bilingual desk, not a "
    "word-for-word translation."
)


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


def write_note(date: str | None = None, length: str = "short") -> dict:
    """Generate the written note for an archived brief and persist it.

    ``length`` picks the format: ``short`` is the 30-second bullet read,
    ``long`` is a full 600-1000 word sectioned report. Raises
    ``ValueError`` when there is no archived brief to annotate and
    ``RuntimeError`` when the Claude call fails — the caller decides how
    to surface each. The frozen numbers are never touched.
    """
    length = str(length or "short").strip().lower()
    if length not in {"short", "long"}:
        raise ValueError("length must be 'short' or 'long'")
    brief = load_brief(date)
    if brief is None:
        raise ValueError("No archived brief for that date — build one first")
    is_long = length == "long"
    data, meta, err = ai_engine.structured(
        system_prompt=LONG_NOTE_SYSTEM_PROMPT if is_long else NOTE_SYSTEM_PROMPT,
        user_prompt=_note_prompt(brief),
        schema=LONG_NOTE_SCHEMA if is_long else NOTE_SCHEMA,
        name="morning_brief_note_long" if is_long else "morning_brief_note",
        timeout_sec=420 if is_long else 180,
        # The long note is a 600-1000 word sectioned report in two
        # languages; the short one is four bullets. Only the long one is
        # worth paying for extra reasoning.
        thinking_level="medium" if is_long else "low",
    )
    if err is not None or not isinstance(data, dict):
        raise RuntimeError(err or "Empty note response")
    note = {
        "generated_at": _iso(),
        "length": length,
        "engine": meta.get("engine"),
        "model": meta.get("model"),
        "engine_fallback_reason": meta.get("fallback_reason"),
        "headline_en": str(data.get("headline_en") or "").strip(),
        "headline_zh": str(data.get("headline_zh") or "").strip(),
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
