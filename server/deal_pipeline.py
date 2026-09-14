"""Deal Pipeline & Affinity-grade Relationship Warmth Engine.

Tracks institutional VC deal progression (Sourced -> Intro -> Tech DD ->
Term Sheet -> Portfolio), warm intro paths, and relationship scores.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from . import storage

logger = logging.getLogger(__name__)

STAGES = [
    "Sourced",
    "Partner Intro",
    "Technical Diligence",
    "Term Sheet / IC",
    "Portfolio",
]


def _pipeline_path(company_id: str) -> Path:
    return storage.DATA_DIR / "deal_pipeline" / f"{company_id}.json"


def get_deal_pipeline(company_id: str) -> dict:
    path = _pipeline_path(company_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Failed to read deal pipeline for %s: %s", company_id, e)

    company = storage.get_company(company_id) or {}
    status = str(company.get("status") or "").lower()

    # A fresh record starts at the top of the funnel; only a recorded portfolio
    # status moves it. Every relationship field is empty until someone types it.
    initial_stage = "Portfolio" if status == "portfolio" else STAGES[0]

    pipeline = {
        "company_id": company_id,
        "stage": initial_stage,
        "stages": STAGES,
        "deal_lead": None,
        "warmth_score": None,
        "intro_path": None,
        "days_in_stage": 0,
        "last_touchpoint": None,
        "next_step": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pipeline, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save default deal pipeline for %s: %s", company_id, e)

    return pipeline


ALLOWED_UPDATE_KEYS = {
    "stage",
    "deal_lead",
    "warmth_score",
    "intro_path",
    "days_in_stage",
    "last_touchpoint",
    "next_step",
}


def update_deal_pipeline(company_id: str, updates: dict) -> dict:
    current = get_deal_pipeline(company_id)
    clean = {k: v for k, v in (updates or {}).items() if k in ALLOWED_UPDATE_KEYS}
    if "stage" in clean and clean["stage"] not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    current.update(clean)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = _pipeline_path(company_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to update deal pipeline for %s: %s", company_id, e)

    return current
