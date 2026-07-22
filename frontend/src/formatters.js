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
  complete: "Complete",
  completed: "Complete",
  complete_with_warnings: "Complete with notes",
  failed: "Needs attention",
  failed_during_analysis: "Needs attention",
  failed_scope_check: "Needs attention",
  failed_quality_gate: "Needs attention",
  failed_orphaned: "Needs attention",
  memo_task_created: "Task created",
  in_progress: "In progress",
  ready_for_input: "Needs input",
  not_started: "Not started",
  proposed: "Proposed",
  accepted: "Accepted",
  rejected: "Dismissed",
};

const STATUS_LABELS_ZH = {
  complete: "已完成",
  completed: "已完成",
  complete_with_warnings: "已完成（有备注）",
  failed: "需要处理",
  failed_during_analysis: "需要处理",
  failed_scope_check: "需要处理",
  failed_quality_gate: "需要处理",
  failed_orphaned: "需要处理",
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

export function humanizeStatus(value, fallback = "Pending", language = "en") {
  const normalized = String(value || "").trim().toLowerCase();
  if (!normalized) return fallback;
  if (language === "zh" && STATUS_LABELS_ZH[normalized]) return STATUS_LABELS_ZH[normalized];
  if (STATUS_LABELS[normalized]) return STATUS_LABELS[normalized];
  return normalized
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
