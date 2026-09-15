"""Auth-boundary tests for require_api_token, cookie sessions, the shared
token's demotion to a read-only role, login rate limiting, and the promise
that no token is ever served in the page HTML.

These override the autouse ``_disable_auth`` fixture (which opts the rest of
the suite into anonymous dev mode) with their own env manipulation.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from server import auth_store, product_store
from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_auth_stores(monkeypatch, tmp_path):
    """Point the user/session stores at a tmp dir and start from a clean,
    fail-closed env (no shared token, no anon bypass)."""
    monkeypatch.setattr(auth_store, "USERS_FILE", tmp_path / "users.json")
    monkeypatch.setattr(auth_store, "SESSIONS_FILE", tmp_path / "sessions.json")
    monkeypatch.delenv("BSH_RESEARCH_API_TOKEN", raising=False)
    monkeypatch.delenv("BSH_ALLOW_ANON_DEV", raising=False)
    monkeypatch.setenv("BSH_COOKIE_SECURE", "0")
    # Reset the in-memory login rate-limit counters between tests.
    from server import api as api_mod

    api_mod._login_failures.clear()


def _make_user(email="user@bshventures.com", password="s3cret-passw0rd"):
    auth_store.create_user(email, password)
    return email, password


# --- Fail-closed matrix --------------------------------------------------

def test_no_token_no_creds_rejected(client):
    """No shared token, no anon flag, no credentials → 401."""
    r = client.get("/api/companies")
    assert r.status_code == 401


def test_anon_dev_flag_allows_through(client, monkeypatch):
    monkeypatch.setenv("BSH_ALLOW_ANON_DEV", "1")
    r = client.get("/api/health")
    assert r.status_code == 200


def test_anon_dev_ignores_stale_bearer(client, monkeypatch):
    """A leftover token from another checkout must not 401 local anon-dev."""
    monkeypatch.setenv("BSH_ALLOW_ANON_DEV", "1")
    r = client.get(
        "/api/health",
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert r.status_code == 200


def test_anon_dev_me_reports_admin(client, monkeypatch):
    monkeypatch.setenv("BSH_ALLOW_ANON_DEV", "1")
    monkeypatch.setenv("BSH_ANON_DEV_NAME", "Bilel Harrat")
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["auth"] == "anon_dev"
    assert body["role"] == "admin"
    assert body["name"] == "Bilel Harrat"


def test_garbage_bearer_rejected(client):
    r = client.get("/api/companies", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_shared_token_accepted(client, monkeypatch):
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", "TOP-SECRET-123")
    ok = client.get("/api/health", headers={"Authorization": "Bearer TOP-SECRET-123"})
    assert ok.status_code == 200
    bad = client.get("/api/health", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401


# --- Session tokens ------------------------------------------------------

def test_session_token_header_accepted(client):
    email, password = _make_user()
    login = client.post("/api/auth/token", json={"email": email, "password": password})
    assert login.status_code == 200
    token = login.json()["token"]
    r = client.get("/api/health", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_login_sets_session_cookie(client):
    email, password = _make_user()
    login = client.post("/api/auth/token", json={"email": email, "password": password})
    assert login.status_code == 200
    assert "bsh_session" in login.cookies
    # The TestClient now carries the cookie; a header-less request authenticates.
    r = client.get("/api/health")
    assert r.status_code == 200


def test_cookie_auth_blocks_unsafe_method_without_csrf_header(client):
    email, password = _make_user()
    client.post("/api/auth/token", json={"email": email, "password": password})
    # Cookie is now set on the client. A GET is fine; an unsafe method with
    # no X-BSH-Client header is refused (CSRF guard).
    assert client.get("/api/health").status_code == 200
    # /api/auth/logout is POST — cookie-only, no CSRF header → 403.
    # Strip the Authorization path by not sending a bearer header.
    r = client.post("/api/auth/logout")
    assert r.status_code == 403


def test_cookie_auth_allows_unsafe_method_with_csrf_header(client):
    email, password = _make_user()
    client.post("/api/auth/token", json={"email": email, "password": password})
    r = client.post("/api/auth/logout", headers={"X-BSH-Client": "web"})
    assert r.status_code == 204


# --- Shared token is not admin ------------------------------------------

def test_shared_token_role_is_service_not_admin(client, monkeypatch):
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", "TOP-SECRET-123")
    me = client.get("/api/auth/me", headers={"Authorization": "Bearer TOP-SECRET-123"})
    assert me.status_code == 200
    body = me.json()
    assert body["auth"] == "shared"
    assert body["role"] == "service"
    assert body["role"] != "admin"
    # Read-only: none of the gated mutation permissions.
    assert body["permissions"] == []


def test_role_for_email_shared_auth_returns_service():
    assert product_store.role_for_email(None, shared_auth=True) == "service"


def test_owner_email_is_admin():
    # The owner must hold documents:delete (admin-only) — without this
    # mapping the domain fallback made him a partner and every file
    # delete 403'd behind a generic UI banner (live bug, 2026-09-10).
    assert product_store.role_for_email("benma@bshventures.com") == "admin"
    assert product_store.has_permission(
        product_store.role_for_email("benma@bshventures.com"),
        "documents:delete",
    )


@pytest.mark.parametrize(
    "path",
    ["/api/companies/regen-all", "/api/companies/trader/refresh-all"],
)
def test_shared_token_cannot_fire_mass_mutations(client, monkeypatch, path):
    """The demoted service role must not be able to trigger the dangerous
    bulk operations ("Regenerate all" / "Refresh stock views")."""
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", "TOP-SECRET-123")
    r = client.post(path, headers={"Authorization": "Bearer TOP-SECRET-123"})
    assert r.status_code == 403


# --- No token leaks into served HTML ------------------------------------

def test_index_html_has_no_api_token(client, monkeypatch):
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", "TOP-SECRET-123")
    monkeypatch.setenv("BSH_ALLOW_ANON_DEV", "1")  # so the page itself loads
    r = client.get("/")
    # Page may 200 (build present) or 503 (build missing in CI); either way
    # it must never contain the token or the token meta tag.
    body = r.text
    assert "bsh-research-api-token" not in body
    assert "TOP-SECRET-123" not in body


def test_index_html_has_anon_dev_meta_when_enabled(client, monkeypatch):
    monkeypatch.setenv("BSH_ALLOW_ANON_DEV", "1")
    r = client.get("/")
    if r.status_code == 503:
        pytest.skip("frontend build missing")
    assert 'name="bsh-research-anon-dev"' in r.text
    assert 'content="1"' in r.text


def test_index_html_omits_anon_dev_meta_when_disabled(client):
    r = client.get("/")
    if r.status_code == 503:
        pytest.skip("frontend build missing")
    assert "bsh-research-anon-dev" not in r.text


# --- Login rate limiting -------------------------------------------------

def test_login_rate_limited_after_five_failures(client):
    email, _ = _make_user(password="correct-horse")
    for _ in range(5):
        bad = client.post("/api/auth/token", json={"email": email, "password": "wrong"})
        assert bad.status_code == 401
    # 6th attempt is throttled regardless of correctness.
    throttled = client.post("/api/auth/token", json={"email": email, "password": "wrong"})
    assert throttled.status_code == 429
    throttled_ok = client.post("/api/auth/token", json={"email": email, "password": "correct-horse"})
    assert throttled_ok.status_code == 429


def test_login_success_resets_failure_counter(client):
    email, password = _make_user(password="correct-horse")
    for _ in range(4):
        client.post("/api/auth/token", json={"email": email, "password": "wrong"})
    ok = client.post("/api/auth/token", json={"email": email, "password": password})
    assert ok.status_code == 200
    # Counter reset → four fresh failures don't trip the limit.
    for _ in range(4):
        bad = client.post("/api/auth/token", json={"email": email, "password": "wrong"})
        assert bad.status_code == 401


# --- Change password -----------------------------------------------------

def test_change_password_flow(client):
    email, password = _make_user(password="old-passw0rd")
    login = client.post("/api/auth/token", json={"email": email, "password": password})
    token = login.json()["token"]
    r = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": password, "new_password": "new-passw0rd-9"},
    )
    assert r.status_code == 200
    # Old password no longer works; new one does.
    assert client.post("/api/auth/token", json={"email": email, "password": password}).status_code == 401
    assert client.post("/api/auth/token", json={"email": email, "password": "new-passw0rd-9"}).status_code == 200


# --- Phase 4.1: every mutation route rejects the read-only service role ---

# One representative route per group. The service token authenticates fine
# (401 would mean auth failed); each must 403 on the permission gate before
# touching any state — so nonexistent ids are deliberate.
_SERVICE_403_ROUTES = [
    # tasks:action
    ("POST", "/api/companies/search/start?q=zz", {}),
    ("POST", "/api/weekly-stocks/refresh", {}),
    ("POST", "/api/stock-research/trackers/nope/run", {}),
    ("POST", "/api/companies/nope/refresh", {}),
    ("POST", "/api/companies/nope/translate", {}),
    ("POST", "/api/reports", {"company_id": "x", "report_type": "x", "audience": "x"}),
    ("POST", "/api/reports/nope/resume", {}),
    ("POST", "/api/news/brief", {"title": "x"}),
    ("POST", "/api/companies/nope/founder-dossier/deep-search", {}),
    ("POST", "/api/memos/prep", {"company_id": "x"}),
    ("POST", "/api/external/research/nope/translate", {}),
    ("POST", "/api/external/news/nope/retry", {}),
    ("POST", "/api/companies/nope/trader/refresh", {}),
    ("POST", "/api/companies/nope/console/sessions", {}),
    ("POST", "/api/companies/nope/console/sessions/nope/archive", {}),
    # desk:write
    ("PUT", "/api/desk/prefs", {"data": {}}),
    ("POST", "/api/alerts/events", {"events": []}),
    ("POST", "/api/signals/ledger", {"ticker": "SPY", "price_at_signal": 1}),
    ("DELETE", "/api/signals/ledger/nope", None),
    # sources:edit
    ("POST", "/api/stock-research/trackers", {}),
    ("PATCH", "/api/stock-research/trackers/nope", {}),
    ("POST", "/api/companies/select", {"name": "x"}),
    ("POST", "/api/external/link-preview", {"url": "https://example.com"}),
    ("POST", "/api/external/news", {"url": "https://example.com"}),
    ("POST", "/api/companies/nope/threads", {"question": "x"}),
    ("POST", "/api/companies/nope/documents/document_library/nope/use-in-report", {"use_in_report": True}),
    # documents:delete
    ("DELETE", "/api/stock-research/trackers/nope/sources/nope", None),
    ("DELETE", "/api/companies/nope/files/nope/summary", None),
    # memo:edit
    ("PATCH", "/api/companies/nope/memo-analysis/artifacts/nope", {}),
    ("POST", "/api/companies/nope/memo-analysis/approve", {}),
    ("PATCH", "/api/companies/nope/memo-editor/appendix/nope", {}),
    # memo:export
    ("POST", "/api/companies/nope/memo-editor/export-projection", {}),
]


@pytest.mark.parametrize("method,path,body", _SERVICE_403_ROUTES)
def test_service_role_gets_403_on_every_mutation_group(
    client, monkeypatch, method, path, body
):
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", "TOP-SECRET-123")
    monkeypatch.delenv("BSH_ALLOW_ANON_DEV", raising=False)
    r = client.request(
        method,
        path,
        headers={"Authorization": "Bearer TOP-SECRET-123"},
        json=body,
    )
    assert r.status_code == 403, f"{method} {path} -> {r.status_code}: {r.text}"
    assert "Permission denied" in r.text
