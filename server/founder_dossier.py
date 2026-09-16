"""Founder & team dossier — people, board and links from the company record.

Everything returned here comes from fields that exist on the stored company
(``key_people``, ``team_profiles``/``team``, ``founders``, ``board_investors``,
``employee_band``, ``github_url``/``repo_url``). Nothing is inferred or
invented: a founder with no recorded education has ``education`` ``None``, a
company with no repository has ``developer_traction`` ``None``. External
enrichment (LinkedIn, GitHub stats, hiring feeds) is a later phase and will
populate the same shape with sourced values.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage

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
    }


def get_or_synthesize_founder_dossier(company_id: str) -> dict:
    """Return the dossier for the company (rebuilt from the record on every call; never written to disk)."""
    return build_founder_dossier(company_id)


def deep_search_founder_dossier(company_id: str) -> dict:
    """Refresh from the record. External enrichment is not wired yet, so this stays
    honest about what it did: ``is_deep_audited`` remains ``False``."""
    return get_or_synthesize_founder_dossier(company_id)
