"""Seed map of registry company ids to the fund's company types.

`data/` is git-ignored and prod mounts it as a volume, so the backfill
cannot be a yaml commit: storage fills `vertical` on any record missing
it from this map at load time (see storage._backfill_verticals). A value
written in `data/companies.yaml` always wins; records absent here are
left unset and classified at run time by the Phase 1 classifier.

Types: ai_foundation_model | ai_infra | ai_application |
ai_video_short_drama | robotics | other (memo_structure.COMPANY_TYPE_KEYS).
"""

from __future__ import annotations

COMPANY_VERTICALS: dict[str, str] = {
    # AI foundation models
    "anthropic-pbc": "ai_foundation_model",
    "openai-group-pbc": "ai_foundation_model",
    # AI infrastructure — silicon, inference clouds, data, orchestration
    "tenstorrent-inc": "ai_infra",
    "taalas-inc": "ai_infra",
    "cbrs": "ai_infra",
    "groq-inc": "ai_infra",
    "sambanova-systems-inc": "ai_infra",
    "nvda": "ai_infra",
    "runai-labs-ltd": "ai_infra",
    "databricks-inc": "ai_infra",
    "figure-eight-inc": "ai_infra",
    "figure-eight-federal": "ai_infra",
    "tsm": "ai_infra",
    "japan-advanced-semiconductor-manufacturing-inc": "ai_infra",
    "european-semiconductor-manufacturing-company-esmc-gmbh": "ai_infra",
    # Robotics / embodied AI
    "generalist-ai-inc": "robotics",
    "figure-ai-inc": "robotics",
    "realhand-inc": "robotics",
    "righthand-robotics-inc": "robotics",
    "xbot": "robotics",
    # Outside the focus lanes
    "the-generalist": "other",
    "the-generalist-company-ltd": "other",
    "hello-generalist": "other",
    "generalist-capital": "other",
    "toshiba-digital-solutions-corporation": "other",
    "florence": "other",
    "digital-staff-solutions-limited": "other",
    "florence-healthcare-inc": "other",
    "florence-health": "other",
    "florence-technologies-pbc": "other",
    "florencecare": "other",
    "figr": "other",
    "5425": "other",
    "mill-industries-inc": "other",
    "anthropics-technology-limited": "other",
    "openai-foundation": "other",
    # Left to the run-time classifier: msft, zainar-inc,
    # open-artificial-intelligence-inc (ambiguous from the registry text).
}
