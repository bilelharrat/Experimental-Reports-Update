"""What leaves the firm: memo downloads, previews (PDF) and bundles.

Viewing stays open to every signed-in role; an explicit export
(``purpose=export``) needs memo:export and the internal memo needs
memo:edit. Every successful fetch is logged; exports also reach the audit
trail and the report detail. PDFs are made lazily and cached against the
docx they came from. Word is never launched here: every conversion is a
fake.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import threading
import time
import zipfile
from urllib.parse import unquote

import pytest
from fastapi.testclient import TestClient

from server import api, docx_pdf, firm, memo_pdf, memo_prep, report_access, storage
from server.main import app


@pytest.fixture
def env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    # Never reach real Word from a test: no converter unless a test says so.
    monkeypatch.setattr(docx_pdf, "converter_available", lambda: False)
    monkeypatch.setattr(
        docx_pdf,
        "convert_docx_to_pdf",
        lambda *_a, **_k: pytest.fail("conversion must be faked explicitly"),
    )
    memo_pdf._INFLIGHT.clear()
    memo_pdf._FAILURES.clear()
    report_access._recent_views.clear()
    return data_root


@pytest.fixture
def client():
    return TestClient(app)


def as_role(monkeypatch, role: str, email: str | None = None) -> None:
    monkeypatch.setattr(api, "_caller_role", lambda request: role)
    monkeypatch.setattr(api, "_caller_email", lambda request: email)


def make_memo(data_root, *, company_name="Occidental Petroleum Corp /De/", internal=False, status="complete"):
    run_id = "2026-08-25__002314"
    run_dir = data_root / "memos" / "oxy" / f"{run_id}__oxy__memo-run"
    memo_dir = run_dir / "memo"
    memo_dir.mkdir(parents=True)
    en = memo_dir / f"Occidental - Investment Memo - {run_id}.docx"
    zh = memo_dir / f"Occidental - 投资备忘录 - {run_id}.docx"
    en.write_bytes(b"PK-en")
    zh.write_bytes(b"PK-zh")
    extra = {}
    if internal:
        internal_docx = memo_dir / f"Occidental - Internal Diligence Memo - {run_id}.docx"
        internal_docx.write_bytes(b"PK-internal")
        extra["internal_memo_files"] = [
            {"kind": "internal_diligence_memo", "language": "en", "path": memo_prep._rel(internal_docx)}
        ]
    report = storage.create_report_record(
        company_id="oxy",
        company_name=company_name,
        report_type=memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind=memo_prep.LATESTAGE_KIND,
        status=status,
        run_id=run_id,
        run_dir=memo_prep._rel(run_dir),
        memo_files=[
            {"language": "en", "path": memo_prep._rel(en)},
            {"language": "zh", "path": memo_prep._rel(zh)},
        ],
        **extra,
    )
    return report, en, zh


def disposition_filename(response) -> str:
    header = response.headers["content-disposition"]
    if "filename*=utf-8''" in header:
        return unquote(header.split("filename*=utf-8''", 1)[1])
    return header.split('filename="', 1)[1].rstrip('"')


def access_rows() -> list[dict]:
    path = storage.DATA_DIR / "_api" / "report_access.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# ---- downloads --------------------------------------------------------------------


def test_viewing_is_open_logged_once_and_well_named(env, client, monkeypatch):
    as_role(monkeypatch, "research_ops", "ops@bshfoundation.org")
    report, _en, _zh = make_memo(env)
    r = client.get(f"/api/reports/{report['id']}/download?language=zh")
    assert r.status_code == 200, r.text
    assert r.content == b"PK-zh"
    assert disposition_filename(r) == (
        "BSH – Occidental Petroleum Corp – Investment Memo – 2026-08-25 (中文).docx"
    )
    # A viewer re-fetching the same document inside the window logs once.
    assert client.get(f"/api/reports/{report['id']}/download?language=zh").status_code == 200
    rows = access_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["purpose"] == "view"
    assert row["actor"] == "ops@bshfoundation.org"
    assert row["role"] == "research_ops"
    assert row["report_id"] == report["id"]
    assert row["run_id"] == "2026-08-25__002314"
    assert row["language"] == "zh"
    assert row["artifact"] == "memo"


def test_export_needs_memo_export_and_is_audited(env, client, monkeypatch):
    report, _en, _zh = make_memo(env)
    as_role(monkeypatch, "research_ops", "ops@bshfoundation.org")
    denied = client.get(f"/api/reports/{report['id']}/download?language=en&purpose=export")
    assert denied.status_code == 403
    as_role(monkeypatch, "analyst", "ana@bshventures.com")
    ok = client.get(f"/api/reports/{report['id']}/download?language=en&purpose=export")
    assert ok.status_code == 200
    exports = [r for r in access_rows() if r["purpose"] == "export"]
    assert len(exports) == 1 and exports[0]["actor"] == "ana@bshventures.com"
    audit = firm.list_audit()["items"]
    assert any(item["action"] == "export report" for item in audit)
    detail = client.get(f"/api/reports/{report['id']}").json()
    assert detail["recent_exports"][0]["actor"] == "ana@bshventures.com"
    assert detail["recent_exports"][0]["language"] == "en"


def test_internal_memo_needs_memo_edit(env, client, monkeypatch):
    report, _en, _zh = make_memo(env, internal=True)
    as_role(monkeypatch, "guest")
    assert client.get(f"/api/reports/{report['id']}/download?artifact=internal").status_code == 403
    as_role(monkeypatch, "research_ops", "ops@bshfoundation.org")
    ok = client.get(f"/api/reports/{report['id']}/download?artifact=internal")
    assert ok.status_code == 200
    assert "Internal Diligence Memo" in disposition_filename(ok)


def test_service_token_can_still_read(env, client, monkeypatch):
    report, _en, _zh = make_memo(env)
    monkeypatch.setenv("BSH_RESEARCH_API_TOKEN", "TOP-SECRET-123")
    monkeypatch.delenv("BSH_ALLOW_ANON_DEV", raising=False)
    headers = {"Authorization": "Bearer TOP-SECRET-123"}
    assert client.get(f"/api/reports/{report['id']}/download?language=en", headers=headers).status_code == 200
    export = client.get(
        f"/api/reports/{report['id']}/download?language=en&purpose=export", headers=headers
    )
    assert export.status_code == 403
    assert access_rows()[0]["actor"] == "service"


def test_display_name_strips_edgar_suffixes_and_path_characters():
    assert report_access.display_company_name("Occidental Petroleum Corp /De/") == "Occidental Petroleum Corp"
    assert report_access.display_company_name("Foo Holdings /NEW/") == "Foo Holdings"
    cleaned = report_access.display_company_name("A/B\\C:D\x07E")
    assert "/" not in cleaned and "\\" not in cleaned and "\x07" not in cleaned


# ---- PDFs -------------------------------------------------------------------------


def fake_converter(monkeypatch, calls: list):
    monkeypatch.setattr(docx_pdf, "converter_available", lambda: True)

    def convert(src, dst):
        calls.append((src.name, dst.name))
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"%PDF-1.4 " + src.read_bytes())
        return True, None

    monkeypatch.setattr(docx_pdf, "convert_docx_to_pdf", convert)


def test_preview_makes_the_pdf_once_and_remakes_it_for_a_new_docx(env, client, monkeypatch):
    calls: list = []
    fake_converter(monkeypatch, calls)
    report, en, _zh = make_memo(env)
    first = client.get(f"/api/reports/{report['id']}/preview?language=en")
    assert first.status_code == 200, first.text
    assert first.headers["content-type"] == "application/pdf"
    assert first.headers["content-disposition"].startswith("inline")
    assert disposition_filename(first).endswith("(EN).pdf")
    assert first.content == b"%PDF-1.4 PK-en"
    assert client.get(f"/api/reports/{report['id']}/preview?language=en").status_code == 200
    assert len(calls) == 1
    row = next(r for r in client.get("/api/reports").json() if r["id"] == report["id"])
    assert row["pdf_status"] == {"en": "ready", "zh": "pending"}
    # A re-rendered docx gets a new PDF, and the stale one is pruned.
    time.sleep(0.01)
    en.write_bytes(b"PK-en-v2")
    os.utime(en, None)
    second = client.get(f"/api/reports/{report['id']}/preview?language=en")
    assert second.content == b"%PDF-1.4 PK-en-v2"
    assert len(calls) == 2
    cached = list((en.parent / "_pdf").iterdir())
    assert len([p for p in cached if p.name.startswith(en.stem)]) == 1


def test_preview_without_a_converter_is_a_404_and_the_docx_still_serves(env, client):
    report, _en, _zh = make_memo(env)
    r = client.get(f"/api/reports/{report['id']}/preview?language=en")
    assert r.status_code == 404
    assert "No en PDF preview is available" in r.json()["detail"]
    assert client.get(f"/api/reports/{report['id']}/download?language=en").status_code == 200
    row = next(r for r in client.get("/api/reports").json() if r["id"] == report["id"])
    assert row["pdf_status"] == {"en": "unavailable", "zh": "unavailable"}
    assert row["preview_urls"]["en"].endswith("preview?language=en")


def test_preview_waits_for_a_conversion_already_running(env, monkeypatch):
    report, en, _zh = make_memo(env)
    monkeypatch.setattr(docx_pdf, "converter_available", lambda: True)
    started = threading.Event()
    release = threading.Event()

    def slow_convert(src, dst):
        started.set()
        release.wait(5)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b"%PDF")
        return True, None

    monkeypatch.setattr(docx_pdf, "convert_docx_to_pdf", slow_convert)
    results: dict = {}
    owner = threading.Thread(target=lambda: results.update(owner=memo_pdf.get_or_create(report, "en")))
    owner.start()
    assert started.wait(5)
    assert memo_pdf.status(report, "en") == "building"
    # A second caller that gives up quickly is told it is still building.
    assert memo_pdf.get_or_create(report, "en", wait_seconds=0.05) == (None, "building")
    release.set()
    owner.join(5)
    assert results["owner"][0] is not None and results["owner"][1] is None


def test_failed_conversion_backs_off(env, monkeypatch):
    report, _en, _zh = make_memo(env)
    monkeypatch.setattr(docx_pdf, "converter_available", lambda: True)
    calls = []

    def failing(src, dst):
        calls.append(src)
        return False, "Word conversion failed: permission denied"

    monkeypatch.setattr(docx_pdf, "convert_docx_to_pdf", failing)
    assert memo_pdf.get_or_create(report, "en") == (None, "Word conversion failed: permission denied")
    assert memo_pdf.get_or_create(report, "en")[1] == "Word conversion failed: permission denied"
    assert len(calls) == 1
    assert memo_pdf.status(report, "en") == "failed"


def test_schedule_pdf_runs_in_the_background_only_when_enabled(env, monkeypatch):
    calls: list = []
    fake_converter(monkeypatch, calls)
    report, en, _zh = make_memo(env)
    # Under pytest the background job is off unless a test opts in.
    assert memo_pdf.schedule_pdf(report["id"]) is None
    monkeypatch.setenv("BSH_MEMO_PDF_BACKGROUND", "1")
    thread = memo_pdf.schedule_pdf(report["id"])
    assert thread is not None
    thread.join(5)
    assert sorted(name for name, _ in calls) == sorted([en.name, en.name.replace("Investment Memo", "投资备忘录")])
    assert memo_pdf.status(storage.get_report(report["id"]), "zh") == "ready"


def test_bundle_zips_both_languages_as_an_export(env, client, monkeypatch):
    report, _en, _zh = make_memo(env)
    as_role(monkeypatch, "research_ops", "ops@bshfoundation.org")
    assert client.get(f"/api/reports/{report['id']}/bundle").status_code == 403
    as_role(monkeypatch, "partner", "seline.sun@bshfoundation.org")
    r = client.get(f"/api/reports/{report['id']}/bundle")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    assert disposition_filename(r).endswith("(EN + 中文).zip")
    names = sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert names == [
        "BSH – Occidental Petroleum Corp – Investment Memo – 2026-08-25 (EN).docx",
        "BSH – Occidental Petroleum Corp – Investment Memo – 2026-08-25 (中文).docx",
    ]
    assert access_rows()[-1]["artifact"] == "bundle"
    assert access_rows()[-1]["purpose"] == "export"


def test_bundle_with_pdfs(env, client, monkeypatch):
    calls: list = []
    fake_converter(monkeypatch, calls)
    report, _en, _zh = make_memo(env)
    r = client.get(f"/api/reports/{report['id']}/bundle?format=all")
    names = sorted(zipfile.ZipFile(io.BytesIO(r.content)).namelist())
    assert len(names) == 4 and sum(n.endswith(".pdf") for n in names) == 2
    assert client.get(f"/api/reports/{report['id']}/bundle?format=odt").status_code == 400


# ---- docx_pdf: one conversion at a time, LibreOffice as the fallback ----------------


def test_conversion_lock_turns_away_a_caller_that_waits_too_long(tmp_path, monkeypatch):
    src = tmp_path / "a.docx"
    src.write_bytes(b"PK")
    monkeypatch.setattr(docx_pdf, "LOCK_WAIT_SECONDS", 0.05)
    monkeypatch.setattr(
        docx_pdf, "_convert_with_word", lambda *_a: pytest.fail("must not convert while locked")
    )
    assert docx_pdf._CONVERSION_LOCK.acquire(timeout=1)
    try:
        ok, error = docx_pdf.convert_docx_to_pdf(src, tmp_path / "a.pdf")
    finally:
        docx_pdf._CONVERSION_LOCK.release()
    assert ok is False and "still running" in error


def test_soffice_is_tried_when_word_fails(tmp_path, monkeypatch):
    src = tmp_path / "memo.docx"
    src.write_bytes(b"PK")
    dst = tmp_path / "out" / "memo.pdf"
    monkeypatch.setattr(docx_pdf, "_convert_with_word", lambda s, d: (False, "Word conversion failed: x"))
    monkeypatch.setattr(docx_pdf, "soffice_path", lambda: "/opt/soffice")
    seen = {}

    def fake_run(args, **kwargs):
        from pathlib import Path

        seen["args"] = args
        out_dir = args[args.index("--outdir") + 1]
        Path(out_dir, "memo.pdf").write_bytes(b"%PDF-soffice")
        return subprocess.CompletedProcess(args, 0, b"", b"")

    monkeypatch.setattr(docx_pdf.subprocess, "run", fake_run)
    ok, error = docx_pdf.convert_docx_to_pdf(src, dst)
    assert ok is True and error is None
    assert dst.read_bytes() == b"%PDF-soffice"
    assert seen["args"][:4] == ["/opt/soffice", "--headless", "--convert-to", "pdf"]


def test_no_converter_reports_the_word_error(tmp_path, monkeypatch):
    src = tmp_path / "memo.docx"
    src.write_bytes(b"PK")
    monkeypatch.setattr(docx_pdf, "_convert_with_word", lambda s, d: (False, "Word conversion failed: denied"))
    monkeypatch.setattr(docx_pdf, "soffice_path", lambda: None)
    ok, error = docx_pdf.convert_docx_to_pdf(src, tmp_path / "memo.pdf")
    assert ok is False
    assert error in ("Word conversion failed: denied",) or "macOS-only" in error
    assert not (tmp_path / "memo.pdf").exists()
