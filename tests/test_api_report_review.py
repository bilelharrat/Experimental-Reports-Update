"""Review step, deterministic re-render, comments and reader flags, and
reader telemetry on reports.

Renderers are faked: these tests exercise the orchestration (permissions,
state, backups, ink guard, rollback, feature detection), not the layout.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from server import (
    analytics_store,
    annotation_store,
    api,
    buffett_memo_renderer,
    docx_pdf,
    firm,
    memo_analysis,
    memo_docx_renderer,
    memo_prep,
    report_rerender,
    storage,
)
from server.main import app


@pytest.fixture
def env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    monkeypatch.setattr(docx_pdf, "converter_available", lambda: False)
    return data_root


@pytest.fixture
def client():
    return TestClient(app)


def as_role(monkeypatch, role: str, email: str | None = None) -> None:
    monkeypatch.setattr(api, "_caller_role", lambda request: role)
    monkeypatch.setattr(api, "_caller_email", lambda request: email)


PACKAGE = {
    "schema_version": 1,
    "company": {"name": "Acme"},
    "run": {"run_id": "2026-09-01__120000", "as_of": "2026-09-01"},
    "sections": [
        {
            "id": "investment_decision",
            "blocks": [{"type": "paragraph", "text": {"en": "We pass. More.", "zh": "我们放弃。其余。"}}],
        }
    ],
    "sources": [],
}


def make_memo(data_root, *, kind=memo_prep.LATESTAGE_KIND, company_id="acme", status="complete"):
    buffett = kind == memo_prep.BUFFETT_KIND
    run_id = "2026-09-01__120000"
    run_dir = data_root / "memos" / company_id / f"{run_id}__{company_id}__{'buffett-memo-run' if buffett else 'memo-run'}"
    (run_dir / "memo").mkdir(parents=True)
    (run_dir / "logs").mkdir()
    en = run_dir / "memo" / f"Acme - Investment Memo - {run_id}.docx"
    zh = run_dir / "memo" / f"Acme - 投资备忘录 - {run_id}.docx"
    en.write_bytes(b"old-en")
    zh.write_bytes(b"old-zh")
    package = dict(PACKAGE)
    if buffett:
        package = {
            "schema_version": 1,
            "kind": memo_prep.BUFFETT_KIND,
            "company_name": "Acme",
            "decision": "Pass",
            "buy_price": "Below $40",
            "markdown_en": "# Memo\n\n## I. Investment Decision\n\n**Pass.** Not at this price.\n",
            "markdown_zh": "# 备忘录\n\n## 一、投资决策\n\n**放弃。** 此价格不买。\n",
        }
        (run_dir / "memo" / "buffett_memo.en.md").write_text("old md", encoding="utf-8")
    else:
        for name in ("validation.txt", "validation_cn.txt", "file_inventory.md", "run_manifest.md"):
            (run_dir / "logs" / name).write_text(f"old {name}", encoding="utf-8")
    (run_dir / "logs" / "memo_package.json").write_text(json.dumps(package), encoding="utf-8")
    report = storage.create_report_record(
        company_id=company_id,
        company_name="Acme",
        report_type=memo_prep.BUFFETT_REPORT_TYPE if buffett else memo_prep.REPORT_TYPE,
        audience="Internal",
        language="en",
        kind=kind,
        status=status,
        run_id=run_id,
        run_dir=memo_prep._rel(run_dir),
        memo_files=[
            {"language": "en", "path": memo_prep._rel(en)},
            {"language": "zh", "path": memo_prep._rel(zh)},
        ],
        **({"decision": "Pass"} if buffett else {}),
    )
    return report, run_dir, en, zh


def install_late_renderer(monkeypatch, calls: list, *, with_review: bool = True, fail: bool = False):
    if with_review:

        def render_memos(package, *, out_en, out_zh, validation_en=None, validation_zh=None,
                         inventory_path=None, manifest_path=None, strict_sources=True, review=None):
            calls.append({"package": package, "review": review, "strict_sources": strict_sources})
            if fail:
                raise RuntimeError("renderer exploded")
            stamp = json.dumps(package.get("run", {}).get("review"))
            out_en.write_bytes(b"new-en " + stamp.encode())
            out_zh.write_bytes(b"new-zh " + stamp.encode())
            return {"ok": True}

    else:

        def render_memos(package, *, out_en, out_zh, validation_en=None, validation_zh=None,
                         inventory_path=None, manifest_path=None):
            calls.append({"package": package})
            out_en.write_bytes(b"unstamped-en")
            out_zh.write_bytes(b"unstamped-zh")
            return {"ok": True}

    monkeypatch.setattr(memo_docx_renderer, "render_memos", render_memos)
    # A declared flag is taken at its word, whatever else the module has.
    monkeypatch.setattr(memo_docx_renderer, "SUPPORTS_REVIEW_STAMP", with_review, raising=False)


# ---- review permissions and states -------------------------------------------------


def test_analyst_may_only_ask_for_review(env, client, monkeypatch):
    report, *_ = make_memo(env)
    as_role(monkeypatch, "analyst", "ana@bshventures.com")
    asked = client.patch(f"/api/reports/{report['id']}/review", json={"state": "in_review"})
    assert asked.status_code == 200, asked.text
    assert asked.json()["review_state"] == "in_review"
    denied = client.patch(f"/api/reports/{report['id']}/review", json={"state": "approved"})
    assert denied.status_code == 403
    as_role(monkeypatch, "guest")
    assert client.patch(f"/api/reports/{report['id']}/review", json={"state": "in_review"}).status_code == 403


def test_review_state_defaults_to_draft_on_old_records(env, client):
    report, *_ = make_memo(env)
    row = next(r for r in client.get("/api/reports").json() if r["id"] == report["id"])
    assert row["review_state"] == "draft"
    assert row["reviewer"] is None


def test_partner_approval_rerenders_with_the_stamp(env, client, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls)
    report, run_dir, en, zh = make_memo(env)
    as_role(monkeypatch, "partner", "seline.sun@bshfoundation.org")
    r = client.patch(
        f"/api/reports/{report['id']}/review",
        json={"state": "approved", "note": "Numbers checked"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["review_state"] == "approved"
    assert body["reviewer"] == "seline.sun@bshfoundation.org"
    assert body["reviewer_name"] == "Seline Sun"
    assert body["review_note"] == "Numbers checked"
    assert len(body["approved_revision"]) == 12
    assert body["rerender"]["status"] == "rendered"
    assert body["review_render_status"] == "rendered"
    assert body["review_history"][-1]["from"] == "draft" and body["review_history"][-1]["to"] == "approved"
    # The renderer got the review on an in-memory copy of the package.
    review = calls[0]["package"]["run"]["review"]
    assert review["state"] == "approved" and review["reviewer"] == "Seline Sun"
    assert calls[0]["review"]["state"] == "approved"
    assert calls[0]["strict_sources"] is False
    stored = json.loads((run_dir / "logs" / "memo_package.json").read_text(encoding="utf-8"))
    assert "review" not in stored["run"]
    # New documents in place, the old pair and logs kept in memo/_prev/.
    assert en.read_bytes().startswith(b"new-en")
    prev = next((run_dir / "memo" / "_prev").iterdir())
    assert (prev / en.name).read_bytes() == b"old-en"
    assert (prev / zh.name).read_bytes() == b"old-zh"
    assert (prev / "logs" / "run_manifest.md").read_text(encoding="utf-8") == "old run_manifest.md"
    record = storage.get_report(report["id"])
    assert record["rendered_at"] and record["renderer_version"]
    audit = firm.list_audit()["items"]
    assert any(item["action"] == "review report: approved" for item in audit)


def test_rerender_is_skipped_when_the_renderer_cannot_stamp(env, client, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls, with_review=False)
    report, _run_dir, en, _zh = make_memo(env)
    as_role(monkeypatch, "admin", "benma@bshventures.com")
    body = client.patch(f"/api/reports/{report['id']}/review", json={"state": "approved"}).json()
    assert body["review_state"] == "approved"
    assert body["rerender"]["status"] == "skipped"
    assert body["review_render_status"] == "skipped"
    assert calls == []
    assert en.read_bytes() == b"old-en"


def test_ink_blocks_the_rerender_unless_forced(env, client, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls)
    report, run_dir, *_ = make_memo(env)
    annotation_store.save(
        "reader@bshventures.com",
        report["id"],
        drawing_pk_base64=base64.b64encode(b"ink").decode("ascii"),
    )
    as_role(monkeypatch, "partner", "seline.sun@bshfoundation.org")
    refused = client.patch(f"/api/reports/{report['id']}/review", json={"state": "approved"})
    assert refused.status_code == 409
    assert "ink" in refused.json()["detail"]
    assert storage.get_report(report["id"]).get("review_state") in (None, "draft")
    forced = client.patch(
        f"/api/reports/{report['id']}/review", json={"state": "approved", "force": True}
    )
    assert forced.status_code == 200, forced.text
    moved = forced.json()["rerender"]["moved_ink"]
    assert len(moved) == 1
    assert report_rerender.ink_annotations(report["id"]) == []


def test_a_failed_render_restores_the_old_documents(env, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls, fail=True)
    report, run_dir, en, zh = make_memo(env)
    result = report_rerender.rerender_report(report["id"], review={"state": "approved"})
    assert result["status"] == "failed"
    assert "renderer exploded" in result["error"]
    assert en.read_bytes() == b"old-en" and zh.read_bytes() == b"old-zh"
    assert (run_dir / "logs" / "validation.txt").read_text(encoding="utf-8") == "old validation.txt"
    prev_root = run_dir / "memo" / "_prev"
    assert not prev_root.exists() or not any(prev_root.iterdir())


def test_plain_rerender_keeps_the_stamp_the_record_earned(env, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls)
    report, *_ = make_memo(env)
    storage.update_report(
        report["id"],
        review_state="approved",
        reviewer="seline.sun@bshfoundation.org",
        reviewer_name="Seline Sun",
        reviewed_at="2026-09-22T10:00:00+00:00",
    )
    result = report_rerender.rerender_report(report["id"], reason="rerender")
    assert result["status"] == "rendered"
    assert calls[0]["package"]["run"]["review"] == {
        "state": "approved",
        "reviewer": "Seline Sun",
        "reviewed_at": "2026-09-22T10:00:00+00:00",
    }


def test_admin_rerender_endpoint(env, client, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls)
    report, run_dir, en, _zh = make_memo(env)
    as_role(monkeypatch, "partner", "seline.sun@bshfoundation.org")
    assert client.post(f"/api/reports/{report['id']}/rerender", json={}).status_code == 403
    as_role(monkeypatch, "admin", "benma@bshventures.com")
    r = client.post(f"/api/reports/{report['id']}/rerender", json={"relint": False})
    assert r.status_code == 200, r.text
    assert r.json()["rerender"]["status"] == "rendered"
    assert calls[0]["strict_sources"] is False
    assert en.read_bytes().startswith(b"new-en")
    running, *_ = make_memo(env, company_id="other", status="analyzing")
    assert client.post(f"/api/reports/{running['id']}/rerender", json={}).status_code == 409


def test_rerender_refuses_unfinished_or_packageless_runs(env):
    running, *_ = make_memo(env, status="analyzing")
    with pytest.raises(report_rerender.RerenderRefused) as exc:
        report_rerender.rerender_report(running["id"])
    assert exc.value.code == "not_finished"


def test_renderer_capability_rule():
    assert report_rerender.renderer_capabilities(memo_prep.BUFFETT_KIND)["review"] is bool(
        getattr(buffett_memo_renderer, "SUPPORTS_REVIEW_STAMP", True)
    )


def test_undeclared_renderer_is_inspected(monkeypatch):
    monkeypatch.delattr(memo_docx_renderer, "SUPPORTS_REVIEW_STAMP", raising=False)
    monkeypatch.setattr(memo_docx_renderer, "_review_stamp", lambda *a: ("", ""), raising=False)
    assert report_rerender.renderer_capabilities(memo_prep.LATESTAGE_KIND)["review"] is True
    monkeypatch.delattr(memo_docx_renderer, "_review_stamp", raising=False)
    monkeypatch.delattr(memo_docx_renderer, "review_stamp", raising=False)
    monkeypatch.setattr(
        memo_docx_renderer,
        "render_memos",
        lambda package, *, out_en, out_zh, manifest_path=None, inventory_path=None: None,
    )
    assert report_rerender.renderer_capabilities(memo_prep.LATESTAGE_KIND)["review"] is False


def test_buffett_rerender_goes_through_render_package(env, client, monkeypatch):
    seen = {}

    def render_package(package, *, run_dir, memo_paths, review=None):
        seen.update(review=review, decision=package["decision"])
        for lang in ("en", "zh"):
            memo_paths[lang].write_bytes(f"stamped-{lang}".encode())
        (run_dir / "memo" / "buffett_memo.en.md").write_text("new md", encoding="utf-8")
        return {
            "ok": True,
            "decision": "Pass",
            "buy_price": "Below $40",
            "buy_price_zh": "40 美元以下",
            "pass_kind": "price",
            "call_label": {"en": "Pass at today's price — buy at or below $40", "zh": "暂不买入（买入价 ≤ 40 美元）"},
            "fields": {"buy_price_value": 40.0, "currency": "USD"},
            "renderer_version": "buffett-test",
        }

    monkeypatch.setattr(buffett_memo_renderer, "render_package", render_package)
    monkeypatch.setattr(buffett_memo_renderer, "SUPPORTS_REVIEW_STAMP", True, raising=False)
    report, run_dir, en, _zh = make_memo(env, kind=memo_prep.BUFFETT_KIND, company_id="google-llc")
    as_role(monkeypatch, "partner", "seline.sun@bshfoundation.org")
    body = client.patch(f"/api/reports/{report['id']}/review", json={"state": "withdrawn"}).json()
    assert body["review_state"] == "withdrawn"
    assert body["rerender"]["status"] == "rendered"
    assert seen["review"]["state"] == "withdrawn"
    assert en.read_bytes() == b"stamped-en"
    prev = next((run_dir / "memo" / "_prev").iterdir())
    assert (prev / "buffett_memo.en.md").read_text(encoding="utf-8") == "old md"
    # The render's report fields go back on the record (old records gain
    # call_label and the valuation).
    record = storage.get_report(report["id"])
    assert record["call_label"]["zh"] == "暂不买入（买入价 ≤ 40 美元）"
    assert record["buy_price_zh"] == "40 美元以下"
    assert record["renderer_version"] == "buffett-test"
    assert body["call_label"]["en"].startswith("Pass at today's price")


def test_open_flags_block_approval_until_acknowledged(env, client, monkeypatch):
    calls: list = []
    install_late_renderer(monkeypatch, calls)
    report, *_ = make_memo(env)
    as_role(monkeypatch, "partner", "seline.sun@bshfoundation.org")
    client.post(
        f"/api/reports/{report['id']}/comments",
        json={"flag": "wrong_number", "quote": "$1.5B is 2% of a quarter"},
    )
    blocked = client.patch(f"/api/reports/{report['id']}/review", json={"state": "approved"})
    assert blocked.status_code == 409
    ok = client.patch(
        f"/api/reports/{report['id']}/review",
        json={"state": "approved", "acknowledge_open_comments": True},
    )
    assert ok.status_code == 200


def test_resume_puts_an_approved_memo_back_to_draft(env, client, monkeypatch):
    report, run_dir, *_ = make_memo(env, status="complete_with_warnings")
    (run_dir / "analysis").mkdir()
    (run_dir / "analysis" / "pressure_tests.md").write_text("# Pressure\n", encoding="utf-8")
    storage.update_report(
        report["id"],
        review_state="approved",
        approved_revision="abc",
        reader={"v": 1},
        quality_warnings=["parity"],
        quality_warnings_zh=["一致性"],
        quality_warning_items=[{"gate": "chinese_parity", "language": "ZH", "severity": "P0"}],
    )
    started = []
    monkeypatch.setattr(memo_analysis, "start_resume", lambda rid: started.append(rid))
    r = client.post(f"/api/reports/{report['id']}/resume")
    assert r.status_code == 202, r.text
    record = storage.get_report(report["id"])
    assert record["review_state"] == "draft"
    assert record["approved_revision"] is None
    assert record["reader"] is None
    assert record["quality_warnings"] is None and record["quality_warnings_zh"] is None
    assert record["quality_warning_items"] is None
    assert started == [report["id"]]


# ---- comments and flags ----------------------------------------------------------------


def test_report_comments_flags_and_counts(env, client, monkeypatch):
    report, *_ = make_memo(env, company_id="not-in-workspace")
    as_role(monkeypatch, "research_ops", "ops@bshfoundation.org")
    comment = client.post(
        f"/api/reports/{report['id']}/comments",
        json={"text": "Check the TAM", "kind": "section", "label": "Market"},
    )
    assert comment.status_code == 201, comment.text
    flag = client.post(
        f"/api/reports/{report['id']}/comments",
        json={"flag": "wrong_number", "quote": "x" * 400, "language": "zh"},
    ).json()
    assert flag["flag"] == "wrong_number"
    assert flag["text"] == "Flagged: wrong number"
    assert len(flag["quote"]) == 300
    assert flag["language"] == "zh"
    assert flag["target"] == {"kind": "report", "ref": report["id"], "label": ""}
    listing = client.get(f"/api/reports/{report['id']}/comments").json()
    assert listing["open_comments"] == 1 and listing["open_flags"] == 1
    assert [i["id"] for i in client.get(f"/api/reports/{report['id']}/comments?flags_only=true").json()["items"]] == [flag["id"]]
    row = next(r for r in client.get("/api/reports").json() if r["id"] == report["id"])
    assert row["open_flags"] == 1 and row["open_comments"] == 1
    resolved = client.post(f"/api/reports/{report['id']}/comments/{flag['id']}/resolve", json={})
    assert resolved.status_code == 200
    row = next(r for r in client.get("/api/reports").json() if r["id"] == report["id"])
    assert row["open_flags"] == 0
    # Plain comments keep their old shape.
    assert "flag" not in comment.json() and "quote" not in comment.json()


@pytest.mark.parametrize(
    "body",
    [
        {"flag": "rude"},
        {"text": "x", "language": "fr"},
        {"text": "x", "kind": "company"},
        {"text": ""},
    ],
)
def test_bad_comments_are_rejected(env, client, body):
    report, *_ = make_memo(env)
    assert client.post(f"/api/reports/{report['id']}/comments", json=body).status_code == 400


def test_resolving_another_reports_comment_is_a_404(env, client):
    first, *_ = make_memo(env)
    other = storage.create_report_record(company_id="acme", kind=memo_prep.LATESTAGE_KIND, status="complete")
    item = client.post(f"/api/reports/{first['id']}/comments", json={"text": "hi"}).json()
    r = client.post(f"/api/reports/{other['id']}/comments/{item['id']}/resolve", json={})
    assert r.status_code == 404
    assert client.get(f"/api/reports/{first['id']}/comments").json()["open_comments"] == 1


def test_comments_need_memo_edit(env, client, monkeypatch):
    report, *_ = make_memo(env)
    as_role(monkeypatch, "guest")
    assert client.post(f"/api/reports/{report['id']}/comments", json={"text": "x"}).status_code == 403
    assert client.get(f"/api/reports/{report['id']}/comments").status_code == 200


# ---- reader telemetry ----------------------------------------------------------------------


def test_reader_events_once_per_session_and_counted(env, client):
    report, *_ = make_memo(env)
    first = client.post(
        f"/api/reports/{report['id']}/events", json={"event": "report_opened", "language": "en", "source": "reports_list"}
    )
    assert first.json() == {"recorded": True, "event": "report_opened"}
    again = client.post(f"/api/reports/{report['id']}/events", json={"event": "report_opened", "language": "en"})
    assert again.json()["recorded"] is False
    other_lang = client.post(f"/api/reports/{report['id']}/events", json={"event": "report_opened", "language": "zh"})
    assert other_lang.json()["recorded"] is True
    client.post(f"/api/reports/{report['id']}/events", json={"event": "report_downloaded", "language": "en"})
    client.post(f"/api/reports/{report['id']}/comments", json={"flag": "tone"})
    assert client.post(f"/api/reports/{report['id']}/events", json={"event": "page_turned"}).status_code == 400
    block = analytics_store.summary()["reports_read"]
    assert block["opened"] == 2
    assert block["reports_opened"] == 1
    assert block["downloaded"] == 1
    assert block["readers"] == 1
    assert block["flags_total"] == 1 and block["flags_open"] == 1
    assert block["flags_by_type"] == {"tone": 1}
    events = analytics_store.list_events(event="report_opened")
    assert all("reader" in e and "@" not in str(e.get("reader")) for e in events)
    # Telemetry is a read signal: it stays out of the mutation audit trail.
    assert not any("/events" in (item.get("path") or "") for item in firm.list_audit()["items"])
