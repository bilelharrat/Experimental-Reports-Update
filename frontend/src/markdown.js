// Minimal, dependency-free Markdown → HTML renderer for assistant
// answers (Console transcript, etc.).
//
// SECURITY: the input is LLM-generated text rendered via `v-html`, so it
// MUST NOT be able to inject markup. We HTML-escape the *entire* input
// first; every transform below only ever adds tags we generate, never
// interprets raw HTML from the model. Links are restricted to
// http/https/mailto. This is intentionally a small, safe subset (the
// alternative — marked + DOMPurify — would add two runtime deps to a
// deliberately lean frontend).

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Inline spans, applied to already-escaped text. Order matters:
// code first (so its contents aren't re-processed), then links, then
// bold, then italic.
function renderInline(text) {
  let out = text;

  // `inline code`
  out = out.replace(
    /`([^`\n]+)`/g,
    (_m, code) => `<code class="md-code">${code}</code>`,
  );

  // [label](url) — only safe schemes; url is already HTML-escaped.
  out = out.replace(
    /\[([^\]\n]+)\]\(([^)\s]+)\)/g,
    (m, label, url) => {
      if (!/^(https?:|mailto:)/i.test(url)) return m;
      return `<a href="${url}" target="_blank" rel="noopener noreferrer" class="md-link">${label}</a>`;
    },
  );

  // **bold** (before italic so the double-star isn't eaten by it)
  out = out.replace(/\*\*([^\n]+?)\*\*/g, "<strong>$1</strong>");

  // *italic* / _italic_ (single delimiter, not adjacent to another star)
  out = out.replace(/(^|[^*])\*([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>");
  out = out.replace(/(^|[^_])_([^_\n]+?)_(?!_)/g, "$1<em>$2</em>");

  return out;
}

// Block-level pass. Groups lines into headings, ordered / unordered
// lists, horizontal rules, and paragraphs.
export function renderMarkdown(src) {
  if (!src) return "";
  const lines = escapeHtml(String(src)).split(/\r?\n/);
  const html = [];
  let i = 0;

  const flushList = (tag, items) => {
    const lis = items.map((it) => `<li>${renderInline(it)}</li>`).join("");
    html.push(`<${tag} class="md-list">${lis}</${tag}>`);
  };

  while (i < lines.length) {
    const line = lines[i];

    // Blank line → block separator.
    if (/^\s*$/.test(line)) {
      i += 1;
      continue;
    }

    // Horizontal rule.
    if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      html.push('<hr class="md-hr" />');
      i += 1;
      continue;
    }

    // Heading (#..######).
    const h = line.match(/^\s*(#{1,6})\s+(.*)$/);
    if (h) {
      const level = h[1].length;
      html.push(
        `<div class="md-h md-h${level}">${renderInline(h[2].trim())}</div>`,
      );
      i += 1;
      continue;
    }

    // Ordered list (consecutive `N.` lines).
    if (/^\s*\d+\.\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, ""));
        i += 1;
      }
      flushList("ol", items);
      continue;
    }

    // Unordered list (`-`, `*`, `+`).
    if (/^\s*[-*+]\s+/.test(line)) {
      const items = [];
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*+]\s+/, ""));
        i += 1;
      }
      flushList("ul", items);
      continue;
    }

    // Paragraph: consecutive non-blank lines that aren't another block.
    const para = [];
    while (
      i < lines.length &&
      !/^\s*$/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i]) &&
      !/^\s*[-*+]\s+/.test(lines[i]) &&
      !/^\s*(#{1,6})\s+/.test(lines[i]) &&
      !/^\s*([-*_])\1{2,}\s*$/.test(lines[i])
    ) {
      para.push(lines[i]);
      i += 1;
    }
    html.push(
      `<p class="md-p">${renderInline(para.join("<br />"))}</p>`,
    );
  }

  return html.join("");
}
