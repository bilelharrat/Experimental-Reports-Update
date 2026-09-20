"""Durable store of what retrieval found — the fact lottery's other half.

The fact ledger keeps hand-curated facts on disk. This store keeps what
the machines found: every page a memo agent fetched, every search-results
blob it read, and the research prose of every grounded Gemini pass. A
fact that reached one run by luck is then on disk for the next, and a
figure a memo states can be traced to the text that carried it (see
``memo_fact_check``).

Layout, per company::

    data/research/<storage_key>/sources/
        index.json           # list[record], newest fetch first
        <sha256[:16]>.txt    # the retrieved text, one file per content hash

A record carries ``id`` (the content hash prefix), ``kind`` (``web_fetch``,
``web_search`` or ``grounding``), ``url`` / ``canonical_url`` (fetched
pages only), ``title``, ``query`` (searches), ``links`` (the pages a
search or grounding pass reported), ``sha256``, ``chars``, ``file``,
``fetched_at``, ``first_seen_at``, ``origins`` and ``run_ids``.

Fetched pages dedupe on canonical URL; search blobs and grounding prose
dedupe on content. Re-fetching a known URL that now returns different
text replaces the text (newest wins) and keeps ``first_seen_at``. What a
particular run saw is preserved separately: :func:`record_run_source`
also appends to ``<run_dir>/sources/manifest.jsonl`` and writes the text
under ``<run_dir>/sources/`` — the point-in-time input record (URL, hash,
when) that the hypothesis plan calls an input manifest.

Everything here is best-effort by contract: a broken cache must never
fail a memo run, so writers swallow and log OS errors and readers return
empty results for a missing or corrupt index.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from . import company_paths, research_store

logger = logging.getLogger(__name__)

SOURCES_DIRNAME = "sources"
INDEX_FILENAME = "index.json"
MANIFEST_FILENAME = "manifest.jsonl"

KINDS = ("web_fetch", "web_search", "grounding")

# A fetched page shorter than this is an error page or a stub, not evidence.
MIN_TEXT_CHARS = 40
# Per-source text cap. A 10-K runs to a few hundred thousand characters;
# beyond that the file is a data dump, and the fact check scans every byte.
MAX_TEXT_CHARS = 200_000
# Records kept per company; the oldest fetches are evicted past this.
MAX_RECORDS = 2_000

_LOCK = threading.RLock()

_TRACKING_PARAMS = {"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "ref", "yclid"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-']{2,}")
_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "has", "have", "its", "our", "their", "into", "not", "but",
    "you", "they", "them", "than", "then", "www", "com", "org", "net",
    "html", "htm", "http", "https", "report", "page", "article", "news",
    "inc", "ltd", "llc", "corp", "corporation", "company",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _company_dir(company_id: str) -> Path:
    # Read the root at call time: tests re-point research_store.RESEARCH_ROOT.
    return research_store.RESEARCH_ROOT / company_paths.storage_key(company_id) / SOURCES_DIRNAME


def sources_dir(company_id: str) -> Path:
    """Where this company's retrieved sources live (may not exist yet)."""
    return _company_dir(company_id)


def canonical_url(url: Any) -> str | None:
    """A comparable form of ``url``, or None when it is not a web page.

    Lower-cases scheme and host, drops the fragment and tracking
    parameters (``utm_*`` and friends), sorts the remaining query, and
    strips a trailing slash from a non-root path. Local and non-http
    addresses are rejected so the app's own dev server never becomes a
    "source".
    """
    raw = str(url or "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower()
    if not host or host in _LOCAL_HOSTS or host.endswith(".local"):
        return None
    if parts.port and parts.port not in {80, 443}:
        host = f"{host}:{parts.port}"
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    if len(path) > 1:
        path = path.rstrip("/") or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key and not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_pairs), doseq=True)
    return urlunsplit((scheme, host, path, query, ""))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


def _load_index(company_id: str) -> list[dict]:
    path = _company_dir(company_id) / INDEX_FILENAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, ValueError):
        logger.warning("source cache index unreadable: %s", path, exc_info=True)
        return []
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict) and row.get("id")]


def _save_index(company_id: str, rows: list[dict]) -> None:
    rows.sort(key=lambda row: str(row.get("fetched_at") or ""), reverse=True)
    if len(rows) > MAX_RECORDS:
        for stale in rows[MAX_RECORDS:]:
            _unlink_quiet(_company_dir(company_id) / str(stale.get("file") or ""))
        del rows[MAX_RECORDS:]
    _atomic_write(
        _company_dir(company_id) / INDEX_FILENAME,
        json.dumps(rows, ensure_ascii=False, indent=1),
    )


def _unlink_quiet(path: Path) -> None:
    if not path.name or path.suffix != ".txt":
        return
    try:
        path.unlink()
    except OSError:
        pass


def _clean_text(text: Any) -> str:
    cleaned = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(cleaned) > MAX_TEXT_CHARS:
        cleaned = cleaned[:MAX_TEXT_CHARS].rstrip() + "\n[truncated by source cache]"
    return cleaned


def _clean_links(links: Any) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for item in links or []:
        if not isinstance(item, dict):
            continue
        canon = canonical_url(item.get("url"))
        if not canon or canon in seen:
            continue
        seen.add(canon)
        title = " ".join(str(item.get("title") or "").split())[:300]
        out.append({"title": title or canon, "url": str(item.get("url")).strip()})
        if len(out) >= 40:
            break
    return out


def record_source(
    company_id: str,
    *,
    kind: str,
    text: str,
    url: str | None = None,
    title: str | None = None,
    query: str | None = None,
    links: list[dict] | None = None,
    origin: str | None = None,
    run_id: str | None = None,
    fetched_at: str | None = None,
) -> dict | None:
    """Store one retrieval. Returns the record, or None when rejected.

    Rejected: an unknown ``kind``, text shorter than :data:`MIN_TEXT_CHARS`,
    or a ``web_fetch`` whose URL is not a web page. Never raises for a
    storage failure — the cache is a side channel of the run, not a gate.
    """
    if kind not in KINDS:
        return None
    body = _clean_text(text)
    if len(body) < MIN_TEXT_CHARS:
        return None
    canon = canonical_url(url) if url else None
    if kind == "web_fetch" and not canon:
        return None
    digest = _sha(body)
    now = fetched_at or _now()
    origin_label = str(origin or "").strip()[:120]
    record_id = digest[:16]
    try:
        with _LOCK:
            rows = _load_index(company_id)
            existing = None
            for row in rows:
                if kind == "web_fetch" and row.get("kind") == "web_fetch":
                    if row.get("canonical_url") == canon:
                        existing = row
                        break
                elif row.get("sha256") == digest:
                    existing = row
                    break
            company_dir = _company_dir(company_id)
            text_path = company_dir / f"{record_id}.txt"
            if existing is not None:
                old_file = str(existing.get("file") or "")
                existing.update(
                    {
                        "id": record_id,
                        "sha256": digest,
                        "chars": len(body),
                        "file": text_path.name,
                        "fetched_at": now,
                    }
                )
                if title and not existing.get("title"):
                    existing["title"] = " ".join(str(title).split())[:300]
                if url and not existing.get("url"):
                    existing["url"] = str(url).strip()
                    existing["canonical_url"] = canon
                if query and not existing.get("query"):
                    existing["query"] = " ".join(str(query).split())[:500]
                merged_links = _clean_links(list(existing.get("links") or []) + list(links or []))
                if merged_links:
                    existing["links"] = merged_links
                origins = [o for o in existing.get("origins") or [] if isinstance(o, str)]
                if origin_label and origin_label not in origins:
                    origins.append(origin_label)
                existing["origins"] = origins[-20:]
                run_ids = [r for r in existing.get("run_ids") or [] if isinstance(r, str)]
                if run_id and run_id not in run_ids:
                    run_ids.append(run_id)
                existing["run_ids"] = run_ids[-50:]
                record = existing
                if old_file and old_file != text_path.name:
                    _unlink_quiet(company_dir / old_file)
            else:
                record = {
                    "id": record_id,
                    "kind": kind,
                    "url": str(url).strip() if url and canon else None,
                    "canonical_url": canon,
                    "title": " ".join(str(title or "").split())[:300] or None,
                    "query": " ".join(str(query or "").split())[:500] or None,
                    "links": _clean_links(links),
                    "sha256": digest,
                    "chars": len(body),
                    "file": text_path.name,
                    "fetched_at": now,
                    "first_seen_at": now,
                    "origins": [origin_label] if origin_label else [],
                    "run_ids": [run_id] if run_id else [],
                }
                rows.append(record)
            if not text_path.exists():
                _atomic_write(text_path, body)
            _save_index(company_id, rows)
            return dict(record)
    except OSError:
        logger.warning("source cache write failed for %s", company_id, exc_info=True)
        return None


def record_run_source(
    company_id: str,
    run_dir: Path | str,
    *,
    tool: str,
    text: str,
    url: str | None = None,
    query: str | None = None,
    title: str | None = None,
    links: list[dict] | None = None,
    run_id: str | None = None,
) -> dict | None:
    """Store one retrieval made during a memo run, and freeze it in the
    run's own manifest.

    ``tool`` is the Claude tool name (``WebFetch`` / ``WebSearch``). The
    company-level record is what later runs and the fact check read; the
    run-level copy under ``<run_dir>/sources/`` is what this run saw,
    kept even after the company record is refreshed by a later fetch.
    """
    kind = "web_fetch" if tool == "WebFetch" else "web_search"
    origin = f"memo_run:{run_id or Path(run_dir).name}:{tool}"
    record = record_source(
        company_id,
        kind=kind,
        text=text,
        url=url,
        title=title,
        query=query,
        links=links,
        origin=origin,
        run_id=run_id,
    )
    if record is None:
        return None
    try:
        run_sources = Path(run_dir) / SOURCES_DIRNAME
        run_sources.mkdir(parents=True, exist_ok=True)
        copy_path = run_sources / str(record["file"])
        if not copy_path.exists():
            _atomic_write(copy_path, _clean_text(text))
        row = {
            "at": record["fetched_at"],
            "tool": tool,
            "kind": kind,
            "id": record["id"],
            "sha256": record["sha256"],
            "chars": record["chars"],
            "url": record.get("url"),
            "query": record.get("query"),
            "title": record.get("title"),
            "links": len(record.get("links") or []),
            "file": record["file"],
        }
        with (run_sources / MANIFEST_FILENAME).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        logger.warning("run source manifest write failed: %s", run_dir, exc_info=True)
    return record


def record_grounding(
    company_id: str,
    meta: dict | None,
    *,
    origin: str,
    run_id: str | None = None,
) -> dict | None:
    """Store a grounded Gemini pass: its research prose plus the pages the
    grounding metadata reported. ``meta`` is the runner's meta dict
    (``research_text``, ``sources`` as ``[{"title", "url"}]``,
    ``queries``)."""
    if not isinstance(meta, dict):
        return None
    text = str(meta.get("research_text") or "")
    sources = [row for row in meta.get("sources") or [] if isinstance(row, dict)]
    if not text.strip() and not sources:
        return None
    if not text.strip():
        # No prose to keep, but the pages are worth knowing about: list
        # them as a links-only blob so the digest can offer their URLs.
        text = "Pages reported by grounding:\n" + "\n".join(
            f"- {row.get('title') or ''} {row.get('url') or ''}".strip() for row in sources
        )
    queries = [str(q) for q in meta.get("queries") or [] if str(q or "").strip()]
    return record_source(
        company_id,
        kind="grounding",
        text=text,
        query="; ".join(queries)[:500] or None,
        links=sources,
        origin=origin,
        run_id=run_id,
    )


def list_sources(
    company_id: str,
    *,
    kinds: tuple[str, ...] | None = None,
    limit: int | None = None,
) -> list[dict]:
    """Records newest first, optionally filtered by kind."""
    try:
        with _LOCK:
            rows = _load_index(company_id)
    except ValueError:
        return []
    if kinds:
        rows = [row for row in rows if row.get("kind") in kinds]
    rows.sort(key=lambda row: str(row.get("fetched_at") or ""), reverse=True)
    if limit is not None:
        rows = rows[: max(0, limit)]
    return [dict(row) for row in rows]


def source_text(company_id: str, record: dict | str) -> str:
    """The stored text for a record (or record id); "" when missing."""
    try:
        if isinstance(record, str):
            match = next((row for row in _load_index(company_id) if row.get("id") == record), None)
            if match is None:
                return ""
            record = match
        path = _company_dir(company_id) / str(record.get("file") or "")
        if path.suffix != ".txt":
            return ""
        return path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return ""


def find_by_url(company_id: str, url: Any) -> dict | None:
    """The fetched-page record for ``url``, if any (canonical match)."""
    canon = canonical_url(url)
    if not canon:
        return None
    for row in list_sources(company_id, kinds=("web_fetch",)):
        if row.get("canonical_url") == canon:
            return row
    return None


def significant_tokens(text: Any) -> set[str]:
    """Lower-cased word tokens worth matching on (no stopwords, 3+ chars)."""
    return {
        token
        for token in _TOKEN_RE.findall(str(text or "").lower())
        if token not in _STOPWORDS and not token.isdigit()
    }


def _record_tokens(record: dict) -> set[str]:
    tokens = significant_tokens(record.get("title"))
    canon = str(record.get("canonical_url") or "")
    if canon:
        parts = urlsplit(canon)
        host = parts.hostname or ""
        tokens |= significant_tokens(host.replace(".", " ") + " " + parts.path.replace("/", " ").replace("-", " ").replace("_", " "))
    return tokens


def match_title(company_id: str, title: Any, *, min_score: float = 0.6) -> dict | None:
    """The fetched page whose title/URL best matches ``title``, when the
    match is strong enough to attach its URL to a source deterministically.

    Score is the share of the query's significant tokens found in the
    record's title and URL. A short query (under two tokens) never matches:
    "Report" would attach to anything.
    """
    query_tokens = significant_tokens(title)
    if len(query_tokens) < 2:
        return None
    best: tuple[float, dict] | None = None
    for row in list_sources(company_id, kinds=("web_fetch",)):
        tokens = _record_tokens(row)
        if not tokens:
            continue
        score = len(query_tokens & tokens) / len(query_tokens)
        if score >= min_score and (best is None or score > best[0]):
            best = (score, row)
    return dict(best[1]) if best else None


def known_pages(company_id: str, *, limit: int = 60) -> list[dict]:
    """Citable pages, deduped on canonical URL: every fetched page first
    (newest first — these have text on file to reopen), then the links a
    search or grounding pass reported but nothing fetched, newest first."""
    out: list[dict] = []
    seen: set[str] = set()
    rows = list_sources(company_id)

    def _take(candidate: dict) -> bool:
        canon = canonical_url(candidate.get("url"))
        if not canon or canon in seen:
            return False
        seen.add(canon)
        out.append(candidate)
        return len(out) >= limit

    for row in rows:
        if row.get("kind") == "web_fetch" and row.get("canonical_url"):
            if _take(
                {
                    "title": row.get("title") or row.get("url"),
                    "url": row.get("url"),
                    "fetched_at": row.get("fetched_at"),
                    "chars": row.get("chars"),
                    "file": row.get("file"),
                    "id": row.get("id"),
                }
            ):
                return out
    for row in rows:
        for link in row.get("links") or []:
            if _take(
                {
                    "title": link.get("title") or link.get("url"),
                    "url": link.get("url"),
                    "fetched_at": row.get("fetched_at"),
                    "chars": None,
                    "file": None,
                    "id": None,
                }
            ):
                return out
    return out


def render_known_sources_md(
    company_id: str,
    *,
    limit: int = 40,
    max_chars: int = 6000,
) -> str:
    """The digest the memo prompts carry: what retrieval already found for
    this company, newest first, with URLs to cite and files to reopen.
    Empty string when nothing is cached."""
    pages = known_pages(company_id, limit=limit)
    if not pages:
        return ""
    lines = [
        "# Known sources (retrieved for this company earlier)",
        "Pages the research already fetched or was pointed to, newest first.",
        "Cite these by URL when you rely on them; reopen a fetched page's",
        f"text under `{SOURCES_DIRNAME}/<file>` in the research folder rather",
        "than searching for it again.",
        "",
    ]
    for page in pages:
        when = str(page.get("fetched_at") or "")[:10]
        title = " ".join(str(page.get("title") or "").split())[:140]
        line = f"- {when} — {title} — {page.get('url')}"
        if page.get("file"):
            line += f" (text: {SOURCES_DIRNAME}/{page['file']}, {int(page.get('chars') or 0):,} chars)"
        lines.append(line)
    text = "\n".join(lines)
    if len(text) > max_chars:
        cut = text[:max_chars].rsplit("\n", 1)[0]
        text = cut + "\n(known sources truncated)"
    return text


def write_known_sources_file(company_id: str, research_dir: Path | str, filename: str) -> bool:
    """Refresh ``<research_dir>/<filename>`` from the cache. Best-effort:
    returns True when a digest was written, False when there was nothing
    to write or the write failed. Leaves an existing file alone when the
    cache is empty, the way the tracked-news digest does."""
    try:
        text = render_known_sources_md(company_id)
        if not text:
            return False
        target = Path(research_dir) / filename
        _atomic_write(target, text + "\n")
        return True
    except (OSError, ValueError):
        logger.warning("known-sources digest write failed for %s", company_id, exc_info=True)
        return False


def corpus_texts(company_id: str, *, max_total_chars: int = 8_000_000) -> list[tuple[str, str]]:
    """``(label, text)`` pairs of every cached retrieval, newest first, for
    the fact check. Stops adding once ``max_total_chars`` is reached."""
    out: list[tuple[str, str]] = []
    used = 0
    for row in list_sources(company_id):
        text = source_text(company_id, row)
        if not text:
            continue
        if used + len(text) > max_total_chars:
            break
        used += len(text)
        label = row.get("url") or (f"search: {row.get('query')}" if row.get("query") else row.get("kind"))
        out.append((f"cached source {row.get('id')}: {label}", text))
    return out


def run_manifest(run_dir: Path | str) -> list[dict]:
    """The rows of a run's source manifest, in the order they were written."""
    path = Path(run_dir) / SOURCES_DIRNAME / MANIFEST_FILENAME
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    except OSError:
        return []
    return rows


def run_source_texts(run_dir: Path | str) -> list[tuple[str, str]]:
    """``(label, text)`` pairs of the sources frozen with a run."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    base = Path(run_dir) / SOURCES_DIRNAME
    for row in run_manifest(run_dir):
        name = str(row.get("file") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        try:
            text = (base / name).read_text(encoding="utf-8")
        except OSError:
            continue
        label = row.get("url") or (f"search: {row.get('query')}" if row.get("query") else row.get("tool"))
        out.append((f"run source {row.get('id')}: {label}", text))
    return out


# ---- Claude stream-json capture ---------------------------------------------

_LINKS_RE = re.compile(r"Links:\s*(\[.*?\])\s*(?:\n\n|\Z)", re.S)

RETRIEVAL_TOOLS = ("WebFetch", "WebSearch")


def parse_search_links(text: str) -> list[dict]:
    """The ``Links: [...]`` list a WebSearch result carries, when present."""
    match = _LINKS_RE.search(text or "")
    if not match:
        return []
    try:
        payload = json.loads(match.group(1))
    except ValueError:
        return []
    return _clean_links(payload if isinstance(payload, list) else [])


def tool_result_text(block: dict) -> str:
    """The text of a stream-json ``tool_result`` block (string or text parts)."""
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return content if isinstance(content, str) else ""


def observe_stream_event(event: dict, capture: dict) -> dict | None:
    """Feed one Claude stream-json event to the capture; returns the record
    stored, if this event completed a retrieval.

    ``capture`` is per-subprocess mutable state: ``company_id``,
    ``run_dir``, ``run_id`` and a ``pending`` map from tool_use id to the
    WebFetch/WebSearch input. Never raises.
    """
    try:
        etype = event.get("type")
        if etype == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name") or "")
                if name in RETRIEVAL_TOOLS and block.get("id"):
                    capture.setdefault("pending", {})[block["id"]] = {
                        "name": name,
                        "input": block.get("input") if isinstance(block.get("input"), dict) else {},
                    }
            return None
        if etype != "user":
            return None
        stored: dict | None = None
        for block in (event.get("message") or {}).get("content") or []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            meta = capture.setdefault("pending", {}).pop(block.get("tool_use_id"), None)
            if meta is None or block.get("is_error"):
                continue
            text = tool_result_text(block)
            inp = meta.get("input") or {}
            if meta["name"] == "WebFetch":
                record = record_run_source(
                    capture["company_id"],
                    capture["run_dir"],
                    tool="WebFetch",
                    text=text,
                    url=inp.get("url"),
                    run_id=capture.get("run_id"),
                )
            else:
                record = record_run_source(
                    capture["company_id"],
                    capture["run_dir"],
                    tool="WebSearch",
                    text=text,
                    query=inp.get("query"),
                    links=parse_search_links(text),
                    run_id=capture.get("run_id"),
                )
            if record is not None:
                stored = record
                capture["recorded"] = int(capture.get("recorded") or 0) + 1
        return stored
    except Exception:  # noqa: BLE001
        logger.warning("source capture failed on a stream event", exc_info=True)
        return None
