"""IC vote identity, chart provider outages, dividend-yield units, atomic YAML
writes and the opt-in translation backfill."""
from __future__ import annotations

import json
import threading

import pytest
import yaml
from fastapi.testclient import TestClient

from server import auth_store, claude_runner, live_quotes, storage
from server import main as server_main
from server.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _seed_company(cid="acme-ai"):
    storage._write_yaml(
        storage.COMPANIES_FILE,
        [{"id": cid, "name": "Acme AI", "status": "private", "company_type": "private"}],
    )


def _session_headers(client, email, password="s3cret-passw0rd"):
    auth_store.create_user(email, password)
    login = client.post("/api/auth/token", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    client.cookies.clear()
    return {"Authorization": f"Bearer {login.json()['token']}"}


def _open_meeting(client):
    _seed_company()
    r = client.post("/api/companies/acme-ai/ic/meetings", json={"title": "Acme IC"})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _votes(client):
    rows = client.get("/api/companies/acme-ai/ic/meetings").json()["items"][0]["votes"]
    return {row["member"]: row for row in rows}


def test_ic_vote_uses_session_identity_not_client_name(client):
    mid = _open_meeting(client)
    ana = _session_headers(client, "ana.smith@example.com")
    ben = _session_headers(client, "ben.jones@example.com")
    url = f"/api/companies/acme-ai/ic/meetings/{mid}/votes"

    assert client.post(url, json={"member": "Ana Smith", "vote": "invest"}, headers=ana).status_code == 200
    assert client.post(url, json={"vote": "pass"}, headers=ana).status_code == 200
    assert set(_votes(client)) == {"ana.smith@example.com"}
    assert _votes(client)["ana.smith@example.com"]["vote"] == "pass"

    assert client.post(url, json={"member": "Ana Smith", "vote": "invest"}, headers=ben).status_code == 403
    assert set(_votes(client)) == {"ana.smith@example.com"}

    assert client.post(url, json={"vote": "invest"}, headers=ben).status_code == 200
    assert set(_votes(client)) == {"ana.smith@example.com", "ben.jones@example.com"}


def test_ic_vote_same_display_name_different_emails_are_two_votes(client):
    mid = _open_meeting(client)
    url = f"/api/companies/acme-ai/ic/meetings/{mid}/votes"
    one = _session_headers(client, "sam.lee@example.com")
    two = _session_headers(client, "sam.lee@other.example.com")
    assert client.post(url, json={"member": "Sam Lee", "vote": "invest"}, headers=one).status_code == 200
    assert client.post(url, json={"member": "Sam Lee", "vote": "pass"}, headers=two).status_code == 200
    assert len(_votes(client)) == 2


def test_ic_vote_anon_dev_keeps_client_member(client, monkeypatch):
    monkeypatch.setenv("BSH_ANON_DEV_NAME", "Local dev")
    mid = _open_meeting(client)
    url = f"/api/companies/acme-ai/ic/meetings/{mid}/votes"
    assert client.post(url, json={"member": "proxy", "vote": "invest"}).status_code == 200
    assert client.post(url, json={"vote": "pass"}).status_code == 200
    assert set(_votes(client)) == {"proxy", "Local dev"}


def test_chart_provider_outage_is_not_a_client_error(client, monkeypatch):
    live_quotes.clear_cache()

    def rate_limited(url, extra_headers=None):
        if "/v8/finance/chart/" in url:
            raise RuntimeError("Client error '429 Too Many Requests'")
        return json.dumps({"data": None})

    monkeypatch.setattr(live_quotes, "_http_get", rate_limited)
    r = client.get("/api/quotes/BRK.B/chart", params={"range": "1d"})
    assert r.status_code == 503, r.text
    assert r.headers.get("Retry-After") == "60"
    assert "nasdaq" in r.json()["detail"]

    live_quotes.clear_cache()

    def down(url, extra_headers=None):
        if "/v8/finance/chart/" in url:
            raise RuntimeError("connection reset")
        return json.dumps({"data": None})

    monkeypatch.setattr(live_quotes, "_http_get", down)
    r = client.get("/api/quotes/BRK.B/chart", params={"range": "1d"})
    assert r.status_code == 502, r.text

    bad = client.get("/api/quotes/BRK.B/chart", params={"range": "2w"})
    assert bad.status_code == 400


def test_normalize_yield_units():
    assert live_quotes._normalize_yield("0.87%") == pytest.approx(0.0087)
    assert live_quotes._normalize_yield("1.00%") == pytest.approx(0.01)
    assert live_quotes._normalize_yield("2.41%") == pytest.approx(0.0241)
    assert live_quotes._normalize_yield(0.0241) == pytest.approx(0.0241)
    assert live_quotes._normalize_yield(0.87, percent=True) == pytest.approx(0.0087)
    assert live_quotes._normalize_yield(0.87) == pytest.approx(0.87)


def test_cnbc_sub_one_percent_yield_is_a_fraction():
    payload = {
        "FormattedQuoteResult": {
            "FormattedQuote": [
                {
                    "code": "0",
                    "symbol": "TSM",
                    "last": "433.24",
                    "change_pct": "0.5",
                    "dividend": "3.78",
                    "dividendyield": "0.87%",
                }
            ]
        }
    }
    parsed = live_quotes._parse_cnbc(payload)
    assert parsed["TSM"]["dividend_yield"] == pytest.approx(0.0087)


def test_yahoo_yield_prefers_fraction_and_reconciles_percent():
    payload = {
        "quoteResponse": {
            "result": [
                {
                    "symbol": "TSM",
                    "regularMarketPrice": 433.24,
                    "dividendYield": 0.87,
                    "trailingAnnualDividendRate": 3.78,
                }
            ]
        }
    }
    assert live_quotes._parse_yahoo_quote(payload)["dividend_yield"] == pytest.approx(0.0087)
    payload["quoteResponse"]["result"][0]["trailingAnnualDividendYield"] = 0.0087
    assert live_quotes._parse_yahoo_quote(payload)["dividend_yield"] == pytest.approx(0.0087)


def test_write_yaml_survives_concurrent_writers(tmp_path):
    path = tmp_path / "settings" / "comps_peers.yaml"
    errors: list[BaseException] = []

    def writer(n: int) -> None:
        try:
            for i in range(20):
                storage._write_yaml(path, {f"k{n}": i, "pad": "x" * 2000})
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict) and data["pad"] == "x" * 2000
    assert not list(path.parent.glob("*.tmp"))


def test_write_yaml_cleans_up_temp_file_on_failure(tmp_path):
    path = tmp_path / "broken.yaml"

    class Unserializable:
        pass

    with pytest.raises(Exception):
        storage._write_yaml(path, {"x": Unserializable()})
    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_translation_backfill_is_on_by_default_and_opt_out(monkeypatch):
    started: list[str] = []

    class FakeThread:
        def __init__(self, *a, **k):
            started.append(k.get("name", ""))

        def start(self):
            pass

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(server_main.threading, "Thread", FakeThread)

    monkeypatch.setenv("BSH_COMPANY_TRANSLATION_BACKFILL", "0")
    server_main._start_translation_backfill()
    assert started == []

    monkeypatch.setenv("BSH_COMPANY_TRANSLATION_BACKFILL", "off")
    server_main._start_translation_backfill()
    assert started == []

    # Default on: deck intake and AI search do not translate inline, so an
    # opt-in flag would leave those companies untranslated.
    monkeypatch.delenv("BSH_COMPANY_TRANSLATION_BACKFILL", raising=False)
    server_main._start_translation_backfill()
    assert started == ["company-translation-backfill"]

    monkeypatch.setenv("BSH_COMPANY_TRANSLATION_BACKFILL", "1")
    server_main._start_translation_backfill()
    assert started == ["company-translation-backfill"] * 2
