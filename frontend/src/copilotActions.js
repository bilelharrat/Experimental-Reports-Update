/** Resolve situational Co-Pilot actions returned by the server. */
export function resolveCopilotAction(action, t, context = {}) {
  const selection = context.selection || {};
  const attention = context.attention || {};
  const job = context.job || {};
  const workspace = context.workspace || {};
  const label = t(action.label_key);
  const vars = {
    company: context.company_name || "",
    bullet: selection.bullet_text || selection.card_title || "",
    section: selection.section_title || "",
    attention: attention.label || "",
    failure: workspace.memo_failure || job.detail || "",
    contradicted: workspace.evidence_contradicted || attention.count || "",
    label:
      selection.label
      || selection.bullet_text
      || selection.claim
      || selection.metric_label
      || selection.warning
      || selection.signal
      || "",
  };
  let prompt = t(action.prompt_key);
  for (const [key, value] of Object.entries(vars)) {
    prompt = prompt.replaceAll(`{${key}}`, String(value || ""));
  }
  return { id: action.id, label, prompt };
}

export function buildDiscussPrompt(context = {}) {
  const bullet = context.bullet_text || context.card_title || "";
  const section = context.section_title || "";
  const parts = [
    "Challenge this memo point. Lead with disconfirming evidence and cite staged sources.",
  ];
  if (section) parts.push(`Section: ${section}`);
  if (bullet) parts.push(`Point: ${bullet}`);
  return parts.join("\n");
}

export function buildDiveDeeperPrompt(context = {}) {
  const bullet = context.bullet_text || context.card_title || "";
  const section = context.section_title || "";
  const parts = [
    "I just ran dive-deeper on this memo bullet. Summarize what new evidence we need, where to find it in staged files, and what would falsify the claim.",
  ];
  if (section) parts.push(`Section: ${section}`);
  if (bullet) parts.push(`Point: ${bullet}`);
  return parts.join("\n");
}

const STRUCTURED_BLOCK_RE = /```json\s*(\{[\s\S]*?\})\s*```/g;
const STRUCTURED_KEYS = ["research_task", "suggested_edit", "next_route", "contradiction"];

export function parseStructuredOutputs(text = "") {
  const outputs = Object.fromEntries(STRUCTURED_KEYS.map((key) => [key, null]));
  let match;
  while ((match = STRUCTURED_BLOCK_RE.exec(text)) !== null) {
    try {
      const payload = JSON.parse(match[1]);
      for (const key of STRUCTURED_KEYS) {
        if (payload?.[key] && typeof payload[key] === "object") {
          outputs[key] = payload[key];
        }
      }
    } catch {
      /* ignore malformed blocks */
    }
  }
  return outputs;
}

export function stripStructuredBlocks(text = "") {
  return text.replace(STRUCTURED_BLOCK_RE, "").trim();
}

const CITATION_RE = /\(([^)]+?\.(?:pdf|docx?|xlsx?|pptx?|md|txt|csv|png|jpe?g|webp))\s*(?:p\.|page|slide)\s*(\d+)\)/gi;

export function extractCitations(text = "") {
  const citations = [];
  const seen = new Set();
  let match;
  while ((match = CITATION_RE.exec(text)) !== null) {
    const key = `${match[1]}:${match[2]}`;
    if (seen.has(key)) continue;
    seen.add(key);
    citations.push({
      file: match[1],
      page: match[2],
      label: `${match[1]} p.${match[2]}`,
    });
  }
  return citations;
}

export function resolveCitationTarget(citation, files = []) {
  if (!citation?.file) return null;
  const needle = String(citation.file).toLowerCase();
  const file = files.find((row) => String(row.filename || "").toLowerCase() === needle)
    || files.find((row) => String(row.filename || "").toLowerCase().endsWith(needle));
  if (!file) return { kind: "missing", filename: citation.file, page: citation.page };
  return {
    kind: "file",
    file,
    page: citation.page,
  };
}

export function parseResearchTask(text = "") {
  return parseStructuredOutputs(text).research_task;
}

export function stripResearchTaskBlock(text = "") {
  return stripStructuredBlocks(text);
}

export function followUpChips(structured = {}, t = (key) => key) {
  const chips = [];
  if (structured.contradiction?.claim) {
    chips.push({
      id: "resolve_contradiction",
      label: t("copilot.followup_resolve"),
      prompt: `How should we resolve this contradiction: ${structured.contradiction.claim}`,
    });
  }
  if (structured.suggested_edit?.text) {
    chips.push({
      id: "refine_edit",
      label: t("copilot.followup_refine"),
      prompt: "Refine the suggested memo edit — keep it shorter and more IC-ready.",
    });
  }
  chips.push({
    id: "evidence_next",
    label: t("copilot.followup_evidence"),
    prompt: "What is the single best next source to read?",
  });
  return chips.slice(0, 3);
}
