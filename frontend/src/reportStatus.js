// What a report is, in words people read: its type label, its state, why a
// run failed, what a complete-with-warnings memo was flagged for, and the
// memo jobs coming and going on the shared active-jobs poll.
//
// The Reports desk, its document viewer, the jobs rail and the company
// desk's report card all used to read report records their own way — and
// several read fields the API never sends (`title`, `can_open`,
// `overall_score`). This module is the one reading of the real
// ReportSummary shape (server/api.py ReportSummary), so the surfaces agree.
//
// Wire values stay byte-identical: `report_type` and `kind` are compared
// against these literals, never rewritten.

import { getCurrentScope, onScopeDispose, ref } from "vue";

// ---------------------------------------------------------------------------
// Type labels
// ---------------------------------------------------------------------------

// report_type → i18n key. The label follows report_type, not kind, so an
// Auto run keeps its own name after it resolves to the late-stage kind.
const REPORT_TYPE_KEYS = {
  "Investment Report (Auto)": "research.report_type.investment_report_auto",
  "Investment Memo (Late-Stage)": "research.report_type.investment_memo_late_stage",
  "Buffett Investment Memo": "research.report_type.buffett_investment_memo",
  "Financial Analysis": "research.report_type.financial_analysis",
  "Market Analysis": "research.report_type.market_analysis",
  Background: "research.report_type.background",
  // Stored rows from before the Auto type still carry the old name.
  "Investment Report": "research.report_type.investment_report",
};

// kind → i18n key, for rows without a known report_type (the Hormuz
// appendix has neither company nor audience, and older records vary).
const KIND_KEYS = {
  investment_memo_latestage: "research.report_type.investment_memo_late_stage",
  buffett_investment_memo: "research.report_type.buffett_investment_memo",
  hormuz_appendix: "research.report_type.hormuz_appendix",
};

// The kinds the memo pipeline writes: these runs have analysis passes,
// a live stream and a resume path.
export const MEMO_KINDS = new Set(["investment_memo_latestage", "buffett_investment_memo"]);

// Report types that only the placeholder generator ever produced.
const PLACEHOLDER_TYPES = new Set([
  "Financial Analysis",
  "Market Analysis",
  "Background",
  "Investment Report",
]);

function humanize(value) {
  const text = String(value || "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : "";
}

/** The key a report is grouped under in the type filter. */
export function reportTypeKey(report) {
  const type = String(report?.report_type || "").trim();
  if (type) return type;
  return String(report?.kind || "").trim();
}

/**
 * The reader-facing name of a report's type. Takes a report, or a bare
 * report_type / kind value (the type filter passes the group key).
 */
export function reportTypeLabel(reportOrType, t) {
  const report =
    reportOrType && typeof reportOrType === "object"
      ? reportOrType
      : { report_type: reportOrType, kind: reportOrType };
  const type = String(report.report_type || "").trim();
  const kind = String(report.kind || "").trim();
  const key = REPORT_TYPE_KEYS[type] || KIND_KEYS[kind] || KIND_KEYS[type];
  if (key) return t(key);
  return humanize(type || kind) || t("research.report_type.investment_report");
}

export function isMemoReport(report) {
  return MEMO_KINDS.has(String(report?.kind || ""));
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

/**
 * One of: "complete", "warnings", "failed", "cards_ready", "paused",
 * "running".
 *
 * Every status the pipeline writes while it works (queued, prepping,
 * ready_for_analysis, analyzing, investigating, generating…) is running;
 * formatters.normalizeReportStatus files the unknown ones under complete,
 * which is how an analyzing memo came to read "Ready".
 *
 * "paused" is a run that stopped on purpose after the English memo was
 * accepted (status english_ready_paused, from the Generate dialog's
 * "Pause after English"): nothing is running, the English document is on
 * file, and the resume endpoint writes the Chinese, artifacts and IC memo.
 */
export function reportState(report) {
  const status = String(report?.status || "").trim().toLowerCase();
  if (status === "complete_with_warnings") return "warnings";
  if (status.startsWith("complete") || status === "ready") return "complete";
  if (status.includes("fail") || status === "error" || status === "cancelled") {
    return "failed";
  }
  if (status === "awaiting_studio" || status === "cards_ready") return "cards_ready";
  if (status === "english_ready_paused") return "paused";
  return "running";
}

/** The Reports list's filter bucket: complete, running, needs_attention, failed. */
export function reportListStatus(report) {
  const state = reportState(report);
  if (state === "warnings" || state === "cards_ready" || state === "paused") {
    return "needs_attention";
  }
  return state;
}

/** Stopped after the English memo, waiting for someone to continue it. */
export function reportIsPaused(report) {
  return reportState(report) === "paused";
}

/** Read the way MacReport does: complete means a finished status. */
export function reportIsComplete(report) {
  const state = reportState(report);
  return state === "complete" || state === "warnings";
}

export function reportIsFailed(report) {
  return reportState(report) === "failed";
}

export function reportIsRunning(report) {
  return reportState(report) === "running";
}

/**
 * A report can be opened when a document (docx or PDF) is on file. The
 * server says so outright with `has_document` (false for the placeholder
 * records and runs that never wrote one); older payloads carry only URLs.
 */
export function reportCanOpen(report) {
  if (report?.has_document === false) return false;
  return (
    Object.keys(report?.download_urls || {}).length > 0 ||
    Object.keys(report?.preview_urls || {}).length > 0
  );
}

/** A finished record with nothing to read: it says "No document" plainly. */
export function reportIsDocless(report) {
  return reportIsComplete(report) && !reportCanOpen(report);
}

/** Dismissed failures and runs a newer run replaced stay out of the way. */
export function reportIsHidden(report) {
  return Boolean(report?.dismissed_at || report?.superseded_by);
}

/** The short status word for a chip, in the UI language. */
export function reportStatusLabel(report, t) {
  switch (reportState(report)) {
    case "complete":
      return t("reports.status_complete");
    case "warnings":
      return t("reports.status_needs_attention");
    case "failed":
      return t("reports.status_failed");
    case "cards_ready":
      return t("reports.status_cards_ready");
    case "paused":
      return t("reports.status_paused");
    default:
      return t("reports.status_running");
  }
}

// ---------------------------------------------------------------------------
// Failure
// ---------------------------------------------------------------------------

/**
 * The headline for a failed run, from the server's failure_kind when it
 * sends one, else failure_phase, status and stage — ported from the
 * research view's failure banner.
 */
export function reportFailureTitle(report, t) {
  if (!report) return "";
  const kind = String(report.failure_kind || "").toLowerCase();
  const phase = String(report.failure_phase || "").toLowerCase();
  const status = String(report.status || "").toLowerCase();
  const stage = String(report.stage || "").toLowerCase();
  if (kind === "cancelled" || phase === "cancelled" || status === "cancelled") {
    return t("research.failed_run_cancelled");
  }
  if (kind === "interrupted" || ["shutdown", "orphaned", "interrupted"].includes(phase) || status === "failed_orphaned") {
    return t("research.failed_run_interrupted");
  }
  if (kind === "provider_limit") return t("research.failed_run_provider_limit");
  if (kind === "login") return t("research.failed_run_login");
  if (kind === "timeout") return t("research.failed_run_timeout");
  if (kind === "out_of_scope" || status === "failed_scope_check") return t("research.failed_run_scope");
  if (phase === "renderer_contract" || stage.includes("renderer")) {
    return t("research.failed_run_renderer");
  }
  if (phase === "internal_diligence_memo") return t("research.failed_run_internal_memo");
  if (phase === "chinese_parity_gate") return t("research.failed_run_chinese_parity");
  if (phase === "quality_gate" || status === "failed_quality_gate" || stage.includes("quality")) {
    return t("research.failed_run_quality_gate");
  }
  return t("research.failed_run_generic");
}

/**
 * The server's plain-words explanation of a failure (failure_summary_en /
 * _zh), in the UI language; "" for records that predate it.
 */
export function reportFailureSummary(report, lang = "en") {
  const own = report?.[`failure_summary_${lang === "zh" ? "zh" : "en"}`];
  const fallback = report?.failure_summary_en;
  const text = typeof own === "string" && own.trim() ? own : fallback;
  return typeof text === "string" ? text.trim() : "";
}

/** What the record says about the failure, beyond the headline. */
export function reportFailureDetail(report) {
  if (!report) return "";
  const detail = String(report.failure_detail || report.error || "").trim();
  return detail;
}

// ---------------------------------------------------------------------------
// Warnings (complete_with_warnings)
// ---------------------------------------------------------------------------

// The five v1 late-stage sections the parity gate names by key.
const SECTION_KEYS = new Set([
  "executive_summary",
  "company_overview",
  "investment_highlights",
  "investment_risk",
  "financial_forecast_valuation",
]);

/** A section name from a finding's location, or "" when it names none. */
export function findingSection(location, t) {
  const raw = String(location || "").trim();
  if (!raw || raw === "document") return "";
  // Quality lint: "paragraph 42 (Investment Risk)" — the heading in brackets.
  const bracket = raw.match(/\(([^()]+)\)\s*$/);
  if (bracket) return bracket[1].trim();
  // Parity: a section id ("financial_forecast_valuation").
  if (/^[a-z][a-z0-9_]*$/.test(raw)) {
    return SECTION_KEYS.has(raw) ? t(`reports.section.${raw}`) : humanize(raw);
  }
  return raw;
}

function basename(path) {
  return String(path || "").split(/[\\/]/).pop();
}

// Which document a lint result read: its path matched against memo_files.
function lintLanguage(report, lint) {
  const name = basename(lint?.path);
  if (name) {
    const file = (report?.memo_files || []).find((f) => basename(f?.path) === name);
    if (file?.language === "zh") return "ZH";
    if (file?.language === "en") return "EN";
  }
  return "EN";
}

// A gate is flagged when it did not pass or found a P0. A pass with P1/P2
// notes is a pass: those are advice, not the reason a memo was held back.
function gateFlagged(payload) {
  if (!payload || typeof payload !== "object") return false;
  const status = String(payload.status || "").toLowerCase();
  if (Number(payload.p0_count || 0) > 0) return true;
  if (status) return !["passed", "ok", "pass", "clean"].includes(status);
  return Array.isArray(payload.findings) && payload.findings.length > 0;
}

/**
 * What a complete_with_warnings memo was flagged for: one item per finding,
 * each naming the gate, the language and the section. Empty for any other
 * state — the banner is for delivered memos that carry a warning.
 *
 * A structured `quality_warning_items` list from the server
 * ([{gate, language, section, severity, summary_en, summary_zh}]) wins when
 * present; until then the items come from the gate payloads, and the raw
 * `quality_warnings` strings are the last resort (their server paths cut).
 */
// gate → i18n key, for every gate memo_analysis writes into
// quality_warning_items. A gate this map does not know is humanized.
const GATE_LABEL_KEYS = {
  quality: "research.gate_quality",
  chinese_parity: "research.gate_chinese_parity",
  fact_check: "research.gate_fact_check",
  chinese_package: "research.gate_chinese_package",
  ic_memo: "research.gate_ic_memo",
  private_diligence: "research.gate_private_diligence",
  boundary: "research.gate_boundary",
  returns: "research.gate_returns",
  signposts: "research.gate_signposts",
  risk_cards: "research.gate_risk_cards",
  length: "research.gate_length",
  claims: "research.gate_claims",
  consistency: "research.gate_consistency",
  red_team: "research.gate_red_team",
  cost: "research.gate_cost",
};

/** The name of a warning gate, in the UI language. */
export function gateLabel(gate, t) {
  const key = GATE_LABEL_KEYS[String(gate || "")];
  return key ? t(key) : humanize(gate);
}

export function reportWarnings(report, t, lang = "en") {
  // A paused run carries the English gates' warnings too (length, claims…).
  if (!["warnings", "paused"].includes(reportState(report))) return [];
  const items = [];
  const seen = new Set();
  const push = (item) => {
    const key = [item.gate, item.language, item.section, item.code, item.summary].join("|");
    if (seen.has(key)) return;
    seen.add(key);
    items.push(item);
  };
  const gateLabels = {
    quality: gateLabel("quality", t),
    chinese_parity: gateLabel("chinese_parity", t),
    fact_check: gateLabel("fact_check", t),
  };

  const structured = Array.isArray(report?.quality_warning_items) ? report.quality_warning_items : [];
  for (const raw of structured) {
    if (!raw || typeof raw !== "object") continue;
    const gate = String(raw.gate || "");
    push({
      gate,
      gateLabel: gateLabel(gate, t),
      language: String(raw.language || "").toUpperCase(),
      section: findingSection(raw.section, t),
      severity: String(raw.severity || ""),
      code: String(raw.code || ""),
      summary: String((lang === "zh" ? raw.summary_zh : raw.summary_en) || raw.summary_en || ""),
    });
  }

  if (!items.length) {
    const gates = [
      ["quality", report?.memo_quality_lint, lintLanguage(report, report?.memo_quality_lint)],
      ["chinese_parity", report?.memo_chinese_parity, "ZH"],
      ["fact_check", report?.memo_fact_check, "EN"],
    ];
    for (const [gate, payload, language] of gates) {
      if (!gateFlagged(payload)) continue;
      const findings = (Array.isArray(payload.findings) ? payload.findings : []).filter(
        (f) => f && typeof f === "object",
      );
      if (!findings.length) {
        push({ gate, gateLabel: gateLabels[gate], language, section: "", severity: "", code: "", summary: "" });
        continue;
      }
      for (const finding of findings) {
        push({
          gate,
          gateLabel: gateLabels[gate],
          language,
          section: findingSection(finding.location, t),
          severity: String(finding.severity || ""),
          code: String(finding.code || ""),
          summary: "",
        });
      }
    }
  }

  if (!items.length) {
    // quality_warnings_zh is the same list in Chinese, in the same order:
    // the Chinese UI reads it, while the gate is told from the English.
    const zhWarnings = Array.isArray(report?.quality_warnings_zh) ? report.quality_warnings_zh : [];
    const cut = (value) =>
      String(value || "")
        .replace(/\s*See\s+\S+\.(md|json|txt)\.?\s*$/i, "")
        .replace(/\s*(?:详见|参见|见)\s*\S+\.(md|json|txt)[。.]?\s*$/i, "")
        .trim();
    for (const [index, warning] of (report?.quality_warnings || []).entries()) {
      const text = cut(warning);
      if (!text) continue;
      const shown = lang === "zh" && cut(zhWarnings[index]) ? cut(zhWarnings[index]) : text;
      const lower = text.toLowerCase();
      const gate = lower.includes("parity")
        ? "chinese_parity"
        : lower.includes("fact")
          ? "fact_check"
          : "quality";
      push({
        gate,
        gateLabel: gateLabels[gate],
        language: lower.includes("chinese") ? "ZH" : "",
        section: "",
        severity: "",
        code: "",
        summary: shown,
      });
    }
  }
  return items;
}

/** The document languages ("EN", "ZH") a warning points at. */
export function warningLanguages(items) {
  return [...new Set((items || []).map((item) => item.language).filter(Boolean))];
}

// ---------------------------------------------------------------------------
// Quality and fact-check chips
// ---------------------------------------------------------------------------

/**
 * The list row's quality chip, from the lint and parity gates. null when
 * the report carries neither (non-memo reports, older records).
 */
export function qualityChip(report, t) {
  const gates = [
    [t("research.gate_quality"), report?.memo_quality_lint],
    [t("research.gate_chinese_parity"), report?.memo_chinese_parity],
  ].filter(([, payload]) => payload && typeof payload === "object");
  if (!gates.length) return null;
  let p0 = 0;
  let findings = 0;
  let flagged = false;
  const lines = [];
  for (const [label, payload] of gates) {
    const gateP0 = Number(payload.p0_count || 0);
    const gateFindings = Number(payload.finding_count || 0);
    p0 += gateP0;
    findings += gateFindings;
    if (gateFlagged(payload)) flagged = true;
    lines.push(
      t("reports.quality_gate_line", {
        gate: label,
        status: String(payload.status || "—"),
        p0: gateP0,
        total: gateFindings,
      }),
    );
  }
  let label;
  if (!flagged) label = t("reports.quality_checked");
  else if (p0 > 0) label = t("reports.quality_p0", { count: p0 });
  else label = t("reports.quality_flags", { count: Math.max(findings, 1) });
  return { flagged, label, title: lines.join("\n") };
}

// ---------------------------------------------------------------------------
// Quality metrics (memo_quality_metrics.compute → report.quality_metrics)
// ---------------------------------------------------------------------------

/** A list's length, or a count the server already took; 0 otherwise. */
function countOf(value) {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") return Object.keys(value).length;
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

/**
 * A share as a whole percentage. `traced_pct` is already 0–100;
 * `repetition_index` is a 0–1 ratio (a value above 1 is taken as a
 * percentage). null when the field is missing or not a number.
 */
function percentOf(value, { ratio = false } = {}) {
  const number = Number(value);
  if (value == null || value === "" || !Number.isFinite(number)) return null;
  const pct = ratio && number <= 1 ? number * 100 : number;
  return Math.max(0, Math.min(100, Math.round(pct)));
}

/**
 * The compact "Quality" line of the viewer's status card: [{key, label,
 * title}] — traced %, sections over their cap, conflicting figures and the
 * repetition index as a percentage, each with a one-sentence tooltip.
 * null when the record carries no `quality_metrics`.
 */
export function qualityMetricsLine(report, t) {
  const metrics = report?.quality_metrics;
  if (!metrics || typeof metrics !== "object") return null;
  const items = [];
  const traced = percentOf(metrics.traced_pct);
  if (traced != null) {
    items.push({
      key: "traced",
      label: t("reports.quality_metrics.traced", { pct: traced }),
      title: t("reports.quality_metrics.traced_hint"),
    });
  }
  if ("over_cap_sections" in metrics) {
    items.push({
      key: "over_cap",
      label: t("reports.quality_metrics.over_cap", { n: countOf(metrics.over_cap_sections) }),
      title: t("reports.quality_metrics.over_cap_hint"),
    });
  }
  if ("metric_conflicts" in metrics) {
    items.push({
      key: "conflicts",
      label: t("reports.quality_metrics.conflicts", { n: countOf(metrics.metric_conflicts) }),
      title: t("reports.quality_metrics.conflicts_hint"),
    });
  }
  const repetition = percentOf(metrics.repetition_index, { ratio: true });
  if (repetition != null) {
    items.push({
      key: "repetition",
      label: t("reports.quality_metrics.repetition", { pct: repetition }),
      title: t("reports.quality_metrics.repetition_hint"),
    });
  }
  return items.length ? items : null;
}

// The honest split of a memo's figures (memo_fact_check.summarize_fact_check):
// the buckets partition `checked`. `found_elsewhere` on a "legacy" check
// still includes registry-only and company-reported figures, which then
// read null (unknown) rather than 0.
const FACT_TIERS = [
  ["verified", "success"],
  ["found_elsewhere", "teal"],
  ["derived", "info"],
  ["company_reported", "accent"],
  ["registry_only", "notice"],
  ["not_traced", "warning"],
];

function count(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

/**
 * The tiers of a fact-check summary that hold figures, in reading order:
 * [{key, count, tone, label}] — label "Verified in sources on file: 12".
 * `registry_only` reads "matches registry, not evidence".
 */
export function factCheckTiers(summary, t) {
  if (!summary || typeof summary !== "object") return [];
  return FACT_TIERS.map(([key, tone]) => ({ key, tone, count: count(summary[key]) }))
    .filter((tier) => tier.count > 0)
    .map((tier) => ({ ...tier, label: t(`reports.fact.tier.${tier.key}`, { count: tier.count }) }));
}

/**
 * What a memo's number check found, in words that don't overstate it
 * (R28): verified, found elsewhere in sources on file, derived, not traced
 * — never one "traced" percentage that mixes them. Reads the compact
 * `memo_fact_check` summary on a list row.
 *
 * - absent (or status not_run): "Checks not run" — memos that predate the
 *   check (2026-09-20) are labelled, never backfilled with a percentage;
 * - thin corpus (not_checkable): "Not checkable: no sources on file";
 * - no_figures / error: said as such;
 * - otherwise "12 of 40 verified", plus "3 not traced" when any are.
 *
 * null for anything that is not a finished memo.
 */
export function factCheckChip(report, t) {
  if (!isMemoReport(report) || !reportIsComplete(report)) return null;
  const fc = report?.memo_fact_check;
  const status = String(fc?.status || "").toLowerCase();
  if (!fc || typeof fc !== "object" || status === "not_run") {
    return {
      state: "not_run",
      tone: "neutral",
      flagged: false,
      label: t("reports.fact.not_run"),
      title: t("reports.fact.not_run_hint"),
    };
  }
  const checked = count(fc.checked);
  if (status === "error") {
    return {
      state: "error",
      tone: "neutral",
      flagged: false,
      label: t("reports.fact.error"),
      title: t("reports.fact.error_hint"),
    };
  }
  if (fc.thin_corpus || status === "not_checkable") {
    return {
      state: "not_checkable",
      tone: "neutral",
      flagged: false,
      label: t("reports.fact.not_checkable"),
      title: t("reports.fact.not_checkable_hint", { checked }),
    };
  }
  if (!checked || status === "no_figures") {
    return {
      state: "no_figures",
      tone: "neutral",
      flagged: false,
      label: t("reports.fact.no_figures"),
      title: t("reports.fact.no_figures"),
    };
  }
  const tiers = factCheckTiers(fc, t);
  const notTraced = count(fc.not_traced ?? fc.unsupported);
  const verified = count(fc.verified);
  const flagged =
    notTraced > 0 || count(fc.p0_count) > 0 || status === "warn" || status === "fail";
  const label = [t("reports.fact.chip", { verified, checked })];
  if (notTraced > 0) label.push(t("reports.fact.chip_not_traced", { count: notTraced }));
  const lines = [t("reports.fact.title", { checked }), ...tiers.map((tier) => tier.label)];
  if (fc.basis === "legacy") lines.push(t("reports.fact.legacy_note"));
  return {
    state: "checked",
    // Green only when figures were verified and none went untraced.
    tone: flagged ? "warning" : verified > 0 ? "success" : "neutral",
    flagged,
    label: label.join(" · "),
    title: lines.join("\n"),
    tiers,
    notTraced,
  };
}

// ---------------------------------------------------------------------------
// Working papers
// ---------------------------------------------------------------------------

/**
 * A failed pass leaves a placeholder paper ("## Status" / "Pass failed: …",
 * memo_analysis.py) whose body is a raw CLI error. It is listed as a pass
 * that did not run, never rendered.
 */
export function isFailedPaperText(text) {
  const body = String(text || "");
  return /^##\s+Status\s*$/m.test(body) || /\bPass failed:/.test(body);
}

// ---------------------------------------------------------------------------
// Memo jobs on the shared active-jobs poll
// ---------------------------------------------------------------------------

/** report_id → report_ready for every memo job in an active-jobs list. */
export function memoJobSnapshot(jobs) {
  const snapshot = new Map();
  for (const job of jobs || []) {
    if (job?.kind !== "memo" || !job.report_id) continue;
    snapshot.set(String(job.report_id), Boolean(job.report_ready));
  }
  return snapshot;
}

/**
 * What changed between two snapshots: memo runs that left the active set
 * (finished, failed or cancelled), turned report_ready, or appeared.
 */
export function memoJobChanges(previous, next) {
  const finished = [];
  const ready = [];
  const started = [];
  for (const [id, wasReady] of previous || new Map()) {
    if (!next.has(id)) finished.push(id);
    else if (!wasReady && next.get(id)) ready.push(id);
  }
  for (const [id, isReady] of next) {
    if (!previous?.has(id)) {
      started.push(id);
      if (isReady) ready.push(id);
    }
  }
  return { finished, ready, started };
}

/** The active memo job for a report, if the poll has one. */
export function memoJobFor(jobs, reportId) {
  if (!reportId) return null;
  return (
    (jobs || []).find((job) => job?.kind === "memo" && String(job.report_id) === String(reportId)) ||
    null
  );
}

// A viewer asks the jobs rail to open its transcript modal for a job, so the
// app keeps one JobLogModal (and one live stream) rather than a second copy.
export const jobLogRequest = ref(null);

export function requestJobLog(job) {
  if (!job) return;
  jobLogRequest.value = { job, at: Date.now() };
}

// ---------------------------------------------------------------------------
// Two-step arming
// ---------------------------------------------------------------------------

/**
 * The app's confirm-by-second-click pattern (the jobs rail's Cancel): the
 * first click arms an action for `ms`, a second click within it runs it.
 * `trigger(key)` answers true when the action should run now.
 */
export function useTwoStepArm(ms = 4000) {
  const armed = ref("");
  let timer = null;
  function reset() {
    clearTimeout(timer);
    timer = null;
    armed.value = "";
  }
  function trigger(key) {
    if (armed.value !== key) {
      armed.value = key;
      clearTimeout(timer);
      timer = setTimeout(() => {
        armed.value = "";
      }, ms);
      return false;
    }
    reset();
    return true;
  }
  if (getCurrentScope()) onScopeDispose(reset);
  return { armed, trigger, reset };
}

// ---------------------------------------------------------------------------
// The Reports desk's company filter
// ---------------------------------------------------------------------------

/**
 * The company the Reports desk is filtered to (`/reports?company=`), or
 * null. ⌘N, the app menu and the sidebar open the customizer on it.
 */
export function reportsCompanyFilter(route) {
  if (!route || route.name !== "reports") return null;
  const raw = route.query?.company;
  const value = Array.isArray(raw) ? raw[0] : raw;
  const id = String(value || "").trim();
  return id && id !== "all" ? id : null;
}

/** Whether a report type is one of the placeholder generator's. */
export function isPlaceholderType(report) {
  return PLACEHOLDER_TYPES.has(String(report?.report_type || "")) && !report?.kind;
}

// ---------------------------------------------------------------------------
// Chip tones
// ---------------------------------------------------------------------------

const TONE_CLASSES = {
  success: "bg-success-soft text-success-ink",
  notice: "bg-notice-soft text-notice-ink",
  teal: "bg-teal-soft text-teal-ink",
  purple: "bg-purple-soft text-purple-ink",
  info: "bg-info-soft text-info-ink",
  warning: "bg-warning-soft text-warning-ink",
  danger: "bg-danger-soft text-danger-ink",
  accent: "bg-accent-soft text-accent-ink",
  neutral: "bg-ink-primary/[0.06] text-ink-secondary",
};

/** The soft background + ink classes of a chip tone (see docs/web-design-language.md). */
export function toneClasses(tone) {
  return TONE_CLASSES[tone] || TONE_CLASSES.neutral;
}

// ---------------------------------------------------------------------------
// Company names
// ---------------------------------------------------------------------------

// A trailing EDGAR suffix token: "/DE/", "/De/", "/MD/", "/NEW/", "/ADR/",
// "/MN" (no closing slash); repeated tokens ("CORP /DE/ /NEW/") all go.
const EDGAR_SUFFIX_RE = /(?:\s*\/\s*[A-Za-z]{2,4}\s*\/?)+\s*$/;

function withoutControlChars(text) {
  let out = "";
  for (const ch of text) {
    const code = ch.codePointAt(0);
    out += code < 32 || code === 127 ? " " : ch;
  }
  return out;
}

/**
 * A company name without SEC EDGAR state/suffix tokens ("Occidental
 * Petroleum Corp /De/" → "Occidental Petroleum Corp"), path separators or
 * control characters — the web twin of server/company_names.
 * clean_display_name, so the list, the viewer and the documents agree.
 */
export function cleanDisplayName(name) {
  let text = withoutControlChars(String(name ?? "").normalize("NFC"))
    .replace(/\s+/g, " ")
    .trim();
  if (!text) return "";
  const stripped = text.replace(EDGAR_SUFFIX_RE, "").trim();
  // Never strip a name down to nothing ("/DE/" alone is not a name).
  if (stripped) text = stripped;
  // A slash left inside the name ("AC/DC Holdings") is not a separator.
  text = text.replace(/\s*[/\\]+\s*/g, "-");
  text = text.replace(/^[.\s-]+/, "").replace(/[\s,;:-]+$/, "");
  return text.replace(/\s+/g, " ").trim();
}

// ---------------------------------------------------------------------------
// What a report concludes: the call, its headline, and how fresh it is
// ---------------------------------------------------------------------------

export function isBuffettReport(report) {
  const kind = String(report?.kind || "");
  if (kind) return kind === "buffett_investment_memo";
  return String(report?.report_type || "") === "Buffett Investment Memo";
}

/** The call a report makes: the stored decision, else the reader block's. */
export function reportDecision(report) {
  for (const value of [report?.decision, report?.reader?.decision]) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function decisionKey(decision) {
  return String(decision || "")
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, " ");
}

// Buffett calls (Buy / Pass / Too Hard), and the late-stage verdicts: the v2
// spine's Strong Buy / Buy / Watch / Pass, or a package's invest/pass/watch.
const BUFFETT_DECISIONS = { buy: "buy", pass: "pass", "too hard": "too_hard" };
const LATE_DECISIONS = {
  "strong buy": "strong_buy",
  buy: "late_buy",
  invest: "invest",
  watch: "watch",
  pass: "late_pass",
};

/** A decision in the UI language: a Buffett "Pass" is 放弃, a late-stage one 不建议投资. */
export function decisionWord(decision, report, t) {
  const key = decisionKey(decision);
  if (!key) return "";
  const found = (isBuffettReport(report) ? BUFFETT_DECISIONS : LATE_DECISIONS)[key];
  return found ? t(`reports.verdict.${found}`) : String(decision).trim();
}

/** The Buffett buy price as the memo wrote it, in the UI language when there is a Chinese one. */
export function buyPriceText(report, lang = "en") {
  const reader = report?.reader || {};
  const raw = report?.buy_price;
  const english =
    (typeof raw === "string" ? raw : raw && typeof raw === "object" ? raw.en : "") ||
    reader.buy_price_text ||
    "";
  const chinese =
    report?.buy_price_zh ||
    (raw && typeof raw === "object" ? raw.zh : "") ||
    reader.buy_price_text_zh ||
    "";
  const text = lang === "zh" ? chinese || english : english || chinese;
  return typeof text === "string" ? text.replace(/\s+/g, " ").trim() : "";
}

const MONEY_RE =
  /(US\$|NT\$|HK\$|\$|€|£)\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?:\s?(million|billion|trillion)\b)?/i;
const CURRENCY_SYMBOLS = { USD: "$", EUR: "€", GBP: "£", HKD: "HK$", TWD: "NT$" };

function perShareText(value) {
  const magnitude = Math.abs(value);
  return Math.abs(magnitude - Math.round(magnitude)) < 0.005
    ? Math.round(magnitude).toLocaleString("en-US")
    : magnitude.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function totalText(value) {
  return String(Number(Math.abs(value).toFixed(2)));
}

// buffett_memo_renderer.format_money, English: a per-share amount, or with
// `millions` a whole-company total given in millions.
function formatMoney(value, currency, millions) {
  const code = String(currency || "USD").toUpperCase();
  const prefix = CURRENCY_SYMBOLS[code] || `${code} `;
  const sign = value < 0 ? "−" : "";
  if (!millions) return `${sign}${prefix}${perShareText(value)}`;
  const magnitude = Math.abs(value);
  if (magnitude >= 1_000_000) return `${sign}${prefix}${totalText(value / 1_000_000)} trillion`;
  if (magnitude >= 1_000) return `${sign}${prefix}${totalText(value / 1_000)} billion`;
  return `${sign}${prefix}${totalText(value)} million`;
}

/**
 * The buy price as a short amount for a chip ("$215", "US$220", "$75
 * million"): the structured value when the run stored one, else the first
 * money figure in the call label or the memo's own buy-price text; "" when
 * it names none. Figures stay in "$" in both languages, as the memos do.
 */
export function buyPriceAmount(report) {
  const raw = report?.buy_price_value;
  const value = Number(raw);
  if (raw != null && raw !== "" && Number.isFinite(value) && value > 0) {
    const valuation = report?.buffett_valuation || {};
    return formatMoney(
      value,
      report?.currency || valuation.currency,
      valuation.value_basis === "company",
    );
  }
  for (const text of [report?.call_label?.en, buyPriceText(report, "en")]) {
    const match = MONEY_RE.exec(String(text || ""));
    if (match) return `${match[1]}${match[2]}${match[3] ? ` ${match[3].toLowerCase()}` : ""}`;
  }
  return "";
}

function passKind(report, amount) {
  const kind = String(report?.pass_kind || report?.reader?.pass_kind || "").toLowerCase();
  if (kind === "price" || kind === "business") return kind;
  // A Pass that names a buy price is a pass at today's price.
  return amount ? "price" : "";
}

function callLabel(report) {
  const label = report?.call_label;
  if (label && typeof label === "object") return label;
  const fromReader = report?.reader?.call_label;
  return fromReader && typeof fromReader === "object" ? fromReader : null;
}

/**
 * The memo's call as a chip, in the UI language — {key, label, title, tone,
 * full} or null when the report records no call (every v1 late-stage memo:
 * its headline carries the call instead).
 *
 * Buffett-method: "Pass · buy ≤ $215" / "暂不买入 · 买入价 ≤ $215", "Buy · up
 * to $360", "Pass · not at any price" / 放弃, "Too Hard" / 超出能力圈; the
 * server's full `call_label` is the tooltip. Late-stage: the v2 verdict
 * (Strong Buy / Buy / Watch / Pass → 强烈推荐 / 推荐投资 / 观察名单 / 不建议投资).
 */
export function verdictChip(report, t, lang = "en") {
  const decision = reportDecision(report);
  if (!decision) return null;
  const key = decisionKey(decision);
  const labels = callLabel(report);
  const full =
    (lang === "zh" ? labels?.zh || labels?.en : labels?.en || labels?.zh) || "";
  if (isBuffettReport(report)) {
    const amount = key === "too hard" ? "" : buyPriceAmount(report);
    let label = decision;
    let tone = "neutral";
    if (key === "buy") {
      label = amount ? t("reports.verdict.buy_up_to", { price: amount }) : t("reports.verdict.buy");
      tone = "success";
    } else if (key === "pass") {
      const kind = passKind(report, amount);
      if (kind === "price") {
        label = amount
          ? t("reports.verdict.pass_price", { price: amount })
          : t("reports.verdict.pass_price_bare");
        tone = "notice";
      } else {
        label = kind === "business" ? t("reports.verdict.pass_business") : t("reports.verdict.pass");
      }
    } else if (key === "too hard") {
      label = t("reports.verdict.too_hard");
      tone = "purple";
    }
    const lines = [full || label];
    const buyText = buyPriceText(report, lang);
    if (buyText) lines.push(t("reports.verdict.buy_price_line", { price: buyText }));
    return { key, label, title: lines.join("\n"), tone, full: full || label };
  }
  const known = LATE_DECISIONS[key];
  const label = known ? t(`reports.verdict.${known}`) : decision;
  const tone = ["strong_buy", "late_buy", "invest"].includes(known)
    ? "success"
    : known === "watch"
      ? "teal"
      : "neutral";
  return { key, label, title: full || label, tone, full: full || label };
}

/** The memo's one-line headline (its first decision sentence) in the UI language. */
export function reportHeadline(report, lang = "en") {
  const headline = report?.reader?.headline;
  if (!headline || typeof headline !== "object") return "";
  const own = headline[lang === "zh" ? "zh" : "en"];
  const other = headline[lang === "zh" ? "en" : "zh"];
  const text = typeof own === "string" && own.trim() ? own : other;
  return typeof text === "string" ? text.replace(/\s+/g, " ").trim() : "";
}

const DAY_MS = 86_400_000;
// The newest source is named only when it is this much older than the memo;
// the line turns amber once the memo itself is older than a month.
export const SOURCE_GAP_DAYS = 14;
export const STALE_AFTER_DAYS = 30;

function parseDay(value) {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime())
      ? null
      : new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }
  const raw = String(value || "").trim();
  if (!raw) return null;
  const dateOnly = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dateOnly) return new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]));
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parseDay(parsed);
}

function daysBetween(earlier, later) {
  return Math.round((later.getTime() - earlier.getTime()) / DAY_MS);
}

function shortDay(day, today, lang) {
  const options =
    day.getFullYear() === today.getFullYear()
      ? { month: "short", day: "numeric" }
      : { year: "numeric", month: "short", day: "numeric" };
  return day.toLocaleDateString(lang === "zh" ? "zh-CN" : "en-US", options);
}

/**
 * Whether a finished memo is still current: "Written Sep 1 · 21 days ago ·
 * latest source Jun 13". The source date shows only when it is more than
 * two weeks older than the memo ("latest source", never "evidence
 * through"), and `stale` (amber) is set once the memo is over 30 days old.
 * null for anything that is not a finished memo.
 */
export function reportFreshness(report, t, lang = "en", now = Date.now()) {
  if (!isMemoReport(report) || !reportIsComplete(report)) return null;
  const reader = report?.reader && typeof report.reader === "object" ? report.reader : {};
  const written =
    parseDay(reader.memo_as_of) || parseDay(report?.report_ready_at) || parseDay(report?.created_at);
  if (!written) return null;
  const today = parseDay(new Date(now));
  const age = Math.max(0, daysBetween(written, today));
  const parts = [t("reports.fresh.written", { date: shortDay(written, today, lang) })];
  if (age === 0) parts.push(t("reports.fresh.today"));
  else if (age === 1) parts.push(t("reports.fresh.yesterday"));
  else parts.push(t("reports.fresh.days_ago", { count: age }));
  const source = parseDay(reader.evidence_latest);
  const gap = source ? daysBetween(source, written) : 0;
  const showSource = Boolean(source) && gap > SOURCE_GAP_DAYS;
  if (showSource) parts.push(t("reports.fresh.latest_source", { date: shortDay(source, today, lang) }));
  const stale = age > STALE_AFTER_DAYS;
  const lines = [];
  if (stale) lines.push(t("reports.fresh.stale_hint", { count: age }));
  if (showSource) lines.push(t("reports.fresh.source_hint", { count: gap }));
  const total = Number(reader.sources_total) || 0;
  if (total > 0) {
    lines.push(t("reports.fresh.sources_dated", { dated: Number(reader.sources_dated) || 0, total }));
  }
  return {
    text: parts.join(" · "),
    title: lines.join("\n"),
    stale,
    age,
    showSource,
    sourceGap: gap,
  };
}

// ---------------------------------------------------------------------------
// Review
// ---------------------------------------------------------------------------

export const REVIEW_STATES = ["draft", "in_review", "approved", "withdrawn"];
const REVIEW_TONES = { draft: "neutral", in_review: "info", approved: "success", withdrawn: "danger" };

export function reviewState(report) {
  const state = String(report?.review_state || "draft").toLowerCase();
  return REVIEW_STATES.includes(state) ? state : "draft";
}

function reviewedAt(value, lang) {
  const parsed = Date.parse(value || "");
  if (Number.isNaN(parsed)) return "";
  return new Date(parsed).toLocaleDateString(lang === "zh" ? "zh-CN" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * The review chip — Draft / In review / Approved by <name> / Withdrawn —
 * for a finished memo (or any memo whose review moved off draft); null
 * otherwise.
 */
export function reviewChip(report, t, lang = "en") {
  if (!isMemoReport(report)) return null;
  const state = reviewState(report);
  if (state === "draft" && !reportIsComplete(report)) return null;
  const name = String(report?.reviewer_name || report?.reviewer || "").trim();
  const label =
    state === "approved" && name
      ? t("review.state.approved_by", { name })
      : t(`review.state.${state}`);
  const lines = [];
  if (state === "draft") {
    lines.push(t("review.draft_hint"));
  } else {
    lines.push(label);
    const date = reviewedAt(report?.reviewed_at, lang);
    if (date) lines.push(t("review.changed_by", { name: name || t("review.someone"), date }));
    if (report?.review_note) lines.push(`“${String(report.review_note).trim()}”`);
  }
  return { state, label, title: lines.join("\n"), tone: REVIEW_TONES[state] };
}

/** Whether a permission list (GET /api/auth/me) grants a permission. */
export function hasPermission(permissions, name) {
  return Array.isArray(permissions) && permissions.includes(name);
}

/**
 * The review moves the reader may make, in menu order: memo:edit asks for
 * review (draft → in review); memo:approve may approve, return a memo to
 * draft or withdraw it. Approving and asking for review need a finished
 * memo (the server's rule).
 */
export function reviewActions(report, permissions) {
  if (!isMemoReport(report)) return [];
  const canApprove = hasPermission(permissions, "memo:approve");
  const canRequest = canApprove || hasPermission(permissions, "memo:edit");
  const finished = reportIsComplete(report);
  const state = reviewState(report);
  const actions = [];
  if (state === "draft" && canRequest && finished) actions.push("in_review");
  if (canApprove) {
    if (state !== "approved" && finished) actions.push("approved");
    if (state !== "draft") actions.push("draft");
    if (state !== "withdrawn") actions.push("withdrawn");
  }
  return actions;
}

/** Why the documents may not carry the review stamp yet ("" when they do). */
export function reviewRenderNote(report, t) {
  const status = String(report?.review_render_status || "").toLowerCase();
  return ["skipped", "failed", "refused"].includes(status) ? t(`review.render.${status}`) : "";
}

// ---------------------------------------------------------------------------
// Versions (derived by the server at read time: server/memo_diff.py)
// ---------------------------------------------------------------------------

/** A memo's place among the finished memos of its company and kind. */
export function versionInfo(report) {
  const flip = report?.verdict_flip_days;
  return {
    grouped: report?.is_latest === true || report?.is_latest === false,
    isLatest: report?.is_latest === true,
    index: Number(report?.version_index) || 0,
    count: Number(report?.version_count) || 0,
    previousId: String(report?.previous_version_id || ""),
    latestId: String(report?.latest_version_id || ""),
    changedFrom: String(report?.verdict_changed_from || "").trim(),
    unstable: report?.unstable_call === true,
    flipDays: flip != null && Number.isFinite(Number(flip)) ? Number(flip) : null,
  };
}

/** A span of days in words: "18 hours" under two days, else "3 days". */
export function spanLabel(days, t) {
  const value = Number(days);
  if (days == null || !Number.isFinite(value) || value < 0) return "";
  if (value < 2) {
    const hours = Math.max(1, Math.round(value * 24));
    return hours === 1 ? t("reports.span.hour") : t("reports.span.hours", { count: hours });
  }
  return t("reports.span.days", { count: Math.round(value) });
}

// ---------------------------------------------------------------------------
// Document sources
// ---------------------------------------------------------------------------

/** Whether a download key is the IC decision memo ("internal", "internal_zh"). */
export function isInternalSource(key) {
  return /^internal/i.test(String(key || ""));
}

/** The document language behind a source key: en, zh, or "" when unknown. */
export function sourceLanguage(key) {
  const k = String(key || "").toLowerCase();
  if (k === "zh" || k.endsWith("_zh")) return "zh";
  if (k === "en" || k === "internal" || k.endsWith("_en")) return "en";
  return "";
}

/**
 * A source key as a reader reads it: EN / ZH for the memo, and the
 * internal document as the IC memo (投委会备忘录), with its language named
 * only when both of its languages are on file.
 */
export function sourceLabel(key, keys, t) {
  const k = String(key || "").toLowerCase();
  const all = (keys || []).map((value) => String(value || "").toLowerCase());
  const both = all.includes("internal") && all.includes("internal_zh");
  if (k === "internal") return both ? t("reports.source_ic_memo_en") : t("reports.source_ic_memo");
  if (k === "internal_zh") return both ? t("reports.source_ic_memo_zh") : t("reports.source_ic_memo");
  return k.toUpperCase();
}
