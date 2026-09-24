// Real records from GET /api/reports and GET /api/reports/{id}/diff after
// the Reports API work (reader block, versions, review, fact check, PDF
// status) — the renderer contract is dropped; every other field is as the
// API sends it. Build variants with `withReport(base, patch)`.

/** Google, Buffett-method, the newer of two versions: Pass, flipped from Buy 18 hours earlier. */
export const GOOGLE_PASS = Object.freeze({
  "id": "3cb7ec52fa15",
  "company_id": "google-llc",
  "company_name": "Google",
  "logo_domain": "google.com",
  "logo_url": "https://assets.parqet.com/logos/symbol/GOOG",
  "report_type": "Buffett Investment Memo",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "created_at": "2026-08-25T18:48:56.743036+00:00",
  "updated_at": "2026-09-22T23:27:40.587077+00:00",
  "kind": "buffett_investment_memo",
  "run_id": "2026-08-25__184856",
  "run_dir": "data/memos/google-llc/2026-08-25__184856__google-llc__buffett-memo-run",
  "skill": "bsh-buffett-investment-memo-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/google-llc/2026-08-25__184856__google-llc__buffett-memo-run/memo/Google - Buffett Investment Memo - EN - 2026-08-25__184856.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/google-llc/2026-08-25__184856__google-llc__buffett-memo-run/memo/Google - Buffett Investment Memo - ZH - 2026-08-25__184856.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": null,
  "memo_chinese_parity": null,
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/3cb7ec52fa15/download?language=en",
    "zh": "/api/reports/3cb7ec52fa15/download?language=zh"
  },
  "preview_urls": {
    "en": "/api/reports/3cb7ec52fa15/preview?language=en",
    "zh": "/api/reports/3cb7ec52fa15/preview?language=zh"
  },
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null,
  "reader": {
    "v": 1,
    "headline": {
      "en": "I think the core business is one of the finest commercial franchises ever assembled, but the price on offer — roughly $349 a share and about $4.3 trillion of equity value — asks me to pay in full today for a capital-spending program whose returns are entirely unproven.",
      "zh": "我认为核心业务是商业史上最出色的特许经营权之一，但当前报价——每股约 349 美元、约 4.3 万亿美元的股权价值——要求我今天就为一项回报完全未经验证的资本开支计划全额付款。"
    },
    "decision": "Pass",
    "buy_price_text": "$215 per share or less (about $2.65 trillion equity value)",
    "buy_price_text_zh": null,
    "pass_kind": null,
    "memo_as_of": "2026-08-25",
    "evidence_latest": null,
    "sources_dated": 0,
    "sources_total": 0,
    "source": "buffett",
    "computed_at": "2026-09-22T23:27:40Z",
    "docs_stamp": "en:1787938301874796604,zh:1787938301894030062"
  },
  "decision": "Pass",
  "buy_price": "$215 per share or less (about $2.65 trillion equity value)",
  "buy_price_zh": null,
  "pass_kind": null,
  "call_label": null,
  "buffett_valuation": null,
  "market_inputs": null,
  "web_lookups": null,
  "retrieved_sources": null,
  "quality_warnings_zh": null,
  "quality_warning_items": null,
  "price": null,
  "price_date": null,
  "currency": null,
  "value_low": null,
  "value_central": null,
  "value_high": null,
  "buy_price_value": null,
  "mos_pct": null,
  "memo_fact_check": null,
  "has_document": true,
  "pdf_status": {
    "en": "pending",
    "zh": "pending"
  },
  "is_latest": true,
  "version_index": 2,
  "version_count": 2,
  "previous_version_id": "37acb580ef1e",
  "newer_version_id": null,
  "latest_version_id": "3cb7ec52fa15",
  "verdict_changed_from": "Buy",
  "verdict_flip_days": 0.76,
  "unstable_call": true,
  "review_state": "draft",
  "reviewer": null,
  "reviewer_name": null,
  "reviewed_at": null,
  "review_note": null,
  "approved_revision": null,
  "review_render_status": null,
  "open_comments": 0,
  "open_flags": 0,
  "failure_kind": null,
  "failure_summary_en": null,
  "failure_summary_zh": null,
  "failure_resets_at": null,
  "failure_spend_usd": null,
  "company_identity": null,
  "structure_version": null,
  "requested_audience": null,
  "rendered_at": null,
  "renderer_version": null
});

/** Google, Buffett-method, the older version: Buy. */
export const GOOGLE_BUY = Object.freeze({
  "id": "37acb580ef1e",
  "company_id": "google-llc",
  "company_name": "Google",
  "logo_domain": "google.com",
  "logo_url": "https://assets.parqet.com/logos/symbol/GOOG",
  "report_type": "Buffett Investment Memo",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "created_at": "2026-08-25T00:31:53.886490+00:00",
  "updated_at": "2026-09-22T23:27:40.601842+00:00",
  "kind": "buffett_investment_memo",
  "run_id": "2026-08-25__003153",
  "run_dir": "data/memos/google-llc/2026-08-25__003153__google-llc__buffett-memo-run",
  "skill": "bsh-buffett-investment-memo-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/google-llc/2026-08-25__003153__google-llc__buffett-memo-run/memo/Google - Buffett Investment Memo - EN - 2026-08-25__003153.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/google-llc/2026-08-25__003153__google-llc__buffett-memo-run/memo/Google - Buffett Investment Memo - ZH - 2026-08-25__003153.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": null,
  "memo_chinese_parity": null,
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/37acb580ef1e/download?language=en",
    "zh": "/api/reports/37acb580ef1e/download?language=zh"
  },
  "preview_urls": {
    "en": "/api/reports/37acb580ef1e/preview?language=en",
    "zh": "/api/reports/37acb580ef1e/preview?language=zh"
  },
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null,
  "reader": {
    "v": 1,
    "headline": {
      "en": "I would own this business at today's quote of about $345 a share, and Berkshire does own it — a little over 106 million shares at the end of June, our third-largest common stock position.",
      "zh": "以今天约 345 美元的股价，我愿意持有这家企业；伯克希尔也确实持有它——截至 6 月底略超过 1.06 亿股，是我们股票组合中的第三大仓位。"
    },
    "decision": "Buy",
    "buy_price_text": "Up to about $360 per Alphabet share (roughly $4.4 trillion for the whole company); I stop buying above $400",
    "buy_price_text_zh": null,
    "pass_kind": null,
    "memo_as_of": "2026-08-25",
    "evidence_latest": null,
    "sources_dated": 0,
    "sources_total": 0,
    "source": "buffett",
    "computed_at": "2026-09-22T23:27:40Z",
    "docs_stamp": "en:1787618644953273362,zh:1787618644974389895"
  },
  "decision": "Buy",
  "buy_price": "Up to about $360 per Alphabet share (roughly $4.4 trillion for the whole company); I stop buying above $400",
  "buy_price_zh": null,
  "pass_kind": null,
  "call_label": null,
  "buffett_valuation": null,
  "market_inputs": null,
  "web_lookups": null,
  "retrieved_sources": null,
  "quality_warnings_zh": null,
  "quality_warning_items": null,
  "price": null,
  "price_date": null,
  "currency": null,
  "value_low": null,
  "value_central": null,
  "value_high": null,
  "buy_price_value": null,
  "mos_pct": null,
  "memo_fact_check": null,
  "has_document": true,
  "pdf_status": {
    "en": "pending",
    "zh": "pending"
  },
  "is_latest": false,
  "version_index": 1,
  "version_count": 2,
  "previous_version_id": null,
  "newer_version_id": "3cb7ec52fa15",
  "latest_version_id": "3cb7ec52fa15",
  "verdict_changed_from": null,
  "verdict_flip_days": null,
  "unstable_call": null,
  "review_state": "draft",
  "reviewer": null,
  "reviewer_name": null,
  "reviewed_at": null,
  "review_note": null,
  "approved_revision": null,
  "review_render_status": null,
  "open_comments": 0,
  "open_flags": 0,
  "failure_kind": null,
  "failure_summary_en": null,
  "failure_summary_zh": null,
  "failure_resets_at": null,
  "failure_spend_usd": null,
  "company_identity": null,
  "structure_version": null,
  "requested_audience": null,
  "rendered_at": null,
  "renderer_version": null
});

/** Occidental, Buffett-method, with the EDGAR suffix still on the stored name. */
export const OXY_PASS = Object.freeze({
  "id": "3db0cdd7fe8a",
  "company_id": "oxy",
  "company_name": "Occidental Petroleum Corp /De/",
  "logo_domain": "oxy.com",
  "logo_url": "https://assets.parqet.com/logos/symbol/OXY",
  "report_type": "Buffett Investment Memo",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "created_at": "2026-08-25T00:23:14.008601+00:00",
  "updated_at": "2026-09-22T23:27:40.617017+00:00",
  "kind": "buffett_investment_memo",
  "run_id": "2026-08-25__002314",
  "run_dir": "data/memos/oxy/2026-08-25__002314__oxy__buffett-memo-run",
  "skill": "bsh-buffett-investment-memo-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/oxy/2026-08-25__002314__oxy__buffett-memo-run/memo/Occidental Petroleum Corp /De/ - Buffett Investment Memo - 2026-08-25__002314.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/oxy/2026-08-25__002314__oxy__buffett-memo-run/memo/Occidental Petroleum Corp /De/ - 巴菲特投资备忘录 - 2026-08-25__002314.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": null,
  "memo_chinese_parity": null,
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/3db0cdd7fe8a/download?language=en",
    "zh": "/api/reports/3db0cdd7fe8a/download?language=zh"
  },
  "preview_urls": {
    "en": "/api/reports/3db0cdd7fe8a/preview?language=en",
    "zh": "/api/reports/3db0cdd7fe8a/preview?language=zh"
  },
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null,
  "reader": {
    "v": 1,
    "headline": {
      "en": "Pass — at $60 a share.",
      "zh": "放弃——在每股 60 美元这个价位上。"
    },
    "decision": "Pass",
    "buy_price_text": "$45 or below per share",
    "buy_price_text_zh": null,
    "pass_kind": null,
    "memo_as_of": "2026-08-25",
    "evidence_latest": null,
    "sources_dated": 0,
    "sources_total": 0,
    "source": "buffett",
    "computed_at": "2026-09-22T23:27:40Z",
    "docs_stamp": "en:1787618365726332224,zh:1787618365754681690"
  },
  "decision": "Pass",
  "buy_price": "$45 or below per share",
  "buy_price_zh": null,
  "pass_kind": null,
  "call_label": null,
  "buffett_valuation": null,
  "market_inputs": null,
  "web_lookups": null,
  "retrieved_sources": null,
  "quality_warnings_zh": null,
  "quality_warning_items": null,
  "price": null,
  "price_date": null,
  "currency": null,
  "value_low": null,
  "value_central": null,
  "value_high": null,
  "buy_price_value": null,
  "mos_pct": null,
  "memo_fact_check": null,
  "has_document": true,
  "pdf_status": {
    "en": "pending",
    "zh": "pending"
  },
  "is_latest": true,
  "version_index": 1,
  "version_count": 1,
  "previous_version_id": null,
  "newer_version_id": null,
  "latest_version_id": "3db0cdd7fe8a",
  "verdict_changed_from": null,
  "verdict_flip_days": null,
  "unstable_call": null,
  "review_state": "draft",
  "reviewer": null,
  "reviewer_name": null,
  "reviewed_at": null,
  "review_note": null,
  "approved_revision": null,
  "review_render_status": null,
  "open_comments": 0,
  "open_flags": 0,
  "failure_kind": null,
  "failure_summary_en": null,
  "failure_summary_zh": null,
  "failure_resets_at": null,
  "failure_spend_usd": null,
  "company_identity": null,
  "structure_version": null,
  "requested_audience": null,
  "rendered_at": null,
  "renderer_version": null
});

/** CIeNET, late-stage, the newer of two versions (no recorded call). */
export const CIENET_LATE_NEW = Object.freeze({
  "id": "e62b89cebcbc",
  "company_id": "cienet-technologies-beijing-co-ltd",
  "company_name": "CIeNET Technologies",
  "logo_domain": "cienet.com",
  "logo_url": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  "report_type": "Investment Memo (Late-Stage)",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "created_at": "2026-08-20T23:41:54.690393+00:00",
  "updated_at": "2026-09-22T23:27:40.661627+00:00",
  "kind": "investment_memo_latestage",
  "run_id": "2026-08-20__234154",
  "run_dir": "data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__234154__cienet-technologies-beijing-co-ltd__memo-run",
  "skill": "bsh-investment-memo-latestage-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__234154__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - Investment Memo - 2026-08-20__234154.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__234154__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - 投资备忘录 - 2026-08-20__234154.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": {
    "path": "/Users/bilelharrrat/BSH Updated UI From Main Repo /data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__234154__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - Investment Memo - 2026-08-20__234154.docx",
    "status": "passed",
    "finding_count": 0,
    "p0_count": 0,
    "findings": []
  },
  "memo_chinese_parity": {
    "en_path": "/Users/bilelharrrat/BSH Updated UI From Main Repo /data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__234154__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - Investment Memo - 2026-08-20__234154.docx",
    "zh_path": "/Users/bilelharrrat/BSH Updated UI From Main Repo /data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__234154__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - 投资备忘录 - 2026-08-20__234154.docx",
    "status": "passed",
    "finding_count": 0,
    "p0_count": 0,
    "findings": []
  },
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/e62b89cebcbc/download?language=en",
    "zh": "/api/reports/e62b89cebcbc/download?language=zh"
  },
  "preview_urls": {
    "en": "/api/reports/e62b89cebcbc/preview?language=en",
    "zh": "/api/reports/e62b89cebcbc/preview?language=zh"
  },
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null,
  "reader": {
    "v": 1,
    "headline": {
      "en": "We do not recommend a private allocation to CIeNET, and the reason is structural rather than a judgment on the operating business.",
      "zh": "我们不建议对 CIeNET 进行私募配置，其原因属于结构性问题，而非对其经营业务的评判。"
    },
    "decision": null,
    "buy_price_text": null,
    "buy_price_text_zh": null,
    "pass_kind": null,
    "memo_as_of": "2026-08-20",
    "evidence_latest": "2026-08-20",
    "sources_dated": 12,
    "sources_total": 12,
    "source": "package",
    "computed_at": "2026-09-22T23:27:40Z",
    "docs_stamp": "en:1787271656798852899,zh:1787271656945592428"
  },
  "decision": null,
  "buy_price": null,
  "buy_price_zh": null,
  "pass_kind": null,
  "call_label": null,
  "buffett_valuation": null,
  "market_inputs": null,
  "web_lookups": null,
  "retrieved_sources": null,
  "quality_warnings_zh": null,
  "quality_warning_items": null,
  "price": null,
  "price_date": null,
  "currency": null,
  "value_low": null,
  "value_central": null,
  "value_high": null,
  "buy_price_value": null,
  "mos_pct": null,
  "memo_fact_check": null,
  "has_document": true,
  "pdf_status": {
    "en": "pending",
    "zh": "pending"
  },
  "is_latest": true,
  "version_index": 2,
  "version_count": 2,
  "previous_version_id": "83f7153c1612",
  "newer_version_id": null,
  "latest_version_id": "e62b89cebcbc",
  "verdict_changed_from": null,
  "verdict_flip_days": null,
  "unstable_call": false,
  "review_state": "draft",
  "reviewer": null,
  "reviewer_name": null,
  "reviewed_at": null,
  "review_note": null,
  "approved_revision": null,
  "review_render_status": null,
  "open_comments": 0,
  "open_flags": 0,
  "failure_kind": null,
  "failure_summary_en": null,
  "failure_summary_zh": null,
  "failure_resets_at": null,
  "failure_spend_usd": null,
  "company_identity": null,
  "structure_version": null,
  "requested_audience": null,
  "rendered_at": null,
  "renderer_version": null
});

/** CIeNET, late-stage, the older version. */
export const CIENET_LATE_OLD = Object.freeze({
  "id": "83f7153c1612",
  "company_id": "cienet-technologies-beijing-co-ltd",
  "company_name": "CIeNET Technologies",
  "logo_domain": "cienet.com",
  "logo_url": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  "report_type": "Investment Memo (Late-Stage)",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "created_at": "2026-08-20T19:50:10.797081+00:00",
  "updated_at": "2026-09-22T23:27:40.712688+00:00",
  "kind": "investment_memo_latestage",
  "run_id": "2026-08-20__195010",
  "run_dir": "data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__195010__cienet-technologies-beijing-co-ltd__memo-run",
  "skill": "bsh-investment-memo-latestage-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__195010__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - Investment Memo - 2026-08-20__195010.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__195010__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - 投资备忘录 - 2026-08-20__195010.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": {
    "path": "/Users/bilelharrrat/BSH Updated UI From Main Repo /data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__195010__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - Investment Memo - 2026-08-20__195010.docx",
    "status": "passed",
    "finding_count": 0,
    "p0_count": 0,
    "findings": []
  },
  "memo_chinese_parity": {
    "en_path": "/Users/bilelharrrat/BSH Updated UI From Main Repo /data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__195010__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - Investment Memo - 2026-08-20__195010.docx",
    "zh_path": "/Users/bilelharrrat/BSH Updated UI From Main Repo /data/memos/cienet-technologies-beijing-co-ltd/2026-08-20__195010__cienet-technologies-beijing-co-ltd__memo-run/memo/CIeNET Technologies - 投资备忘录 - 2026-08-20__195010.docx",
    "status": "passed",
    "finding_count": 0,
    "p0_count": 0,
    "findings": []
  },
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/83f7153c1612/download?language=en",
    "zh": "/api/reports/83f7153c1612/download?language=zh"
  },
  "preview_urls": {
    "en": "/api/reports/83f7153c1612/preview?language=en",
    "zh": "/api/reports/83f7153c1612/preview?language=zh"
  },
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null,
  "reader": {
    "v": 1,
    "headline": {
      "en": "We do not recommend participating.",
      "zh": "我们不建议参与。"
    },
    "decision": null,
    "buy_price_text": null,
    "buy_price_text_zh": null,
    "pass_kind": null,
    "memo_as_of": "2026-08-20",
    "evidence_latest": "2026-08-20",
    "sources_dated": 9,
    "sources_total": 9,
    "source": "package",
    "computed_at": "2026-09-22T23:27:40Z",
    "docs_stamp": "en:1787258848706975416,zh:1787258848849698223"
  },
  "decision": null,
  "buy_price": null,
  "buy_price_zh": null,
  "pass_kind": null,
  "call_label": null,
  "buffett_valuation": null,
  "market_inputs": null,
  "web_lookups": null,
  "retrieved_sources": null,
  "quality_warnings_zh": null,
  "quality_warning_items": null,
  "price": null,
  "price_date": null,
  "currency": null,
  "value_low": null,
  "value_central": null,
  "value_high": null,
  "buy_price_value": null,
  "mos_pct": null,
  "memo_fact_check": null,
  "has_document": true,
  "pdf_status": {
    "en": "pending",
    "zh": "pending"
  },
  "is_latest": false,
  "version_index": 1,
  "version_count": 2,
  "previous_version_id": null,
  "newer_version_id": "e62b89cebcbc",
  "latest_version_id": "e62b89cebcbc",
  "verdict_changed_from": null,
  "verdict_flip_days": null,
  "unstable_call": null,
  "review_state": "draft",
  "reviewer": null,
  "reviewer_name": null,
  "reviewed_at": null,
  "review_note": null,
  "approved_revision": null,
  "review_render_status": null,
  "open_comments": 0,
  "open_flags": 0,
  "failure_kind": null,
  "failure_summary_en": null,
  "failure_summary_zh": null,
  "failure_resets_at": null,
  "failure_spend_usd": null,
  "company_identity": null,
  "structure_version": null,
  "requested_audience": null,
  "rendered_at": null,
  "renderer_version": null
});

/** A placeholder generator's record: complete, no document. */
export const PLACEHOLDER_FINANCIAL = Object.freeze({
  "id": "f831d124b01d",
  "company_id": "cienet-technologies-beijing-co-ltd",
  "company_name": "CIeNET Technologies",
  "logo_domain": "cienet.com",
  "logo_url": "https://t1.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=http://cienet.com&size=128",
  "report_type": "Financial Analysis",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Complete",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "created_at": "2026-08-20T19:37:55.915047+00:00",
  "updated_at": "2026-08-20T19:38:03.189319+00:00",
  "kind": null,
  "run_id": null,
  "run_dir": null,
  "skill": null,
  "memo_files": [],
  "internal_memo_files": [],
  "artifacts_available": false,
  "memo_quality_lint": null,
  "memo_chinese_parity": null,
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": null,
  "preview_urls": null,
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null,
  "reader": null,
  "decision": null,
  "buy_price": null,
  "buy_price_zh": null,
  "pass_kind": null,
  "call_label": null,
  "buffett_valuation": null,
  "market_inputs": null,
  "web_lookups": null,
  "retrieved_sources": null,
  "quality_warnings_zh": null,
  "quality_warning_items": null,
  "price": null,
  "price_date": null,
  "currency": null,
  "value_low": null,
  "value_central": null,
  "value_high": null,
  "buy_price_value": null,
  "mos_pct": null,
  "memo_fact_check": null,
  "has_document": false,
  "pdf_status": null,
  "is_latest": null,
  "version_index": null,
  "version_count": null,
  "previous_version_id": null,
  "newer_version_id": null,
  "latest_version_id": null,
  "verdict_changed_from": null,
  "verdict_flip_days": null,
  "unstable_call": null,
  "review_state": "draft",
  "reviewer": null,
  "reviewer_name": null,
  "reviewed_at": null,
  "review_note": null,
  "approved_revision": null,
  "review_render_status": null,
  "open_comments": 0,
  "open_flags": 0,
  "failure_kind": null,
  "failure_summary_en": null,
  "failure_summary_zh": null,
  "failure_resets_at": null,
  "failure_spend_usd": null,
  "company_identity": null,
  "structure_version": null,
  "requested_audience": null,
  "rendered_at": null,
  "renderer_version": null
});

/** GET /api/reports/3cb7ec52fa15/diff — the Buffett pair. */
export const GOOGLE_DIFF = Object.freeze({
  "report_id": "3cb7ec52fa15",
  "against_id": "37acb580ef1e",
  "kind": "buffett_investment_memo",
  "current": {
    "id": "3cb7ec52fa15",
    "created_at": "2026-08-25T18:48:56.743036+00:00",
    "report_type": "Buffett Investment Memo",
    "status": "complete",
    "decision": "Pass",
    "memo_as_of": "2026-08-25",
    "headline": {
      "en": "I think the core business is one of the finest commercial franchises ever assembled, but the price on offer — roughly $349 a share and about $4.3 trillion of equity value — asks me to pay in full today for a capital-spending program whose returns are entirely unproven.",
      "zh": "我认为核心业务是商业史上最出色的特许经营权之一，但当前报价——每股约 349 美元、约 4.3 万亿美元的股权价值——要求我今天就为一项回报完全未经验证的资本开支计划全额付款。"
    }
  },
  "previous": {
    "id": "37acb580ef1e",
    "created_at": "2026-08-25T00:31:53.886490+00:00",
    "report_type": "Buffett Investment Memo",
    "status": "complete",
    "decision": "Buy",
    "memo_as_of": "2026-08-25",
    "headline": {
      "en": "I would own this business at today's quote of about $345 a share, and Berkshire does own it — a little over 106 million shares at the end of June, our third-largest common stock position.",
      "zh": "以今天约 345 美元的股价，我愿意持有这家企业；伯克希尔也确实持有它——截至 6 月底略超过 1.06 亿股，是我们股票组合中的第三大仓位。"
    }
  },
  "days_apart": 0.76,
  "verdict": {
    "current": "Pass",
    "previous": "Buy",
    "changed": true,
    "unstable": true
  },
  "tables": [],
  "sources": null,
  "spine": null,
  "buffett": {
    "fields": [
      {
        "field": "decision",
        "current": "Pass",
        "previous": "Buy",
        "changed": true
      },
      {
        "field": "buy_price",
        "current": "$215 per share or less (about $2.65 trillion equity value)",
        "previous": "Up to about $360 per Alphabet share (roughly $4.4 trillion for the whole company); I stop buying above $400",
        "changed": true
      }
    ]
  },
  "notes": []
});

/** GET /api/reports/e62b89cebcbc/diff — the late-stage pair, rows trimmed to one of each match kind. */
export const CIENET_DIFF = Object.freeze({
  "report_id": "e62b89cebcbc",
  "against_id": "83f7153c1612",
  "kind": "investment_memo_latestage",
  "current": {
    "id": "e62b89cebcbc",
    "created_at": "2026-08-20T23:41:54.690393+00:00",
    "report_type": "Investment Memo (Late-Stage)",
    "status": "complete",
    "decision": null,
    "memo_as_of": "2026-08-20",
    "headline": {
      "en": "We do not recommend a private allocation to CIeNET, and the reason is structural rather than a judgment on the operating business.",
      "zh": "我们不建议对 CIeNET 进行私募配置，其原因属于结构性问题，而非对其经营业务的评判。"
    }
  },
  "previous": {
    "id": "83f7153c1612",
    "created_at": "2026-08-20T19:50:10.797081+00:00",
    "report_type": "Investment Memo (Late-Stage)",
    "status": "complete",
    "decision": null,
    "memo_as_of": "2026-08-20",
    "headline": {
      "en": "We do not recommend participating.",
      "zh": "我们不建议参与。"
    }
  },
  "days_apart": 0.16,
  "verdict": {
    "current": null,
    "previous": null,
    "changed": false,
    "unstable": false
  },
  "tables": [
    {
      "component": "scenario_analysis",
      "headers": {
        "current": [
          {
            "en": "Scenario",
            "zh": "情景"
          },
          {
            "en": "Revenue and margin",
            "zh": "收入与利润率"
          },
          {
            "en": "Implied enterprise value",
            "zh": "隐含企业价值"
          },
          {
            "en": "What drives it",
            "zh": "驱动因素"
          }
        ],
        "previous": [
          {
            "en": "Scenario",
            "zh": "情景"
          },
          {
            "en": "What happens",
            "zh": "情景描述"
          },
          {
            "en": "Modeled entity revenue",
            "zh": "测算的主体收入"
          },
          {
            "en": "Implied enterprise value",
            "zh": "隐含企业价值"
          },
          {
            "en": "Weight",
            "zh": "权重"
          }
        ]
      },
      "rows": [
        {
          "key": "bear",
          "match": "scenario",
          "current": [
            {
              "en": "Bear (30%)",
              "zh": "悲观情形（30%）"
            },
            {
              "en": "~$80M revenue declining 1% to 3% per year, 5% to 6% operating margin",
              "zh": "收入约 $80M，每年下滑 1% 至 3%，经营利润率 5% 至 6%"
            },
            {
              "en": "~$20M to $30M",
              "zh": "约 $20M 至 $30M"
            },
            {
              "en": "Automotive stays down as it did at group level at -16% in FY2025, AI test generation deflates rates across the 600-plus tester book, and one Western tier-one moves engineering out of Greater China.",
              "zh": "汽车行业延续集团层面 FY2025 -16% 的下滑态势，AI 测试用例生成拉低 600 人以上测试团队的整体费率，且一家西方一级供应商将工程业务迁出大中华区。"
            }
          ],
          "previous": [
            {
              "en": "Bear",
              "zh": "悲观情形"
            },
            {
              "en": "AI tooling compresses testing and validation hours while procurement benchmarks rates down. Automotive and telecom budgets stay under the pressure ALTEN reported in 2025. Western clients mandate non-China delivery for part of the book, raising unit costs.",
              "zh": "AI 工具压缩测试与验证工时，同时采购方以标杆比价压低费率。汽车与电信预算持续承受 ALTEN 于 2025 年所报告的压力。西方客户要求部分业务改由非中国地区交付，推高单位成本。"
            },
            {
              "en": "$70M to $85M",
              "zh": "$70M 至 $85M"
            },
            {
              "en": "$56M to $85M at 0.8x to 1.0x revenue",
              "zh": "按 0.8x 至 1.0x 收入倍数计为 $56M 至 $85M"
            },
            {
              "en": "35%",
              "zh": "35%"
            }
          ],
          "changed": true
        },
        {
          "key": "access across all overlay three",
          "match": "none",
          "current": [
            {
              "en": "Access overlay across all three",
              "zh": "适用于上述三种情形的参与路径叠加项"
            },
            {
              "en": "Not applicable to a private allocation",
              "zh": "不适用于私募配置"
            },
            {
              "en": "No entry price exists",
              "zh": "不存在入场价格"
            },
            {
              "en": "Every lane reaches investors only through ALTEN equity, where CIeNET is about 2% of revenue. A correct view of the unit is not an investable edge until a carve-out creates a security.",
              "zh": "所有路径均只能通过 ALTEN 股票触达投资人，而 CIeNET 仅约占其收入 2%。在业务分拆产生可投资标的之前，对该单元的正确判断并不构成可投资的优势。"
            }
          ],
          "previous": null,
          "changed": null
        },
        {
          "key": "all scenarios",
          "match": "none",
          "current": null,
          "previous": [
            {
              "en": "All scenarios",
              "zh": "全部情景"
            },
            {
              "en": "Every figure above is modeled from a headcount proxy and a six-year-old revenue anchor, not from entity accounts.",
              "zh": "上述每一个数字均依据人员规模替代指标与一个已有六年之久的收入锚点测算得出，而非来自主体财务账目。"
            },
            {
              "en": "Range width 12.8x before scenario narrowing",
              "zh": "情景收窄前的区间宽度为 12.8 倍"
            },
            {
              "en": "No entry price exists to compare any of these values against",
              "zh": "不存在可供比对上述任何估值的进入价格"
            },
            {
              "en": "Not applicable",
              "zh": "不适用"
            }
          ],
          "changed": null
        }
      ]
    },
    {
      "component": "risk_register",
      "rows": [
        {
          "risk_type": {
            "current": {
              "en": "Structure",
              "zh": "结构"
            },
            "previous": {
              "en": "Deal Structure",
              "zh": "交易结构"
            }
          },
          "match": "fuzzy",
          "current": {
            "rating": {
              "en": "9/10: no instrument exists, so nothing here becomes investable without a new transaction.",
              "zh": "9/10：不存在任何投资工具，因此在没有新交易的情况下，此处的任何内容都不具备可投资性。"
            },
            "likelihood": null,
            "impact": null,
            "watch": {
              "en": "Any ALTEN announcement of a carve-out, disposal, or minority sale; ALTEN investor communications that name CIeNET as a separable unit; a change to CIeNET's wholly owned status in ALTEN FY2026 reporting expected in early 2027.",
              "zh": "ALTEN 发布的任何关于分拆、处置或少数股权出售的公告；ALTEN 投资者沟通材料中将 CIeNET 列为可分离业务单元的表述；预计于 2027 年初发布的 ALTEN FY2026 报告中 CIeNET 全资持有状态的变化。"
            }
          },
          "previous": {
            "rating": {
              "en": "9/10: on its own this removes the transaction, regardless of how good the operating business is.",
              "zh": "9/10：仅此一项即令交易无从成立，无论经营业务本身多么优秀。"
            },
            "likelihood": null,
            "impact": null,
            "watch": {
              "en": "A marketed carve-out, minority stake, or management buyout from ALTEN; any ALTEN disclosure signaling divestment of the CIeNET book; an intermediary presenting a named and priced instrument.",
              "zh": "ALTEN 对外推介的分拆、少数股权或管理层收购；ALTEN 任何显示拟剥离 CIeNET 业务的披露；中介机构提出标的明确、报价明确的可投资工具。"
            }
          },
          "rating_changed": true
        },
        {
          "risk_type": {
            "current": {
              "en": "Technology",
              "zh": "技术"
            },
            "previous": {
              "en": "Technology",
              "zh": "技术"
            }
          },
          "match": "exact",
          "current": {
            "rating": {
              "en": "8/10: it attacks the largest disclosed capability block and shows up in price before it shows up in headcount.",
              "zh": "8/10：该风险直击已披露的最大能力板块，且会先在价格上显现，而后才反映到人数上。"
            },
            "likelihood": null,
            "impact": null,
            "watch": {
              "en": "Evidence of outcome-based or value-based pricing replacing hourly rates in CIeNET contracts; ALTEN commentary on testing and validation pricing in FY2026 results; whether the published tester count grows, holds, or shrinks in the next company refresh.",
              "zh": "CIeNET 合同中以结果导向或价值导向定价取代小时费率的证据；ALTEN 在 FY2026 业绩中关于测试与验证业务定价的表述；公司下一次信息更新中已披露的测试工程师人数是增长、持平还是收缩。"
            }
          },
          "previous": {
            "rating": {
              "en": "8/10: it attacks the revenue mechanism itself and would push the outcome below base case.",
              "zh": "8/10：它直接冲击收入形成机制本身，会将结果推至基准情景之下。"
            },
            "likelihood": null,
            "impact": null,
            "watch": {
              "en": "Evidence of outcome-based or fixed-price AI offerings replacing time and materials pricing; disclosed AI attach rates or AI-linked contract values; ALTEN commentary on hours per delivered scope across 2026 and 2027 reporting.",
              "zh": "以成果计价或固定价格的 AI 服务取代按工时与材料计价的证据；对外披露的 AI 附加率或与 AI 挂钩的合同金额；ALTEN 在 2026 年与 2027 年财报中对单位交付范围所需工时的评论。"
            }
          },
          "rating_changed": true
        },
        {
          "risk_type": {
            "current": {
              "en": "Regulatory",
              "zh": "监管"
            },
            "previous": null
          },
          "match": "none",
          "current": {
            "rating": {
              "en": "7/10: real and directional, but it removes accounts one at a time rather than all at once.",
              "zh": "7/10：风险真实且方向明确，但其影响是逐个客户流失，而非一次性全面冲击。"
            },
            "likelihood": null,
            "impact": null,
            "watch": {
              "en": "Named client relocations of engineering work out of China; new export control or data localization rules touching automotive and semiconductor software; growth in CIeNET's North America, Canada, and Europe centers relative to its Greater China footprint.",
              "zh": "具名客户将工程作业迁出中国的情况；涉及汽车与半导体软件的新出口管制或数据本地化规则；CIeNET 北美、加拿大与欧洲交付中心相对于其大中华区布局的增长情况。"
            }
          },
          "previous": null,
          "rating_changed": null
        }
      ]
    },
    {
      "component": "key_metrics_snapshot",
      "headers": {
        "current": [
          {
            "en": "Metric",
            "zh": "指标"
          },
          {
            "en": "Figure",
            "zh": "数值"
          },
          {
            "en": "Source class and treatment",
            "zh": "来源类别与处理方式"
          }
        ],
        "previous": [
          {
            "en": "Metric",
            "zh": "指标"
          },
          {
            "en": "Disclosed position",
            "zh": "已披露情况"
          },
          {
            "en": "Treatment and valuation sensitivity",
            "zh": "处理方式与估值敏感性"
          }
        ]
      },
      "rows": [
        {
          "label": {
            "current": {
              "en": "Ownership",
              "zh": "所有权"
            },
            "previous": {
              "en": "Ownership",
              "zh": "股权结构"
            }
          },
          "match": "exact",
          "current": [
            {
              "en": "100% held by ALTEN S.A. since 8 November 2021",
              "zh": "ALTEN S.A. 自 2021 年 11 月 8 日起持有 100% 股权"
            },
            {
              "en": "Acquirer disclosure. The controlling fact for access and the reason no private allocation is available.",
              "zh": "收购方披露。该事实决定了准入条件，也是无法获得私募配置额度的原因。"
            }
          ],
          "previous": [
            {
              "en": "100% ALTEN (Euronext Paris: ATE) since 8 November 2021",
              "zh": "自 2021 年 11 月 8 日起由 ALTEN（Euronext Paris: ATE）持股 100%"
            },
            {
              "en": "Parent-reported and corroborated by independent coverage. This removes any standalone capital structure and is the binding constraint on the investment case.",
              "zh": "由母公司披露并经独立报道印证。这消除了任何独立资本结构的可能，是投资逻辑面临的约束性限制。"
            }
          ],
          "changed": true
        },
        {
          "label": {
            "current": {
              "en": "Growth",
              "zh": "增长"
            },
            "previous": {
              "en": "Growth rate",
              "zh": "增长率"
            }
          },
          "match": "fuzzy",
          "current": [
            {
              "en": "~1.5% per year headcount CAGR from 2020 to 2026",
              "zh": "2020 年至 2026 年员工人数 CAGR 约为每年 1.5%"
            },
            {
              "en": "Derived from company headcount disclosures; used as the base-case revenue growth proxy in the absence of reported revenue.",
              "zh": "根据公司披露的员工人数推导；在缺少已报告收入的情况下，用作基准情形下的收入增长替代指标。"
            }
          ],
          "previous": [
            {
              "en": "Not published at entity level",
              "zh": "主体层面未披露"
            },
            {
              "en": "Proxied by ALTEN group organic growth of 1.6% in H1 2026 with the International zone at negative 0.5% and China described as stable in the first quarter of 2026. Our base case is flat.",
              "zh": "以 ALTEN 集团 2026 年上半年 1.6% 的有机增长作为代理指标，其中国际区域为负 0.5%，中国区在 2026 年第一季度被描述为保持平稳。我们的基准情形为零增长。"
            }
          ],
          "changed": true
        },
        {
          "label": {
            "current": {
              "en": "Security available to us",
              "zh": "我们可获得的证券"
            },
            "previous": null
          },
          "match": "none",
          "current": [
            {
              "en": "None offered",
              "zh": "无任何要约"
            },
            {
              "en": "No round, instrument, or process exists; treated as a no-action situation rather than a pricing question.",
              "zh": "不存在融资轮次、投资工具或交易流程；按无行动情形处理，而非作为定价问题处理。"
            }
          ],
          "previous": null,
          "changed": null
        }
      ]
    },
    {
      "component": "deal_terms",
      "headers": {
        "current": [
          {
            "en": "Term",
            "zh": "条款"
          },
          {
            "en": "Position",
            "zh": "现状"
          },
          {
            "en": "What it means for investors",
            "zh": "对投资人的含义"
          }
        ],
        "previous": [
          {
            "en": "Deal element",
            "zh": "交易要素"
          },
          {
            "en": "Position",
            "zh": "当前情况"
          },
          {
            "en": "What it means economically",
            "zh": "经济含义"
          }
        ]
      },
      "rows": [
        {
          "label": {
            "current": {
              "en": "Instrument offered to us",
              "zh": "向我方提供的投资工具"
            },
            "previous": {
              "en": "Instrument offered to us",
              "zh": "向我们提供的投资工具"
            }
          },
          "match": "exact",
          "current": [
            {
              "en": "None",
              "zh": "无"
            },
            {
              "en": "No primary round, secondary block, or structured interest exists. There is nothing to price, so we hold a watch position and commit no capital.",
              "zh": "不存在任何一级融资轮次、二级份额或结构化权益。没有可供定价的标的，因此我们维持观察状态，不投入任何资本。"
            }
          ],
          "previous": [
            {
              "en": "None",
              "zh": "无"
            },
            {
              "en": "No SAFE, preferred round, secondary block, or vehicle interest in CIeNET has been presented. Without a named instrument there is no entry price to test and no economics to model.",
              "zh": "我们未收到任何有关 CIeNET 的 SAFE、优先股融资轮次、老股转让份额或投资载体权益。缺少明确的投资工具，就不存在可供检验的进入价格，也无从对其经济性建模。"
            }
          ],
          "changed": true
        },
        {
          "label": {
            "current": {
              "en": "Acquisition consideration",
              "zh": "收购对价"
            },
            "previous": {
              "en": "2021 acquisition consideration",
              "zh": "2021 年收购对价"
            }
          },
          "match": "fuzzy",
          "current": [
            {
              "en": "Not published for the November 2021 transaction",
              "zh": "2021 年 11 月的交易未予披露"
            },
            {
              "en": "No transaction mark exists to anchor a valuation, so the modeled $20M to $60M range rests on parent economics rather than on a precedent price. Non-disclosure of a bolt-on price is routine for French issuers and is weak evidence of size in either direction.",
              "zh": "不存在可用于锚定估值的交易价格，因此 $20M 至 $60M 的测算区间建立在母公司经济性之上，而非先例价格。法国发行人对补强型收购价格不予披露属常规做法，无论据此对规模作出何种推断，均属薄弱证据。"
            }
          ],
          "previous": [
            {
              "en": "Not disclosed by ALTEN",
              "zh": "ALTEN 未予披露"
            },
            {
              "en": "Non-disclosure by a Euronext issuer indicates the transaction sat below group materiality thresholds, which loosely caps CIeNET's 2021 value in the low hundreds of millions. Consistent with our modeled range but not confirmation of it.",
              "zh": "作为泛欧交易所上市发行人未予披露，表明该交易低于集团重要性门槛，从而大致将 CIeNET 在 2021 年的价值上限限定在数亿的较低区间。这与我们的建模区间一致，但并不构成对该区间的确认。"
            }
          ],
          "changed": true
        },
        {
          "label": {
            "current": {
              "en": "Ownership and control",
              "zh": "股权与控制权"
            },
            "previous": null
          },
          "match": "none",
          "current": [
            {
              "en": "ALTEN S.A. holds 100%, acquired 8 November 2021",
              "zh": "ALTEN S.A. 持股 100%，于 2021 年 11 月 8 日完成收购"
            },
            {
              "en": "A single corporate owner controls every decision about the asset, including whether it is ever separable. Outside investors have no route to influence timing or terms.",
              "zh": "单一企业股东掌控与该资产相关的全部决策，包括其是否具备可分拆性。外部投资人没有任何途径影响交易时点或条款。"
            }
          ],
          "previous": null,
          "changed": null
        }
      ]
    }
  ],
  "sources": {
    "component": "sources",
    "matched": 1,
    "current_total": 12,
    "previous_total": 9,
    "rows": [
      {
        "match": "title",
        "current": {
          "id": "S3",
          "title": {
            "en": "ALTEN FY2025 annual results",
            "zh": "ALTEN FY2025 年度业绩"
          },
          "url": null,
          "as_of": "2025-12-31",
          "class": {
            "en": "public filings",
            "zh": null
          }
        },
        "previous": {
          "id": "S2",
          "title": {
            "en": "ALTEN FY2025 annual results",
            "zh": "ALTEN 2025 财年年度业绩"
          },
          "url": null,
          "as_of": "2025-12-31",
          "class": {
            "en": "public filings",
            "zh": null
          }
        }
      },
      {
        "match": "none",
        "current": {
          "id": "S1",
          "title": {
            "en": "ALTEN announcement of the CIeNET Group acquisition",
            "zh": "ALTEN 关于收购 CIeNET 集团的公告"
          },
          "url": null,
          "as_of": "2021-11-08",
          "class": {
            "en": "investor materials",
            "zh": null
          }
        },
        "previous": null
      },
      {
        "match": "none",
        "current": {
          "id": "S2",
          "title": {
            "en": "CIeNET corporate website and service pages",
            "zh": "CIeNET 公司官网及服务介绍页面"
          },
          "url": null,
          "as_of": "2026-08-20",
          "class": {
            "en": "company-reported",
            "zh": null
          }
        },
        "previous": null
      },
      {
        "match": "none",
        "current": null,
        "previous": {
          "id": "S1",
          "title": {
            "en": "ALTEN H1 and Q2 2026 results disclosure",
            "zh": "ALTEN 2026 年上半年及第二季度业绩披露"
          },
          "url": null,
          "as_of": "2026-06-30",
          "class": {
            "en": "public filings",
            "zh": null
          }
        }
      }
    ]
  },
  "spine": null,
  "buffett": null,
  "notes": [
    "Some rows were paired by similar labels; they are shown side by side, not as additions or removals."
  ]
});

