// Pure helpers for the Console feature — kept out of CompanyConsole.vue so
// they're trivially unit-testable from vitest without spinning up the
// component lifecycle. The math here mirrors §5 of the design doc:
// `context_used = input + cache_read + cache_creation` from the LAST turn,
// NOT a sum across turns.

export const CONTEXT_WINDOW = 1_000_000;
export const WARNING_THRESHOLD = 0.75;
export const LOCK_THRESHOLD = 0.90;

export const ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024;
// Images and PDFs the model reads itself; every other format is turned
// into text on the server when it is staged (see
// ``server/attachment_text.py``). Keep in sync with
// ``server/console_store.py``'s ``ATTACHMENT_TYPE_BY_EXT``.
export const ATTACHMENT_ALLOWED_MIME = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  "application/rtf",
  "text/rtf",
  "text/plain",
  "text/markdown",
  "text/csv",
  "text/tab-separated-values",
  "application/json",
  "application/yaml",
  "text/yaml",
  "text/html",
]);
export const ATTACHMENT_ALLOWED_EXT = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp",
  ".pdf", ".doc", ".docx", ".xlsx", ".pptx", ".rtf",
  ".txt", ".log", ".md", ".markdown", ".csv", ".tsv",
  ".json", ".yaml", ".yml", ".html", ".htm",
]);
// What the file picker offers. Same list, as a string.
export const ATTACHMENT_ACCEPT = Array.from(ATTACHMENT_ALLOWED_EXT).join(",");

/**
 * Translate one turn's `usage` blob into the meter view-model.
 *
 *   usageToMeter({
 *     input_tokens: 1000,
 *     cache_read_input_tokens: 300_000,
 *     cache_creation_input_tokens: 25_000,
 *   })
 *
 * Returns:
 *   {
 *     used: 326000,
 *     pct_used: 0.326,
 *     pct_free: 0.674,
 *     color: "green" | "yellow" | "red",
 *     state: "ok" | "warning" | "locked",
 *   }
 *
 * `usage` may be null/undefined (no turns yet) — meter then reads 0%.
 */
export function usageToMeter(usage) {
  const used =
    (Number(usage?.input_tokens) || 0) +
    (Number(usage?.cache_read_input_tokens) || 0) +
    (Number(usage?.cache_creation_input_tokens) || 0);
  const pct_used = used / CONTEXT_WINDOW;
  const pct_free = Math.max(0, 1 - pct_used);
  let state = "ok";
  let color = "green";
  if (pct_used >= LOCK_THRESHOLD) {
    state = "locked";
    color = "red";
  } else if (pct_used >= WARNING_THRESHOLD) {
    state = "warning";
    color = "yellow";
  }
  return { used, pct_used, pct_free, state, color };
}

/**
 * Format an integer token count for the meter ("342K", "1.0M", "12.4K").
 */
export function formatTokens(n) {
  const v = Number(n) || 0;
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1) + "M";
  if (v >= 1_000) return (v / 1_000).toFixed(0) + "K";
  return String(v);
}

/**
 * Format a USD cost for the meter ("$0.41", "$1.20").
 */
export function formatCost(c) {
  const v = Number(c);
  if (!Number.isFinite(v)) return "$0.00";
  return "$" + v.toFixed(v >= 1 ? 2 : 3);
}

/**
 * Client-side preflight for an image upload. Mirrors the server's caps in
 * server/console_store.py so the user gets immediate feedback before the
 * round-trip. Returns null when OK, or a `{code, key}` object that maps
 * to a translated error message.
 */
export function validateAttachment(file) {
  if (!file) return { code: "missing", key: "console.error_attachment_missing" };
  if (file.size > ATTACHMENT_MAX_BYTES) {
    return {
      code: "attachment_too_large",
      key: "console.error_attachment_too_large",
    };
  }
  const mime = (file.type || "").toLowerCase();
  if (mime && ATTACHMENT_ALLOWED_MIME.has(mime)) return null;
  // Some browsers / drag-drop scenarios omit a MIME — fall back to extension.
  const name = (file.name || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  if (dot >= 0 && ATTACHMENT_ALLOWED_EXT.has(name.slice(dot))) return null;
  return {
    code: "attachment_type_not_allowed",
    key: "console.error_attachment_type",
  };
}
