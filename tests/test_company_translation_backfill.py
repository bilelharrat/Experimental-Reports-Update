from __future__ import annotations

import json

from server import claude_runner
from server import company_translate
from server import main as server_main


def test_structured_prompt_error_includes_stdout(monkeypatch):
    class Completed:
        returncode = 1
        stderr = ""
        stdout = "You've hit your session limit · resets 2am (America/Los_Angeles)"

    def fake_run(*args, **kwargs):
        return Completed()

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)

    data, err = claude_runner.run_structured_prompt(
        system_prompt="Return JSON.",
        user_prompt="Translate this.",
        schema={"type": "object", "properties": {}, "required": []},
        name="company_translation",
    )

    assert data is None
    assert err is not None
    assert "claude exited 1" in err
    assert "session limit" in err


def test_structured_prompt_error_extracts_json_stdout(monkeypatch):
    class Completed:
        returncode = 1
        stderr = ""
        stdout = json.dumps({
            "result": (
                "You've hit your session limit · resets 2am "
                "(America/Los_Angeles)"
            ),
            "stop_reason": "stop_sequence",
            "session_id": "mock-session",
        })

    def fake_run(*args, **kwargs):
        return Completed()

    monkeypatch.setattr(claude_runner, "is_available", lambda: True)
    monkeypatch.setattr(claude_runner, "claude_path", lambda: "claude")
    monkeypatch.setattr(claude_runner.subprocess, "run", fake_run)

    data, err = claude_runner.run_structured_prompt(
        system_prompt="Return JSON.",
        user_prompt="Translate this.",
        schema={"type": "object", "properties": {}, "required": []},
        name="company_translation",
    )

    assert data is None
    assert err == (
        "claude exited 1: You've hit your session limit · resets 2am "
        "(America/Los_Angeles)"
    )
    assert "stop_reason" not in err
    assert "session_id" not in err


def test_translate_company_does_not_warn_on_provider_limit(monkeypatch, caplog):
    def fake_run_structured_prompt(**kwargs):
        return None, "claude exited 1: You've hit your session limit"

    monkeypatch.setattr(
        claude_runner, "run_structured_prompt", fake_run_structured_prompt
    )
    caplog.set_level("WARNING")

    result = company_translate.translate_company({"name": "AMD"})

    assert result["translation"] is None
    assert not any(
        "Company translation failed" in record.getMessage()
        for record in caplog.records
    )


def test_translation_backfill_pauses_on_usage_limit(monkeypatch):
    companies = [
        {"id": "amd", "name": "AMD", "description": "Chip company"},
        {"id": "amzn", "name": "Amazon", "description": "Retail and cloud"},
    ]
    translated: list[str] = []
    updates: list[tuple[str, dict]] = []

    def fake_translate(company):
        translated.append(company["id"])
        return {
            "language": "other",
            "translation": None,
            "error": "claude exited 1",
        }

    def fake_update(company_id, **patch):
        updates.append((company_id, patch))
        return {"id": company_id, **patch}

    monkeypatch.setattr(server_main, "list_companies", lambda: list(companies))
    monkeypatch.setattr(server_main, "translate_company", fake_translate)
    monkeypatch.setattr(server_main, "update_company", fake_update)

    server_main._run_translation_backfill_once()

    assert translated == ["amd"]
    assert updates == []


def test_translation_backfill_continues_after_non_limit_error(monkeypatch):
    companies = [
        {"id": "amd", "name": "AMD", "description": "Chip company"},
        {"id": "amzn", "name": "Amazon", "description": "Retail and cloud"},
    ]
    translated: list[str] = []
    updates: list[tuple[str, dict]] = []

    def fake_translate(company):
        translated.append(company["id"])
        if company["id"] == "amd":
            return {
                "language": "other",
                "translation": None,
                "error": "claude output didn't parse as JSON",
            }
        return {
            "language": "en",
            "translation": {
                "language": "zh",
                "description": f"ZH {company['description']}",
            },
        }

    def fake_update(company_id, **patch):
        updates.append((company_id, patch))
        return {"id": company_id, **patch}

    monkeypatch.setattr(server_main, "list_companies", lambda: list(companies))
    monkeypatch.setattr(server_main, "translate_company", fake_translate)
    monkeypatch.setattr(server_main, "update_company", fake_update)

    server_main._run_translation_backfill_once()

    assert translated == ["amd", "amzn"]
    assert [company_id for company_id, _ in updates] == ["amd", "amzn"]
