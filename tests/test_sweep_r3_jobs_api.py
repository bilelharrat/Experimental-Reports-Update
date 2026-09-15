"""Round-3 job sweep (API): a failed company search ends as an error, a red-team rerun
never shows the previous run's error, non-deck uploads are refused by the summary
route, audit rows and the mentions inbox tell the service token and anonymous
probes apart, desk prefs keys the server reads are validated, startup does not
wait for the recovery sweeps, the report list has a lite form, and oversized
comment / chat / transcript bodies are rejected instead of truncated."""
from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from server import api, desk_store, files_store, firm, job_history, red_team, storage, transcripts
from server import main as server_main
from server.main import app

TOKEN = "TOP-SECRET-123"


@pytest.fixture
def client():
    return TestClient(app)


def _seed() -> None:
    storage._write_yaml(storage.COMPANIES_FILE, [
        {"id": "acme-ai", "name": "Acme AI", "status": "private", "company_type": "private"},
    ])


def _jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- F4: company search ----------------------------------------------------------------------


def test_search_that_falls_back_ends_as_an_error_with_the_reason(monkeypatch):
    reason = "claude search stalled after 120s without output"
    local = [{"id": "acme-ai", "name": "Acme AI"}]
    monkeypatch.setattr(
        api.companies_ai,
        "deep_search",
        lambda q, **kw: {"source": "fallback", "reason": reason, "matches": local, "cached_at": None},
    )
    job_id = api._search_job_id("acme stalled")

    api._run_search_job(job_id, "acme stalled", True)

    last = _jsonl(api._search_progress_path(job_id))[-1]
    assert (last["type"], last["error"], last["matches"]) == ("error", reason, local)
    row = _jsonl(job_history._history_file())[-1]
    assert (row["kind"], row["terminal_type"], row["error"]) == ("search", "error", reason)


def test_search_that_completes_still_ends_done(monkeypatch):
    monkeypatch.setattr(
        api.companies_ai,
        "deep_search",
        lambda q, **kw: {"source": "claude_code", "matches": [], "cached_at": "2026-09-14T00:00:00Z"},
    )
    job_id = api._search_job_id("acme ok")

    api._run_search_job(job_id, "acme ok", True)

    assert _jsonl(api._search_progress_path(job_id))[-1]["type"] == "done"


# ---- F6: red team ----------------------------------------------------------------------------

RED_TEAM_RESULT = {
    "counter_thesis": "The wedge is a feature.",
    "kill_risks": [],
    "questionable_assumptions": [],
    "what_would_change_my_mind": [],
    "pre_mortem": "Bundled away.",
    "questions_for_founders": [],
}


def test_red_team_rerun_does_not_show_the_previous_error_while_running(client):
    _seed()
    red_team.run("acme-ai", runner=lambda *_a: (None, "claude exited 1: boom"))
    assert client.get("/api/companies/acme-ai/ic/red-team").json()["error"] == "claude exited 1: boom"
    seen: dict = {}

    def runner(*_a):
        seen.update(client.get("/api/companies/acme-ai/ic/red-team").json())
        return RED_TEAM_RESULT, None

    assert red_team.run("acme-ai", runner=runner)["status"] == "done"
    assert (seen["status"], seen["error"], seen["result"]) == ("running", None, None)
    final = client.get("/api/companies/acme-ai/ic/red-team").json()
    assert (final["status"], final["error"]) == ("done", None)


def test_red_team_crash_is_recorded_as_an_error(client):
    _seed()

    def runner(*_a):
        raise RuntimeError("runner exploded")

    payload = red_team.run("acme-ai", runner=runner)

    assert payload["status"] == "error"
    assert "runner exploded" in payload["error"]
    assert client.get("/api/companies/acme-ai/ic/red-team").json()["status"] == "error"


# ---- F7: summary route -----------------------------------------------------------------------


def test_summary_of_a_markdown_upload_is_rejected_with_the_supported_types(client, monkeypatch):
    _seed()
    record = files_store.upload_file("acme-ai", filename="notes.md", content_type="text/markdown", data=b"# Notes\n")
    monkeypatch.setattr(api, "_run_summary_job", lambda *a, **k: pytest.fail("summary job must not start"))

    r = client.post(f"/api/companies/acme-ai/files/{record['id']}/summary")

    assert r.status_code == 400
    assert r.json()["detail"] == "Summaries support PDF, PPTX and PPT files only; .md files can't be summarized."


# ---- R2: audit attribution -------------------------------------------------------------------


def test_audit_names_the_service_token_and_anonymous_probes(client, monkeypatch):
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", TOKEN)
    monkeypatch.delenv("BSH_ALLOW_ANON_DEV", raising=False)

    service = client.post("/api/chat/general", json={"text": "hi"}, headers={"Authorization": f"Bearer {TOKEN}"})
    anonymous = client.post("/api/chat/general", json={"text": "hi"})

    assert (service.status_code, anonymous.status_code) == (403, 401)
    rows = firm.list_audit()["items"]
    assert [(row["actor"], row["status"]) for row in rows[:2]] == [("anonymous", 401), ("service", 403)]


def test_audit_keeps_anon_dev_attribution(client):
    client.post("/api/chat/general", json={"text": "hi"})
    assert firm.list_audit()["items"][0]["actor"] == "anon-dev"


def test_service_token_reads_its_own_mentions_inbox(client, monkeypatch):
    firm.post_message("general", text="@dev ping", author="ana@firm.com")
    firm.post_message("general", text="@service ping", author="ana@firm.com")
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", TOKEN)
    monkeypatch.delenv("BSH_ALLOW_ANON_DEV", raising=False)

    inbox = client.get("/api/me/mentions", headers={"Authorization": f"Bearer {TOKEN}"}).json()

    assert inbox["handle"] == "service"
    assert [item["text"] for item in inbox["items"]] == ["@service ping"]


# ---- R3: desk prefs validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("data", "detail"),
    [
        ({"bsh.bookLots": [{"ticker": "NVDA", "shares": "10", "cost": 100}]}, "bsh.bookLots[0].shares must be a finite number >= 0"),
        ({"bsh.bookLots": [{"ticker": "NVDA", "shares": True, "cost": 100}]}, "bsh.bookLots[0].shares must be a finite number >= 0"),
        ({"bsh.bookLots": [{"ticker": "NVDA", "shares": 10, "cost": -1}]}, "bsh.bookLots[0].cost must be a finite number >= 0"),
        ({"bsh.bookLots": [{"ticker": "NVDA", "shares": 10}]}, "bsh.bookLots[0] needs cost"),
        ({"bsh.bookLots": {"ticker": "NVDA"}}, "bsh.bookLots must be a list"),
        (
            {"bsh.marketAlertRules": [{"ticker": "NVDA", "kind": "price", "threshold": "high"}]},
            "bsh.marketAlertRules[0].threshold must be a finite number",
        ),
        (
            {"bsh.marketAlertRules": [{"ticker": "NVDA", "kind": "moon", "threshold": 1}]},
            "bsh.marketAlertRules[0].kind must be one of pct, earnings, volume, price, sma_cross",
        ),
        (
            {"bsh.marketAlertRules": [{"ticker": "NVDA", "kind": "price", "threshold": 1, "direction": "sideways"}]},
            "bsh.marketAlertRules[0].direction must be one of above, below",
        ),
        (
            {"bsh.marketPinnedTickers": ["NVDA", "not a ticker"]},
            "bsh.marketPinnedTickers[1] must be an upper-case ticker symbol (letters, digits, '.' or '-')",
        ),
        ({"bsh.marketPinnedTickers": [7]}, "bsh.marketPinnedTickers[0] must be an upper-case ticker symbol (letters, digits, '.' or '-')"),
    ],
)
def test_desk_prefs_reject_invalid_values_for_the_keys_the_server_reads(client, data, detail):
    r = client.put("/api/desk/prefs", json={"data": data})

    assert r.status_code == 400
    assert r.json()["detail"] == detail
    assert client.get("/api/desk/prefs").json()["data"] == {}


def test_desk_prefs_reject_non_finite_numbers():
    with pytest.raises(ValueError, match="threshold must be a finite number"):
        desk_store.save_prefs({"bsh.marketAlertRules": [{"ticker": "NVDA", "kind": "pct", "threshold": float("inf")}]})
    with pytest.raises(ValueError, match="shares must be a finite number"):
        desk_store.save_prefs({"bsh.bookLots": [{"ticker": "NVDA", "shares": float("nan"), "cost": 1}]})


def test_desk_prefs_accept_web_and_mac_shapes_and_leave_other_keys_alone(client):
    data = {
        "bsh.bookLots": [
            {"ticker": "NVDA", "companyId": None, "shares": 10, "cost": 101.5},
            {"id": "L1", "ticker": "BRK.B", "shares": 2.5, "qty": 2.5, "costBasis": 0, "cost": 0},
        ],
        "bsh.marketAlertRules": [
            {"id": "r1", "ticker": "NVDA", "kind": "price", "threshold": 100, "window": None, "direction": "below", "enabled": True},
            {"id": "r2", "ticker": "TSM", "kind": "sma_cross", "threshold": 50, "window": 50, "direction": "above"},
        ],
        "bsh.marketPinnedTickers": ["NVDA", "BRK-B", "0700.HK"],
        "bsh.marketTickerNotes": {"NVDA": {"anything": [1, "two", None]}},
        "bsh.marketChartPrefs": "not validated",
    }

    r = client.put("/api/desk/prefs", json={"data": data})

    assert r.status_code == 200, r.text
    assert client.get("/api/desk/prefs").json()["data"] == data


# ---- S4b: startup ----------------------------------------------------------------------------


def test_startup_does_not_wait_for_the_recovery_sweeps(monkeypatch):
    from server import alert_engine, tracking_updates

    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def slow_memo_recovery():
        started.set()
        release.wait(10)
        calls.append("memo-recovery")
        return 0

    def noop(*_a, **_k):
        return None

    monkeypatch.setattr(server_main.local_generation, "generate_local_runtime_state", lambda: {})
    monkeypatch.setattr(server_main.claude_runner, "is_available", lambda: False)
    monkeypatch.setattr(server_main.console_session, "recover", noop)
    monkeypatch.setattr(server_main.memo_analysis, "recover_stale_reports", slow_memo_recovery)
    monkeypatch.setattr(server_main.buffett_memo_analysis, "recover_stale_reports", lambda: 0)
    monkeypatch.setattr(server_main, "resume_interrupted_memo_runs", lambda: calls.append("auto-resume") or 0)
    monkeypatch.setattr(server_main, "resume_regen_all_if_needed", lambda: False)
    monkeypatch.setattr(server_main, "start_stale_job_recovery", lambda: calls.append("stale-jobs"))
    monkeypatch.setattr(tracking_updates, "start_tracking_sync_loop", noop)
    monkeypatch.setattr(alert_engine, "start_background_engine", lambda: False)
    monkeypatch.setattr(server_main.companies_autocomplete, "prewarm_indexes", noop)
    monkeypatch.setattr(server_main, "migrate_trader_snapshots", lambda **_k: 0)
    monkeypatch.setattr(server_main.company_paths, "migrate_legacy_dirs", lambda: [])
    monkeypatch.setattr(server_main, "_start_translation_backfill", noop)

    t0 = time.monotonic()
    server_main._startup()
    elapsed = time.monotonic() - t0

    assert started.wait(5)
    assert elapsed < 5
    assert calls == []
    release.set()
    for thread in [t for t in threading.enumerate() if t.name == "startup-recovery"]:
        thread.join(10)
    assert calls == ["memo-recovery", "auto-resume", "stale-jobs"]


# ---- S5: report list -------------------------------------------------------------------------


def test_report_list_lite_blanks_the_heavy_per_report_blobs(client):
    _seed()
    storage.create_report_record(
        company_id="acme-ai",
        company_name="Acme AI",
        report_type="Investment Memo (Late-Stage)",
        audience="Internal",
        language="en",
        kind="investment_memo_latestage",
        status="complete",
        renderer_contract={"errors": ["x" * 2000]},
        memo_quality_lint={"overall_score": 88},
        memo_chinese_parity={"ok": True, "notes": ["y" * 2000]},
        memo_files=[{"language": "en", "path": "data/memos/none.docx"}],
    )

    full = client.get("/api/reports").json()[0]
    lite = client.get("/api/reports?lite=1").json()[0]

    assert full["memo_quality_lint"] == {"overall_score": 88}
    assert full["renderer_contract"] and full["memo_chinese_parity"] and full["memo_files"]
    assert {field: lite[field] for field in api._REPORT_LIST_HEAVY_FIELDS} == {
        "renderer_contract": None,
        "memo_files": [],
        "memo_chinese_parity": None,
        "memo_quality_lint": None,
    }
    assert (lite["id"], lite["status"]) == (full["id"], "complete")
    assert len(json.dumps(lite)) < len(json.dumps(full)) - 4000


# ---- S6: oversized bodies --------------------------------------------------------------------


def test_oversized_comment_chat_and_transcript_bodies_are_rejected(client):
    _seed()
    too_long_comment = client.post("/api/companies/acme-ai/comments", json={"text": "x" * (firm.COMMENT_MAX_CHARS + 1)})
    assert (too_long_comment.status_code, too_long_comment.json()["detail"]) == (
        400,
        f"Comment is too long, max {firm.COMMENT_MAX_CHARS} characters",
    )
    at_limit = client.post("/api/companies/acme-ai/comments", json={"text": "x" * firm.COMMENT_MAX_CHARS})
    assert at_limit.status_code == 200
    assert len(at_limit.json()["text"]) == firm.COMMENT_MAX_CHARS

    too_long_message = client.post("/api/chat/general", json={"text": "y" * (firm.CHAT_MESSAGE_MAX_CHARS + 1)})
    assert (too_long_message.status_code, too_long_message.json()["detail"]) == (
        400,
        f"Message is too long, max {firm.CHAT_MESSAGE_MAX_CHARS} characters",
    )

    transcript_detail = f"Transcript text is too long, max {transcripts.TRANSCRIPT_MAX_CHARS} characters"
    body = "Expert: " + "z" * transcripts.TRANSCRIPT_MAX_CHARS
    pasted = client.post("/api/transcripts", json={"title": "Call", "text": body})
    assert (pasted.status_code, pasted.json()["detail"]) == (400, transcript_detail)
    uploaded = client.post("/api/transcripts/upload", files={"file": ("call.txt", body.encode(), "text/plain")})
    assert (uploaded.status_code, uploaded.json()["detail"]) == (400, transcript_detail)

    assert firm.all_messages() == []
    assert transcripts.all_transcripts() == []
