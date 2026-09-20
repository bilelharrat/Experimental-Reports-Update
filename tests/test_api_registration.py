"""Registration, approval, password reset and session management.

The promises worth pinning, in order of what they'd cost to get wrong:

1. An account that has not been approved can do nothing, and neither can a
   disabled one — checked on every request, not only at sign-in.
2. Approval assigns the role. Registration is open, so the email domain is
   the applicant's choice; inferring a role from it would let a stranger
   pick their own permissions.
3. Neither open form says whether an address is registered.
4. A reset link is single use, expires, and ends every other session.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import auth_store, product_store
from server.main import app

GOOD_PASSWORD = "correct-horse-battery"
OTHER_PASSWORD = "another-good-passphrase"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_auth_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth_store, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(auth_store, "RESETS_FILE", tmp_path / "resets.json")
    monkeypatch.delenv("BSH_RESEARCH_API_TOKEN", raising=False)
    monkeypatch.delenv("BSH_ALLOW_ANON_DEV", raising=False)
    monkeypatch.setenv("BSH_COOKIE_SECURE", "0")
    from server import api as api_mod

    api_mod._login_failures.clear()
    api_mod._ip_attempts.clear()


def _admin(client) -> dict:
    """An approved admin, and the auth header for it."""
    email = "robert@bshventures.com"
    auth_store.create_user(email, GOOD_PASSWORD)
    auth_store.set_account_status(email, auth_store.STATUS_ACTIVE, role="admin")
    token = client.post(
        "/api/auth/token", json={"email": email, "password": GOOD_PASSWORD}
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _register(client, email: str, password: str = GOOD_PASSWORD):
    return client.post(
        "/api/auth/register", json={"email": email, "password": password}
    )


# ---- Registration -------------------------------------------------------


def test_registration_opens_a_pending_account(client):
    r = _register(client, "newcomer@example.com")
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert auth_store.account("newcomer@example.com")["status"] == "pending"


def test_a_pending_account_can_sign_in_to_nothing(client):
    _register(client, "newcomer@example.com")
    r = client.post(
        "/api/auth/token",
        json={"email": "newcomer@example.com", "password": GOOD_PASSWORD},
    )
    assert r.status_code == 403
    assert "approve" in r.json()["detail"].lower()


def test_a_taken_address_answers_exactly_as_a_free_one(client):
    """Otherwise the form is a way to discover who holds an account here."""
    first = _register(client, "newcomer@example.com")
    second = _register(client, "newcomer@example.com", OTHER_PASSWORD)
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    # And the original password still stands.
    assert auth_store.verify_credentials("newcomer@example.com", GOOD_PASSWORD)
    assert not auth_store.verify_credentials("newcomer@example.com", OTHER_PASSWORD)


@pytest.mark.parametrize(
    "password", ["short", "aaaaaaaaaaaaaaaa", "newcomer-and-more"]
)
def test_a_weak_password_is_refused_with_its_reason(client, password):
    r = _register(client, "newcomer@example.com", password)
    assert r.status_code == 400
    assert r.json()["detail"]
    assert auth_store.account("newcomer@example.com") is None


def test_registration_is_throttled_per_caller(client):
    for i in range(10):
        assert _register(client, f"user{i}@example.com").status_code == 202
    assert _register(client, "user10@example.com").status_code == 429


# ---- Approval assigns the role -----------------------------------------


def test_approval_lets_the_account_in_with_the_role_the_admin_picked(client):
    headers = _admin(client)
    _register(client, "newcomer@example.com")

    r = client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["account"]["role"] == "analyst"

    login = client.post(
        "/api/auth/token",
        json={"email": "newcomer@example.com", "password": GOOD_PASSWORD},
    )
    assert login.status_code == 200
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    ).json()
    assert me["role"] == "analyst"


def test_a_bsh_address_does_not_grant_itself_partner(client):
    """The domain mapping makes @bshventures.com a partner. Registration is
    open, so that address is the applicant's choice — the assigned role is
    the only thing that counts."""
    headers = _admin(client)
    _register(client, "stranger@bshventures.com")
    client.post(
        "/api/auth/accounts/stranger@bshventures.com/approve",
        json={"role": "guest"},
        headers=headers,
    )
    login = client.post(
        "/api/auth/token",
        json={"email": "stranger@bshventures.com", "password": GOOD_PASSWORD},
    )
    me = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {login.json()['token']}"},
    ).json()
    assert me["role"] == "guest"
    assert "tasks:action" not in me["permissions"]


def test_approving_without_a_role_is_refused(client):
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    r = client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": None},
        headers=headers,
    )
    assert r.status_code == 400
    assert auth_store.account("newcomer@example.com")["status"] == "pending"


def test_only_an_admin_may_approve(client):
    _admin(client)
    _register(client, "newcomer@example.com")
    auth_store.set_account_status(
        "newcomer@example.com", auth_store.STATUS_ACTIVE, role="analyst"
    )
    token = client.post(
        "/api/auth/token",
        json={"email": "newcomer@example.com", "password": GOOD_PASSWORD},
    ).json()["token"]

    _register(client, "second@example.com")
    r = client.post(
        "/api/auth/accounts/second@example.com/approve",
        json={"role": "admin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


# ---- Disabling ends access now -----------------------------------------


def test_disabling_ends_a_live_session_immediately(client):
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    token = client.post(
        "/api/auth/token",
        json={"email": "newcomer@example.com", "password": GOOD_PASSWORD},
    ).json()["token"]
    user_headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=user_headers).status_code == 200

    client.post(
        "/api/auth/accounts/newcomer@example.com/disable", headers=headers
    )
    assert client.get("/api/auth/me", headers=user_headers).status_code in (401, 403)


def test_an_admin_cannot_disable_themselves(client):
    headers = _admin(client)
    r = client.post(
        "/api/auth/accounts/robert@bshventures.com/disable", headers=headers
    )
    assert r.status_code == 400


# ---- Reset ---------------------------------------------------------------


def test_reset_request_says_the_same_thing_either_way(client):
    known = client.post(
        "/api/auth/reset/request", json={"email": "nobody@example.com"}
    )
    _register(client, "someone@example.com")
    unknown = client.post(
        "/api/auth/reset/request", json={"email": "someone@example.com"}
    )
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_a_reset_link_sets_the_password_once_and_signs_in(client):
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    minted = client.post(
        "/api/auth/accounts/newcomer@example.com/reset-link", headers=headers
    ).json()
    assert client.get(f"/api/auth/reset/check?token={minted['token']}").status_code == 200

    r = client.post(
        "/api/auth/reset/consume",
        json={"token": minted["token"], "new_password": OTHER_PASSWORD},
    )
    assert r.status_code == 200 and r.json()["token"]

    # Single use.
    again = client.post(
        "/api/auth/reset/consume",
        json={"token": minted["token"], "new_password": "third-password-here"},
    )
    assert again.status_code == 404
    assert auth_store.verify_credentials("newcomer@example.com", OTHER_PASSWORD)


def test_a_reset_ends_every_other_session(client):
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    old = client.post(
        "/api/auth/token",
        json={"email": "newcomer@example.com", "password": GOOD_PASSWORD},
    ).json()["token"]
    minted = client.post(
        "/api/auth/accounts/newcomer@example.com/reset-link", headers=headers
    ).json()
    client.post(
        "/api/auth/reset/consume",
        json={"token": minted["token"], "new_password": OTHER_PASSWORD},
    )
    assert auth_store.validate_token(old) is None


def test_an_expired_reset_link_is_refused(client):
    from datetime import timedelta

    _admin(client)
    _register(client, "newcomer@example.com")
    stale = auth_store.mint_reset_token(
        "newcomer@example.com", ttl=timedelta(seconds=-1)
    )
    assert auth_store.peek_reset_token(stale) is None
    r = client.post(
        "/api/auth/reset/consume",
        json={"token": stale, "new_password": OTHER_PASSWORD},
    )
    assert r.status_code == 404


def test_a_reset_cannot_activate_an_account_awaiting_approval(client):
    """Holding a reset link is not approval: the link sets the password,
    and the account still cannot be used until an admin lets it in."""
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    minted = client.post(
        "/api/auth/accounts/newcomer@example.com/reset-link", headers=headers
    ).json()
    r = client.post(
        "/api/auth/reset/consume",
        json={"token": minted["token"], "new_password": OTHER_PASSWORD},
    )
    assert r.status_code == 403
    assert "approve" in r.json()["detail"].lower()


def test_a_reset_token_is_not_stored_in_the_clear(client, tmp_path):
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    minted = client.post(
        "/api/auth/accounts/newcomer@example.com/reset-link", headers=headers
    ).json()
    assert minted["token"] not in (tmp_path / "resets.json").read_text()


# ---- Sessions ------------------------------------------------------------


def test_a_person_can_see_and_end_their_other_sessions(client):
    headers = _admin(client)
    email, password = "robert@bshventures.com", GOOD_PASSWORD
    second = client.post(
        "/api/auth/token", json={"email": email, "password": password}
    ).json()["token"]

    listed = client.get("/api/auth/sessions", headers=headers).json()["sessions"]
    assert len(listed) == 2
    assert sum(1 for s in listed if s["current"]) == 1

    revoked = client.post("/api/auth/sessions/revoke", headers=headers).json()
    assert revoked["revoked"] == 1
    assert auth_store.validate_token(second) is None
    # The caller's own session survives.
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_changing_a_password_ends_the_other_sessions(client):
    headers = _admin(client)
    other = client.post(
        "/api/auth/token",
        json={"email": "robert@bshventures.com", "password": GOOD_PASSWORD},
    ).json()["token"]
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": GOOD_PASSWORD, "new_password": OTHER_PASSWORD},
        headers=headers,
    )
    assert r.status_code == 200
    assert auth_store.validate_token(other) is None


def test_users_manage_is_admin_only():
    assert "users:manage" in product_store.ROLE_PERMISSIONS["admin"]
    for role, perms in product_store.ROLE_PERMISSIONS.items():
        if role != "admin":
            assert "users:manage" not in perms


def test_the_machine_role_is_not_on_the_menu(client):
    """"service" is the shared env token's role — a machine credential,
    never a person."""
    headers = _admin(client)
    offered = client.get("/api/auth/accounts", headers=headers).json()["roles"]
    assert "service" not in offered
    assert "analyst" in offered

    _register(client, "newcomer@example.com")
    r = client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "service"},
        headers=headers,
    )
    assert r.status_code == 400
    assert auth_store.account("newcomer@example.com")["status"] == "pending"
