import { t } from "./i18n.js";

/**
 * Ask before any manual action that spends tokens.
 *
 * Owner policy (2026-09-15): a button that costs money says so first.
 * Report generation is the one exception — everybody already knows a
 * memo run costs, and confirming it twice only trains people to click
 * through. Conversational sends (Ask, Console) are exempt for the same
 * reason: the whole point of the box is that it answers.
 *
 * `detail` is an optional already-translated line of extra context
 * ("16 headlines", "every tracked company") shown under the warning.
 */
export function confirmTokenSpend(detail = "") {
  const lines = [t("tokens.confirm")];
  if (detail) lines.push(detail);
  return window.confirm(lines.join("\n\n"));
}

export default confirmTokenSpend;
