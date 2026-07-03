from __future__ import annotations

import os

import yaml
from fastapi.testclient import TestClient

from server import (
    analytics_store,
    auth_store,
    context_store,
    external_store,
    files_store,
    memo_editor_store,
    product_store,
    research_store,
    storage,
)
from server.main import app


def _seed_company(data_root):
    data_root.mkdir(parents=True, exist_ok=True)
    companies = [
        {
            "id": "zainar-inc",
            "name": "ZaiNar, Inc.",
            "aliases": ["ZaiNar"],
            "status": "private",
            "company_type": "private",
            "description": "Network PNT platform.",
            "industry": "Wireless Positioning / Physical AI",
            "positioning": {"category": "network-based positioning platform"},
            "metrics": [
                {"label": "ARR", "value": "$24M", "source_class": "BSH diligence"},
                {"label": "Valuation", "value": "$1.0B+", "source_class": "company"},
            ],
            "company_news": [
                {
                    "title": "ZaiNar raises growth round",
                    "published_at": "2026-02-19",
                    "category": "fundraising",
                    "source": "company announcement",
                    "summary": "Stealth exit with $100M+ raised.",
                    "source_class": "company",
                }
            ],
            "recent_news": [
                {
                    "headline": "ZaiNar enterprise SDK passes 50 pilots",
                    "date": "2026-06-01",
                    "summary": "Pilot count update.",
                }
            ],
            "competitors": [
                {
                    "id": "nextnav",
                    "name": "NextNav",
                    "status": "Public",
                    "ticker": "NN",
                    "exchange": "NASDAQ",
                    "note": "Closest listed terrestrial-PNT pure-play.",
                    "source_refs": [{"label": "Public comp set", "source_class": "public"}],
                }
            ],
            "industry_view": {
                "metrics": [
                    {
                        "label": "Sector TAM",
                        "value": "$45B",
                        "source_class": "third-party market data",
                    }
                ],
                "sector_signals": [
                    {
                        "category": "standardization",
                        "signal": "3GPP positioning matures",
                        "implication": "Watch moat durability.",
                    }
                ],
            },
            "expert_opinions": [
                {
                    "speaker": "BSH Research",
                    "affiliation": "Internal diligence",
                    "stance": "Cautious",
                    "summary": "Valuation needs source-backed support.",
                    "source_class": "BSH primary diligence",
                }
            ],
        }
    ]
    with (data_root / "companies.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(companies, f, sort_keys=False)


def _patch_roots(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(external_store, "EXTERNAL_ROOT", data_root / "external")
    monkeypatch.setattr(files_store, "UPLOADS_ROOT", data_root / "uploads")
    monkeypatch.setattr(research_store, "RESEARCH_ROOT", data_root / "research")
    monkeypatch.setattr(memo_editor_store, "EDITOR_ROOT", data_root / "memo_editor")
    monkeypatch.setattr(auth_store, "USERS_FILE", data_root / "users.json")
    monkeypatch.setattr(auth_store, "SESSIONS_FILE", data_root / "sessions.json")
    monkeypatch.delenv("BSH_RESEARCH_API_TOKEN", raising=False)
    _seed_company(data_root)
    return data_root


def test_company_context_news_industry_and_competitor(monkeypatch, tmp_path):
    data_root = _patch_roots(monkeypatch, tmp_path)
    external_store.write_item(
        "news",
        {
            "id": "news-1",
            "kind": "news",
            "title": "Analyst says ZaiNar could benefit from GPS backup demand",
            "summary": "The note mentions ZaiNar and terrestrial PNT.",
            "source_url": "https://example.com/zainar",
            "captured_at": "2026-06-15T00:00:00Z",
            "source_class": "third-party market data",
        },
    )

    feed = context_store.company_news("zainar-inc")
    assert feed["rows"][0]["title"].startswith("Analyst says")
    assert {row["source_class"] for row in feed["rows"]} >= {
        "company material",
        "third-party market data",
    }
    assert context_store.company_news("zainar-inc", category="fundraising")["rows"][0]["category"] == "fundraising"

    industry = context_store.industry_view("zainar-inc")
    assert industry["metrics"][0]["source_refs"]
    assert industry["expert_opinions"][0]["stance"] == "Cautious"
    assert industry["public_comps"][0]["ticker"] == "NN"
    assert industry["sector_signals"][0]["category"] == "standardization"

    detail = context_store.competitor_detail("zainar-inc", "nextnav")
    assert detail["competitor"]["name"] == "NextNav"
    assert detail["head_to_head"]

    client = TestClient(app)
    response = client.get("/api/companies/zainar-inc/news-feed")
    assert response.status_code == 200, response.text
    assert response.json()["rows"]
    assert (data_root / "analytics").exists() is False


def test_settings_analytics_and_rbac(monkeypatch, tmp_path):
    data_root = _patch_roots(monkeypatch, tmp_path)
    analytics_store.record_event("copilot_task_proposed", company_id="zainar-inc")
    analytics_store.record_event("copilot_task_actioned", company_id="zainar-inc")
    client = TestClient(app)

    settings = client.get("/api/workspace/settings")
    assert settings.status_code == 200, settings.text
    assert settings.json()["account"]["role"] == "admin"

    patched = client.patch("/api/workspace/settings", json={"compact_density": True})
    assert patched.status_code == 200, patched.text
    assert patched.json()["preferences"]["compact_density"] is True

    user = client.get("/api/workspace/user-center")
    assert user.status_code == 200, user.text
    assert user.json()["analytics"]["copilot_task_acceptance"]["acceptance_rate"] == 1.0

    auth_store.bootstrap_seed_users()
    login = client.post("/api/auth/token", json={"email": "guest", "password": "guest"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    forbidden = client.delete(
        "/api/companies/zainar-inc/files/missing-file",
        headers=headers,
    )
    assert forbidden.status_code == 403
    assert not product_store.has_permission("guest", "documents:delete")
    assert (data_root / "settings" / "preferences.yaml").exists()
