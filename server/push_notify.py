"""Device push registration + APNs fanout.

Stores device tokens so memo/brief/ask/alert completion can wake phones.
Without APNs credentials this module still records tokens and logs; it
does not crash the API. Set:

- ``BSH_APNS_KEY_ID``
- ``BSH_APNS_TEAM_ID``
- ``BSH_APNS_BUNDLE_ID`` (default com.bilelharrrat.bshresearch)
- ``BSH_APNS_KEY_PATH`` — path to AuthKey_XXX.p8
- ``BSH_APNS_USE_SANDBOX=1`` for development builds
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_STORE_PATH = Path(os.environ.get("BSH_DATA_DIR", "data")) / "device_tokens.json"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load() -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return {"tokens": []}
    try:
        payload = json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"tokens": []}
    if not isinstance(payload, dict):
        return {"tokens": []}
    rows = payload.get("tokens")
    if not isinstance(rows, list):
        rows = []
    return {"tokens": rows}


def _save(payload: dict[str, Any]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(_STORE_PATH)


def register_token(
    token: str,
    *,
    platform: str = "ios",
    user: str | None = None,
    topics: list[str] | None = None,
) -> dict:
    clean = str(token or "").strip()
    if len(clean) < 16:
        raise ValueError("device token is required")
    plat = str(platform or "ios").strip().lower() or "ios"
    wanted = [
        str(t).strip()
        for t in (topics or ["memo", "brief", "ask", "alert", "mover"])
        if str(t).strip()
    ]
    with _LOCK:
        payload = _load()
        rows: list[dict] = list(payload.get("tokens") or [])
        found = None
        for row in rows:
            if row.get("token") == clean:
                found = row
                break
        if found is None:
            found = {"token": clean, "created_at": _iso()}
            rows.append(found)
        found["platform"] = plat
        found["user"] = user
        found["topics"] = wanted or ["memo", "brief", "ask", "alert", "mover"]
        found["updated_at"] = _iso()
        payload["tokens"] = rows[-200:]
        _save(payload)
    return {"ok": True, "token": clean, "topics": found["topics"]}


def list_tokens(*, topic: str | None = None) -> list[dict]:
    with _LOCK:
        rows = list(_load().get("tokens") or [])
    if not topic:
        return rows
    return [row for row in rows if topic in (row.get("topics") or [])]


def apns_configured() -> bool:
    return bool(
        os.environ.get("BSH_APNS_KEY_ID")
        and os.environ.get("BSH_APNS_TEAM_ID")
        and (os.environ.get("BSH_APNS_KEY_PATH") or os.environ.get("BSH_APNS_KEY_PEM"))
    )


def _build_apns_jwt() -> str | None:
    key_id = os.environ.get("BSH_APNS_KEY_ID") or ""
    team_id = os.environ.get("BSH_APNS_TEAM_ID") or ""
    key_path = os.environ.get("BSH_APNS_KEY_PATH") or ""
    key_pem = os.environ.get("BSH_APNS_KEY_PEM") or ""
    if not key_id or not team_id:
        return None
    try:
        import jwt  # PyJWT
    except ImportError:
        logger.warning("PyJWT not installed; cannot sign APNs JWT")
        return None
    if key_path:
        pem = Path(key_path).read_text(encoding="utf-8")
    elif key_pem:
        pem = key_pem.replace("\\n", "\n")
    else:
        return None
    now = int(time.time())
    return jwt.encode(
        {"iss": team_id, "iat": now},
        pem,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id},
    )


def _send_apns(token: str, title: str, body: str, data: dict[str, Any]) -> bool:
    jwt_token = _build_apns_jwt()
    if not jwt_token:
        return False
    bundle = os.environ.get("BSH_APNS_BUNDLE_ID") or "com.bilelharrrat.bshresearch"
    sandbox = os.environ.get("BSH_APNS_USE_SANDBOX", "1") == "1"
    host = "api.sandbox.push.apple.com" if sandbox else "api.push.apple.com"
    url = f"https://{host}/3/device/{token}"
    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        },
        **{k: v for k, v in data.items() if k != "aps"},
    }
    try:
        import httpx
    except ImportError:
        logger.warning("httpx missing; cannot POST to APNs")
        return False
    headers = {
        "authorization": f"bearer {jwt_token}",
        "apns-topic": bundle,
        "apns-push-type": "alert",
        "apns-priority": "10",
        "content-type": "application/json",
    }
    try:
        with httpx.Client(http2=True, timeout=15.0) as client:
            res = client.post(url, headers=headers, content=json.dumps(payload))
        if res.status_code == 200:
            return True
        logger.warning("APNs reject %s: %s %s", token[:12], res.status_code, res.text[:200])
        return False
    except Exception as exc:  # noqa: BLE001
        logger.warning("APNs send failed: %s", exc)
        return False


def notify(topic: str, title: str, body: str, *, data: dict | None = None) -> dict:
    """Best-effort fanout. Logs when APNs is not configured."""
    rows = list_tokens(topic=topic)
    payload = data or {}
    if not apns_configured():
        logger.info(
            "push skipped (APNs not configured): topic=%s title=%s recipients=%d",
            topic,
            title,
            len(rows),
        )
        return {
            "queued": 0,
            "sent": 0,
            "recipients": len(rows),
            "configured": False,
            "topic": topic,
            "title": title,
            "body": body,
            "data": payload,
        }

    sent = 0
    for row in rows:
        token = str(row.get("token") or "")
        if not token:
            continue
        if _send_apns(token, title, body, {"topic": topic, **payload}):
            sent += 1
    return {
        "queued": sent,
        "sent": sent,
        "recipients": len(rows),
        "configured": True,
        "topic": topic,
        "title": title,
        "body": body,
        "data": payload,
    }
