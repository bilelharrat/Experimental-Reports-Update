import { t } from "./i18n.js";

/**
 * Ask before any manual action that spends tokens.
 *
 * Owner policy (2026-09-15): a button that costs money says so first.
 * Report generation is the one exception — everybody already knows a
 * memo run costs, and confirming it twice only trains people to click
 * through. Conversational sends (Ask, Console) are exempt for the same
 * reason: the whole point of the box is that it answers. The Team tab's
 * "Research team" (2026-09-22) is exempt too: it runs the cheapest, fastest
 * Gemini tier, cheap enough that a blocking dialog costs more of the
 * person's time than the call costs in tokens — the button's tooltip says
 * it searches the web, which is disclosure enough for something this small.
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
