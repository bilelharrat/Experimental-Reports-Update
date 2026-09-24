// Anchoring a reader's flag in a docx-preview render (G7): the selected
// text, and the heading it sits under — the renderer's section bookmarks
// (bsh_sec_*, the same in EN and ZH), else Word heading styles (Buffett
// memos). The Reports viewer uses its own outline for the same answer.

function labelOf(el) {
  const text = (node) => String(node?.textContent || "").replace(/\s+/g, " ").trim();
  let label = text(el);
  if (!label) label = text(el?.nextElementSibling);
  return label.length > 90 ? `${label.slice(0, 88)}…` : label;
}

/** The headings of a rendered document, in document order: [{ el, label }]. */
export function documentHeadings(root) {
  if (!root?.querySelectorAll) return [];
  const marks = [...root.querySelectorAll('[id^="bsh_sec_"]')].map((mark) => mark.closest("p") || mark);
  const nodes = marks.length ? marks : [...root.querySelectorAll(".docx_heading1, .docx_heading2")];
  return nodes.map((el) => ({ el, label: labelOf(el) })).filter((heading) => heading.label);
}

/** The label of the last heading at or before `node`, or "". */
export function headingBefore(headings, node) {
  let label = "";
  if (!node) return label;
  for (const heading of headings || []) {
    const el = heading.el;
    const precedes =
      el === node ||
      el.contains(node) ||
      Boolean(el.compareDocumentPosition(node) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (!precedes) break;
    label = heading.label;
  }
  return label;
}

/**
 * The reader's text selection inside `container`: { quote (≤ max chars,
 * whitespace collapsed), range } — or null when nothing (or too little)
 * is selected there.
 */
export function selectionIn(container, max = 300) {
  if (!container || typeof window.getSelection !== "function") return null;
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !selection.rangeCount) return null;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) return null;
  const quote = String(selection.toString() || "").replace(/\s+/g, " ").trim();
  if (quote.length < 2) return null;
  return { quote: quote.slice(0, max), range };
}

/** The report id in a memo download or preview URL (/api/reports/<id>/…), or "". */
export function reportIdFromUrl(url) {
  const match = String(url || "").match(/\/api\/reports\/([^/?#]+)\/(?:download|preview)\b/);
  if (!match) return "";
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}
