/** Drag-and-tell target kinds and helpers. */

export const TARGET_KINDS = {
  MEMO_BULLET: "memo_bullet",
  METRIC: "metric",
  EVIDENCE_CLAIM: "evidence_claim",
  MEMO_WARNING: "memo_warning",
  GATE_FINDING: "gate_finding",
  DOCUMENT_SUMMARY: "document_summary",
  REPORT_SIGNAL: "report_signal",
};

export function buildSelection(targetKind, payload = {}) {
  return {
    target_kind: targetKind,
    ...payload,
  };
}

export function dropZoneKey(targetKind, targetId = "default") {
  return `${targetKind}:${targetId}`;
}

export function buildDragTellPrompt(selection = {}) {
  const kind = selection.target_kind;
  const label =
    selection.label
    || selection.bullet_text
    || selection.claim
    || selection.warning
    || selection.metric_label
    || selection.signal
    || selection.excerpt
    || "this item";

  if (kind === TARGET_KINDS.METRIC) {
    return (
      `Trace where this metric comes from (${label}: ${selection.metric_value || "n/a"}). `
      + "List supporting sources, freshness, and evidence gaps."
    );
  }
  if (kind === TARGET_KINDS.EVIDENCE_CLAIM) {
    return (
      `Explain the evidence behind this claim and what would change your mind: ${label}`
    );
  }
  if (kind === TARGET_KINDS.MEMO_WARNING) {
    return `Explain this memo quality warning and the fastest fix: ${label}`;
  }
  if (kind === TARGET_KINDS.GATE_FINDING) {
    return `Explain this memo gate finding and what source would clear it: ${label}`;
  }
  if (kind === TARGET_KINDS.DOCUMENT_SUMMARY) {
    return (
      `Trace the sources behind this document summary and flag anything unsupported: ${label}`
    );
  }
  if (kind === TARGET_KINDS.REPORT_SIGNAL) {
    return `Where does this sector signal come from and how does it affect the thesis? ${label}`;
  }
  if (kind === TARGET_KINDS.MEMO_BULLET) {
    return (
      "Trace where this memo point comes from. Cite staged sources and list gaps. "
      + `Point: ${selection.bullet_text || label}`
    );
  }
  return `Where does this data come from? Explain sources, confidence, and gaps for: ${label}`;
}

export function activateCopilotTarget(openCopilot, { companyId, surface, tab, selection }) {
  if (!openCopilot || !companyId || !selection?.target_kind) return;
  openCopilot({
    companyId,
    mode: "quick",
    dragTell: true,
    context: {
      surface,
      tab: tab || null,
      selection,
    },
    prompt: buildDragTellPrompt(selection),
  });
}
