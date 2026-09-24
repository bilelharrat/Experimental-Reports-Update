"""Reports API: what each report concludes and how current it is.

Covers the reader block (headline / decision / freshness) and its lazy,
persist-once backfill; the compact fact-check summary; ``has_document``;
the removed placeholder report types; memo-template resolution and the
``structure_version`` record field; identity snapshots and logo rules;
versions and verdict flips; the plain-language failure explanation; and
the working-papers order.
"""
from __future__ import annotations

import itertools
import json

import pytest
from fastapi.testclient import TestClient

from server import (
    analytics_store,
    api,
    buffett_memo_analysis,
    memo_analysis,
    memo_prep,
    product_store,
    report_reader,
    storage,
)
from server.main import app

_COUNTER = itertools.count(1)


@pytest.fixture
def env(monkeypatch, tmp_path):
    data_root = tmp_path / "data"
    # Record paths are stored relative to memo_prep.DATA_DIR.parent.
    monkeypatch.setattr(memo_prep, "DATA_DIR", data_root)
    monkeypatch.setattr(memo_prep, "MEMOS_ROOT", data_root / "memos")
    return data_root


@pytest.fixture
def client():
    return TestClient(app)


def late_package(
    decision_en: str = (
        "BSH is not committing at the $1.2-1.5 trillion strip. At $1.35 trillion "
        "a 3x needs bull-case growth."
    ),
    decision_zh: str = "BSH 不会按 1.2 万亿至 1.5 万亿美元的区间出资。以 1.35 万亿美元入场需要乐观情形。",
    as_of: str = "2026-09-01",
    sources: list | None = None,
) -> dict:
    return {
        "schema_version": 1,
        "company": {"name": "Acme"},
        "run": {"run_id": "2026-09-01__120000", "as_of": as_of},
        "sections": [
            {
                "id": "investment_decision",
                "title": {"en": "Investment Decision", "zh": "投资决策"},
                "blocks": [
                    {"type": "paragraph", "text": {"en": decision_en, "zh": decision_zh}},
                    {
                        "type": "bullets",
                        "items": [{"en": "**Decision.** Not at this price.", "zh": "**决策。** 此价格不投。"}],
                    },
                ],
            }
        ],
        "sources": sources
        if sources is not None
        else [
            {"id": "S1", "title": {"en": "Round"}, "as_of": "2026-05-01"},
            {"id": "S2", "title": {"en": "Press"}, "as_of": "2026-08"},
            {"id": "S3", "title": {"en": "Undated"}},
            {"id": "S4", "title": {"en": "Future"}, "as_of": "2026-10-15"},
        ],
    }


BUFFETT_MD_EN = (
    "# Investment Memorandum — Google\n\nOmaha, August 2026\n\n"
    "## I. Investment Decision\n\n"
    "**Buy.** I would own this business at today's quote of about $345 a share, and "
    "Berkshire does own it. More follows here.\n\n"
    "The call changes on price.\n\n## II. The Business\n\nSearch.\n"
)
BUFFETT_MD_ZH = (
    "# 投资备忘录 — Google\n\n## 一、投资决策\n\n"
    "**买入。** 以今天约 345 美元的股价，我愿意持有这家企业。后文还有。\n\n## 二、业务\n\n搜索。\n"
)


def make_report(
    data_root,
    *,
    kind: str = memo_prep.LATESTAGE_KIND,
    company_id: str = "acme",
    company_name: str = "Acme",
    status: str = "complete",
    created_at: str | None = None,
    package: dict | None = None,
    docx: bool = True,
    report_type: str | None = None,
    **fields,
) -> tuple[dict, object]:
    n = next(_COUNTER)
    run_id = f"2026-09-01__12{n:04d}"
    suffix = "buffett-memo-run" if kind == memo_prep.BUFFETT_KIND else "memo-run"
    run_dir = data_root / "memos" / company_id / f"{run_id}__{company_id}__{suffix}"
    memo_dir = run_dir / "memo"
    memo_dir.mkdir(parents=True)
    (run_dir / "logs").mkdir()
    en = memo_dir / f"{company_name} - Investment Memo - {run_id}.docx"
    zh = memo_dir / f"{company_name} - 投资备忘录 - {run_id}.docx"
    if docx:
        en.write_bytes(b"PK-en-" + run_id.encode())
        zh.write_bytes(b"PK-zh-" + run_id.encode())
    if package is not None:
        (run_dir / "logs" / "memo_package.json").write_text(
            json.dumps(package, ensure_ascii=False), encoding="utf-8"
        )
    report = storage.create_report_record(
        company_id=company_id,
        company_name=company_name,
        report_type=report_type
        or (memo_prep.BUFFETT_REPORT_TYPE if kind == memo_prep.BUFFETT_KIND else memo_prep.REPORT_TYPE),
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
        **fields,
    )
    if created_at:
        storage.update_report(report["id"], created_at=created_at)
    return storage.get_report(report["id"]), run_dir


def row_for(rows: list[dict], report_id: str) -> dict:
    return next(r for r in rows if r["id"] == report_id)


# ---- reader block ----------------------------------------------------------------


def test_late_stage_reader_block_headline_and_freshness(env, client):
    report, _ = make_report(env, package=late_package())
    rows = client.get("/api/reports").json()
    reader = row_for(rows, report["id"])["reader"]
    assert reader["headline"]["en"] == "BSH is not committing at the $1.2-1.5 trillion strip."
    assert reader["headline"]["zh"] == "BSH 不会按 1.2 万亿至 1.5 万亿美元的区间出资。"
    assert reader["memo_as_of"] == "2026-09-01"
    # The newest source on or before the memo date, at its own precision; a
    # date after the memo is not counted as evidence.
    assert reader["evidence_latest"] == "2026-08"
    assert reader["sources_dated"] == 2
    assert reader["sources_total"] == 4
    assert reader["source"] == "package"
    assert reader["decision"] is None
    # Persisted once on the record.
    assert storage.get_report(report["id"])["reader"]["headline"] == reader["headline"]


def test_reader_backfill_reads_the_package_once(env, client, monkeypatch):
    report, _ = make_report(env, package=late_package())
    calls = []
    original = report_reader.load_package

    def counting(rep):
        calls.append(rep.get("id"))
        return original(rep)

    monkeypatch.setattr(report_reader, "load_package", counting)
    client.get("/api/reports")
    client.get("/api/reports")
    client.get(f"/api/reports/{report['id']}")
    assert calls == [report["id"]]


def test_reader_block_recomputed_once_after_a_rerender(env, client, monkeypatch):
    import os
    import time

    report, run_dir = make_report(env, package=late_package())
    client.get("/api/reports")
    # A resume or re-render rewrites the documents from a new package.
    new_package = late_package(decision_en="We would commit at or below $1.0 trillion. More.")
    (run_dir / "logs" / "memo_package.json").write_text(json.dumps(new_package), encoding="utf-8")
    time.sleep(0.01)
    for entry in storage.get_report(report["id"])["memo_files"]:
        path = memo_prep.DATA_DIR.parent / entry["path"]
        path.write_bytes(b"PK-rerendered")
        os.utime(path, None)
    calls = []
    original = report_reader.load_package
    monkeypatch.setattr(report_reader, "load_package", lambda rep: calls.append(1) or original(rep))
    rows = client.get("/api/reports").json()
    client.get("/api/reports")
    assert row_for(rows, report["id"])["reader"]["headline"]["en"] == (
        "We would commit at or below $1.0 trillion."
    )
    assert len(calls) == 1


def test_reader_block_skipped_for_unfinished_runs(env, client):
    report, _ = make_report(env, package=late_package(), status="analyzing")
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["reader"] is None
    assert "reader" not in storage.get_report(report["id"])


def test_buffett_reader_block_decision_price_and_fields(env, client):
    package = {
        "schema_version": 1,
        "kind": memo_prep.BUFFETT_KIND,
        "company_name": "Google",
        "decision": "Buy",
        "buy_price": "Up to about $360 per share",
        "markdown_en": BUFFETT_MD_EN,
        "markdown_zh": BUFFETT_MD_ZH,
    }
    report, _ = make_report(
        env,
        kind=memo_prep.BUFFETT_KIND,
        company_id="google-llc",
        company_name="Google",
        package=package,
        decision="Buy",
        price=345.5,
        price_date="2026-08-24",
        currency="USD",
        mos_pct="12%",
        value_central="410",
        pass_kind=None,
    )
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["decision"] == "Buy"
    assert row["buy_price"] == "Up to about $360 per share"
    assert row["reader"]["headline"]["en"] == (
        "I would own this business at today's quote of about $345 a share, and "
        "Berkshire does own it."
    )
    assert row["reader"]["headline"]["zh"] == "以今天约 345 美元的股价，我愿意持有这家企业。"
    assert row["reader"]["source"] == "buffett"
    assert row["reader"]["buy_price_text"] == "Up to about $360 per share"
    assert row["price"] == 345.5
    assert row["price_date"] == "2026-08-24"
    assert row["currency"] == "USD"
    assert row["mos_pct"] == 12.0
    assert row["value_central"] == 410.0
    assert row["value_low"] is None


def test_buffett_valuation_object_and_call_label_reach_the_row(env, client):
    """The Buffett finalize step stores the valuation under
    ``buffett_valuation`` with a reader-facing ``call_label``."""
    report, _ = make_report(
        env,
        kind=memo_prep.BUFFETT_KIND,
        company_id="google-llc",
        company_name="Google",
        decision="Pass",
        pass_kind="price",
        buy_price="$215 per share or less",
        buy_price_zh="每股 215 美元或以下",
        call_label={"en": "Pass at today's price — buy at or below $215", "zh": "暂不买入（买入价 ≤ 215 美元）"},
        buffett_valuation={
            "currency": "USD",
            "price": 349.1,
            "price_date": "2026-08-25",
            "value_central": 250,
            "buy_price_value": 215,
            "mos_pct": -39.6,
        },
        market_inputs={"status": "pinned", "ticker": "GOOGL", "price": 349.1, "ust10y": 4.1},
        web_lookups=14,
        retrieved_sources=9,
        quality_warnings=["Section VIII does not state the hurdle"],
        quality_warnings_zh=["第八节没有写明门槛收益率"],
        quality_warning_items=[
            {
                "gate": "buffett_checks",
                "language": None,
                "section": "VIII",
                "severity": "P1",
                "code": "hurdle_missing",
                "summary_en": "Section VIII does not state the hurdle",
                "summary_zh": "第八节没有写明门槛收益率",
                "detail_path": None,
            },
            "not-a-dict",
        ],
        renderer_version="buffett-frame-2026-09-22",
    )
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["market_inputs"]["ticker"] == "GOOGL"
    assert row["web_lookups"] == 14 and row["retrieved_sources"] == 9
    assert row["quality_warnings_zh"] == ["第八节没有写明门槛收益率"]
    assert [item["code"] for item in row["quality_warning_items"]] == ["hurdle_missing"]
    assert row["renderer_version"] == "buffett-frame-2026-09-22"
    assert row["pass_kind"] == "price"
    assert row["buy_price_zh"] == "每股 215 美元或以下"
    assert row["call_label"]["zh"] == "暂不买入（买入价 ≤ 215 美元）"
    assert row["price"] == 349.1 and row["price_date"] == "2026-08-25"
    assert row["buy_price_value"] == 215.0 and row["mos_pct"] == -39.6
    assert row["buffett_valuation"]["value_central"] == 250
    assert row["reader"]["buy_price_text_zh"] == "每股 215 美元或以下"


def test_spine_verdict_is_the_decision_on_v2_runs(env, client):
    report, run_dir = make_report(env, package=late_package())
    units = run_dir / "logs" / "english_units"
    units.mkdir(parents=True)
    (units / "spine.json").write_text(
        json.dumps({"shared_facts": {"verdict": "Watch", "recommendation_sentence": "Watch it."}}),
        encoding="utf-8",
    )
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["decision"] == "Watch"
    assert row["reader"]["source"] == "spine"


def test_first_sentence_helpers_handle_abbreviations_and_bold_labels():
    assert (
        report_reader.first_sentence_en("U.S. revenue grew 5.2% in 2025 at Acme Inc. again. Then more.")
        == "U.S. revenue grew 5.2% in 2025 at Acme Inc. again."
    )
    # A bold label is dropped; bold that is part of the sentence stays.
    assert report_reader.first_sentence_en("**Decision.** We pass. More.") == "We pass."
    assert (
        report_reader.first_sentence_en("**BSH is not committing** at $1.2T. More.")
        == "BSH is not committing at $1.2T."
    )
    assert report_reader.first_sentence_zh("**买入。** 我们买入 1.06 亿股。其余。") == "我们买入 1.06 亿股。"
    assert report_reader.first_sentence_en("[S1] Cited sentence [S2, C3]. Next.") == "Cited sentence."


def test_headline_skips_a_sentence_that_only_restates_the_call():
    en = report_reader.headline_sentence(
        ["Pass.", "The call is **Pass**. TSMC is superb, but not at $410 a share."], "en"
    )
    assert en == "TSMC is superb, but not at $410 a share."
    zh = report_reader.headline_sentence(["Too Hard（超出能力圈）。我不会买它。"], "zh")
    assert zh == "我不会买它。"
    # A price condition is substance, not a restatement.
    assert report_reader.headline_sentence(["**Pass** — at $60 a share. More."], "en") == (
        "Pass — at $60 a share."
    )
    assert report_reader.restates_the_call("我的结论是**放弃**。")
    assert not report_reader.restates_the_call("We do not recommend participating.")


# ---- fact check -------------------------------------------------------------------


FULL_FACT_CHECK = {
    "status": "warn",
    "checked": 40,
    "verified": 30,
    "supported": 4,
    "derived": 2,
    "unsupported": 4,
    "coverage_pct": 90,
    "thin_corpus": False,
    "p0_count": 4,
    "findings": [{"code": "unsupported_figure", "snippet": "$9B"}],
    "corpus": [],
}


def test_fact_check_compact_on_list_and_full_on_detail(env, client):
    report, run_dir = make_report(env, package=late_package())
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps(FULL_FACT_CHECK), encoding="utf-8")
    row = row_for(client.get("/api/reports").json(), report["id"])
    compact = row["memo_fact_check"]
    # memo_fact_check.summarize_fact_check shapes it when present; either
    # way the row carries the counts and never the findings.
    assert compact["checked"] == 40
    assert compact["unsupported"] == 4
    assert compact["p0_count"] == 4
    assert compact["thin_corpus"] is False
    assert "findings" not in compact and "corpus" not in compact
    detail = client.get(f"/api/reports/{report['id']}").json()
    assert detail["memo_fact_check"]["findings"] == FULL_FACT_CHECK["findings"]


def test_fact_check_local_summary_without_the_helper(env, client, monkeypatch):
    from server import memo_fact_check

    monkeypatch.delattr(memo_fact_check, "summarize_fact_check", raising=False)
    report, run_dir = make_report(env, package=late_package())
    (run_dir / "logs" / "fact_check.json").write_text(json.dumps(FULL_FACT_CHECK), encoding="utf-8")
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["memo_fact_check"] == {
        "status": "warn",
        "checked": 40,
        "verified": 30,
        "supported": 4,
        "derived": 2,
        "unsupported": 4,
        "coverage_pct": 90,
        "thin_corpus": False,
        "p0_count": 4,
    }


def test_fact_check_uses_summarize_fact_check_when_available(env, client, monkeypatch):
    from server import memo_fact_check

    monkeypatch.setattr(
        memo_fact_check,
        "summarize_fact_check",
        lambda payload: {"checked": payload["checked"], "status": "custom"},
        raising=False,
    )
    report, _ = make_report(env, package=late_package(), memo_fact_check=FULL_FACT_CHECK)
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["memo_fact_check"] == {"checked": 40, "status": "custom"}


def test_runs_before_the_fact_check_get_no_field(env, client):
    report, _ = make_report(env, package=late_package())
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["memo_fact_check"] is None


# ---- documents and placeholder types ------------------------------------------------


def test_has_document_and_previews_for_finished_memos(env, client, monkeypatch):
    from server import docx_pdf

    monkeypatch.setattr(docx_pdf, "converter_available", lambda: False)
    report, _ = make_report(env, package=late_package())
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    placeholder = storage.create_report(
        company_id="zainar-inc", report_type="Financial Analysis", audience="Internal"
    )
    rows = client.get("/api/reports").json()
    memo_row = row_for(rows, report["id"])
    assert memo_row["has_document"] is True
    # A finished memo always offers a PDF preview; it is made on request.
    assert memo_row["preview_urls"]["en"].endswith("/preview?language=en")
    assert memo_row["pdf_status"] == {"en": "unavailable", "zh": "unavailable"}
    stub_row = row_for(rows, placeholder["id"])
    assert stub_row["has_document"] is False
    assert "download_urls" not in stub_row or not stub_row["download_urls"]


@pytest.mark.parametrize("report_type", ["Background", "Financial Analysis", "Market Analysis"])
def test_placeholder_report_types_get_a_readable_400(client, report_type):
    r = client.post(
        "/api/reports",
        json={"company_id": "acme", "report_type": report_type, "audience": "Internal"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == f"{report_type} reports are not available yet"


def test_options_drop_placeholder_types_and_expose_structure_flags(client, monkeypatch):
    # memo_flags: the switches default ON; "=0" is how a server turns them off.
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "0")
    body = client.get("/api/options").json()
    assert body["report_types"] == [
        "Investment Report (Auto)",
        "Investment Memo (Late-Stage)",
        "Buffett Investment Memo",
    ]
    assert body["structure_v2_enabled"] is False
    assert body["english_parallel_enabled"] is False
    assert body["memo_templates"] == ["standard", "ic_v2"]
    assert body["memo_template_default"] == "standard"
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "1")
    monkeypatch.setenv("BSH_MEMO_ENGLISH_PARALLEL", "1")
    flipped = client.get("/api/options").json()
    assert flipped["structure_v2_enabled"] is True
    assert flipped["english_parallel_enabled"] is True
    assert flipped["memo_template_default"] == "ic_v2"


def test_legacy_investment_report_type_still_maps_to_auto(client, monkeypatch):
    seen = {}

    def fake_bootstrap(company_id, **kwargs):
        seen.update(kwargs)
        raise ValueError("stop here")

    monkeypatch.setattr(memo_prep, "bootstrap_memo_run", fake_bootstrap)
    r = client.post(
        "/api/reports",
        json={"company_id": "acme", "report_type": "Investment Report", "audience": "Internal"},
    )
    assert r.status_code == 404
    assert seen["report_type"] == memo_prep.AUTO_STAGE_REPORT_TYPE


# ---- the LP / Partner / Assistant 500 (investigation) ------------------------------


@pytest.fixture
def seeded_company(env, monkeypatch):
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    started: list[str] = []
    monkeypatch.setattr(memo_analysis, "start_analysis", lambda rid: started.append(rid))
    monkeypatch.setattr(buffett_memo_analysis, "start_analysis", lambda rid: started.append(rid))
    return started


@pytest.mark.parametrize("audience", ["LP", "Partner", "Assistant", "Internal"])
def test_every_audience_creates_a_memo(client, seeded_company, audience, monkeypatch):
    """The 2026-08-20 500s for LP / Partner / Assistant were the missing
    settings file (serena_background.md), which failed every audience
    alike; ensure_settings_file now creates it. The audience reaches
    memo_prep (it used to be hard-coded "Internal"): the record carries it,
    and it decides whether the internal IC decision memo is written next to
    the LP memo — never for an LP run."""
    monkeypatch.delenv("BSH_MEMO_GENERATE_INTERNAL", raising=False)
    r = client.post(
        "/api/reports",
        json={
            "company_id": "zainar-inc",
            "report_type": "Investment Memo (Late-Stage)",
            "audience": audience,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["requested_audience"] == audience
    assert body["audience"] == audience
    assert seeded_company == [body["id"]]
    stored = storage.get_report(body["id"])
    languages = sorted(entry["language"] for entry in stored["internal_memo_files"])
    assert languages == ([] if audience == "LP" else ["en", "zh"])


def test_the_template_is_on_the_record_before_the_worker_starts(
    client, seeded_company, monkeypatch
):
    """structure_version used to land a moment after bootstrap had started
    the worker, so a fast worker resolved its structure without it."""
    seen: dict = {}

    def start(report_id):
        seen.update(storage.get_report(report_id) or {})

    monkeypatch.setattr(memo_analysis, "start_analysis", start)
    body = _post_late(client, memo_template="ic_v2")
    assert seen["id"] == body["id"]
    assert seen["structure_version"] == "v2"
    assert seen["structure_version_source"] == "request"
    assert seen["audience"] == "Internal"


def test_new_report_snapshots_company_identity(client, seeded_company):
    body = client.post(
        "/api/reports",
        json={"company_id": "zainar-inc", "report_type": "Buffett Investment Memo", "audience": "Internal"},
    ).json()
    identity = storage.get_report(body["id"])["company_identity"]
    assert identity["name"] == "ZaiNar, Inc."
    assert identity["website"] == "https://zainartech.com"
    assert body["company_identity"]["logo_domain"] == "zainartech.com"
    # Buffett memos get no template field.
    assert body["structure_version"] is None


# ---- memo template ------------------------------------------------------------------


def _post_late(client, **extra) -> dict:
    r = client.post(
        "/api/reports",
        json={
            "company_id": "zainar-inc",
            "report_type": "Investment Report (Auto)",
            "audience": "Internal",
            **extra,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_memo_template_precedence_and_record_field(client, seeded_company, monkeypatch):
    # Switched off with =0 (memo_flags); unset means the default, which is on.
    monkeypatch.setenv("BSH_MEMO_STRUCTURE_V2", "0")
    first = _post_late(client)
    stored = storage.get_report(first["id"])
    assert stored["structure_version"] == "v1"
    assert stored["structure_version_source"] == "env_default"
    assert first["structure_version"] == "v1"

    settings = client.get("/api/workspace/settings").json()
    assert settings["preferences"]["memo_template"] is None
    assert settings["preferences"]["memo_template_effective"] == "standard"
    assert settings["memo_template_effective"] == "standard"

    patched = client.patch("/api/workspace/settings", json={"memo_template": "ic_v2"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["preferences"]["memo_template"] == "ic_v2"
    assert patched.json()["memo_template_effective"] == "ic_v2"
    by_pref = _post_late(client)
    assert storage.get_report(by_pref["id"])["structure_version"] == "v2"
    assert storage.get_report(by_pref["id"])["structure_version_source"] == "preference"

    override = _post_late(client, memo_template="standard")
    assert storage.get_report(override["id"])["structure_version"] == "v1"
    assert storage.get_report(override["id"])["structure_version_source"] == "request"

    # Clearing the choice hands the decision back to the switch, whose
    # default (unset) is the IC template.
    monkeypatch.delenv("BSH_MEMO_STRUCTURE_V2", raising=False)
    reset = client.patch("/api/workspace/settings", json={"memo_template": "default"}).json()
    assert reset["preferences"]["memo_template"] is None
    assert reset["memo_template_effective"] == "ic_v2"
    by_env = _post_late(client)
    assert storage.get_report(by_env["id"])["structure_version"] == "v2"
    assert storage.get_report(by_env["id"])["structure_version_source"] == "env_default"

    rows = client.get("/api/reports").json()
    assert row_for(rows, by_env["id"])["structure_version"] == "v2"


def test_memo_template_validation(client, seeded_company):
    bad = client.post(
        "/api/reports",
        json={
            "company_id": "zainar-inc",
            "report_type": "Investment Report (Auto)",
            "audience": "Internal",
            "memo_template": "fancy",
        },
    )
    assert bad.status_code == 400
    assert client.patch("/api/workspace/settings", json={"memo_template": "fancy"}).status_code == 400


def test_memo_template_is_per_user(monkeypatch):
    product_store.update_preferences("ana@bshventures.com", {"memo_template": "ic_v2"})
    assert product_store.effective_memo_template("ana@bshventures.com") == ("ic_v2", "preference")
    assert product_store.effective_memo_template("bo@bshventures.com") == ("standard", "env_default")
    assert product_store.effective_memo_template("bo@bshventures.com", "ic_v2") == ("ic_v2", "request")


def test_analyst_may_set_their_own_template_but_not_workspace_settings(client, monkeypatch):
    monkeypatch.setattr(api, "_caller_role", lambda request: "analyst")
    assert client.patch("/api/workspace/settings", json={"memo_template": "ic_v2"}).status_code == 200
    assert client.patch("/api/workspace/settings", json={"compact_density": True}).status_code == 403


# ---- logos and identity ---------------------------------------------------------------


def test_lookalike_slugs_no_longer_wear_famous_logos(env, client):
    ravine, _ = make_report(
        env, company_id="open-artificial-intelligence-inc", company_name="Open Artificial Intelligence Inc"
    )
    ko, _ = make_report(env, company_id="ko", company_name="Coca-Cola")
    rows = client.get("/api/reports").json()
    assert row_for(rows, ravine["id"])["logo_url"] is None
    assert row_for(rows, ko["id"])["logo_url"] == "https://assets.parqet.com/logos/symbol/KO"


def test_logo_resolves_from_the_record_before_any_map():
    # No name rules: "OpenAI" in the name gives no logo.
    assert api._company_logo_url({"id": "ravine", "name": "Ravine OpenAI Labs"}, None) is None
    assert api._company_logo_domain({"id": "ravine", "name": "Coca-Cola bottler"}) is None
    # The record's own ticker beats the slug map.
    assert api._company_logo_url({"id": "anthropic", "ticker": "ANTH"}, None) == (
        "https://assets.parqet.com/logos/symbol/ANTH"
    )
    own = {"id": "anthropic", "logo_url": "https://example.org/logo.svg"}
    assert api._company_logo_url(own, None) == "https://example.org/logo.svg"
    by_site = {"id": "anthropic", "website": "https://www.example.org/about"}
    assert "example.org" in api._company_logo_url(by_site, api._company_logo_domain(by_site))


def test_report_logo_prefers_its_identity_snapshot(env, client):
    report, _ = make_report(
        env,
        company_id="anthropic-pbc",
        company_name="Anthropic",
        company_identity={"website": "https://snapshot.example", "name": "Anthropic"},
    )
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["logo_domain"] == "snapshot.example"
    assert "snapshot.example" in row["logo_url"]


# ---- versions -----------------------------------------------------------------------------


def test_versions_latest_and_a_flipped_call(env, client):
    first, _ = make_report(
        env,
        kind=memo_prep.BUFFETT_KIND,
        company_id="google-llc",
        created_at="2026-08-25T00:31:53+00:00",
        decision="Buy",
    )
    second, _ = make_report(
        env,
        kind=memo_prep.BUFFETT_KIND,
        company_id="google-llc",
        created_at="2026-08-25T18:48:56+00:00",
        decision="Pass",
    )
    failed, _ = make_report(
        env,
        kind=memo_prep.BUFFETT_KIND,
        company_id="google-llc",
        created_at="2026-08-26T10:00:00+00:00",
        status="failed_during_analysis",
    )
    other_kind, _ = make_report(env, company_id="google-llc", created_at="2026-08-27T10:00:00+00:00")
    rows = client.get("/api/reports").json()
    a, b, c = row_for(rows, first["id"]), row_for(rows, second["id"]), row_for(rows, failed["id"])
    assert a["is_latest"] is False
    assert a["newer_version_id"] == second["id"]
    assert a["latest_version_id"] == second["id"]
    assert b["is_latest"] is True
    assert b["previous_version_id"] == first["id"]
    assert b["verdict_changed_from"] == "Buy"
    assert b["unstable_call"] is True
    assert b["version_index"] == 2 and b["version_count"] == 2
    assert c["is_latest"] is None
    # Late-stage memos are their own group.
    assert row_for(rows, other_kind["id"])["is_latest"] is True
    # superseded_by keeps its own meaning (failed run replaced): never set here.
    assert all(r["superseded_by"] is None for r in rows)
    detail = client.get(f"/api/reports/{second['id']}").json()
    assert detail["verdict_changed_from"] == "Buy"
    assert detail["previous_version_id"] == first["id"]


# ---- failure explanation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("fields", "kind"),
    [
        ({"failure_phase": "shutdown"}, "interrupted"),
        ({"failure_phase": "orphaned"}, "interrupted"),
        ({"failure_phase": "cancelled"}, "cancelled"),
        ({"failure_detail": "Failed to authenticate. API Error: 403"}, "login"),
        ({"failure_detail": "Claude usage limit reached; resets in 2 hr"}, "provider_limit"),
        ({"failure_detail": "memo English package stalled after 180s without output"}, "timeout"),
        ({"failure_phase": "renderer_contract", "failure_detail": "Renderer contract failed"}, "engine_output_malformed"),
        ({"failure_detail": "ZeroDivisionError: division by zero"}, "internal_error"),
    ],
)
def test_failure_kind_mapping(env, fields, kind):
    report, _ = make_report(env, status="failed_during_analysis", docx=False, **fields)
    explained = report_reader.classify_failure(report)
    assert explained["failure_kind"] == kind
    assert explained["failure_summary_en"]
    assert explained["failure_summary_zh"]


def test_failure_explanation_on_rows_with_reset_and_spend(env, client):
    report, _ = make_report(
        env,
        status="failed_during_analysis",
        docx=False,
        failure_detail="You've hit your usage limit. Resets in 2 hr 30 min",
        claude_cost_usd=3.25,
    )
    scope, _ = make_report(env, status="failed_scope_check", docx=False)
    rows = client.get("/api/reports").json()
    row = row_for(rows, report["id"])
    assert row["failure_kind"] == "provider_limit"
    assert row["failure_resets_at"]
    assert row["failure_resets_at"] in row["failure_summary_en"]
    assert "重置" in row["failure_summary_zh"]
    assert row["failure_spend_usd"] == 3.25
    assert row_for(rows, scope["id"])["failure_kind"] == "out_of_scope"
    assert row["has_document"] is False


def test_finished_reports_carry_no_failure_fields(env, client):
    report, _ = make_report(env, package=late_package())
    row = row_for(client.get("/api/reports").json(), report["id"])
    assert row["failure_kind"] is None


# ---- working papers -----------------------------------------------------------------------


def test_working_papers_reader_order_and_failed_placeholders(env, client):
    report, run_dir = make_report(env, package=late_package())
    analysis = run_dir / "analysis"
    analysis.mkdir()
    (analysis / "custom_notes.md").write_text("# Notes\n", encoding="utf-8")
    (analysis / "growth_bridge.md").write_text(
        "# Growth bridge\n\n## Status\n\nPass failed: weekly limit\n", encoding="utf-8"
    )
    (analysis / "pressure_tests.md").write_text("# Pressure\n\nFindings.\n", encoding="utf-8")
    (analysis / "countercase.md").write_text("# Countercase\n\nThe case against.\n", encoding="utf-8")
    papers = client.get(f"/api/reports/{report['id']}").json()["analysis_artifacts"]
    assert [p["filename"] for p in papers] == [
        "countercase.md",
        "pressure_tests.md",
        "growth_bridge.md",
        "custom_notes.md",
    ]
    assert [p["failed"] for p in papers] == [False, False, True, False]


# ---- telemetry noise ---------------------------------------------------------------------


def test_company_get_no_longer_logs_workspace_opened(client):
    storage.bootstrap_seed_data()
    storage.materialize_seed_company_records()
    assert client.get("/api/companies/zainar-inc").status_code == 200
    assert analytics_store.list_events(event="workspace_opened") == []


# ---- jobs route -----------------------------------------------------------------------------


def test_memo_job_rows_link_to_the_reports_page(env):
    from server import job_progress

    report, run_dir = make_report(env, status="analyzing")
    log = job_progress.ProgressLog(run_dir / "logs" / "stream.jsonl")
    log.emit("job_init", kind="memo", title="Memo", report_id=report["id"], company_id="acme")
    log.emit("stage", stage="analyzing", message="Working")
    rows = [r for r in api._memo_kind_records() if r.get("report_id") == report["id"]]
    assert rows and rows[0]["primary_route"] == {"name": "reports", "query": {"id": report["id"]}}
