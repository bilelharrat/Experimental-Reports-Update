"""End-to-end check of the new bearer-token login flow.

Runs against an in-process FastAPI app (no need to restart the running
dev server). Exercises:

  - bootstrap seeds the named users on first start
  - POST /api/auth/token with bad password is rejected (401)
  - POST /api/auth/token with the seed creds returns a token
  - the issued token unlocks /api/options
  - GET /api/auth/me reports the logged-in email + auth='session'
  - the legacy shared BSH_RESEARCH_API_TOKEN still works in parallel
    and reports auth='shared' via /api/auth/me
  - POST /api/auth/logout revokes only that session token

Usage:
    uv run python scripts/check_auth.py
"""
from __future__ import annotations

import json
import os
import sys

from fastapi.testclient import TestClient

# Make sure we test against the real on-disk data dir so the seeded
# users land where the production server will read them.
from server.main import app  # noqa: E402  (import after path setup)
from server import auth_store  # noqa: E402

SEED_EMAIL = "robert@bshventures.com"
SEED_PASSWORD = "redapple"


def _check(label: str, cond: bool, detail: str = "") -> None:
    mark = "OK " if cond else "FAIL"
    print(f"  [{mark}] {label}{(' — ' + detail) if detail else ''}")
    if not cond:
        sys.exit(1)


def main() -> None:
    print(f"BSH_RESEARCH_API_TOKEN configured: {bool(os.environ.get('BSH_RESEARCH_API_TOKEN'))}")
    # `with` form fires the FastAPI startup event (which seeds users)
    # eagerly; a bare TestClient(app) defers startup until first request.
    with TestClient(app) as client:
        _run_checks(client)


def _run_checks(client: TestClient) -> None:
    print("\n1. Seed users present after startup")
    emails = auth_store.list_user_emails()
    _check(
        f"{len(auth_store.SEED_USERS)} seed users registered",
        len(emails) == len(auth_store.SEED_USERS),
        ", ".join(emails),
    )
    _check(f"{SEED_EMAIL} present", SEED_EMAIL in emails)

    print("\n2. Login: wrong password → 401")
    r = client.post(
        "/api/auth/token",
        json={"email": SEED_EMAIL, "password": "not-the-password"},
    )
    _check("401 on bad password", r.status_code == 401, f"got {r.status_code}")

    print("\n3. Login: unknown email → 401")
    r = client.post(
        "/api/auth/token",
        json={"email": "stranger@nowhere.example", "password": SEED_PASSWORD},
    )
    _check("401 on unknown email", r.status_code == 401, f"got {r.status_code}")

    print("\n4. Login: correct creds → 200 + token")
    r = client.post(
        "/api/auth/token",
        json={"email": SEED_EMAIL, "password": SEED_PASSWORD},
    )
    _check("200 on valid login", r.status_code == 200, f"got {r.status_code}: {r.text}")
    body = r.json()
    _check("response has token", bool(body.get("token")))
    _check("response email matches", body.get("email") == SEED_EMAIL)
    _check("response has expires_at", bool(body.get("expires_at")))
    session_token = body["token"]

    print("\n5. Hit /api/options with session token → 200")
    r = client.get(
        "/api/options",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    _check("200 with session bearer", r.status_code == 200, f"got {r.status_code}")

    print("\n6. /api/auth/me reports the session email")
    r = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    _check("200 from /me", r.status_code == 200, f"got {r.status_code}")
    me = r.json()
    _check("auth='session'", me.get("auth") == "session", repr(me))
    _check("email matches", me.get("email") == SEED_EMAIL, repr(me))

    print("\n7. Hit /api/options with NO auth")
    r = client.get("/api/options")
    if os.environ.get("BSH_RESEARCH_API_TOKEN"):
        _check(
            "401 when env token is configured and no auth presented",
            r.status_code == 401,
            f"got {r.status_code}",
        )
    else:
        _check(
            "200 in dev mode (no env token) with no auth",
            r.status_code == 200,
            f"got {r.status_code}",
        )

    print("\n8. Shared env token still works (if configured)")
    shared = os.environ.get("BSH_RESEARCH_API_TOKEN")
    if shared:
        r = client.get(
            "/api/options",
            headers={"Authorization": f"Bearer {shared}"},
        )
        _check("200 with shared env token", r.status_code == 200, f"got {r.status_code}")
        r = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {shared}"},
        )
        _check("/me reports auth='shared'", r.json().get("auth") == "shared", r.text)
    else:
        print("  [SKIP] BSH_RESEARCH_API_TOKEN not set in env — skipping shared-token check")

    print("\n9. Logout revokes the session token")
    r = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    _check("204 on logout", r.status_code == 204, f"got {r.status_code}")
    r = client.get(
        "/api/options",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    _check(
        "401 with revoked session token",
        r.status_code == 401,
        f"got {r.status_code}",
    )

    print("\n10. Shared env token survives the logout (unrelated)")
    if shared:
        r = client.get(
            "/api/options",
            headers={"Authorization": f"Bearer {shared}"},
        )
        _check(
            "shared token still works after session logout",
            r.status_code == 200,
            f"got {r.status_code}",
        )

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
