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
    monkeypatch.delenv("BSH_TRUSTED_PROXY", raising=False)
    from server import api as api_mod, firm

    api_mod._login_failures.clear()
    api_mod._ip_attempts.clear()
    monkeypatch.setattr(firm, "_audit_file", lambda: tmp_path / "audit.jsonl")


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
    assert client.post("/api/auth/reset/check", json={"token": minted["token"]}).status_code == 200

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


# ---- Hardening ------------------------------------------------------------


def _flag_must_reset(email: str) -> None:
    payload = auth_store._load_users()
    payload["users"][auth_store.normalize_email(email)]["must_reset"] = True
    auth_store._save_users(payload)


def test_a_must_reset_account_can_change_its_password_and_nothing_else(client):
    """The flag was returned to the client and enforced by no one: a seeded
    account on the shared bootstrap password had the run of the API."""
    headers = _admin(client)
    _flag_must_reset("robert@bshventures.com")

    assert client.get("/api/companies", headers=headers).status_code == 403
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["must_reset"] is True

    r = client.post(
        "/api/auth/change-password",
        json={"current_password": GOOD_PASSWORD, "new_password": OTHER_PASSWORD},
        headers=headers,
    )
    assert r.status_code == 200
    fresh = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/api/companies", headers=fresh).status_code == 200
    assert auth_store.must_reset("robert@bshventures.com") is False


def test_change_password_holds_to_the_policy(client):
    headers = _admin(client)
    r = client.post(
        "/api/auth/change-password",
        json={"current_password": GOOD_PASSWORD, "new_password": "short"},
        headers=headers,
    )
    assert r.status_code == 400
    same = client.post(
        "/api/auth/change-password",
        json={"current_password": GOOD_PASSWORD, "new_password": GOOD_PASSWORD},
        headers=headers,
    )
    assert same.status_code == 400
    # Neither refusal touched the password.
    assert auth_store.verify_credentials("robert@bshventures.com", GOOD_PASSWORD)


def test_a_session_whose_account_is_gone_is_rejected(client):
    headers = _admin(client)
    payload = auth_store._load_users()
    payload["users"].pop("robert@bshventures.com")
    auth_store._save_users(payload)
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_a_disabled_account_gets_401_so_the_client_lets_the_session_go(client):
    """The SPA tears a session down only on 401; a 403 would leave a
    disabled person signed in to a wall of errors."""
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    tok = client.post(
        "/api/auth/token",
        json={"email": "newcomer@example.com", "password": GOOD_PASSWORD},
    ).json()["token"]
    client.post("/api/auth/accounts/newcomer@example.com/disable", headers=headers)
    # Disabling revokes the sessions outright, so the token is simply gone:
    # a 401 either way, which is what makes the SPA drop it.
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 401


def test_login_is_throttled_per_caller_as_well_as_per_email(client):
    """The per-email limiter is useless against a spray across addresses."""
    for i in range(10):
        client.post(
            "/api/auth/token",
            json={"email": f"user{i}@example.com", "password": "wrong-wrong-wrong"},
        )
    r = client.post(
        "/api/auth/token",
        json={"email": "user10@example.com", "password": "wrong-wrong-wrong"},
    )
    assert r.status_code == 429


def test_the_forwarded_address_is_trusted_only_when_told_to(client, monkeypatch):
    from server import api as api_mod

    spoofed = {"X-Forwarded-For": "203.0.113.9, 10.0.0.1"}
    for i in range(10):
        client.post(
            "/api/auth/register",
            json={"email": f"a{i}@example.com", "password": GOOD_PASSWORD},
            headers=spoofed,
        )
    # Untrusted: the header is ignored, the socket peer is the bucket, and
    # the eleventh attempt is throttled whatever the header claims.
    r = client.post(
        "/api/auth/register",
        json={"email": "a10@example.com", "password": GOOD_PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert r.status_code == 429

    api_mod._ip_attempts.clear()
    monkeypatch.setenv("BSH_TRUSTED_PROXY", "1")
    for i in range(10):
        client.post(
            "/api/auth/register",
            json={"email": f"b{i}@example.com", "password": GOOD_PASSWORD},
            headers=spoofed,
        )
    # Trusted: the first forwarded hop is the caller, so a different one
    # is a different bucket.
    r = client.post(
        "/api/auth/register",
        json={"email": "b10@example.com", "password": GOOD_PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.7"},
    )
    assert r.status_code == 202


def test_the_reset_check_takes_the_token_in_the_body_not_the_url(client):
    headers = _admin(client)
    _register(client, "newcomer@example.com")
    minted = client.post(
        "/api/auth/accounts/newcomer@example.com/reset-link", headers=headers
    ).json()
    # No GET route exists for it any more, so a token in a URL answers nothing.
    assert client.get(f"/api/auth/reset/check?token={minted['token']}").status_code != 200
    assert client.post("/api/auth/reset/check", json={"token": minted["token"]}).status_code == 200


def test_registering_a_taken_address_costs_the_same_kdf_as_a_free_one(monkeypatch):
    """A stopwatch must not tell a taken address from a free one: the KDF
    runs before the lookup either way."""
    calls = []
    real = auth_store._hash_password

    def counting(password, *, salt=None):
        calls.append(password)
        return real(password, salt=salt)

    monkeypatch.setattr(auth_store, "_hash_password", counting)
    assert auth_store.register("x@example.com", GOOD_PASSWORD) == "created"
    assert auth_store.register("x@example.com", OTHER_PASSWORD) == "exists"
    assert len(calls) == 2


@pytest.mark.parametrize("email", ["nope", "a@b", "@example.com", "user@", "a b@example.com", "x" * 250 + "@e.com"])
def test_a_malformed_address_is_refused(client, email):
    # 400 from the shape check; 422 when the body bound rejects it first.
    assert _register(client, email).status_code in (400, 422)
    assert auth_store.account(email) is None


def test_an_overlong_password_is_refused_before_the_kdf(client):
    r = _register(client, "newcomer@example.com", "x" * 300)
    assert r.status_code == 400


def test_store_files_are_owner_only(client, tmp_path):
    import stat

    _register(client, "newcomer@example.com")
    for name in ("users.json", "sessions.json"):
        path = tmp_path / name
        if path.exists():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, name


def test_a_corrupt_store_is_an_outage_not_an_empty_store(tmp_path):
    """Returning {} for an unreadable users.json would let the next write
    replace every account with a fresh seed set."""
    (tmp_path / "users.json").write_text("{not json")
    with pytest.raises(auth_store.StoreUnreadableError):
        auth_store.list_accounts()


def test_a_sign_in_past_the_session_cap_retires_the_oldest(client):
    _admin(client)
    tokens = [
        client.post(
            "/api/auth/token",
            json={"email": "robert@bshventures.com", "password": GOOD_PASSWORD},
        ).json()["token"]
        for _ in range(auth_store.MAX_SESSIONS_PER_ACCOUNT + 3)
    ]
    live = [t for t in tokens if auth_store.validate_token(t)]
    assert len(live) == auth_store.MAX_SESSIONS_PER_ACCOUNT
    assert auth_store.validate_token(tokens[-1]) is not None
    assert auth_store.validate_token(tokens[0]) is None


def test_a_reset_link_spent_twice_at_once_succeeds_once():
    import threading

    auth_store.create_user("racer@example.com", GOOD_PASSWORD)
    auth_store.set_account_status("racer@example.com", auth_store.STATUS_ACTIVE, role="analyst")
    token = auth_store.mint_reset_token("racer@example.com")
    outcomes = []

    def spend(pw):
        outcomes.append(auth_store.consume_reset_token(token, pw))

    threads = [threading.Thread(target=spend, args=(pw,)) for pw in (OTHER_PASSWORD, "third-password-here")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert sum(1 for o in outcomes if o) == 1


def test_an_admin_cannot_change_their_own_role(client):
    headers = _admin(client)
    r = client.post(
        "/api/auth/accounts/robert@bshventures.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    assert r.status_code == 400
    assert auth_store.account("robert@bshventures.com")["role"] == "admin"


def _second_admin(client) -> dict:
    """A second approved admin and the auth header for it."""
    auth_store.create_user("second@bshventures.com", GOOD_PASSWORD)
    auth_store.set_account_status(
        "second@bshventures.com", auth_store.STATUS_ACTIVE, role="admin"
    )
    token = client.post(
        "/api/auth/token",
        json={"email": "second@bshventures.com", "password": GOOD_PASSWORD},
    ).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_the_last_administrator_cannot_be_demoted(client):
    robert = _admin(client)
    second = _second_admin(client)
    # Two admins: demoting one of them is allowed.
    r = client.post(
        "/api/auth/accounts/robert@bshventures.com/approve",
        json={"role": "analyst"},
        headers=second,
    )
    assert r.status_code == 200
    # Robert is an analyst now and may not manage accounts at all.
    assert client.get("/api/auth/accounts", headers=robert).status_code == 403
    # Second is the only admin left: an admin may not change their own role,
    # and nobody else can act, so the demotion path is closed either way.
    r = client.post(
        "/api/auth/accounts/second@bshventures.com/approve",
        json={"role": "analyst"},
        headers=second,
    )
    assert r.status_code == 400
    assert auth_store.account("second@bshventures.com")["role"] == "admin"


def test_an_admin_may_disable_another_admin_but_never_themself(client):
    robert = _admin(client)
    second = _second_admin(client)
    # Two admins: disabling the other one is allowed — one remains.
    assert client.post(
        "/api/auth/accounts/robert@bshventures.com/disable", headers=second
    ).status_code == 200
    # The one left cannot disable themself, so the firm always keeps one.
    assert client.post(
        "/api/auth/accounts/second@bshventures.com/disable", headers=second
    ).status_code == 400
    assert auth_store.account("second@bshventures.com")["status"] == "active"
    # And the disabled admin's session is already gone.
    assert client.get("/api/auth/accounts", headers=robert).status_code == 401


def test_the_last_admin_guard_holds_even_if_the_caller_check_were_bypassed(client, monkeypatch):
    """Through the API this guard cannot fire — only an admin can act, and
    an admin acting on another admin never removes the last one — so it is
    defence in depth for any future route or CLI. Exercised directly."""
    from server import api as api_mod

    robert = _admin(client)
    _second_admin(client)
    monkeypatch.setattr(api_mod, "_other_active_admins", lambda email: 0)
    assert client.post(
        "/api/auth/accounts/second@bshventures.com/disable", headers=robert
    ).status_code == 400
    assert client.post(
        "/api/auth/accounts/second@bshventures.com/approve",
        json={"role": "analyst"},
        headers=robert,
    ).status_code == 400
    assert auth_store.account("second@bshventures.com")["status"] == "active"
    assert auth_store.account("second@bshventures.com")["role"] == "admin"


def test_account_decisions_land_on_the_audit_trail(client, tmp_path):
    import json

    headers = _admin(client)
    _register(client, "newcomer@example.com")
    client.post(
        "/api/auth/accounts/newcomer@example.com/approve",
        json={"role": "analyst"},
        headers=headers,
    )
    client.post("/api/auth/accounts/newcomer@example.com/reset-link", headers=headers)
    client.post("/api/auth/accounts/newcomer@example.com/disable", headers=headers)
    rows = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]
    actions = [r["action"] for r in rows]
    assert actions == ["account.approve", "account.reset_link", "account.disable"]
    assert all("newcomer@example.com" in r["detail"] for r in rows)
    assert all("robert" in str(r["actor"]) for r in rows)


def test_auth_responses_are_never_cached_and_pages_cannot_be_framed_elsewhere(client):
    r = client.post(
        "/api/auth/token", json={"email": "x@example.com", "password": "nope-nope-nope"}
    )
    assert r.headers.get("Cache-Control") == "no-store"
    assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert r.headers.get("Content-Security-Policy") == "frame-ancestors 'self'"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "same-origin"
    # Plain http: no HSTS promise the browser would then hold a dev to.
    assert "Strict-Transport-Security" not in r.headers
