"""Founder & team dossier — people, board and links for the Team tab.

Two layers, and the distinction matters for how much a reader should trust
a field:

- **The record layer** (``build_founder_dossier``) reshapes fields that
  already exist on the stored company (``key_people``,
  ``team_profiles``/``team``, ``founders``, ``board_investors``,
  ``employee_band``, ``github_url``/``repo_url``). Nothing is inferred: a
  founder with no recorded education has ``education`` ``None``.
- **The research layer** (``deep_search_founder_dossier``) is the Refresh
  button. It runs a web-grounded Gemini Flash pass — Gemini only, whatever
  engine the desk is set to, with no Claude fallback — and fills in what the
  record left blank: backgrounds, prior companies, board seats, headcount
  and hiring signals, with the source URLs the model actually read.

Curated record values always win over researched ones: research fills
holes, it never overwrites what a human put on the record. Researched
people the record has never heard of are appended and tagged
``source: "research"`` so the UI can tell them apart.

A researched dossier is cached under ``data/founder_dossiers/`` because the
call costs money; plain reads merge it back over current record data, so
editing the record still shows up immediately.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ai_engine, company_paths, storage

logger = logging.getLogger(__name__)

BOARD_ROLE_WORDS = ("board", "advisor", "investor", "director", "observer", "chair")


def _text(value: Any, *, limit: int = 600) -> str | None:
    text = " ".join(str(value or "").split())
    return text[:limit] or None


def _list(value: Any, *, limit: int = 12) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _text(item, limit=200)
        if text and text not in out:
            out.append(text)
    return out[:limit]


def _int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _profile(person: dict, *, company_name: str) -> dict:
    """Map a stored person row onto the dossier profile shape — recorded fields only."""
    name = _text(person.get("name"), limit=120) or "Unnamed"
    role = _text(person.get("role") or person.get("title"), limit=120) or "Team"
    return {
        "name": name,
        "role": role,
        "bio": _text(person.get("bio") or person.get("summary")),
        "pedigree_tags": _list(person.get("tags") or person.get("pedigree_tags"), limit=6),
        "education": _text(person.get("education"), limit=200),
        "past_companies": _list(person.get("past_companies") or person.get("previous_companies")),
        "prior_exits": _text(person.get("prior_exits"), limit=200),
        "patents_papers_count": _int(person.get("patents_papers_count") or person.get("patents")),
        "github_handle": _text(person.get("github") or person.get("github_handle"), limit=80),
        "linkedin_url": _text(person.get("linkedin_url") or person.get("linkedin"), limit=300),
        "profile_url": _text(person.get("profile_url") or person.get("url") or person.get("website"), limit=300),
        "company": company_name,
    }


def _merge_person(target: dict, row: dict) -> None:
    """Fill fields the first-seen row left empty from a later row for the same person.

    ``key_people`` usually carries only name + role while ``team_profiles`` carries
    the bio and LinkedIn link; the dossier must keep both rather than the first.
    """
    for key, value in row.items():
        if value in (None, "", [], {}):
            continue
        if target.get(key) in (None, "", [], {}):
            target[key] = value


def _person_key(row: dict) -> str:
    return " ".join(str(row.get("name") or "").split()).lower()


def _is_board(profile: dict) -> bool:
    role = (profile.get("role") or "").lower()
    return any(word in role for word in BOARD_ROLE_WORDS)


def build_founder_dossier(company_id: str) -> dict:
    """Dossier built purely from the company record."""
    company = storage.get_company(company_id) or {}
    name = company.get("name") or company_id

    # One merged row per person, in first-seen order. The same person often
    # appears in several record fields (key_people, team_profiles, board
    # investors); later rows fill in whatever the earlier ones left blank.
    merged: dict[str, dict] = {}
    for key in ("key_people", "team_profiles", "team", "founders", "board_investors"):
        rows = company.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, str) and row.strip():
                row = {"name": row}
            if not isinstance(row, dict) or not row.get("name"):
                continue
            person_key = _person_key(row)
            if not person_key:
                continue
            if person_key in merged:
                _merge_person(merged[person_key], row)
            else:
                merged[person_key] = dict(row)
                if key == "board_investors":
                    merged[person_key].setdefault("_from_board", True)

    founders: list[dict] = []
    board: list[dict] = []
    for row in merged.values():
        profile = _profile(row, company_name=name)
        if _is_board(profile):
            board.append(profile)
        elif row.get("_from_board"):
            profile["role"] = _text(row.get("role"), limit=120) or "Board / Investor"
            board.append(profile)
        else:
            founders.append(profile)

    headcount = None
    band = _text(company.get("employee_band") or company.get("employees") or company.get("headcount"), limit=60)
    open_roles = _int(company.get("open_roles_count") or company.get("open_roles"))
    if band or open_roles is not None:
        headcount = {
            "employee_count_estimate": band,
            "engineering_pct": _int(company.get("engineering_pct")),
            "gtm_sales_pct": _int(company.get("gtm_sales_pct")),
            "operations_pct": _int(company.get("operations_pct")),
            "open_roles_count": open_roles,
            "hiring_velocity": _text(company.get("hiring_velocity"), limit=120),
        }

    traction = None
    repo = _text(company.get("repo_url") or company.get("github_url") or company.get("github"), limit=300)
    if repo:
        traction = {
            "repo_url": repo,
            "stars": _int(company.get("github_stars")),
            "stars_growth_weekly": None,
            "forks": _int(company.get("github_forks")),
            "weekly_downloads": _text(company.get("weekly_downloads"), limit=60),
            "commit_cadence": None,
            "inflection_signal": None,
        }

    return {
        "company_id": company_id,
        "founders": founders,
        "advisors_and_board": board,
        "team_headcount": headcount,
        "developer_traction": traction,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "is_deep_audited": False,
        "source": "company_record",
        # Research fields, always present so the payload shape does not change
        # between a company that has been researched and one that has not.
        "engine": None,
        "model": None,
        "sources": [],
        "research_error": None,
    }


# ---- Research layer -------------------------------------------------------

RESEARCH_TIMEOUT_SEC = 240
# Team research is Gemini's: grounded search returns the source URLs the Team
# tab shows, where the Claude fallback returned none and took up to fifteen
# minutes behind a spinner. A Gemini failure comes back as `research_error`.
RESEARCH_ENGINE_POLICY = "gemini-only"

PERSON_PROPERTIES: dict[str, Any] = {
    "name": {"type": "string", "description": "Full name as it appears in sources."},
    "role": {
        "type": "string",
        "description": "Current title at this company, e.g. 'Co-founder & CTO'.",
    },
    "is_board_or_advisor": {
        "type": "boolean",
        "description": "True for board members, observers and advisors; false for operators.",
    },
    "bio": {
        "type": "string",
        "description": "Two or three sentences on what this person did before, and why it matters here.",
    },
    "education": {"type": "string", "description": "Degrees and institutions, if reported."},
    "past_companies": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Employers before this company, most relevant first.",
    },
    "prior_exits": {
        "type": "string",
        "description": "Prior acquisitions or IPOs this person was part of, with the acquirer if reported.",
    },
    "pedigree_tags": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Short tags, e.g. 'ex-Google', 'YC W21', 'PhD Stanford'.",
    },
    "linkedin_url": {"type": "string", "description": "LinkedIn profile URL."},
    "profile_url": {"type": "string", "description": "Company bio page or personal site."},
}

RESEARCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "people": {
            "type": "array",
            "description": "Founders, executives, board members and advisors found in sources.",
            "items": {
                "type": "object",
                "properties": PERSON_PROPERTIES,
                "required": ["name", "role"],
            },
        },
        "team_headcount": {
            "type": "object",
            "properties": {
                "employee_count_estimate": {
                    "type": "string",
                    "description": "A band such as '50-100', not a false-precision number.",
                },
                "engineering_pct": {"type": "integer"},
                "gtm_sales_pct": {"type": "integer"},
                "operations_pct": {"type": "integer"},
                "open_roles_count": {"type": "integer"},
                "hiring_velocity": {
                    "type": "string",
                    "description": "e.g. 'hiring steadily, ~8 open roles across eng and GTM'.",
                },
            },
        },
        "developer_traction": {
            "type": "object",
            "properties": {
                "repo_url": {"type": "string"},
                "stars": {"type": "integer"},
                "forks": {"type": "integer"},
                "weekly_downloads": {"type": "string"},
                "commit_cadence": {"type": "string"},
                "inflection_signal": {"type": "string"},
            },
        },
        "notes": {
            "type": "string",
            "description": "What could not be established, and where the record looks stale.",
        },
    },
    "required": ["people"],
}

RESEARCH_SYSTEM_PROMPT = """You are a venture research analyst building a founder
and team dossier for an investment desk.

Rules you do not break:
- Search the web and report only what the sources you read actually say.
- Never invent a person, a title, a degree, an employer or a number. A field
  you cannot source is left out entirely — an omitted field is correct, a
  guessed one is a defect that ends up in an investment memo.
- Prefer primary sources: the company's own team page, SEC and Companies House
  filings, the person's LinkedIn, funding announcements from the investors.
- Distinguish current from former. Do not list someone who has left as if they
  were still there, and say so in `notes` if you find a departure.
- People who sit on the board or advise (including investor directors and
  board observers) get `is_board_or_advisor: true`; operators get false.
- When sources disagree about headcount, give the band, not a point estimate.
"""


def _dossier_path(company_id: str) -> Path:
    # Derived per call: tests monkeypatch ``storage.DATA_DIR``.
    return storage.DATA_DIR / "founder_dossiers" / f"{company_paths.storage_key(company_id)}.json"


def _read_cached(company_id: str) -> dict | None:
    path = _dossier_path(company_id)
    try:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("founder_dossier: unreadable cache at %s", path, exc_info=True)
        return None
    return data if isinstance(data, dict) else None


def _write_cached(company_id: str, payload: dict) -> None:
    path = _dossier_path(company_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        # A dossier we cannot cache is still a dossier worth returning.
        logger.warning("founder_dossier: could not cache %s", path, exc_info=True)


def _research_prompt(company: dict, *, known: list[dict]) -> str:
    name = company.get("name") or company.get("id")
    lines = [f"Company: {name}"]
    for label, key in (
        ("Website", "website"),
        ("Headquarters", "hq"),
        ("Stage", "stage"),
        ("Sector", "sector"),
    ):
        value = _text(company.get(key), limit=200)
        if value:
            lines.append(f"{label}: {value}")
    description = _text(
        company.get("description") or company.get("one_liner") or company.get("positioning"),
        limit=600,
    )
    if description:
        lines.append(f"What the desk has on file: {description}")

    if known:
        lines.append("")
        lines.append(
            "People already on the record — confirm each one is current, and "
            "fill in the background the desk is missing:"
        )
        for person in known:
            lines.append(f"- {person['name']} — {person['role']}")
    else:
        lines.append("")
        lines.append("The desk has no people on file. Find the founding and executive team.")

    lines.append("")
    lines.append(
        "Return every founder and executive you can source, plus the board and "
        "advisors. Include anyone on the list above even if you find nothing "
        "new about them, so the desk can see they were checked."
    )
    return "\n".join(lines)


def _researched_profile(row: dict, *, company_name: str) -> dict | None:
    """Map one researched person onto the dossier profile shape."""
    if not isinstance(row, dict):
        return None
    profile = _profile(row, company_name=company_name)
    if profile["name"] == "Unnamed":
        return None
    profile["source"] = "research"
    return profile


def _merge_profile(target: dict, researched: dict) -> None:
    """Fill blanks on a recorded profile from a researched one.

    The record is curated by the desk, so it wins every contested field; the
    research pass only supplies what was missing. ``researched_fields``
    records which keys came from the model so the UI can mark them.
    """
    filled: list[str] = []
    for key, value in researched.items():
        if key in {"name", "company", "source", "researched_fields"}:
            continue
        if value in (None, "", [], {}):
            continue
        if target.get(key) in (None, "", [], {}):
            target[key] = value
            filled.append(key)
    if filled:
        prior = set(target.get("researched_fields") or [])
        target["researched_fields"] = sorted(prior | set(filled))


def _merge_mapping(target: dict | None, researched: object) -> dict | None:
    """Fill blanks on a recorded sub-object (headcount, traction) from research."""
    if not isinstance(researched, dict):
        return target
    clean = {k: v for k, v in researched.items() if v not in (None, "", [], {})}
    if not clean:
        return target
    if not isinstance(target, dict):
        return clean
    merged = dict(target)
    for key, value in clean.items():
        if merged.get(key) in (None, "", [], {}):
            merged[key] = value
    return merged


def _apply_research(dossier: dict, data: dict, *, company_name: str) -> None:
    """Merge a research payload into a record-built dossier, in place."""
    by_key = {
        _person_key(person): person
        for person in dossier["founders"] + dossier["advisors_and_board"]
    }
    for row in data.get("people") or []:
        profile = _researched_profile(row, company_name=company_name)
        if profile is None:
            continue
        existing = by_key.get(_person_key(profile))
        if existing is not None:
            _merge_profile(existing, profile)
            continue
        # A person the record has never heard of. The model's own
        # board/advisor flag decides the column, falling back to the role text.
        is_board = row.get("is_board_or_advisor")
        if is_board is None:
            is_board = _is_board(profile)
        (dossier["advisors_and_board"] if is_board else dossier["founders"]).append(profile)
        by_key[_person_key(profile)] = profile

    dossier["team_headcount"] = _merge_mapping(
        dossier.get("team_headcount"), data.get("team_headcount")
    )
    dossier["developer_traction"] = _merge_mapping(
        dossier.get("developer_traction"), data.get("developer_traction")
    )
    notes = _text(data.get("notes"), limit=1200)
    if notes:
        dossier["research_notes"] = notes


def get_or_synthesize_founder_dossier(company_id: str) -> dict:
    """The dossier to show for a company.

    The record layer is rebuilt on every call so record edits appear at once;
    a cached research pass is merged back over it. Reading never calls a model.
    """
    dossier = build_founder_dossier(company_id)
    cached = _read_cached(company_id)
    if cached is None:
        return dossier
    company = storage.get_company(company_id) or {}
    _apply_research(
        dossier,
        {
            "people": cached.get("people") or [],
            "team_headcount": cached.get("team_headcount"),
            "developer_traction": cached.get("developer_traction"),
            "notes": cached.get("notes"),
        },
        company_name=company.get("name") or company_id,
    )
    dossier.update(
        {
            "searched_at": cached.get("searched_at") or dossier["searched_at"],
            "is_deep_audited": bool(cached.get("is_deep_audited")),
            "source": cached.get("source") or "research",
            "engine": cached.get("engine"),
            "model": cached.get("model"),
            "sources": cached.get("sources") or [],
        }
    )
    return dossier


def deep_search_founder_dossier(company_id: str) -> dict:
    """Run the web-grounded research pass and cache it.

    Never raises for a model failure: the record-built dossier comes back with
    ``research_error`` set, so the Team tab degrades to what it had rather
    than showing an error where the team should be.
    """
    company = storage.get_company(company_id)
    if company is None:
        raise ValueError(f"Unknown company: {company_id}")
    company_name = company.get("name") or company_id
    dossier = build_founder_dossier(company_id)
    known = [
        {"name": person["name"], "role": person["role"]}
        for person in dossier["founders"] + dossier["advisors_and_board"]
    ]

    data, meta, error = ai_engine.grounded(
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        user_prompt=_research_prompt(company, known=known),
        schema=RESEARCH_SCHEMA,
        name="founder_dossier",
        gemini_timeout_sec=RESEARCH_TIMEOUT_SEC,
        policy_override=RESEARCH_ENGINE_POLICY,
    )
    if error is not None or not isinstance(data, dict):
        logger.warning("founder_dossier: research failed for %s — %s", company_id, error)
        dossier["research_error"] = error or "Research returned nothing"
        dossier["engine"] = meta.get("engine")
        return dossier

    _apply_research(dossier, data, company_name=company_name)
    searched_at = datetime.now(timezone.utc).isoformat()
    sources = meta.get("sources") or []
    dossier.update(
        {
            "searched_at": searched_at,
            # Only a run that actually read sources is an audit. The Claude
            # fallback returns no machine-readable sources, so it does not
            # get to claim one.
            "is_deep_audited": bool(sources),
            "source": "research",
            "engine": meta.get("engine"),
            "model": meta.get("model"),
            "sources": sources,
            "research_error": None,
        }
    )
    _write_cached(
        company_id,
        {
            "company_id": company_id,
            "searched_at": searched_at,
            "is_deep_audited": dossier["is_deep_audited"],
            "source": "research",
            "engine": meta.get("engine"),
            "model": meta.get("model"),
            "sources": sources,
            "queries": meta.get("queries") or [],
            "people": data.get("people") or [],
            "team_headcount": data.get("team_headcount"),
            "developer_traction": data.get("developer_traction"),
            "notes": data.get("notes"),
        },
    )
    return dossier
