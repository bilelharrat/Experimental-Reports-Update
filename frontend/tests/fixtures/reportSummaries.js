// Real report records from GET /api/reports (server/api.py ReportSummary),
// trimmed for the specs: the renderer contract's expected-file list is cut
// and absolute paths are shortened to data/…; every other field is as the
// API sends it. Build variants with `withReport(base, patch)` rather than
// inventing fields — the specs used to pass on shapes the server never sent
// (`title`, `can_open`, `overall_score`).

/** ZaiNar, late-stage memo, complete_with_warnings (Chinese parity P0). */
export const ZAINAR_WARNINGS = Object.freeze({
  "id": "e8ab6007ccec",
  "company_id": "zainar-inc",
  "company_name": "ZaiNar, Inc.",
  "logo_domain": null,
  "logo_url": null,
  "report_type": "Investment Memo (Late-Stage)",
  "audience": "Internal",
  "language": "en",
  "status": "complete_with_warnings",
  "progress": 100,
  "stage": "Memo ready (quality warnings)",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "renderer_contract": {
    "run_dir": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run",
    "errors": []
  },
  "created_at": "2026-08-31T22:48:28.992755+00:00",
  "updated_at": "2026-08-31T23:10:10.900659+00:00",
  "kind": "investment_memo_latestage",
  "run_id": "2026-08-31__224828",
  "run_dir": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run",
  "skill": "bsh-investment-memo-latestage-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/memo/ZaiNar, Inc. - Investment Memo - 2026-08-31__224828.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/memo/ZaiNar, Inc. - 投资备忘录 - 2026-08-31__224828.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": {
    "path": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/memo/ZaiNar, Inc. - Investment Memo - 2026-08-31__224828.docx",
    "status": "passed",
    "finding_count": 0,
    "p0_count": 0,
    "findings": []
  },
  "memo_chinese_parity": {
    "en_path": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/memo/ZaiNar, Inc. - Investment Memo - 2026-08-31__224828.docx",
    "zh_path": "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/memo/ZaiNar, Inc. - 投资备忘录 - 2026-08-31__224828.docx",
    "status": "failed",
    "finding_count": 1,
    "p0_count": 1,
    "findings": [
      {
        "severity": "P0",
        "code": "zh_core_section_missing",
        "location": "financial_forecast_valuation",
        "snippet": "financial_forecast_valuation",
        "suggestion": "Render every required core section in the Chinese memo."
      }
    ]
  },
  "quality_warnings": [
    "Chinese memo parity gate found 1 P0 finding. See data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/logs/memo_chinese_parity.md."
  ],
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/e8ab6007ccec/download?language=en",
    "zh": "/api/reports/e8ab6007ccec/download?language=zh"
  },
  "preview_urls": null,
  "memo_mode": null,
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": true,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": null
});

/** Coca-Cola, Buffett memo, complete, no gate blocks. */
export const KO_BUFFETT = Object.freeze({
  "id": "1ec8dc8b2a57",
  "company_id": "ko",
  "company_name": "Coca Cola Co",
  "logo_domain": null,
  "logo_url": null,
  "report_type": "Buffett Investment Memo",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "renderer_contract": null,
  "created_at": "2026-08-25T00:09:22.057769+00:00",
  "updated_at": "2026-08-25T00:17:28.360818+00:00",
  "kind": "buffett_investment_memo",
  "run_id": "2026-08-25__000922",
  "run_dir": "data/memos/ko/2026-08-25__000922__ko__buffett-memo-run",
  "skill": "bsh-buffett-investment-memo-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/ko/2026-08-25__000922__ko__buffett-memo-run/memo/Coca Cola Co - Buffett Investment Memo - 2026-08-25__000922.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/ko/2026-08-25__000922__ko__buffett-memo-run/memo/Coca Cola Co - 巴菲特投资备忘录 - 2026-08-25__000922.docx"
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
    "en": "/api/reports/1ec8dc8b2a57/download?language=en",
    "zh": "/api/reports/1ec8dc8b2a57/download?language=zh"
  },
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
  "dismissed_at": null
});

/** Anthropic, late-stage memo, complete with both gates passed. */
export const ANTHROPIC_COMPLETE = Object.freeze({
  "id": "4d9369783cb0",
  "company_id": "anthropic-pbc",
  "company_name": "Anthropic",
  "logo_domain": null,
  "logo_url": null,
  "report_type": "Investment Memo (Late-Stage)",
  "audience": "Internal",
  "language": "en",
  "status": "complete",
  "progress": 100,
  "stage": "Memo ready",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "renderer_contract": {
    "run_dir": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run",
    "errors": []
  },
  "created_at": "2026-09-01T18:51:14.997024+00:00",
  "updated_at": "2026-09-01T19:24:03.696431+00:00",
  "kind": "investment_memo_latestage",
  "run_id": "2026-09-01__185114",
  "run_dir": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run",
  "skill": "bsh-investment-memo-latestage-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run/memo/Anthropic - Investment Memo - 2026-09-01__185114.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run/memo/Anthropic - 投资备忘录 - 2026-09-01__185114.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": true,
  "memo_quality_lint": {
    "path": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run/memo/Anthropic - Investment Memo - 2026-09-01__185114.docx",
    "status": "passed",
    "finding_count": 0,
    "p0_count": 0,
    "findings": []
  },
  "memo_chinese_parity": {
    "en_path": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run/memo/Anthropic - Investment Memo - 2026-09-01__185114.docx",
    "zh_path": "data/memos/anthropic-pbc/2026-09-01__185114__anthropic-pbc__memo-run/memo/Anthropic - 投资备忘录 - 2026-09-01__185114.docx",
    "status": "passed",
    "finding_count": 1,
    "p0_count": 0,
    "findings": [
      {
        "severity": "P1",
        "code": "english_only_body_prose",
        "location": "table 1 row 5 cell 2",
        "snippet": "Series H at $965B post-money (May 2026); secondary $1.2-1.5T (Jul-Aug 2026); $2T+ October 2026 listing target",
        "suggestion": "Translate body prose into professional Chinese."
      }
    ]
  },
  "quality_warnings": null,
  "analysis_session_id": "aff2acddf0fe",
  "analysis_session_approved": false,
  "download_urls": {
    "en": "/api/reports/4d9369783cb0/download?language=en",
    "zh": "/api/reports/4d9369783cb0/download?language=zh"
  },
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
  "dismissed_at": null
});

/** The one failed record on disk: an Auto run that crashed, then cleared. */
export const FAILED_DISMISSED = Object.freeze({
  "id": "d36911c310ab",
  "company_id": "中经网数据有限公司",
  "company_name": "x",
  "logo_domain": null,
  "logo_url": null,
  "report_type": "Investment Report (Auto)",
  "audience": "Internal",
  "language": "en",
  "status": "failed_during_analysis",
  "progress": 10,
  "stage": "Analysis crashed",
  "error": null,
  "failure_phase": null,
  "failure_detail": null,
  "renderer_contract": null,
  "created_at": "2026-09-15T04:32:29.365649+00:00",
  "updated_at": "2026-09-15T04:32:32.600158+00:00",
  "kind": "investment_memo_latestage",
  "run_id": "2026-09-15__043229",
  "run_dir": "data/memos/中经网数据有限公司/2026-09-15__043229__中经网数据有限公司__memo-run",
  "skill": "bsh-investment-memo-latestage-v1",
  "memo_files": [
    {
      "language": "en",
      "path": "data/memos/中经网数据有限公司/2026-09-15__043229__中经网数据有限公司__memo-run/memo/x - Investment Memo - 2026-09-15__043229.docx"
    },
    {
      "language": "zh",
      "path": "data/memos/中经网数据有限公司/2026-09-15__043229__中经网数据有限公司__memo-run/memo/x - 投资备忘录 - 2026-09-15__043229.docx"
    }
  ],
  "internal_memo_files": [],
  "artifacts_available": false,
  "memo_quality_lint": null,
  "memo_chinese_parity": null,
  "quality_warnings": null,
  "analysis_session_id": null,
  "analysis_session_approved": false,
  "download_urls": null,
  "preview_urls": null,
  "memo_mode": "auto",
  "studio_investigation": null,
  "studio_generate": null,
  "resume_available": false,
  "trigger": null,
  "auto_run_id": null,
  "report_ready_at": null,
  "run_finished_at": null,
  "superseded_by": null,
  "dismissed_at": "2026-09-15T04:32:32.599321+00:00"
});

/** A copy of a real record with some fields changed. */
export function withReport(base, patch = {}) {
  return JSON.parse(JSON.stringify({ ...base, ...patch }));
}

/** A memo run in flight: the late-stage record before its documents land. */
export function runningReport(patch = {}) {
  return withReport(ANTHROPIC_COMPLETE, {
    id: "run000000001",
    status: "analyzing",
    stage: "Phase 2 - Parallel analysis passes",
    progress: 40,
    download_urls: null,
    preview_urls: null,
    memo_quality_lint: null,
    memo_chinese_parity: null,
    renderer_contract: null,
    resume_available: false,
    ...patch,
  });
}

/**
 * A run paused after its English memo (the Generate dialog's "Pause after
 * English"): status english_ready_paused, the English docx on file, no
 * Chinese yet, and the run's quality metrics (memo_quality_metrics).
 */
export function pausedReport(patch = {}) {
  return withReport(ANTHROPIC_COMPLETE, {
    id: "pause0000001",
    status: "english_ready_paused",
    stage: "English ready — review before Chinese",
    progress: 60,
    memo_files: [
      {
        language: "en",
        path: "data/memos/anthropic-pbc/2026-09-23__101010__anthropic-pbc__memo-run/memo/Anthropic - Investment Memo - 2026-09-23__101010.docx",
      },
    ],
    download_urls: { en: "/api/reports/pause0000001/download?language=en" },
    memo_chinese_parity: null,
    resume_available: true,
    quality_warning_items: [
      {
        gate: "length",
        language: "en",
        section: "risks",
        severity: "P2",
        code: "section_over_cap",
        summary_en: "Risks runs 5,319 words against a 5,200-word cap.",
        summary_zh: "风险章节 5,319 词，超出 5,200 词上限。",
      },
    ],
    quality_metrics: {
      traced_pct: 72,
      unsupported_headline_figures: 0,
      repetition_index: 0.04,
      words_total: 21_400,
      words_by_section: { executive_summary: 1_200, risks: 5_319 },
      over_cap_sections: ["risks"],
      metric_conflicts: [],
      zh_term_drift: 0,
      untranslated_zh_lines: 0,
    },
    ...patch,
  });
}

/** The working papers GET /api/reports/{id} lists for the ZaiNar run. */
export const ZAINAR_ANALYSIS_ARTIFACTS = Object.freeze([
  {
    label: "Arithmetic / pressure tests",
    filename: "pressure_tests.md",
    path: "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/analysis/pressure_tests.md",
    download_url: "/api/reports/e8ab6007ccec/download?artifact=analysis&file=pressure_tests.md",
  },
  {
    label: "Growth bridge",
    filename: "growth_bridge.md",
    path: "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/analysis/growth_bridge.md",
    download_url: "/api/reports/e8ab6007ccec/download?artifact=analysis&file=growth_bridge.md",
  },
  {
    label: "Claim register",
    filename: "claim_register.md",
    path: "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/analysis/claim_register.md",
    download_url: "/api/reports/e8ab6007ccec/download?artifact=analysis&file=claim_register.md",
  },
  {
    label: "Countercase analysis",
    filename: "countercase.md",
    path: "data/memos/zainar-inc/2026-08-31__224828__zainar-inc__memo-run/analysis/countercase.md",
    download_url: "/api/reports/e8ab6007ccec/download?artifact=analysis&file=countercase.md",
  },
]);
