from __future__ import annotations

import yaml
from fastapi.testclient import TestClient
import pytest

from server import memo_editor_store, serena_analysis, storage
from server.main import app


@pytest.fixture
def memo_editor_env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_root)
    monkeypatch.setattr(storage, "COMPANIES_FILE", data_root / "companies.yaml")
    monkeypatch.setattr(storage, "REPORTS_DIR", data_root / "reports")
    monkeypatch.setattr(storage, "THREADS_DIR", data_root / "threads")
    monkeypatch.setattr(memo_editor_store, "EDITOR_ROOT", data_root / "memo_editor")
    monkeypatch.setattr(serena_analysis, "ANALYSIS_ROOT", data_root / "serena_analysis")
    monkeypatch.setattr(serena_analysis, "TRAINING_ROOT", data_root / "serena_training")

    data_root.mkdir(parents=True)
    companies = [
        {
            "id": "zainar-test",
            "name": "ZaiNar Test",
            "status": "private",
            "company_type": "private",
            "description": "Network-based PNT platform for indoor and GPS-denied positioning.",
            "hq": "Belmont, CA",
            "founded_year": 2017,
            "positioning": {
                "benefit": "Sub-meter location in real time.",
                "differentiator": "Uses existing 5G and Wi-Fi networks.",
                "source_refs": [
                    {"label": "Company positioning deck", "source_class": "company"}
                ],
            },
            "metrics": [
                {
                    "label": "ARR",
                    "value": "$24M",
                    "as_of": "2026-06-13",
                    "source_class": "BSH diligence",
                    "source_refs": [
                        {
                            "label": "BSH diligence pack",
                            "source_class": "BSH primary diligence",
                        }
                    ],
                },
                {
                    "label": "TAM",
                    "value": "$45B",
                    "as_of": "2030",
                    "source_class": "third-party market data",
                    "source_refs": [
                        {
                            "label": "Market model",
                            "source_class": "third-party market data",
                        }
                    ],
                },
            ],
            "products": [
                {
                    "name": "Physical AI Platform",
                    "description": "Software layer for sub-meter 3D location.",
                }
            ],
            "team_profiles": [{"name": "Daniel Jacker", "role": "CEO"}],
            "board_investors": [{"name": "Future Ventures", "role": "Investor"}],
            "industry_view": {
                "metrics": [
                    {
                        "label": "5-year CAGR",
                        "value": "24%",
                        "source_class": "third-party market data",
                    }
                ],
                "sector_signals": [
                    {
                        "signal": "Standards evolve.",
                        "implication": "Claim-chart diligence remains required.",
                    }
                ],
            },
            "disclosures": [
                {
                    "label": "BSH position disclosure",
                    "body": "BSH may hold or seek a position.",
                }
            ],
        }
    ]
    with (data_root / "companies.yaml").open("w", encoding="utf-8") as f:
        yaml.safe_dump(companies, f, sort_keys=False)
    return data_root


def test_source_class_normalization():
    assert memo_editor_store.normalize_source_class("company") == "company material"
    assert memo_editor_store.normalize_source_class("BSH diligence") == "BSH primary diligence"
    assert memo_editor_store.normalize_source_class("third-party") == "third-party market data"
    assert memo_editor_store.normalize_source_class("") == "unknown/pending"


def test_memo_editor_state_persists_rank_edit_and_dive(memo_editor_env):
    state = memo_editor_store.get_state("zainar-test")
    assert state["sections"]["executive_summary"]["title"] == "Executive Summary"
    assert state["sections"]["appendix"]["blocks"][0]["expanded"] is False

    thesis_cards = state["sections"]["investment_thesis"]["cards"]
    first_id = thesis_cards[0]["id"]
    second_id = thesis_cards[1]["id"]

    moved = memo_editor_store.move_card(
        "zainar-test",
        "investment_thesis",
        first_id,
        "down",
    )
    moved_cards = moved["sections"]["investment_thesis"]["cards"]
    assert moved_cards[0]["id"] == second_id
    assert moved_cards[1]["id"] == first_id

    card = moved_cards[1]
    bullet_id = card["bullets"][0]["id"]
    edited = memo_editor_store.patch_bullet(
        "zainar-test",
        "investment_thesis",
        card["id"],
        bullet_id,
        {"text": "Edited source-backed point about existing networks."},
    )
    edited_bullet = edited["sections"]["investment_thesis"]["cards"][1]["bullets"][0]
    assert edited_bullet["text"] == "Edited source-backed point about existing networks."

    dived = memo_editor_store.add_dive_deeper(
        "zainar-test",
        "investment_thesis",
        card["id"],
        bullet_id,
    )
    children = dived["sections"]["investment_thesis"]["cards"][1]["bullets"][0]["children"]
    assert children
    assert "Dive deeper" in children[0]["text"]
    assert dived["memo_tasks"][0]["action_type"] == "dive_deeper"
    assert dived["memo_tasks"][0]["status"] == "completed"

    reloaded = memo_editor_store.get_state("zainar-test", create=False)
    assert reloaded["sections"]["investment_thesis"]["cards"][1]["bullets"][0]["children"]
    history = memo_editor_store.history("zainar-test")
    assert history["versions"]
    assert any(row["event"] == "memo_task_created" for row in history["audit_records"])

    rerun = memo_editor_store.request_section_rerun(
        "zainar-test",
        "investment_thesis",
    )
    assert rerun["sections"]["investment_thesis"]["last_rerun_status"] == "recorded"


def test_export_projection_blocks_unsupported_key_figures(memo_editor_env):
    state = memo_editor_store.get_state("zainar-test")
    card = state["sections"]["investment_thesis"]["cards"][0]
    bullet = card["bullets"][0]

    memo_editor_store.patch_bullet(
        "zainar-test",
        "investment_thesis",
        card["id"],
        bullet["id"],
        {
            "text": "ARR is $50M and growth is 150% without source coverage.",
            "source_class": "unknown/pending",
            "source_refs": [],
        },
    )

    projection = memo_editor_store.export_projection("zainar-test", record_attempt=True)
    assert projection["blocked"] is True
    assert projection["missing_sources"]
    assert projection["missing_sources"][0]["reason"].startswith("Key figure lacks")
    assert projection["source_coverage"]["missing_key_figure_count"] >= 1


def test_memo_editor_api_mutates_state_and_projects_export(memo_editor_env):
    client = TestClient(app)
    initial = client.get("/api/companies/zainar-test/memo-editor")
    assert initial.status_code == 200, initial.text
    body = initial.json()
    card = body["sections"]["investment_thesis"]["cards"][0]

    patch = client.patch(
        f"/api/companies/zainar-test/memo-editor/sections/investment_thesis/cards/{card['id']}",
        json={"included": False},
    )
    assert patch.status_code == 200, patch.text
    patched_card = patch.json()["sections"]["investment_thesis"]["cards"][0]
    assert patched_card["included"] is False

    projection = client.post("/api/companies/zainar-test/memo-editor/export-projection")
    assert projection.status_code == 200, projection.text
    projected = projection.json()
    assert "source_coverage" in projected
    assert projected["projection"]["sections"]["investment_thesis"][0]["id"] != card["id"]

    task = client.post(
        "/api/companies/zainar-test/memo-editor/tasks",
        json={
            "action_type": "discuss",
            "title": "Discuss revenue quality",
            "description": "Check ARR versus source package.",
            "context": {"section_id": "investment_thesis"},
        },
    )
    assert task.status_code == 201, task.text
    accepted = client.patch(
        f"/api/companies/zainar-test/memo-editor/tasks/{task.json()['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["status"] == "accepted"

    history = client.get("/api/companies/zainar-test/memo-editor/history")
    assert history.status_code == 200, history.text
    assert history.json()["versions"]
    assert any(row["event"] == "memo_task_updated" for row in history.json()["audit_records"])
