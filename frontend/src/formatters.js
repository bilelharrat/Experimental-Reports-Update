const PENDING_VALUES = new Set([
  "",
  "unknown",
  "unknown/pending",
  "pending",
  "source pending",
  "n/a",
  "na",
  "null",
  "undefined",
]);

export function isPendingValue(value) {
  if (value == null) return true;
  return PENDING_VALUES.has(String(value).trim().toLowerCase());
}

function numericValue(value) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const raw = String(value ?? "").trim();
  if (!/^[-+]?\d+(?:\.\d+)?$/.test(raw)) return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatCompactNumber(value, { currency = false, signed = false } = {}) {
  if (isPendingValue(value)) return "—";
  const numeric = numericValue(value);
  if (numeric == null) return String(value);

  const absolute = Math.abs(numeric);
  const scale = absolute >= 1e12
    ? [1e12, "T"]
    : absolute >= 1e9
      ? [1e9, "B"]
      : absolute >= 1e6
        ? [1e6, "M"]
        : absolute >= 1e3
          ? [1e3, "K"]
          : [1, ""];
  const scaled = numeric / scale[0];
  const decimals = scale[0] === 1 || Math.abs(scaled) >= 100 ? 0 : 1;
  const formatted = Math.abs(scaled).toFixed(decimals);
  const sign = numeric < 0 ? "-" : signed && numeric > 0 ? "+" : "";
  return `${sign}${currency ? "$" : ""}${formatted}${scale[1]}`;
}

export function formatMetricValue(label, value) {
  if (isPendingValue(value)) return "—";
  const normalizedLabel = String(label || "").toLowerCase();
  const raw = String(value).trim();
  if (raw.includes("%") || /[KMBT]$/i.test(raw) || raw.startsWith("$")) return raw;
  if (/growth|cagr|margin|rate|change|return/.test(normalizedLabel)) {
    const numeric = numericValue(value);
    return numeric == null ? raw : `${numeric > 0 ? "+" : ""}${numeric}%`;
  }
  return formatCompactNumber(value, {
    currency: /arr|tam|valuation|revenue|funding|raised|investment|ev|price/.test(normalizedLabel),
  });
}

export function formatIsoDate(value, fallback = "—") {
  if (!value) return fallback;
  const raw = String(value);
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return fallback;
  return parsed.toISOString().slice(0, 10);
}

const STATUS_LABELS = {
  complete: "Ready",
  completed: "Ready",
  awaiting_studio: "Cards ready",
  complete_with_warnings: "Needs attention",
  failed: "Failed",
  failed_during_analysis: "Failed",
  failed_scope_check: "Failed",
  failed_quality_gate: "Failed",
  failed_orphaned: "Failed",
  memo_task_created: "Task created",
  in_progress: "Running",
  ready_for_input: "Needs input",
  not_started: "Not started",
  proposed: "Proposed",
  accepted: "Accepted",
  rejected: "Dismissed",
};

const STATUS_LABELS_ZH = {
  complete: "已就绪",
  completed: "已就绪",
  awaiting_studio: "卡片已就绪",
  complete_with_warnings: "待处理",
  failed: "失败",
  failed_during_analysis: "失败",
  failed_scope_check: "失败",
  failed_quality_gate: "失败",
  failed_orphaned: "失败",
  memo_task_created: "已创建任务",
  in_progress: "进行中",
  ready_for_input: "等待输入",
  not_started: "尚未开始",
  proposed: "待确认",
  accepted: "已接受",
  rejected: "已忽略",
  draft: "草稿",
  open: "待处理",
  reviewed: "已审核",
  waived: "已豁免",
};

// Web twin of MacTimeFormat.relative: abbreviated relative stamps ("2 hr. ago").
export function formatRelativeTime(value, fallback = "") {
  if (!value) return fallback;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { style: "short", numeric: "auto" });
  const steps = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.348, "week"],
    [12, "month"],
    [Infinity, "year"],
  ];
  let amount = seconds;
  for (const [size, unit] of steps) {
    if (Math.abs(amount) < size) return rtf.format(Math.round(amount), unit);
    amount /= size;
  }
  return rtf.format(Math.round(amount), "year");
}

export function isTerminalReportStatus(status) {
  const s = String(status || "");
  return (
    s === "complete" ||
    s === "complete_with_warnings" ||
    // Memo Studio: the investigation parked for card review — nothing is
    // running; the user's Generate starts the next phase.
    s === "awaiting_studio" ||
    s.startsWith("failed")
  );
}

export function humanizeStatus(value, fallback = "Pending", language = "en") {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return fallback;
  if (language === "zh" && STATUS_LABELS_ZH[normalized]) return STATUS_LABELS_ZH[normalized];
  if (STATUS_LABELS[normalized]) return STATUS_LABELS[normalized];
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Mirror ``product_store.display_name`` — local-part → Title Case words. */
export function displayNameFromEmail(email) {
  const normalized = String(email || "").trim();
  if (!normalized) return "";
  const source = normalized.includes("@") ? normalized.split("@", 1)[0] : normalized;
  const parts = source.split(/[._\-\s]+/).filter(Boolean);
  return parts
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

/** Compact 1–2 letter mark for a company rail badge (e.g. "ZaiNar, Inc." → "ZI"). */
export function companyInitials(company, fallback = "?") {
  const ticker = String(company?.ticker || "").trim();
  if (/^[A-Za-z]{1,5}$/.test(ticker)) {
    return ticker.slice(0, 2).toUpperCase();
  }
  const name = String(company?.name || "").trim();
  if (!name) return fallback;
  const tokens = name.split(/[\s,./&+_–—-]+/).filter(Boolean);
  if (tokens.length >= 2) {
    return `${tokens[0].charAt(0)}${tokens[1].charAt(0)}`.toUpperCase();
  }
  const word = (tokens[0] || name).replace(/[^A-Za-z0-9]/g, "");
  const caps = word.match(/[A-Z]/g) || [];
  if (caps.length >= 2) return caps.slice(0, 2).join("");
  if (word.length >= 2) return word.slice(0, 2).toUpperCase();
  if (word.length === 1) return word.toUpperCase();
  return fallback;
}

/** Two-letter initials from a display name or email (e.g. "Bilel Harrat" / bilel.harrat@… → "BH"). */
export function accountInitials(nameOrEmail, fallback = "?") {
  const raw = String(nameOrEmail || "").trim();
  if (!raw) return fallback;
  const name = raw.includes("@") ? displayNameFromEmail(raw) : raw;
  const parts = name.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0].charAt(0)}${parts[parts.length - 1].charAt(0)}`.toUpperCase();
  }
  if (parts.length === 1 && parts[0].length >= 2) {
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase() || fallback;
  return fallback;
}

export {
  companyFallbackLogoUrl,
  companyLogoUrl,
  resolveCompanyDomain,
} from "./companyLogo.js";
