"""Settings, user center, and RBAC adapters for the local workspace."""
from __future__ import annotations

import copy
import re
import threading
from datetime import datetime, timezone

import yaml

from . import analytics_store, auth_store, claude_runner, storage

SETTINGS_ROOT = storage.DATA_DIR / "settings"
PREFERENCES_FILE = SETTINGS_ROOT / "preferences.yaml"

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "admin:read",
        # Approving a registration, assigning its role, disabling an
        # account, minting a reset link. Admin only: it is the permission
        # that hands out every other permission.
        "users:manage",
        "settings:update",
        "sources:edit",
        "documents:delete",
        "memo:export",
        "memo:edit",
        # Signing a finished memo off (or withdrawing it). Analysts with
        # memo:edit may only ask for review.
        "memo:approve",
        "tasks:action",
        "desk:write",
    },
    "partner": {
        "settings:update",
        "sources:edit",
        "memo:export",
        "memo:edit",
        "memo:approve",
        "tasks:action",
        "desk:write",
    },
    "analyst": {
        "sources:edit",
        "memo:export",
        "memo:edit",
        "tasks:action",
        "desk:write",
    },
    "research_ops": {
        "sources:edit",
        "memo:edit",
        "tasks:action",
        "desk:write",
    },
    "guest": set(),
    # The shared env token (BSH_RESEARCH_API_TOKEN) authenticates as this
    # role. Read-only: it can reach any non-permission-gated GET but none
    # of the state-changing actions above. It is NOT admin.
    "service": set(),
}

ROLE_BY_EMAIL = {
    "benma@bshventures.com": "admin",
    "robert@bshventures.com": "admin",
    "serena@bshfoundation.org": "admin",
    "seline.sun@bshfoundation.org": "partner",
    "elina.sun@bshventures.com": "analyst",
    "aurora.pan@bshventures.com": "analyst",
}

_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_yaml(default: dict) -> dict:
    path = storage.DATA_DIR / "settings" / "preferences.yaml"
    if not path.exists():
        return copy.deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:  # noqa: BLE001
        # Quarantine and fail loud: silently answering with defaults meant
        # the next update_preferences persisted defaults over everyone's
        # stored preferences without a trace.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        quarantined = path.with_name(f"{path.name}.corrupt-{stamp}")
        try:
            path.replace(quarantined)
        except OSError:
            raise RuntimeError(f"Unreadable preferences {path}: {exc}") from exc
        raise RuntimeError(
            f"Corrupt preferences quarantined to {quarantined.name}: {exc}"
        ) from exc
    return data if isinstance(data, dict) else copy.deepcopy(default)


def _write_yaml(payload: dict) -> None:
    storage._write_yaml(storage.DATA_DIR / "settings" / "preferences.yaml", payload)


def role_for_email(email: str | None, *, shared_auth: bool = False) -> str:
    if shared_auth and not email:
        # Shared-token callers get the read-only "service" role, never
        # admin. The token is a machine credential, not a person.
        return "service"
    normalized = (email or "").strip().lower()
    if not normalized:
        return "guest"
    if normalized == "guest":
        return "guest"
    if normalized in ROLE_BY_EMAIL:
        return ROLE_BY_EMAIL[normalized]
    if normalized.endswith("@bshventures.com"):
        return "partner"
    if normalized.endswith("@bshfoundation.org"):
        return "research_ops"
    return "analyst"


# "service" is the shared env token's role — a machine credential, never a
# person — so it is not on the menu when an admin approves an account.
_UNASSIGNABLE_ROLES = frozenset({"service"})


def assignable_roles() -> list[str]:
    """The roles an administrator may give a person."""
    return sorted(set(ROLE_PERMISSIONS) - _UNASSIGNABLE_ROLES)


def permissions_for_role(role: str) -> list[str]:
    return sorted(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["guest"]))


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def default_preferences(email: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "updated_at": _now(),
        "preferences": {
            "weekly_summary": True,
            "stock_auto_refresh": True,
            "agent_alerts": True,
            "compact_density": False,
            "language": "en",
            "memo_parallel_runs": MEMO_PARALLEL_RUNS_DEFAULT,
        },
        "users": {},
    }


def get_preferences(email: str | None = None) -> dict:
    with _LOCK:
        payload = _read_yaml(default_preferences(email))
        prefs = payload.setdefault("preferences", {})
        user_key = (email or "").strip().lower()
        if user_key:
            prefs = {**prefs, **(payload.get("users") or {}).get(user_key, {})}
        else:
            prefs = dict(prefs)
        stored_template = _valid_memo_template(prefs.get("memo_template"))
        prefs["memo_template"] = stored_template
        prefs["memo_template_effective"] = stored_template or default_memo_template()
        return {
            "schema_version": payload.get("schema_version", 1),
            "updated_at": payload.get("updated_at"),
            "preferences": prefs,
            "adapter_scope": "local workspace preferences adapter",
        }


# The memo template a new late-stage / Auto memo is written against:
# "standard" is the historical 5-section memo (structure v1), "ic_v2" the
# founder's IC template (structure v2). Per user; when a user has never
# chosen, the BSH_MEMO_STRUCTURE_V2 switch decides (memo_flags: on unless
# the environment says =0), so the default is the IC template.
MEMO_TEMPLATES = ("standard", "ic_v2")
MEMO_TEMPLATE_STRUCTURE_VERSIONS = {"standard": "v1", "ic_v2": "v2"}


def _valid_memo_template(value) -> str | None:
    text = str(value or "").strip().lower()
    return text if text in MEMO_TEMPLATES else None


def default_memo_template() -> str:
    """The template for someone who has never chosen: the switch's."""
    from . import memo_flags

    return "ic_v2" if memo_flags.enabled("BSH_MEMO_STRUCTURE_V2") else "standard"


def memo_template_for(email: str | None) -> str | None:
    """The template this user saved, or None when they never chose one."""
    return get_preferences(email)["preferences"].get("memo_template")


def effective_memo_template(email: str | None, override: str | None = None) -> tuple[str, str]:
    """``(template, source)``: a valid per-run override wins ("request"),
    then the user's saved choice ("preference"), then the env default
    ("env_default")."""
    requested = _valid_memo_template(override)
    if requested:
        return requested, "request"
    saved = memo_template_for(email)
    if saved:
        return saved, "preference"
    return default_memo_template(), "env_default"


def update_preferences(email: str | None, patch: dict) -> dict:
    allowed = {
        "weekly_summary",
        "stock_auto_refresh",
        "agent_alerts",
        "compact_density",
        "language",
        "memo_parallel_runs",
        "research_engine",
        "warren_engine",
        "memo_template",
    }
    normalized = {
        key: patch[key]
        for key in allowed
        if key in patch and patch[key] is not None
    }
    reset_memo_template = False
    if "memo_template" in normalized:
        template = str(normalized["memo_template"] or "").strip().lower()
        if template in ("", "default"):
            # Back to "never chosen": the env flag decides again.
            normalized.pop("memo_template")
            reset_memo_template = True
        elif template not in MEMO_TEMPLATES:
            raise ValueError("memo_template must be 'standard' or 'ic_v2'")
        else:
            normalized["memo_template"] = template
    if "language" in normalized and normalized["language"] not in {"en", "zh"}:
        raise ValueError("language must be 'en' or 'zh'")
    if "research_engine" in normalized:
        if normalized["research_engine"] not in RESEARCH_ENGINES:
            raise ValueError(
                "research_engine must be one of " + ", ".join(RESEARCH_ENGINES)
            )
    if "warren_engine" in normalized:
        if normalized["warren_engine"] not in WARREN_ENGINES:
            raise ValueError(
                "warren_engine must be one of " + ", ".join(WARREN_ENGINES)
            )
    for key in ("weekly_summary", "stock_auto_refresh", "agent_alerts", "compact_density"):
        if key in normalized:
            normalized[key] = bool(normalized[key])
    if "memo_parallel_runs" in normalized:
        normalized["memo_parallel_runs"] = _clamp_memo_parallel_runs(
            normalized["memo_parallel_runs"]
        )
    # Machine-global keys guard shared resources (the memo cap protects the
    # server's memory), so they never live in a per-user override.
    global_only = {
        key: normalized.pop(key)
        for key in ("memo_parallel_runs", "research_engine", "warren_engine")
        if key in normalized
    }
    with _LOCK:
        payload = _read_yaml(default_preferences(email))
        payload["updated_at"] = _now()
        user_key = (email or "").strip().lower()
        if global_only:
            payload["preferences"] = {**payload.get("preferences", {}), **global_only}
        if user_key:
            users = payload.setdefault("users", {})
            users[user_key] = {**users.get(user_key, {}), **normalized}
            if reset_memo_template:
                users[user_key].pop("memo_template", None)
        else:
            payload["preferences"] = {**payload.get("preferences", {}), **normalized}
            if reset_memo_template:
                payload["preferences"].pop("memo_template", None)
        _write_yaml(payload)
    changed = sorted({**normalized, **global_only})
    if reset_memo_template:
        changed = sorted({*changed, "memo_template"})
    analytics_store.record_event("settings_updated", user_email=email, keys=changed)
    return get_preferences(email)


MEMO_PARALLEL_RUNS_DEFAULT = 2
MEMO_PARALLEL_RUNS_MAX = 8


def _clamp_memo_parallel_runs(raw) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = MEMO_PARALLEL_RUNS_DEFAULT
    return max(1, min(MEMO_PARALLEL_RUNS_MAX, value))


def memo_parallel_runs() -> int:
    """The machine-global cap on concurrently running user memo runs.

    Read from the global preferences branch only (per-user overrides are
    ignored on purpose — the cap protects the server's memory).
    """
    with _LOCK:
        payload = _read_yaml(default_preferences(None))
    raw = (payload.get("preferences") or {}).get(
        "memo_parallel_runs", MEMO_PARALLEL_RUNS_DEFAULT
    )
    return _clamp_memo_parallel_runs(raw)


# Which engine answers the three web-grounded research surfaces — the
# founder/team dossier, the daily desk note and the company news sweep.
# Machine-global for the same reason as the memo cap: it decides where the
# workspace spends, so it is a desk-wide setting rather than a per-user one.
RESEARCH_ENGINES = ("gemini", "gemini-only", "claude")


def _normalize_research_engine(raw) -> str | None:
    value = str(raw or "").strip().lower()
    return value if value in RESEARCH_ENGINES else None


def research_engine() -> str | None:
    """The stored desk-wide engine policy, or None when nothing is set.

    None means "not configured here", which lets ``ai_engine.policy()``
    keep falling through to ``BSH_AI_ENGINE`` and then its own default —
    so an existing deployment's env pin keeps working until somebody
    chooses in the UI.
    """
    with _LOCK:
        payload = _read_yaml(default_preferences(None))
    return _normalize_research_engine(
        (payload.get("preferences") or {}).get("research_engine")
    )


# Which engine answers Warren first. Desk-wide for the same reason as the
# research engine: it decides where the workspace spends. The other engine
# still answers when the first cannot (server/warren_engine.py).
WARREN_ENGINES = ("claude", "gemini")


def warren_engine() -> str | None:
    """The stored engine Warren asks first, or None when nothing is set."""
    with _LOCK:
        payload = _read_yaml(default_preferences(None))
    value = str((payload.get("preferences") or {}).get("warren_engine") or "").strip().lower()
    return value if value in WARREN_ENGINES else None


def display_name(email: str | None) -> str:
    normalized = (email or "shared workspace").strip()
    if "@" not in normalized:
        return normalized.title()
    local = normalized.split("@", 1)[0]
    parts = re.split(r"[._\-]+", local)
    return " ".join(part.capitalize() for part in parts if part) or normalized


def workspace_profile(
    email: str | None, *, shared_auth: bool = False, role_override: str | None = None
) -> dict:
    role = role_override or role_for_email(email, shared_auth=shared_auth)
    users = auth_store.list_user_emails()
    company_count = len(storage.list_companies())
    report_count = len(storage.list_reports())
    analytics = analytics_store.summary()
    return {
        "account": {
            "name": display_name(email),
            "email": email or "shared-token session",
            "workspace": "Berkeley Summit House Research Center",
            "role": role,
            "plan": "Enterprise workspace adapter",
            "auth": "shared" if shared_auth and not email else "session",
            "permissions": permissions_for_role(role),
        },
        "team": {
            "licensed_seats": max(len(users), 1),
            "active_users": len(users),
            "members": [
                {
                    "email": item,
                    "name": display_name(item),
                    "role": role_for_email(item),
                }
                for item in users
            ],
        },
        "preferences": get_preferences(email)["preferences"],
        "status": {
            "research_engine": "ready" if claude_runner.is_available() else "needs Claude CLI",
            "memo_generation": "ready",
            "stock_data_feed": "local tracker cache",
            "document_index": "ready",
            "model": "Claude Code local CLI",
            "adapter_scope": "local/test adapter; no external telemetry or admin SaaS",
        },
        "usage": {
            "company_count": company_count,
            "report_count": report_count,
            "analytics_events": sum(analytics.get("event_counts", {}).values()),
            "research_runs": report_count,
            "reset_date": None,
        },
        "analytics": analytics,
        "generated_at": _now(),
    }
