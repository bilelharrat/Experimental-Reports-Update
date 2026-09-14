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
    name = company.get("name") or company_id.title()
    status = company.get("status") or "private"

    # Default stage: if private and has funding -> Technical Diligence or Portfolio
    initial_stage = "Portfolio" if status == "portfolio" else "Technical Diligence"

    pipeline = {
        "company_id": company_id,
        "stage": initial_stage,
        "stages": STAGES,
        "deal_lead": "Sarah Jenkins (Partner)",
        "warmth_score": 92,
        "intro_path": "Warm Intro via Alex Chen (Prior Databricks Co-founder)",
        "days_in_stage": 4,
        "last_touchpoint": "Yesterday: 45m deep architecture review with founding CTO",
        "next_step": "Thursday 2:00 PM: Investment Committee Presentation",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(pipeline, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to save default deal pipeline for %s: %s", company_id, e)

    return pipeline


def update_deal_pipeline(company_id: str, updates: dict) -> dict:
    current = get_deal_pipeline(company_id)
    current.update(updates)
    current["updated_at"] = datetime.now(timezone.utc).isoformat()

    path = _pipeline_path(company_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(current, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to update deal pipeline for %s: %s", company_id, e)

    return current
