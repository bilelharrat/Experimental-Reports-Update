"""YAML-backed durable storage for the research center.

Companies, reports, and knowledge-base threads live as plain YAML files under
the data directory so a human can inspect/edit them without running the app.
"""
from __future__ import annotations

import copy
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMPANIES_FILE = DATA_DIR / "companies.yaml"
REPORTS_DIR = DATA_DIR / "reports"
THREADS_DIR = DATA_DIR / "threads"
COMPANY_SEED_FILE = (
    Path(__file__).resolve().parent / "seed_data" / "company_records.yaml"
)
COMPANY_FIXTURE_FILE = (
    Path(__file__).resolve().parent / "seed_data" / "company_fixtures.yaml"
)

_LOCAL_GENERATED_COMPANY_FIELDS: frozenset[str] = frozenset({
    "audit_records",
    "memo_state",
    "trader_snapshot",
    "translation",
})

# Bulk locally-generated fields stored OUTSIDE companies.yaml, in per-company
# sidecar files (data/company_ext/<id>.yaml). Inline, these two fields were
# 96% of a 1.24 MB companies.yaml — every index read paid for them.
# ``get_company`` merges them back in; ``list_companies`` stays slim.
COMPANY_EXT_FIELDS: frozenset[str] = frozenset({
    "trader_snapshot",
    "translation",
})

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    THREADS_DIR.mkdir(parents=True, exist_ok=True)


def _read_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data if data is not None else default


def _write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
    tmp.replace(path)


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


# ---------- Companies ----------
#
# ``companies.yaml`` is large (~1.2 MB) and re-parsing it with PyYAML on every
# call cost ~1.25 s — the root cause of slow autocomplete, starved /api/reports,
# and the sidebar's loading flash. We memoize the parsed structure keyed on the
# file's ``(mtime_ns, size)``: any write (all go through ``_write_yaml`` +
# ``tmp.replace``, which bumps mtime) is picked up automatically on the next
# read, so there is no separate invalidation to keep in sync. The cached objects
# are shared, so every public accessor deepcopies what it hands out.

_companies_cache_key: tuple[int, int] | None = None
_companies_cache_list: list[dict] = []
_companies_cache_index: dict[str, dict] = {}


def _companies_stat_key() -> tuple[int, int] | None:
    try:
        st = COMPANIES_FILE.stat()
    except (FileNotFoundError, NotADirectoryError):
        return None
    return (st.st_mtime_ns, st.st_size)


def _load_companies_locked() -> tuple[list[dict], dict[str, dict]]:
    """Return the shared cached ``(list, id_index)``, rebuilding only when
    ``companies.yaml`` has changed on disk. Caller must hold ``_LOCK`` and must
    NOT mutate or leak the returned structures — deepcopy before handing out.
    """
    global _companies_cache_key, _companies_cache_list, _companies_cache_index
    key = _companies_stat_key()
    if key is None:
        _companies_cache_key = None
        _companies_cache_list = []
        _companies_cache_index = {}
        return _companies_cache_list, _companies_cache_index
    if key != _companies_cache_key:
        data = list(_read_yaml(COMPANIES_FILE, []))
        _companies_cache_key = key
        _companies_cache_list = data
        _companies_cache_index = {
            c.get("id"): c for c in data if isinstance(c, dict) and c.get("id")
        }
    return _companies_cache_list, _companies_cache_index


def list_companies() -> list[dict]:
    with _LOCK:
        _ensure_dirs()
        data, _ = _load_companies_locked()
        return copy.deepcopy(data)


def search_companies(query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return []
    with _LOCK:
        _ensure_dirs()
        data, _ = _load_companies_locked()
        return _search_companies_scored(data, q, limit)


def _search_companies_scored(data: list[dict], q: str, limit: int) -> list[dict]:
    scored: list[tuple[int, dict]] = []
    for c in data:
        name = str(c.get("name", "")).lower()
        ticker = str(c.get("ticker", "")).lower()
        aliases = [str(a).lower() for a in c.get("aliases", []) or []]
        score = 0
        if name == q or ticker == q:
            score = 100
        elif name.startswith(q) or ticker.startswith(q):
            score = 80
        elif any(a == q or a.startswith(q) for a in aliases):
            score = 70
        elif q in name:
            score = 50
        elif any(q in a for a in aliases):
            score = 40
        if score:
            scored.append((score, c))
    scored.sort(key=lambda t: -t[0])
    return [copy.deepcopy(c) for _, c in scored[:limit]]


# ---------- Company ext sidecars (trader_snapshot / translation) ----------

# {path: ((mtime_ns, size), parsed_dict)} — same mtime-keyed pattern as the
# companies cache; writes bump mtime and self-invalidate.
_company_ext_cache: dict[str, tuple[tuple[int, int], dict]] = {}


def _company_ext_path(company_id: str) -> Path:
    # Derived per call: tests monkeypatch ``storage.DATA_DIR``.
    return DATA_DIR / "company_ext" / f"{company_id}.yaml"


def get_company_ext(company_id: str) -> dict:
    """Bulk locally-generated fields for one company from its sidecar file.

    Returns ``{}`` when no sidecar exists. Deepcopied — safe to mutate.
    """
    path = _company_ext_path(company_id)
    cache_key = str(path)
    with _LOCK:
        try:
            st = path.stat()
        except (FileNotFoundError, NotADirectoryError):
            _company_ext_cache.pop(cache_key, None)
            return {}
        key = (st.st_mtime_ns, st.st_size)
        cached = _company_ext_cache.get(cache_key)
        if cached is None or cached[0] != key:
            data = _read_yaml(path, {})
            cached = (key, data if isinstance(data, dict) else {})
            _company_ext_cache[cache_key] = cached
        return copy.deepcopy(cached[1])


def set_company_ext(company_id: str, field: str, value: Any) -> None:
    if field not in COMPANY_EXT_FIELDS:
        raise ValueError(f"not a company ext field: {field!r}")
    with _LOCK:
        ext = get_company_ext(company_id)
        ext[field] = value
        _write_yaml(_company_ext_path(company_id), ext)


def get_company(company_id: str) -> dict | None:
    """Full company record: the slim companies.yaml entry with sidecar ext
    fields (trader_snapshot / translation) merged in. Detail paths use this;
    list paths use ``list_companies`` and stay slim."""
    with _LOCK:
        _ensure_dirs()
        _, index = _load_companies_locked()
        record = index.get(company_id)
        if record is None:
            return None
        record = copy.deepcopy(record)
        ext = get_company_ext(company_id)
        for field in COMPANY_EXT_FIELDS:
            if field in ext:
                record[field] = ext[field]
        return record


def company_names() -> dict[str, str]:
    """Cheap ``{id: name}`` map from the companies cache. Returns immutable
    string values (no per-record deepcopy), so callers that only need to label
    a record by id can build this once instead of calling ``get_company`` in a
    loop."""
    with _LOCK:
        _ensure_dirs()
        _, index = _load_companies_locked()
        return {
            cid: (rec.get("name") or cid)
            for cid, rec in index.items()
        }


def _valid_company_type(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in {"public", "private"} else None


def _remember_company_type(record: dict, *, force: bool = False) -> None:
    if not force and _valid_company_type(record.get("company_type")):
        record["company_type"] = _valid_company_type(record.get("company_type"))
        return
    record["company_type"] = infer_company_type(record)


def update_company(company_id: str, **patch: Any) -> dict | None:
    """Merge `patch` into the existing company record. Returns the updated
    record (with ext fields merged) or None if the company isn't found.

    Ext fields (``trader_snapshot``/``translation``) are routed to the
    company's sidecar file so the hot companies.yaml stays slim; everything
    else lands on the main record as before.
    """
    ext_patch = {k: v for k, v in patch.items() if k in COMPANY_EXT_FIELDS}
    core_patch = {k: v for k, v in patch.items() if k not in COMPANY_EXT_FIELDS}
    with _LOCK:
        _ensure_dirs()
        companies = list_companies()
        found = False
        for i, c in enumerate(companies):
            if c.get("id") == company_id:
                found = True
                c.update(core_patch)
                if "company_type" in core_patch:
                    explicit_type = _valid_company_type(core_patch.get("company_type"))
                    if explicit_type:
                        c["company_type"] = explicit_type
                    else:
                        _remember_company_type(c, force=True)
                elif "ticker" in core_patch or "status" in core_patch:
                    _remember_company_type(c, force=True)
                companies[i] = c
                if core_patch:
                    _write_yaml(COMPANIES_FILE, companies)
                break
        if not found:
            return None
        for k, v in ext_patch.items():
            set_company_ext(company_id, k, v)
        return get_company(company_id)


def update_company_snapshot(
    company_id: str, snapshot: dict
) -> dict | None:
    """Persist a freshly-generated ``trader_snapshot`` onto a company
    record. ``snapshot`` is the dict returned by
    ``companies_ai_public.generate_snapshot`` plus a ``refreshed_at`` and
    optional ``generation_cost_usd`` / ``generation_duration_ms``.
    """
    return update_company(company_id, trader_snapshot=snapshot)


# Marker keys that ONLY existed in the v1 heat_card. Their presence on
# a saved snapshot proves the snapshot predates the v2 Positioning
# Structure rewrite and that the iOS / web clients will hit a wall
# trying to decode the legacy shape through v2 code paths.
_HEAT_CARD_V1_MARKERS: frozenset[str] = frozenset({
    "rel_volume_20d", "iv_30d_pct", "iv_percentile_1y",
    "options_skew", "news_flow_24h", "insider_activity_30d",
    "social_mentions_trend",
})


def migrate_company_ext() -> int:
    """Hoist inline ``trader_snapshot``/``translation`` blocks out of
    companies.yaml into per-company sidecar files. Idempotent — once the
    index file is slim, a second call returns 0.

    Inline values win over any existing sidecar content (they were written
    by the legacy in-file writers and are therefore the freshest copy).
    Returns the number of company records slimmed.
    """
    moved = 0
    with _LOCK:
        _ensure_dirs()
        if not COMPANIES_FILE.exists():
            return 0
        companies = list(_read_yaml(COMPANIES_FILE, []))
        changed = False
        for c in companies:
            if not isinstance(c, dict):
                continue
            company_id = c.get("id")
            inline = {k: c.pop(k) for k in list(c) if k in COMPANY_EXT_FIELDS}
            if not inline:
                continue
            changed = True
            valued = {k: v for k, v in inline.items() if _has_value(v)}
            if company_id and valued:
                ext = get_company_ext(company_id)
                ext.update(valued)
                _write_yaml(_company_ext_path(company_id), ext)
                moved += 1
        if changed:
            _write_yaml(COMPANIES_FILE, companies)
    return moved


def migrate_trader_snapshots(target_schema_version: int) -> int:
    """One-shot sweep at server startup. For every company whose
    ``trader_snapshot`` is older than ``target_schema_version`` (or
    still carries v1-only heat_card keys), strip the ``heat_card``
    block and bump ``schema_version`` so the iOS / web clients render
    the empty-state until the user clicks Refresh.

    Returns the number of snapshots mutated. Idempotent — a second call
    returns 0. Runs the companies.yaml → sidecar migration first so it
    only ever has to look at sidecar files.

    See docs/heat-card-v2.md §6 (Schema versioning + legacy migration).
    """
    mutated = 0
    with _LOCK:
        _ensure_dirs()
        migrate_company_ext()
        ext_dir = DATA_DIR / "company_ext"
        if not ext_dir.is_dir():
            return 0
        for path in sorted(ext_dir.glob("*.yaml")):
            data = _read_yaml(path, {})
            if not isinstance(data, dict):
                continue
            snap = data.get("trader_snapshot")
            if not isinstance(snap, dict):
                continue
            current = snap.get("schema_version")
            heat = snap.get("heat_card")
            has_v1_markers = (
                isinstance(heat, dict)
                and any(k in heat for k in _HEAT_CARD_V1_MARKERS)
            )
            needs_migration = (
                (not isinstance(current, int))
                or current < target_schema_version
                or has_v1_markers
            )
            if not needs_migration:
                continue
            # Drop the now-incompatible heat_card; everything else
            # (price/momentum/sentiment/catalysts/news/tech_movers)
            # is still valid under v2 so we leave it alone.
            if "heat_card" in snap:
                snap["heat_card"] = None
            snap["schema_version"] = target_schema_version
            _write_yaml(path, data)
            mutated += 1
    return mutated


def _slugify(name: str) -> str:
    out = []
    for ch in name.lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "company"


_LEGAL_SUFFIX_RE = re.compile(
    r"[,\.]?\s+(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|"
    r"plc|holdings|holding|sa|nv|ag|gmbh|kk)\.?$",
    re.IGNORECASE,
)


# Bucket the deep-search ``status`` field (plus a ticker-presence fallback)
# into a two-value discriminator the UI and Console use to dispatch.
# See docs/public-company-trader-view.md §1.
def infer_company_type(record: dict) -> str:
    """Return ``"public"`` or ``"private"`` for a company record.

    Rules:
      - status == "public" → public
      - status in {"private","subsidiary","nonprofit"} → private
      - status missing/null:
          * non-empty ticker → public (ticker presence is a strong
            signal; deep-search just didn't classify)
          * empty ticker → private
    """
    status = (record.get("status") or "").strip().lower()
    if status == "public":
        return "public"
    if status in {"private", "subsidiary", "nonprofit"}:
        return "private"
    ticker = (record.get("ticker") or "").strip()
    return "public" if ticker else "private"


_PARENTHETICAL_RE = re.compile(r"\(([^)]*)\)")


def _normalize_company_name(name: str) -> str:
    """Lowercase + strip punctuation + drop trailing legal suffixes.

    Used so 'Anduril Industries, Inc.', 'Anduril Industries Inc',
    'Anduril Industries' all collapse to the same comparison key.
    Parenthetical segments are disambiguators/aliases, not identity —
    'Advanced Machine Intelligence, Inc. (AMI Labs)' must normalize the
    same as 'Advanced Machine Intelligence, Inc.' (the trailing
    parenthetical otherwise defeats the $-anchored suffix regex).
    """
    if not name:
        return ""
    n = name.strip().lower()
    n = _PARENTHETICAL_RE.sub(" ", n)
    # Drop punctuation we don't care about for identity.
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    while True:
        stripped = _LEGAL_SUFFIX_RE.sub("", n).strip()
        if stripped == n:
            break
        n = stripped
    return n


def _company_name_aliases(name: str) -> list[str]:
    """Extract parenthetical segments of a name as aliases.

    'Advanced Machine Intelligence Labs (AMI Labs)' → ['AMI Labs'].
    """
    aliases: list[str] = []
    for seg in _PARENTHETICAL_RE.findall(name or ""):
        seg = seg.strip()
        if seg and _normalize_company_name(seg):
            aliases.append(seg)
    return aliases


def _normalize_host(value) -> str:
    """Normalize a website URL or bare domain to a comparable host.

    Strips scheme, path/query/fragment, credentials, port and a leading
    'www.'. Returns '' for empty input.
    """
    if not value:
        return ""
    v = str(value).strip().lower()
    v = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", v)
    v = v.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    v = v.rsplit("@", 1)[-1].split(":", 1)[0]
    if v.startswith("www."):
        v = v[4:]
    return v


def _company_hosts(record: dict) -> set[str]:
    return {
        h
        for h in (
            _normalize_host(record.get("website")),
            _normalize_host(record.get("logo_domain")),
        )
        if h
    }


def _company_name_keys(record: dict) -> set[str]:
    keys = {
        _normalize_company_name(record.get("name") or ""),
        _normalize_company_name(record.get("legal_name") or ""),
    }
    for alias in record.get("aliases") or []:
        keys.add(_normalize_company_name(alias))
    keys.discard("")
    return keys


def _find_company_match_index(companies: list[dict], match: dict) -> int | None:
    """Return the index in ``companies`` that ``match`` identifies, or None.

    Evidence priority: ticker equality → website/logo host equality →
    name/alias equality (gated on same standing + no host contradiction).
    """
    ticker = (match.get("ticker") or "").strip().upper() or None
    name = (match.get("name") or "").strip()
    cand_hosts = _company_hosts(match)
    cand_names = _company_name_keys(match) | {
        _normalize_company_name(a) for a in _company_name_aliases(name)
    }
    cand_names.discard("")

    # 1. Ticker equality — unambiguous for public companies.
    for i, c in enumerate(companies):
        c_ticker = (c.get("ticker") or "").strip().upper() or None
        if ticker and c_ticker and ticker == c_ticker:
            return i

    # 2. Website/logo host equality — stable key independent of the
    #    LLM-generated name string.
    if cand_hosts:
        for i, c in enumerate(companies):
            if cand_hosts & _company_hosts(c):
                return i

    # 3. Name/alias equality, gated on corroborating identity.
    if cand_names:
        for i, c in enumerate(companies):
            c_ticker = (c.get("ticker") or "").strip().upper() or None
            # A tickerless candidate must never merge into a tickered
            # record on name alone (a private company must not absorb a
            # public one — the goog guard). The inverse is allowed: a
            # tickered candidate may enrich a tickerless record (IPO).
            if c_ticker and not ticker:
                continue
            # Both tickered but different tickers (pass 1 already
            # failed): different public companies sharing a name.
            if ticker and c_ticker:
                continue
            if not (cand_names & _company_name_keys(c)):
                continue
            # Both sides claim a web identity and they disagree →
            # a different company that happens to share the name.
            c_hosts = _company_hosts(c)
            if cand_hosts and c_hosts and not (cand_hosts & c_hosts):
                continue
            return i
    return None


def resolve_company_match(match: dict) -> str | None:
    """Read-only: return the local company id ``match`` identifies, or None.

    Same evidence rules as ``upsert_company_from_match``, with no writes —
    used by refresh flows to decide which returned match belongs to the
    record being refreshed before persisting anything.
    """
    with _LOCK:
        companies = list_companies()
        idx = _find_company_match_index(companies, match)
        return companies[idx].get("id") if idx is not None else None


def upsert_company_from_match(match: dict) -> dict:
    """Reconcile an AI search hit with the local company list.

    Identity is established on evidence, in priority order:

      1. ticker equality (both sides non-null);
      2. website / logo_domain host equality — the strongest stable key
         for private companies;
      3. normalized name or alias equality, but only between records of
         the same public/private standing (a tickerless candidate must
         never merge into a tickered record — that is the guard that
         keeps 'Alphabet Inc.' the signage company from overwriting
         ``goog``), and never when both sides carry hosts that disagree.

    If found, merge any newly-discovered fields and return the local
    entry; if not, mint a fresh id and append. Always returns a dict that
    includes the local `id` plus all enrichment fields the caller passed in.
    """
    ticker = (match.get("ticker") or "").strip().upper() or None
    name = (match.get("name") or "").strip()
    if not name:
        raise ValueError("match missing name")

    with _LOCK:
        _ensure_dirs()
        companies = list_companies()
        found_idx = _find_company_match_index(companies, match)

        enrichment = {
            "legal_name": match.get("legal_name"),
            "disambiguator": match.get("disambiguator"),
            "exchange": match.get("exchange"),
            "status": match.get("status"),
            "company_type": _valid_company_type(match.get("company_type")),
            "industry": match.get("industry"),
            "hq": match.get("hq"),
            "founded_year": match.get("founded_year"),
            "website": match.get("website"),
            "logo_domain": match.get("logo_domain"),
            "employee_band": match.get("employee_band"),
            "parent_company": match.get("parent_company"),
            "key_people": match.get("key_people") or [],
            "highlight_2026": match.get("highlight_2026"),
            "latest_funding": match.get("latest_funding"),
            "latest_earnings": match.get("latest_earnings"),
            "total_funding_usd": match.get("total_funding_usd"),
            "products": match.get("products") or [],
            "competitors": match.get("competitors") or [],
            "recent_news": match.get("recent_news") or [],
            "notable_contracts": match.get("notable_contracts") or [],
            "notable_acquisitions": match.get("notable_acquisitions") or [],
        }

        if found_idx is not None:
            existing = companies[found_idx]
            # Remember name variants we merged so future variants keep
            # matching (pass 3 checks aliases too).
            existing_keys = _company_name_keys(existing)
            new_aliases = list(existing.get("aliases") or [])
            for alias in [name, *_company_name_aliases(name)]:
                norm = _normalize_company_name(alias)
                if norm and norm not in existing_keys:
                    new_aliases.append(alias)
                    existing_keys.add(norm)
            existing["aliases"] = new_aliases
            for k, v in enrichment.items():
                if v not in (None, [], ""):
                    if (
                        k == "competitors"
                        and any(isinstance(item, dict) for item in existing.get(k) or [])
                        and not any(isinstance(item, dict) for item in v)
                    ):
                        continue
                    existing[k] = v
            if not existing.get("description") and match.get("description"):
                existing["description"] = match["description"]
            if not existing.get("sector") and match.get("sector"):
                existing["sector"] = match["sector"]
            _remember_company_type(
                existing,
                force=not _valid_company_type(match.get("company_type")),
            )
            companies[found_idx] = existing
            _write_yaml(COMPANIES_FILE, companies)
            return {**existing}

        # Slug from the legal name when the model provided one — it is the
        # most stable string across repeat searches (the display name is a
        # non-deterministic LLM judgment).
        legal_name = (match.get("legal_name") or "").strip()
        base = ticker.lower() if ticker else _slugify(legal_name or name)
        existing_ids = {c.get("id") for c in companies}
        company_id = base
        suffix = 2
        while company_id in existing_ids:
            company_id = f"{base}-{suffix}"
            suffix += 1

        new_entry = {
            "id": company_id,
            "name": name,
            "ticker": ticker,
            "aliases": _company_name_aliases(name),
            "description": match.get("description"),
            "sector": match.get("sector"),
            **enrichment,
        }
        _remember_company_type(new_entry)
        companies.append(new_entry)
        _write_yaml(COMPANIES_FILE, companies)
        return {**new_entry}


# ---------- Reports ----------

def _report_path(report_id: str) -> Path:
    return REPORTS_DIR / f"{report_id}.yaml"


# Per-file parse cache for reports: {path: ((mtime_ns, size), parsed_dict)}.
# list_reports re-globs every call (cheap — dir stat), but only re-parses the
# report files whose (mtime_ns, size) changed, so the common "nothing changed"
# poll costs a directory scan instead of parsing every report YAML.
_reports_cache: dict[str, tuple[tuple[int, int], dict]] = {}


def list_reports() -> list[dict]:
    """All reports, newest first. Used for the sidebar."""
    with _LOCK:
        _ensure_dirs()
        out: list[dict] = []
        seen: set[str] = set()
        for p in REPORTS_DIR.glob("*.yaml"):
            path_key = str(p)
            seen.add(path_key)
            try:
                st = p.stat()
            except (FileNotFoundError, NotADirectoryError):
                continue
            stat_key = (st.st_mtime_ns, st.st_size)
            cached = _reports_cache.get(path_key)
            if cached is not None and cached[0] == stat_key:
                out.append(cached[1])
                continue
            data = _read_yaml(p, None)
            if isinstance(data, dict):
                _reports_cache[path_key] = (stat_key, data)
                out.append(data)
            else:
                _reports_cache.pop(path_key, None)
        # Drop cache entries for deleted report files.
        for stale in [k for k in _reports_cache if k not in seen]:
            _reports_cache.pop(stale, None)
        out.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return copy.deepcopy(out)


def get_report(report_id: str) -> dict | None:
    with _LOCK:
        data = _read_yaml(_report_path(report_id), None)
        return data if isinstance(data, dict) else None


def create_report(
    *,
    company_id: str,
    report_type: str,
    audience: str,
    language: str = "en",
) -> dict:
    company = get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    if language not in ("en", "zh"):
        raise ValueError(f"Unsupported language: {language}")
    report_id = uuid.uuid4().hex[:12]
    report = {
        "id": report_id,
        "company_id": company_id,
        "company_name": company.get("name"),
        "report_type": report_type,
        "audience": audience,
        "language": language,
        "status": "queued",
        "progress": 0,
        "stage": "Queued",
        "stages": [],
        "content": "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    with _LOCK:
        _ensure_dirs()
        _write_yaml(_report_path(report_id), report)
    return report


def create_report_record(**fields: Any) -> dict:
    """Mint a report record that is NOT company-scoped.

    `create_report` requires a known company; some report kinds (e.g. the
    Hormuz appendix) aren't tied to a company. This writes a minimal
    record with a fresh id and whatever fields the caller passes. The
    caller owns `kind`, `status`, `run_dir`, etc.
    """
    report_id = uuid.uuid4().hex[:12]
    report = {
        "id": report_id,
        "status": "queued",
        "progress": 0,
        "stage": "Queued",
        "created_at": _now(),
        "updated_at": _now(),
        **fields,
    }
    with _LOCK:
        _ensure_dirs()
        _write_yaml(_report_path(report_id), report)
    return report


def update_report(report_id: str, **patch: Any) -> dict | None:
    with _LOCK:
        data = get_report(report_id)
        if data is None:
            return None
        data.update(patch)
        data["updated_at"] = _now()
        _write_yaml(_report_path(report_id), data)
        return data


def append_report_stage(report_id: str, stage: dict) -> dict | None:
    with _LOCK:
        data = get_report(report_id)
        if data is None:
            return None
        stages = list(data.get("stages") or [])
        stages.append({**stage, "at": _now()})
        data["stages"] = stages
        data["updated_at"] = _now()
        _write_yaml(_report_path(report_id), data)
        return data


# ---------- Knowledge base / threads ----------

def _threads_path(company_id: str) -> Path:
    return THREADS_DIR / f"{company_id}.yaml"


def list_threads(company_id: str) -> list[dict]:
    with _LOCK:
        _ensure_dirs()
        threads = _read_yaml(_threads_path(company_id), [])
        return list(threads or [])


def add_thread(company_id: str, question: str, answer: str = "") -> dict:
    if get_company(company_id) is None:
        raise ValueError(f"Unknown company: {company_id}")
    thread = {
        "id": uuid.uuid4().hex[:12],
        "question": question,
        "answer": answer,
        "created_at": _now(),
    }
    with _LOCK:
        _ensure_dirs()
        threads = list_threads(company_id)
        threads.insert(0, thread)
        _write_yaml(_threads_path(company_id), threads)
    return thread


# ---------- Bootstrap ----------

_SEED_COMPANIES = [
    {
        "id": "acme",
        "name": "Acme Corporation",
        "ticker": "ACME",
        "aliases": ["Acme Inc", "Acme Co"],
        "description": "Diversified industrial conglomerate. Roadrunner countermeasures, novelty explosives, anvils.",
        "sector": "Industrials",
    },
    {
        "id": "globex",
        "name": "Globex Corporation",
        "ticker": "GLBX",
        "aliases": ["Globex"],
        "description": "Multinational holding company with interests in tech, media, and biotech.",
        "sector": "Diversified",
    },
    {
        "id": "initech",
        "name": "Initech",
        "ticker": "INIT",
        "aliases": [],
        "description": "Enterprise software vendor specializing in legacy banking middleware.",
        "sector": "Technology",
    },
    {
        "id": "soylent",
        "name": "Soylent Corp",
        "ticker": "SLNT",
        "aliases": ["Soylent"],
        "description": "Food-tech company producing nutritional staples at industrial scale.",
        "sector": "Consumer Staples",
    },
    {
        "id": "umbrella",
        "name": "Umbrella Industries",
        "ticker": "UMBR",
        "aliases": ["Umbrella Corp"],
        "description": "Pharmaceutical and biotech firm with a defense-research subsidiary.",
        "sector": "Healthcare",
    },
    {
        "id": "stark",
        "name": "Stark Industries",
        "ticker": "STRK",
        "aliases": ["Stark"],
        "description": "Advanced materials, energy, and aerospace; recently expanded into clean power.",
        "sector": "Aerospace & Defense",
    },
]


def bootstrap_seed_data() -> None:
    """Write a starter company list if the data directory is empty, then
    backfill the ``company_type`` discriminator on every existing record
    so the public/private dispatch in the rest of the app has something
    to switch on. Idempotent.
    """
    with _LOCK:
        _ensure_dirs()
        if not COMPANIES_FILE.exists():
            _write_yaml(COMPANIES_FILE, _SEED_COMPANIES)
        _backfill_company_types()


def _load_company_seed_records(seed_file: Path = COMPANY_SEED_FILE) -> list[dict]:
    if not seed_file.exists():
        return []
    data = _read_yaml(seed_file, [])
    if not isinstance(data, list):
        raise ValueError(f"Company seed file must contain a list: {seed_file}")
    records: list[dict] = []
    seen: set[str] = set()
    for idx, record in enumerate(data, start=1):
        if not isinstance(record, dict):
            raise ValueError(
                f"Company seed record #{idx} must be a mapping: {seed_file}",
            )
        company_id = str(record.get("id") or "").strip()
        name = str(record.get("name") or "").strip()
        if not company_id or not name:
            raise ValueError(
                f"Company seed record #{idx} is missing id/name: {seed_file}",
            )
        if company_id in seen:
            raise ValueError(
                f"Duplicate company seed id {company_id!r}: {seed_file}",
            )
        seen.add(company_id)
        records.append(copy.deepcopy(record))
    return records


def _merge_company_seed_records(
    companies: list[dict],
    seed_records: list[dict],
) -> tuple[list[dict], int]:
    """Merge Git-tracked curated company records into runtime storage.

    ``data/companies.yaml`` is intentionally ignored because it contains local
    state. Seed fields should travel through Git, while locally generated fields
    stay local once they have a value.
    """
    normalized = [copy.deepcopy(c) for c in companies if isinstance(c, dict)]
    by_id = {
        str(c.get("id")): i
        for i, c in enumerate(normalized)
        if c.get("id") is not None
    }
    changed_records = 0

    for seed in seed_records:
        company_id = str(seed["id"])
        existing_idx = by_id.get(company_id)
        if existing_idx is None:
            normalized.append(copy.deepcopy(seed))
            by_id[company_id] = len(normalized) - 1
            changed_records += 1
            continue

        existing = normalized[existing_idx]
        fixture_seed = seed.get("seed_kind") == "fixture" or seed.get("fixture") is True
        fixture_existing = (
            existing.get("seed_kind") == "fixture"
            or existing.get("fixture") is True
        )
        if fixture_seed and not fixture_existing:
            continue

        record_changed = False
        for key, seed_value in seed.items():
            if key == "id":
                continue
            if (
                key in _LOCAL_GENERATED_COMPANY_FIELDS
                and _has_value(existing.get(key))
            ):
                continue
            if existing.get(key) != seed_value:
                existing[key] = copy.deepcopy(seed_value)
                record_changed = True
        if record_changed:
            changed_records += 1

    return normalized, changed_records


def materialize_seed_company_records(
    seed_file: Path = COMPANY_SEED_FILE,
    *,
    include_fixtures: bool = False,
    fixture_file: Path = COMPANY_FIXTURE_FILE,
) -> int:
    """Apply tracked company seed records to ``data/companies.yaml``.

    Returns the number of company records created or updated. This is designed
    for startup/server-local generation: generated runtime fields stay in the
    ignored ``data`` directory, but curated records such as the ZaiNar PRD
    overview can persist through Git and be re-materialized after deploy.
    """
    seed_records = _load_company_seed_records(seed_file)
    if include_fixtures:
        seen = {str(record.get("id")) for record in seed_records}
        for record in _load_company_seed_records(fixture_file):
            company_id = str(record.get("id"))
            if company_id in seen:
                raise ValueError(f"Duplicate company seed id {company_id!r}")
            seen.add(company_id)
            seed_records.append(record)
    if not seed_records:
        return 0

    with _LOCK:
        _ensure_dirs()
        current = _read_yaml(COMPANIES_FILE, [])
        if not isinstance(current, list):
            current = []
        merged, changed_records = _merge_company_seed_records(current, seed_records)
        if changed_records:
            _write_yaml(COMPANIES_FILE, merged)
        _backfill_company_types()
        return changed_records


def _backfill_company_types() -> None:
    """Set ``company_type`` on any record missing it. Caller holds the
    lock.
    """
    companies = _read_yaml(COMPANIES_FILE, [])
    if not isinstance(companies, list):
        return
    changed = False
    for c in companies:
        if not isinstance(c, dict):
            continue
        if c.get("company_type") in ("public", "private"):
            continue
        c["company_type"] = infer_company_type(c)
        changed = True
    if changed:
        _write_yaml(COMPANIES_FILE, companies)
