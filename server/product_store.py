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
        "settings:update",
        "sources:edit",
        "documents:delete",
        "memo:export",
        "memo:edit",
        "tasks:action",
        "desk:write",
    },
    "partner": {
        "settings:update",
        "sources:edit",
        "memo:export",
        "memo:edit",
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
        return {
            "schema_version": payload.get("schema_version", 1),
            "updated_at": payload.get("updated_at"),
            "preferences": prefs,
            "adapter_scope": "local workspace preferences adapter",
        }


def update_preferences(email: str | None, patch: dict) -> dict:
    allowed = {
        "weekly_summary",
        "stock_auto_refresh",
        "agent_alerts",
        "compact_density",
        "language",
        "memo_parallel_runs",
    }
    normalized = {
        key: patch[key]
        for key in allowed
        if key in patch and patch[key] is not None
    }
    if "language" in normalized and normalized["language"] not in {"en", "zh"}:
        raise ValueError("language must be 'en' or 'zh'")
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
        for key in ("memo_parallel_runs",)
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
        else:
            payload["preferences"] = {**payload.get("preferences", {}), **normalized}
        _write_yaml(payload)
    changed = sorted({**normalized, **global_only})
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
