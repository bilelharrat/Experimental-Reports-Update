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

def list_companies() -> list[dict]:
    with _LOCK:
        _ensure_dirs()
        return list(_read_yaml(COMPANIES_FILE, []))


def search_companies(query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip().lower()
    if not q:
        return []
    scored: list[tuple[int, dict]] = []
    for c in list_companies():
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
    return [c for _, c in scored[:limit]]


def get_company(company_id: str) -> dict | None:
    for c in list_companies():
        if c.get("id") == company_id:
            return c
    return None


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
    record or None if the company isn't found.
    """
    with _LOCK:
        _ensure_dirs()
        companies = list_companies()
        for i, c in enumerate(companies):
            if c.get("id") == company_id:
                c.update(patch)
                if "company_type" in patch:
                    explicit_type = _valid_company_type(patch.get("company_type"))
                    if explicit_type:
                        c["company_type"] = explicit_type
                    else:
                        _remember_company_type(c, force=True)
                elif "ticker" in patch or "status" in patch:
                    _remember_company_type(c, force=True)
                companies[i] = c
                _write_yaml(COMPANIES_FILE, companies)
                return c
    return None


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


def migrate_trader_snapshots(target_schema_version: int) -> int:
    """One-shot sweep at server startup. For every company whose
    ``trader_snapshot`` is older than ``target_schema_version`` (or
    still carries v1-only heat_card keys), strip the ``heat_card``
    block and bump ``schema_version`` so the iOS / web clients render
    the empty-state until the user clicks Refresh.

    Returns the number of company records mutated. Idempotent — a
    second call returns 0.

    See docs/heat-card-v2.md §6 (Schema versioning + legacy migration).
    """
    mutated = 0
    with _LOCK:
        _ensure_dirs()
        if not COMPANIES_FILE.exists():
            return 0
        companies = list(_read_yaml(COMPANIES_FILE, []))
        changed = False
        for c in companies:
            snap = c.get("trader_snapshot")
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
            changed = True
            mutated += 1
        if changed:
            _write_yaml(COMPANIES_FILE, companies)
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


def _normalize_company_name(name: str) -> str:
    """Lowercase + strip punctuation + drop trailing legal suffixes.

    Used so 'Anduril Industries, Inc.', 'Anduril Industries Inc',
    'Anduril Industries' all collapse to the same comparison key.
    """
    if not name:
        return ""
    n = name.strip().lower()
    # Drop punctuation we don't care about for identity.
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    while True:
        stripped = _LEGAL_SUFFIX_RE.sub("", n).strip()
        if stripped == n:
            break
        n = stripped
    return n


def upsert_company_from_match(match: dict) -> dict:
    """Reconcile an AI search hit with the local company list.

    Match by ticker first, then by exact (case-insensitive) name. If found,
    merge any newly-discovered fields and return the local entry; if not,
    mint a fresh id and append. Always returns a dict that includes the local
    `id` plus all enrichment fields the caller passed in.
    """
    ticker = (match.get("ticker") or "").strip().upper() or None
    name = (match.get("name") or "").strip()
    if not name:
        raise ValueError("match missing name")

    norm_name = _normalize_company_name(name)

    with _LOCK:
        _ensure_dirs()
        companies = list_companies()
        found_idx: int | None = None
        for i, c in enumerate(companies):
            c_ticker = (c.get("ticker") or "").strip().upper() or None
            c_name_norm = _normalize_company_name(c.get("name") or "")
            if ticker and c_ticker and ticker == c_ticker:
                found_idx = i
                break
            if norm_name and norm_name == c_name_norm:
                found_idx = i
                break

        enrichment = {
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

        base = ticker.lower() if ticker else _slugify(name)
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
            "aliases": [],
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


def list_reports() -> list[dict]:
    """All reports, newest first. Used for the sidebar."""
    with _LOCK:
        _ensure_dirs()
        out: list[dict] = []
        for p in REPORTS_DIR.glob("*.yaml"):
            data = _read_yaml(p, None)
            if isinstance(data, dict):
                out.append(data)
        out.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return out


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
