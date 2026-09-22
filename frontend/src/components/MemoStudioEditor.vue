<script setup>
// Web twin of MacMemoStudioView.swift — the Memo Studio Workbench.
// Header with the HUMAN-IN-THE-LOOP badge, the synthesize / spine-active
// action banner, and the five editorial sections restyled to the Mac desk
// language, plus the Mac workbench features the web lacked: move up/down,
// double-click title rename, risk refine-framing, and the Readiness Gates
// and Evidence Claims sections. Web-native features stay: drag reorder,
// bullet tree with dive-deeper/discuss, tasks, export gating, history.
import { computed, inject, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { collapseRuns } from "../collapseRuns.js";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Circle,
  Download,
  FileSearch,
  GripVertical,
  ListChecks,
  Loader2,
  MinusCircle,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  X,
  XCircle,
} from "lucide-vue-next";
import { useRouter } from "vue-router";
import { api } from "../api.js";
import { formatIsoDate, formatRelativeTime, humanizeStatus } from "../formatters.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import AiMark from "./AiMark.vue";
import MemoStudioBulletTree from "./memo/MemoStudioBulletTree.vue";

const props = defineProps({
  companyId: { type: String, required: true },
  generateAvailable: { type: Boolean, default: false },
  generating: { type: Boolean, default: false },
  // Company reports from the dossier: drives the awaiting-studio synthesize
  // banner and the Open Memo View shortcut, like the Mac workbench.
  reports: { type: Array, default: () => [] },
  // Bumped by the parent when an investigation seeds fresh cards, so an
  // already-mounted editor reloads instead of showing stale state.
  refreshKey: { type: String, default: "" },
  // A listed company raises no private round, so its summary drops the
  // Round tile rather than showing "Pending" forever.
  isPublic: { type: Boolean, default: false },
  // A memo point to show on arrival: one Warren just edited ({ bullet }) or
  // a section he pointed at ({ section }). `key` tells one ask from the
  // next. The editor reloads first: the edit landed after it loaded.
  focus: { type: Object, default: null },
});

const emit = defineEmits(["discuss", "generate", "synthesized"]);
const t = useT();
const router = useRouter();

const editor = ref(null);
const loading = ref(true);
const error = ref("");
const savingId = ref("");
const exportResult = ref(null);
const exportError = ref("");
const exporting = ref(false);
const history = ref({ versions: [], audit_records: [], memo_tasks: [] });
const historyError = ref("");
const errorMessage = computed(() =>
  error.value === "load" ? t("memo.load_error") : t("memo.action_failed"),
);
const historyErrorMessage = computed(() =>
  historyError.value === "load" ? t("memo.history_error") : t("memo.action_failed"),
);
const exportErrorMessage = computed(() => t("memo.export_error"));

const sectionIds = [
  "executive_summary",
  "investment_thesis",
  "risks_mitigations",
  "conclusion",
  "appendix",
];

const sections = computed(() => editor.value?.sections || {});
const thesisCards = computed(() => orderedCards("investment_thesis"));
const riskCards = computed(() => orderedCards("risks_mitigations"));
const conclusion = computed(() => sections.value.conclusion || {});
const appendixBlocks = computed(() => sections.value.appendix?.blocks || []);
const memoTasks = computed(() => {
  const rows = history.value?.memo_tasks || editor.value?.memo_tasks || [];
  const seen = new Set();
  return rows.filter((task) => {
    const signature = `${task.title || ""}|${task.description || ""}`
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
    if (!signature || seen.has(signature)) return false;
    seen.add(signature);
    return true;
  });
});
const auditRecords = computed(() => history.value?.audit_records || editor.value?.audit_records || []);
const versions = computed(() => history.value?.versions || []);
// Repeats of the same event fold into one row ("Conclusion Selected ×5");
// the counts above still count every revision and every event.
const versionRuns = computed(() => collapseRuns(versions.value, (v) => v.event || ""));
const auditRuns = computed(() =>
  collapseRuns(
    auditRecords.value,
    (r) => `${r.event || ""}|${formatIsoDate(r.created_at) || ""}`,
  ),
);
const completedSections = computed(() =>
  sectionIds.filter((id) => {
    const status = String(sections.value[id]?.status || "").toLowerCase();
    return ["done", "complete", "completed", "approved", "ready"].includes(status);
  }).length,
);
const progressPct = computed(() =>
  Math.round((completedSections.value / sectionIds.length) * 100),
);

// The Mac workbench's studio flow, from the dossier's report list.
const awaitingStudioReport = computed(() =>
  (props.reports || []).find((rep) => rep.status === "awaiting_studio"),
);
const latestOpenableReport = computed(() =>
  (props.reports || []).find((rep) => rep.status === "complete" || rep.can_open),
);

const synthesizing = ref(false);
const synthesisStarted = ref(false);

async function synthesizeFromStudio() {
  const awaiting = awaitingStudioReport.value;
  if (!awaiting || synthesizing.value) return;
  synthesizing.value = true;
  try {
    await api.studioGenerate(awaiting.id);
    synthesisStarted.value = true;
    emit("synthesized", awaiting.id);
  } catch {
    error.value = "action";
  } finally {
    synthesizing.value = false;
  }
}

function openMemoView() {
  const rep = latestOpenableReport.value;
  if (!rep) return;
  router.push({ name: "reports", query: { id: rep.id, company: props.companyId } });
}

function orderedCards(sectionId) {
  const cards = sections.value[sectionId]?.cards || [];
  const seen = new Set();
  const ordered = [...cards]
    .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0))
    .filter((card) => {
      const bulletText = (card.bullets || []).map((bullet) => bullet.text || "").join("|");
      const signature = `${card.title || ""}|${bulletText}`.toLowerCase().replace(/\s+/g, " ").trim();
      if (!signature || seen.has(signature)) return false;
      seen.add(signature);
      return true;
    });
  // During a drag (and while its save is in flight), render the live
  // preview order instead of the stored ranks.
  if (dragSectionId.value === sectionId && previewOrder.value.length) {
    const position = new Map(
      previewOrder.value.map((id, index) => [id, index]),
    );
    ordered.sort(
      (a, b) =>
        (position.get(String(a.id)) ?? 999) -
        (position.get(String(b.id)) ?? 999),
    );
  }
  return ordered;
}

const agentRun = computed(() => editor.value?.agent_run || null);
// Opens the report customizer on Memo Studio review — the run that replaces
// template cards with source-backed ones. It still asks before spending.
const openReportCustomizer = inject("openReportCustomizer", () => {});
const includedRiskCount = computed(
  () => riskCards.value.filter((card) => card.included).length,
);
const riskCountWarning = computed(
  () => includedRiskCount.value < 4 || includedRiskCount.value > 6,
);

const RATING_OPTIONS = Array.from({ length: 10 }, (_, i) => `${10 - i}/10`);
const LIKELIHOOD_OPTIONS = ["High", "Medium", "Low"];

function severityFromRating(rating) {
  const value = Number.parseInt(String(rating || ""), 10);
  if (!Number.isFinite(value)) return "medium";
  if (value >= 8) return "high";
  if (value >= 5) return "medium";
  return "low";
}

function likelihoodLabel(value) {
  if (value === "High") return t("memo.likelihood_high");
  if (value === "Medium") return t("memo.likelihood_medium");
  if (value === "Low") return t("memo.likelihood_low");
  return value;
}

// Left accent stripe per card, like the Mac severity tinting.
function cardStripe(sectionId, card) {
  if (sectionId === "risks_mitigations") {
    if (card.severity === "high" || card.severity === "critical") return "var(--mac-red)";
    if (card.severity === "medium") return "var(--mac-orange)";
    return "var(--mac-secondary)";
  }
  return "var(--mac-accent)";
}

// MacMemoStudioView.severityBadge tints.
function severityTint(severity) {
  switch (String(severity || "").toLowerCase()) {
    case "critical": return "var(--mac-red)";
    case "high": return "var(--mac-orange)";
    case "medium": return "var(--mac-yellow)";
    case "low": return "var(--mac-green)";
    default: return "var(--mac-secondary)";
  }
}

function statusTone(status) {
  const value = String(status || "").toLowerCase();
  if (["done", "complete", "completed", "approved", "ready"].includes(value)) return "var(--mac-green)";
  if (["error", "failed", "blocked"].includes(value)) return "var(--mac-red)";
  return "var(--mac-secondary)";
}

function sourceLabel(item) {
  return item?.source_class || item?.source_refs?.[0]?.source_class || t("memo.source_pending");
}

function sourceCount(item) {
  return Array.isArray(item?.source_refs) ? item.source_refs.length : 0;
}

function coverageLabel(result) {
  const coverage = result?.source_coverage;
  if (!coverage) return t("memo.coverage_pending");
  return t("memo.source_coverage", { pct: Math.round((coverage.coverage || 0) * 100) });
}

let loadRequest = 0;

async function load() {
  // Newest request wins: a company switch and a point Warren edited can
  // both ask for a reload in one tick, and the older answer must not land
  // over the newer one.
  const ticket = ++loadRequest;
  loading.value = true;
  error.value = "";
  exportResult.value = null;
  try {
    const state = await api.memoEditor.get(props.companyId);
    if (ticket !== loadRequest) return;
    editor.value = state;
    await loadHistory();
    // Never let the automatic gates read break the editor it sits in.
    loadGatesAndEvidence({ create: false }).catch(() => {});
  } catch {
    if (ticket === loadRequest) error.value = "load";
  } finally {
    if (ticket === loadRequest) loading.value = false;
  }
  if (ticket === loadRequest && !error.value) showFocus();
}

async function loadHistory() {
  historyError.value = "";
  try {
    history.value = await api.memoEditor.history(props.companyId);
  } catch {
    historyError.value = "load";
    history.value = {
      versions: [],
      audit_records: editor.value?.audit_records || [],
      memo_tasks: editor.value?.memo_tasks || [],
    };
  }
}

onMounted(load);
watch(() => props.companyId, () => {
  synthesisStarted.value = false;
  analysisData.value = null;
  evidenceData.value = null;
  refiningRiskId.value = "";
  load();
});
watch(
  () => props.refreshKey,
  () => {
    load();
  },
);

const rootEl = ref(null);
const focusedBulletId = ref("");
let shownFocusKey = null;
let focusGlowTimer = null;

function holdsBullet(bullets, id) {
  return (bullets || []).some(
    (bullet) => bullet.id === id || holdsBullet(bullet.children, id),
  );
}

// The card holding the point opens (on screen only: its saved state is left
// alone), and the point scrolls to the middle and glows for a moment.
async function showFocus() {
  const focus = props.focus;
  if (!focus || focus.key === shownFocusKey) return;
  shownFocusKey = focus.key;
  const card = focus.bullet
    ? [focus.section, ...sectionIds]
        .flatMap((id) => sections.value[id]?.cards || [])
        .find((item) => holdsBullet(item.bullets, focus.bullet))
    : null;
  if (card) card.expanded = true;
  await nextTick();
  const point = card
    ? [...(rootEl.value?.querySelectorAll("[data-bullet-id]") || [])].find(
        (el) => el.dataset.bulletId === focus.bullet,
      )
    : null;
  if (point) {
    point.scrollIntoView({ behavior: "smooth", block: "center" });
    focusedBulletId.value = focus.bullet;
    clearTimeout(focusGlowTimer);
    focusGlowTimer = setTimeout(() => {
      focusedBulletId.value = "";
    }, 2400);
  } else if (navSections.value.some((section) => section.id === focus.section)) {
    jumpTo(focus.section);
  }
}

watch(
  () => props.focus,
  (focus) => {
    if (focus) load();
  },
);
onBeforeUnmount(() => clearTimeout(focusGlowTimer));

function applyState(state) {
  editor.value = state;
  exportResult.value = null;
  loadHistory();
}

async function patchCard(sectionId, card, patch) {
  savingId.value = `${sectionId}:${card.id}`;
  try {
    applyState(await api.memoEditor.patchCard(props.companyId, sectionId, card.id, patch));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

// ---- Move up/down (Mac workbench chevrons) --------------------------------

async function moveCard(sectionId, card, direction) {
  savingId.value = `move:${sectionId}:${card.id}`;
  try {
    applyState(await api.memoEditor.moveCard(props.companyId, sectionId, card.id, direction));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

// ---- Double-click title rename (Mac workbench) ----------------------------

const editingTitleId = ref("");
const titleDraft = ref("");

function startTitleEdit(card) {
  editingTitleId.value = card.id;
  titleDraft.value = card.title || "";
}

async function commitTitleEdit(sectionId, card) {
  const title = titleDraft.value.trim();
  editingTitleId.value = "";
  if (!title || title === card.title) return;
  await patchCard(sectionId, card, { title });
}

// ---- Risk refine framing (Mac workbench) ----------------------------------

const refiningRiskId = ref("");
const refineFraming = ref("other");
const refineNote = ref("");
const refineBusy = ref(false);
const refinedRiskIds = ref(new Set());

const FRAMING_OPTIONS = [
  ["other", "memo.framing_other"],
  ["overstated", "memo.framing_overstated"],
  ["understated", "memo.framing_understated"],
  ["mitigated", "memo.framing_mitigated"],
];

function toggleRefine(card) {
  if (refiningRiskId.value === card.id) {
    refiningRiskId.value = "";
    return;
  }
  refiningRiskId.value = card.id;
  refineFraming.value = "other";
  refineNote.value = "";
}

async function applyRefinement(card) {
  if (refineBusy.value) return;
  refineBusy.value = true;
  try {
    await api.memoAnalysis.refineRisk(props.companyId, card.id, {
      framing: refineFraming.value,
      analyst_note: refineNote.value.trim(),
    });
    refinedRiskIds.value = new Set([...refinedRiskIds.value, card.id]);
    refiningRiskId.value = "";
    await loadHistory();
  } catch {
    error.value = "action";
  } finally {
    refineBusy.value = false;
  }
}

// ---- Readiness gates & evidence claims (Mac workbench tabs 3–4) -----------
// Load on ask: fetching the memo analysis opens a Studio session server-side.

const analysisData = ref(null);
const evidenceData = ref(null);
const gatesBusy = ref(false);

const readinessAreas = computed(() => analysisData.value?.additional_areas || []);
const evidenceClaims = computed(() => evidenceData.value?.claims || []);

// Loaded with the editor now, not behind a Load button: whether a memo can
// be exported is the thing this panel exists to say. That automatic read
// passes `create: false` so it never starts a session; Refresh still does.
let gatesRequest = 0;
async function loadGatesAndEvidence({ create = true } = {}) {
  // Newest request wins. A busy flag used to drop the call instead, so
  // switching company mid-load left the new company without its gates.
  const ticket = ++gatesRequest;
  gatesBusy.value = true;
  const forCompany = props.companyId;
  try {
    const [analysisRes, evidenceRes] = await Promise.allSettled([
      api.memoAnalysis.get(forCompany, { create }),
      api.memoAnalysis.getEvidenceMatrix(forCompany),
    ]);
    if (ticket !== gatesRequest) return;
    if (analysisRes.status === "fulfilled") analysisData.value = analysisRes.value;
    // No session yet reads as "nothing logged", not as "never loaded".
    else if (analysisRes.reason?.status === 404) analysisData.value = {};
    if (evidenceRes.status === "fulfilled") evidenceData.value = evidenceRes.value;
  } finally {
    if (ticket === gatesRequest) gatesBusy.value = false;
  }
}

function areaIcon(status) {
  const value = String(status || "open").toLowerCase();
  if (["clear", "passed", "approved", "reviewed"].includes(value)) return CheckCircle2;
  if (value === "waived") return MinusCircle;
  if (["blocker", "critical", "failed"].includes(value)) return XCircle;
  return AlertTriangle;
}

function areaTint(status) {
  const value = String(status || "open").toLowerCase();
  if (["clear", "passed", "approved", "reviewed"].includes(value)) return "var(--mac-green)";
  if (value === "waived") return "var(--mac-orange)";
  if (["blocker", "critical", "failed"].includes(value)) return "var(--mac-red)";
  return "var(--mac-orange)";
}

function claimTint(status) {
  const value = String(status || "").toLowerCase();
  if (value === "supported") return "var(--mac-green)";
  if (value === "contradicted") return "var(--mac-red)";
  if (value === "partial" || value === "mixed") return "var(--mac-orange)";
  return "var(--mac-secondary)";
}

function claimLabel(status) {
  const value = String(status || "").toLowerCase();
  if (value === "supported") return t("memo.claim_supported");
  if (value === "contradicted") return t("memo.claim_contradicted");
  if (value === "partial" || value === "mixed") return t("memo.claim_mixed");
  return t("memo.claim_unverified");
}

// ---- Section jump bar ------------------------------------------------------

const navSections = computed(() => [
  { id: "executive_summary", num: "01", label: t("memo.executive_summary") },
  { id: "investment_thesis", num: "02", label: t("memo.investment_thesis"), count: thesisCards.value.length },
  { id: "risks_mitigations", num: "03", label: t("memo.risks"), count: riskCards.value.length },
  { id: "conclusion", num: "04", label: t("memo.conclusion") },
  { id: "appendix", num: "05", label: t("memo.appendix") },
  { id: "readiness_gates", num: "06", label: t("memo.readiness_gates") },
  { id: "evidence_claims", num: "07", label: t("memo.evidence_claims") },
]);
const activeNav = ref("executive_summary");

function jumpTo(id) {
  activeNav.value = id;
  document.getElementById(`memo-sec-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- Drag-to-reorder (live preview) ---------------------------------------
// The card body stays selectable: dragging arms only from the grip handle
// (mousedown sets dragArmedId, which is what makes the article draggable).
// While dragging, `previewOrder` holds the would-be order and the list
// renders it live (TransitionGroup animates the moves); releasing over the
// list commits it, releasing elsewhere (or Esc) snaps back.

const dragArmedId = ref("");
const dragCardId = ref("");
const dragSectionId = ref("");
const previewOrder = ref([]);

// The full section order by rank — NOT the deduped display list: the
// backend requires a complete permutation of the section's card ids.
function rawOrderedIds(sectionId) {
  const cards = sections.value[sectionId]?.cards || [];
  return [...cards]
    .sort((a, b) => Number(a.rank || 0) - Number(b.rank || 0))
    .map((card) => String(card.id));
}

function armDrag(cardId) {
  dragArmedId.value = cardId;
}

function disarmDrag() {
  if (!dragCardId.value) dragArmedId.value = "";
}

function onDragStart(event, sectionId, card) {
  if (dragArmedId.value !== card.id) {
    event.preventDefault();
    return;
  }
  dragCardId.value = card.id;
  dragSectionId.value = sectionId;
  previewOrder.value = rawOrderedIds(sectionId);
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    try {
      event.dataTransfer.setData("text/plain", card.id);
    } catch {
      // Some environments (tests) have no DataTransfer — harmless.
    }
  }
}

function onDragOver(event, sectionId, card) {
  if (
    !dragCardId.value ||
    dragSectionId.value !== sectionId ||
    card.id === dragCardId.value
  ) {
    return;
  }
  // Cursor position → order (idempotent for a stationary cursor, so the
  // live preview cannot oscillate): top half inserts the dragged card
  // before this one, bottom half after.
  const rect = event.currentTarget?.getBoundingClientRect?.();
  const after =
    !rect || !rect.height
      ? true
      : event.clientY - rect.top >= rect.height / 2;
  const order = previewOrder.value.filter((id) => id !== dragCardId.value);
  const targetIndex = order.indexOf(String(card.id));
  const insertAt =
    targetIndex < 0 ? order.length : targetIndex + (after ? 1 : 0);
  order.splice(insertAt, 0, dragCardId.value);
  if (order.join("|") !== previewOrder.value.join("|")) {
    previewOrder.value = order;
  }
}

function onDragEnd() {
  dragArmedId.value = "";
  dragCardId.value = "";
  dragSectionId.value = "";
  previewOrder.value = [];
}

async function commitDrag(sectionId) {
  if (!dragCardId.value || dragSectionId.value !== sectionId) return;
  const order = [...previewOrder.value];
  if (order.join("|") === rawOrderedIds(sectionId).join("|")) {
    onDragEnd();
    return;
  }
  // Keep the preview applied while the save is in flight so the list
  // doesn't snap back and forth; the server state lands with the same
  // order, then the preview clears invisibly.
  dragCardId.value = "";
  dragArmedId.value = "";
  savingId.value = `${sectionId}:reorder`;
  try {
    applyState(
      await api.memoEditor.reorderCards(props.companyId, sectionId, order),
    );
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
    dragSectionId.value = "";
    previewOrder.value = [];
  }
}

const addingSection = ref("");
const newCardTitle = ref("");

function toggleAddCard(sectionId) {
  if (addingSection.value === sectionId) {
    addCard(sectionId);
    return;
  }
  addingSection.value = sectionId;
  newCardTitle.value = "";
}

async function addCard(sectionId) {
  const title = newCardTitle.value.trim();
  if (!title) {
    addingSection.value = "";
    return;
  }
  savingId.value = `add:${sectionId}`;
  try {
    applyState(
      await api.memoEditor.addCard(props.companyId, sectionId, { title }),
    );
    newCardTitle.value = "";
    addingSection.value = "";
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function removeCard(sectionId, card) {
  savingId.value = `remove:${sectionId}:${card.id}`;
  try {
    applyState(
      await api.memoEditor.deleteCard(props.companyId, sectionId, card.id),
    );
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function setRiskRating(card, rating) {
  await patchCard("risks_mitigations", card, {
    agent_rating: rating,
    // Keep the severity tone in sync with the pinned rating.
    severity: severityFromRating(rating),
  });
}

async function setRiskLikelihood(card, likelihood) {
  await patchCard("risks_mitigations", card, { likelihood });
}

async function selectConclusion(option) {
  savingId.value = `conclusion:${option.id}`;
  try {
    applyState(await api.memoEditor.selectConclusion(props.companyId, option.id));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function rerunSection(sectionId) {
  savingId.value = `rerun:${sectionId}`;
  try {
    applyState(await api.memoEditor.rerunSection(props.companyId, sectionId));
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function toggleAppendix(block) {
  savingId.value = `appendix:${block.id}`;
  try {
    applyState(
      await api.memoEditor.patchAppendixBlock(props.companyId, block.id, {
        expanded: !block.expanded,
      }),
    );
  } catch {
    error.value = "action";
  } finally {
    savingId.value = "";
  }
}

async function projectExport() {
  exporting.value = true;
  exportError.value = "";
  try {
    exportResult.value = await api.memoEditor.exportProjection(props.companyId, {
      record: true,
    });
    await loadHistory();
  } catch {
    exportError.value = "export";
  } finally {
    exporting.value = false;
  }
}

async function discuss(context) {
  const taskPayload = {
    action_type: "discuss",
    title: t("memo.discuss_title", { point: context.card_title || context.bullet_text || t("memo.memo_point") }),
    description: context.bullet_text || t("memo.discuss_description"),
    context: {
      ...context,
      company_id: props.companyId,
      memo_version_id: editor.value?.version_id,
    },
    status: "proposed",
  };
  try {
    await api.memoEditor.createTask(props.companyId, taskPayload);
    await loadHistory();
  } catch {
    historyError.value = "action";
  }
  emit("discuss", taskPayload.context);
}

async function setTaskStatus(task, status) {
  savingId.value = `task:${task.id}`;
  historyError.value = "";
  try {
    await api.memoEditor.updateTask(props.companyId, task.id, { status });
    await loadHistory();
  } catch {
    historyError.value = "action";
  } finally {
    savingId.value = "";
  }
}
</script>

<template>
  <section ref="rootEl" class="mac-card flex flex-col gap-3.5 p-[18px]">
    <!-- Workbench header (MacMemoStudioView.studioHeader) -->
    <div class="flex flex-wrap items-center gap-3">
      <SlidersHorizontal class="mac-c-accent h-4 w-4 shrink-0" stroke-width="2.4" />
      <div class="flex min-w-0 flex-col gap-0.5">
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="mac-t-headline">{{ t("memo.workbench_title") }}</h2>
          <span
            class="rounded-full px-1.5 py-[2px] text-[9px] font-bold tracking-wide"
            :style="{
              background: 'color-mix(in srgb, var(--mac-accent) 12%, transparent)',
              color: 'var(--mac-accent)',
            }"
          >
            {{ t("memo.workbench_hitl") }}
          </span>
        </div>
        <p class="mac-t-caption mac-c-secondary">{{ t("memo.workbench_subtitle") }}</p>
      </div>
      <span class="min-w-2 flex-1" />
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="mac-btn mac-btn--sm" :title="t('common.refresh')" @click="load">
          <RefreshCw class="h-3 w-3" />
          <span>{{ t("common.refresh") }}</span>
        </button>
        <button
          type="button"
          class="mac-btn mac-btn--sm"
          :disabled="exporting || loading"
          @click="projectExport"
        >
          <Loader2 v-if="exporting" class="h-3 w-3 animate-spin" />
          <Download v-else class="h-3 w-3" />
          <span>{{ t("memo.export") }}</span>
        </button>
        <button
          v-if="generateAvailable"
          type="button"
          class="mac-btn mac-btn--sm mac-btn--prominent"
          :disabled="generating || loading"
          @click="emit('generate')"
        >
          <Loader2 v-if="generating" class="h-3 w-3 animate-spin" />
          <AiMark v-else class="h-3 w-3 shrink-0" />
          <span>{{ t("memo.generate_report") }}</span>
        </button>
      </div>
    </div>

    <!-- Action banner: parked investigation → synthesize; else spine active -->
    <div
      v-if="awaitingStudioReport && !synthesisStarted"
      class="flex flex-wrap items-center gap-3 rounded-lg p-3"
      :style="{
        background: 'color-mix(in srgb, var(--mac-orange) 8%, transparent)',
        boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--mac-orange) 25%, transparent)',
      }"
    >
      <span class="h-2.5 w-2.5 shrink-0 animate-pulse rounded-full" :style="{ background: 'var(--mac-orange)' }" />
      <span class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-subhead font-semibold" :style="{ color: 'var(--mac-orange)' }">
          {{ t("memo.parked_title") }}
        </span>
        <span class="mac-t-caption mac-c-secondary">{{ t("memo.parked_subtitle") }}</span>
      </span>
      <span class="min-w-2 flex-1" />
      <button
        type="button"
        class="mac-btn mac-btn--sm mac-btn--prominent mac-btn--tinted shrink-0"
        :style="{ '--tint': 'var(--mac-orange)' }"
        :disabled="synthesizing"
        @click="synthesizeFromStudio"
      >
        <Loader2 v-if="synthesizing" class="h-3 w-3 animate-spin" />
        <Sparkles v-else class="h-3 w-3" />
        <span>{{ t("memo.synthesize_phase3") }}</span>
      </button>
    </div>
    <div
      v-else
      class="flex flex-wrap items-center gap-2.5 rounded-lg p-2.5"
      style="background: color-mix(in srgb, var(--mac-secondary) 4%, transparent)"
    >
      <CheckCircle2 class="h-3.5 w-3.5 shrink-0" :style="{ color: 'var(--mac-green)' }" />
      <span class="mac-t-caption mac-c-secondary min-w-0">
        {{ synthesisStarted ? t("memo.synthesis_started") : t("memo.spine_active") }}
      </span>
      <span class="min-w-2 flex-1" />
      <button
        v-if="latestOpenableReport"
        type="button"
        class="mac-btn mac-btn--mini"
        @click="openMemoView"
      >
        <BookOpen class="h-3 w-3" />
        <span>{{ t("memo.open_memo_view") }}</span>
      </button>
    </div>

    <!-- Provenance -->
    <div
      v-if="agentRun"
      class="mac-t-caption mac-c-secondary rounded-md px-2.5 py-1.5"
      style="background: color-mix(in srgb, var(--mac-accent) 6%, transparent)"
    >
      {{
        t("memo.seeded_from_run", {
          mode: agentRun.mode,
          date: formatIsoDate(agentRun.seeded_at),
        })
      }}
    </div>
    <div
      v-else-if="!loading && editor"
      class="flex flex-wrap items-center gap-2.5 rounded-lg p-3"
      :style="{ background: 'color-mix(in srgb, var(--mac-orange) 9%, transparent)' }"
      data-testid="not-investigated"
    >
      <AlertTriangle class="h-4 w-4 shrink-0" :style="{ color: 'var(--mac-orange)' }" />
      <span class="flex min-w-0 flex-1 flex-col gap-0.5">
        <span class="mac-t-subhead font-semibold">{{ t("memo.not_investigated_title") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("memo.no_agent_seed") }}</span>
      </span>
      <button
        type="button"
        class="mac-btn mac-btn--mini mac-btn--prominent"
        data-testid="run-deep-investigate"
        @click="openReportCustomizer(companyId, { mode: 'studio_review' })"
      >
        <Sparkles class="h-3 w-3" />
        <span>{{ t("memo.run_deep_investigate") }}</span>
      </button>
    </div>

    <div v-if="loading" class="mac-t-caption mac-c-secondary flex items-center gap-2 py-4">
      <Loader2 class="h-3.5 w-3.5 animate-spin" />
      {{ t("memo.loading") }}
    </div>
    <div v-else-if="error" class="mac-t-caption rounded-md p-2.5" :style="{ color: 'var(--mac-red)', background: 'color-mix(in srgb, var(--mac-red) 8%, transparent)' }">
      {{ errorMessage }}
    </div>

    <template v-else-if="editor">
      <!-- Readiness + version strip -->
      <div class="grid gap-2.5 md:grid-cols-[1fr_auto]">
        <div class="mac-tile flex flex-col justify-center gap-1.5 p-3" style="border-radius: 10px">
          <div class="mac-t-caption mac-c-secondary flex items-center justify-between gap-3">
            <span>{{ t("memo.readiness", { ready: completedSections, total: sectionIds.length }) }}</span>
            <span class="mac-mono">{{ progressPct }}%</span>
          </div>
          <div class="h-1 rounded-full" style="background: color-mix(in srgb, var(--mac-secondary) 15%, transparent)">
            <div
              class="h-1 rounded-full transition-all duration-500"
              :style="{ width: `${progressPct}%`, background: progressPct === 100 ? 'var(--mac-green)' : 'var(--mac-accent)' }"
            />
          </div>
        </div>
        <div class="mac-tile flex flex-col justify-center gap-0.5 p-3" style="border-radius: 10px">
          <span class="mac-t-subheadline font-semibold">
            {{ editor.version_id || "v1" }} · {{ humanizeStatus(editor.status, t("memo.draft"), appLanguage) }}
          </span>
          <span class="mac-t-caption10 mac-mono mac-c-secondary">
            {{ t("memo.updated") }} {{ formatIsoDate(editor.updated_at, t("memo.pending")) }}
          </span>
        </div>
      </div>

      <!-- Export gate result -->
      <div
        v-if="exportResult"
        class="flex items-start gap-2.5 rounded-lg p-3"
        :style="
          exportResult.blocked
            ? { background: 'color-mix(in srgb, var(--mac-orange) 8%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--mac-orange) 25%, transparent)' }
            : { background: 'color-mix(in srgb, var(--mac-green) 7%, transparent)', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--mac-green) 22%, transparent)' }
        "
      >
        <AlertTriangle v-if="exportResult.blocked" class="mt-0.5 h-4 w-4 shrink-0" :style="{ color: 'var(--mac-orange)' }" />
        <CheckCircle2 v-else class="mt-0.5 h-4 w-4 shrink-0" :style="{ color: 'var(--mac-green)' }" />
        <div class="flex min-w-0 flex-col gap-1">
          <span class="mac-t-subhead font-semibold">
            <template v-if="exportResult.blocked">{{ exportResult.block_reason }}</template>
            <template v-else>{{ t("memo.export_ready") }}</template>
          </span>
          <span class="mac-t-caption mac-c-secondary">{{ coverageLabel(exportResult) }}</span>
          <ul v-if="exportResult.blocked" class="flex flex-col gap-0.5">
            <li
              v-for="item in exportResult.missing_sources"
              :key="`${item.location}-${item.text}`"
              class="mac-t-caption"
            >
              <span class="font-semibold">{{ item.location }}:</span>
              {{ item.terms.join(", ") }}
            </li>
          </ul>
        </div>
      </div>
      <div v-if="exportError" class="mac-t-caption" :style="{ color: 'var(--mac-red)' }">{{ exportErrorMessage }}</div>

      <!-- Section jump bar -->
      <nav class="mac-tabbar -mx-1 px-1">
        <div class="mac-tabbar-inner">
          <button
            v-for="section in navSections"
            :key="section.id"
            type="button"
            class="mac-tab flex items-center gap-1.5"
            :class="{ 'is-active': activeNav === section.id }"
            @click="jumpTo(section.id)"
          >
            <span class="mac-mono mac-t-caption10" :style="activeNav === section.id ? { color: 'var(--mac-accent)' } : {}">{{ section.num }}</span>
            {{ section.label }}
            <span
              v-if="section.count"
              class="mac-mono rounded-full px-1 text-[10px] font-bold"
              style="background: color-mix(in srgb, var(--mac-label) 8%, transparent)"
            >
              {{ section.count }}
            </span>
          </button>
        </div>
      </nav>

      <!-- 01 · Executive Summary -->
      <section :id="`memo-sec-executive_summary`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-accent)' }">01</span>
          <h3 class="mac-t-headline">{{ t("memo.executive_summary") }}</h3>
          <span class="min-w-2 flex-1" />
          <span class="mac-status-tag" :style="{ '--tint': statusTone(sections.executive_summary?.status) }">
            {{ humanizeStatus(sections.executive_summary?.status, t("memo.not_started"), appLanguage) }}
          </span>
          <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">
            {{ sourceLabel(sections.executive_summary) }}
          </span>
          <button type="button" class="mac-btn mac-btn--mini" @click="rerunSection('executive_summary')">
            {{ t("memo.rerun") }}
          </button>
        </div>
        <div
          class="mac-tile flex flex-col gap-2.5 p-3"
          style="border-radius: 10px; border-left: 3px solid var(--mac-accent)"
        >
          <p class="mac-t-body mac-c-secondary" style="line-height: 1.5">
            {{ sections.executive_summary?.body }}
          </p>
          <div class="grid gap-2.5" :class="isPublic ? 'md:grid-cols-2' : 'md:grid-cols-3'">
            <div class="mac-tile flex flex-col gap-1 p-2.5">
              <span class="mac-t-label mac-c-secondary">{{ t("memo.recommendation") }}</span>
              <p class="mac-t-caption mac-c-secondary" style="line-height: 1.4">{{ sections.executive_summary?.recommendation }}</p>
            </div>
            <div v-if="!isPublic" class="mac-tile flex flex-col gap-1 p-2.5" data-testid="memo-round">
              <span class="mac-t-label mac-c-secondary">{{ t("memo.round") }}</span>
              <p class="mac-t-caption mac-c-secondary" style="line-height: 1.4">{{ sections.executive_summary?.round || t("memo.pending") }}</p>
            </div>
            <div class="mac-tile flex flex-col gap-1 p-2.5">
              <span class="mac-t-label mac-c-secondary">{{ t("memo.top_gate") }}</span>
              <p class="mac-t-caption mac-c-secondary" style="line-height: 1.4">{{ sections.executive_summary?.top_gate }}</p>
            </div>
          </div>
        </div>
      </section>

      <!-- 02 · Investment Thesis -->
      <section :id="`memo-sec-investment_thesis`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-accent)' }">02</span>
          <h3 class="mac-t-headline">{{ t("memo.investment_thesis") }}</h3>
          <span class="min-w-2 flex-1" />
          <span class="mac-t-caption mac-c-secondary">{{ t("memo.card_count", { count: thesisCards.length }) }}</span>
          <input
            v-if="addingSection === 'investment_thesis'"
            v-model="newCardTitle"
            :placeholder="t('memo.new_card_title')"
            class="mac-field w-48"
            style="font-size: 11px; padding: 3px 8px"
            @keyup.enter="addCard('investment_thesis')"
          />
          <button type="button" class="mac-btn mac-btn--mini" :class="addingSection === 'investment_thesis' ? 'mac-btn--tint' : ''" @click="toggleAddCard('investment_thesis')">
            {{ addingSection === 'investment_thesis' ? t("memo.save_card") : t("memo.add_card") }}
          </button>
          <button type="button" class="mac-btn mac-btn--mini" @click="rerunSection('investment_thesis')">
            {{ t("memo.rerun") }}
          </button>
        </div>
        <TransitionGroup
          tag="div"
          name="card-drag"
          class="flex flex-col gap-2"
          @dragover.prevent
          @drop.prevent="commitDrag('investment_thesis')"
        >
          <article
            v-for="(card, cardIndex) in thesisCards"
            :key="card.id"
            class="mac-tile p-2.5"
            :style="{
              borderRadius: '10px',
              borderLeft: `3px solid ${cardStripe('investment_thesis', card)}`,
              opacity: dragCardId === card.id ? 0.6 : card.included ? 1 : 0.55,
            }"
            :draggable="dragArmedId === card.id"
            @dragstart="onDragStart($event, 'investment_thesis', card)"
            @dragover.prevent="onDragOver($event, 'investment_thesis', card)"
            @dragend="onDragEnd"
          >
            <div class="flex items-start gap-2">
              <button
                type="button"
                class="mac-c-secondary mt-0.5 shrink-0 cursor-grab rounded border-none bg-transparent p-0.5"
                :aria-label="t('memo.drag_card')"
                @mousedown="armDrag(card.id)"
                @mouseup="disarmDrag"
              >
                <GripVertical class="h-3.5 w-3.5" />
              </button>
              <input
                type="checkbox"
                :checked="card.included"
                class="mt-0.5 shrink-0"
                :aria-label="t('memo.include_card', { title: card.title })"
                @change="patchCard('investment_thesis', card, { included: $event.target.checked })"
              />
              <span class="mac-mono mt-0.5 w-5 shrink-0 text-center text-[12px] font-semibold">{{ card.rank }}</span>
              <div class="min-w-0 flex-1">
                <input
                  v-if="editingTitleId === card.id"
                  v-model="titleDraft"
                  class="mac-field w-full"
                  style="font-size: 13px; font-weight: 600"
                  @keyup.enter="commitTitleEdit('investment_thesis', card)"
                  @blur="commitTitleEdit('investment_thesis', card)"
                />
                <button
                  v-else
                  type="button"
                  class="flex w-full items-start justify-between gap-3 border-none bg-transparent p-0 text-left"
                  :title="t('memo.rename_hint')"
                  @click="patchCard('investment_thesis', card, { expanded: !card.expanded })"
                  @dblclick.stop.prevent="startTitleEdit(card)"
                >
                  <span class="min-w-0">
                    <span class="mac-t-subhead block font-semibold" :class="card.placeholder ? 'mac-c-secondary' : ''">{{ card.title }}</span>
                    <span class="mt-1 flex flex-wrap items-center gap-1.5">
                      <span
                        v-if="card.placeholder"
                        class="mac-status-tag"
                        :style="{ '--tint': 'var(--mac-orange)' }"
                        :title="t('memo.template_card_hint')"
                        data-testid="template-tag"
                      >
                        {{ t("memo.template_card") }}
                      </span>
                      <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">{{ card.category }}</span>
                      <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">{{ sourceLabel(card) }}</span>
                      <span class="mac-t-caption10 mac-c-secondary">{{ t("memo.source_count", { count: sourceCount(card) }) }}</span>
                    </span>
                  </span>
                  <ChevronDown v-if="card.expanded" class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
                  <ChevronRight v-else class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
                </button>
                <MemoStudioBulletTree
                  v-if="card.expanded"
                  class="mt-2.5"
                  :company-id="companyId"
                  section-id="investment_thesis"
                  :card-id="card.id"
                  :card-title="card.title"
                  :bullets="card.bullets || []"
                  :focus-bullet-id="focusedBulletId"
                  @updated="applyState"
                  @discuss="discuss"
                />
              </div>
              <span class="flex shrink-0 items-center gap-0.5">
                <button
                  type="button"
                  class="mac-c-secondary border-none bg-transparent p-0.5 disabled:opacity-30"
                  :disabled="cardIndex === 0"
                  :aria-label="t('memo.move_up')"
                  @click="moveCard('investment_thesis', card, 'up')"
                >
                  <ChevronUp class="h-3 w-3" />
                </button>
                <button
                  type="button"
                  class="mac-c-secondary border-none bg-transparent p-0.5 disabled:opacity-30"
                  :disabled="cardIndex === thesisCards.length - 1"
                  :aria-label="t('memo.move_down')"
                  @click="moveCard('investment_thesis', card, 'down')"
                >
                  <ChevronDown class="h-3 w-3" />
                </button>
                <button
                  type="button"
                  class="mac-c-secondary border-none bg-transparent p-0.5"
                  :aria-label="t('memo.remove_card')"
                  @click="removeCard('investment_thesis', card)"
                >
                  <X class="h-3 w-3" />
                </button>
              </span>
            </div>
          </article>
        </TransitionGroup>
      </section>

      <!-- 03 · Risks & Mitigations -->
      <section :id="`memo-sec-risks_mitigations`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-red)' }">03</span>
          <h3 class="mac-t-headline">{{ t("memo.risks") }}</h3>
          <span class="min-w-2 flex-1" />
          <span v-if="riskCountWarning" class="mac-t-caption font-semibold" :style="{ color: 'var(--mac-orange)' }">
            {{ t("memo.risk_count_hint", { count: includedRiskCount }) }}
          </span>
          <span class="mac-t-caption mac-c-secondary">{{ t("memo.card_count", { count: riskCards.length }) }}</span>
          <input
            v-if="addingSection === 'risks_mitigations'"
            v-model="newCardTitle"
            :placeholder="t('memo.new_card_title')"
            class="mac-field w-48"
            style="font-size: 11px; padding: 3px 8px"
            @keyup.enter="addCard('risks_mitigations')"
          />
          <button type="button" class="mac-btn mac-btn--mini" :class="addingSection === 'risks_mitigations' ? 'mac-btn--tint' : ''" @click="toggleAddCard('risks_mitigations')">
            {{ addingSection === 'risks_mitigations' ? t("memo.save_card") : t("memo.add_card") }}
          </button>
          <button type="button" class="mac-btn mac-btn--mini" @click="rerunSection('risks_mitigations')">
            {{ t("memo.rerun") }}
          </button>
        </div>
        <TransitionGroup
          tag="div"
          name="card-drag"
          class="flex flex-col gap-2"
          @dragover.prevent
          @drop.prevent="commitDrag('risks_mitigations')"
        >
          <article
            v-for="(card, cardIndex) in riskCards"
            :key="card.id"
            class="mac-tile p-2.5"
            :style="{
              borderRadius: '10px',
              borderLeft: `3px solid ${cardStripe('risks_mitigations', card)}`,
              opacity: dragCardId === card.id ? 0.6 : card.included ? 1 : 0.55,
            }"
            :draggable="dragArmedId === card.id"
            @dragstart="onDragStart($event, 'risks_mitigations', card)"
            @dragover.prevent="onDragOver($event, 'risks_mitigations', card)"
            @dragend="onDragEnd"
          >
            <div class="flex items-start gap-2">
              <button
                type="button"
                class="mac-c-secondary mt-0.5 shrink-0 cursor-grab rounded border-none bg-transparent p-0.5"
                :aria-label="t('memo.drag_card')"
                @mousedown="armDrag(card.id)"
                @mouseup="disarmDrag"
              >
                <GripVertical class="h-3.5 w-3.5" />
              </button>
              <input
                type="checkbox"
                :checked="card.included"
                class="mt-0.5 shrink-0"
                :aria-label="t('memo.include_card', { title: card.title })"
                @change="patchCard('risks_mitigations', card, { included: $event.target.checked })"
              />
              <span class="mac-mono mt-0.5 w-5 shrink-0 text-center text-[12px] font-semibold">{{ card.rank }}</span>
              <div class="min-w-0 flex-1">
                <input
                  v-if="editingTitleId === card.id"
                  v-model="titleDraft"
                  class="mac-field w-full"
                  style="font-size: 13px; font-weight: 600"
                  @keyup.enter="commitTitleEdit('risks_mitigations', card)"
                  @blur="commitTitleEdit('risks_mitigations', card)"
                />
                <button
                  v-else
                  type="button"
                  class="flex w-full items-start justify-between gap-3 border-none bg-transparent p-0 text-left"
                  :title="t('memo.rename_hint')"
                  @click="patchCard('risks_mitigations', card, { expanded: !card.expanded })"
                  @dblclick.stop.prevent="startTitleEdit(card)"
                >
                  <span class="min-w-0">
                    <span class="mac-t-subhead block font-semibold" :class="card.placeholder ? 'mac-c-secondary' : ''">{{ card.title }}</span>
                    <span class="mt-1 flex flex-wrap items-center gap-1.5">
                      <span
                        v-if="card.placeholder"
                        class="mac-status-tag"
                        :style="{ '--tint': 'var(--mac-orange)' }"
                        :title="t('memo.template_card_hint')"
                        data-testid="template-tag"
                      >
                        {{ t("memo.template_card") }}
                      </span>
                      <span
                        class="rounded-full px-1.5 py-[2px] text-[9px] font-bold"
                        :style="{
                          background: `color-mix(in srgb, ${severityTint(card.severity)} 15%, transparent)`,
                          color: severityTint(card.severity),
                        }"
                      >
                        {{ (card.severity || t("memo.risk")).toUpperCase() }}
                      </span>
                      <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">{{ card.category }}</span>
                      <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">{{ sourceLabel(card) }}</span>
                      <span
                        v-if="refinedRiskIds.has(card.id)"
                        class="mac-status-tag"
                        :style="{ '--tint': 'var(--mac-green)' }"
                      >
                        {{ t("memo.refined_tag") }}
                      </span>
                    </span>
                  </span>
                  <ChevronDown v-if="card.expanded" class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
                  <ChevronRight v-else class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
                </button>

                <div class="mt-1.5 flex flex-wrap items-center gap-2">
                  <label class="mac-t-caption10 mac-c-secondary flex items-center gap-1">
                    {{ t("memo.rating") }}
                    <select
                      :value="card.agent_rating || ''"
                      class="mac-field"
                      style="font-size: 10px; padding: 2px 5px"
                      @change="setRiskRating(card, $event.target.value)"
                    >
                      <option value="">—</option>
                      <option v-for="option in RATING_OPTIONS" :key="option" :value="option">{{ option }}</option>
                    </select>
                  </label>
                  <label class="mac-t-caption10 mac-c-secondary flex items-center gap-1">
                    {{ t("memo.likelihood") }}
                    <select
                      :value="card.likelihood || ''"
                      class="mac-field"
                      style="font-size: 10px; padding: 2px 5px"
                      @change="setRiskLikelihood(card, $event.target.value)"
                    >
                      <option value="">—</option>
                      <option v-for="option in LIKELIHOOD_OPTIONS" :key="option" :value="option">
                        {{ likelihoodLabel(option) }}
                      </option>
                    </select>
                  </label>
                  <span class="flex-1" />
                  <button
                    type="button"
                    class="mac-btn mac-btn--mini"
                    :class="refiningRiskId === card.id ? 'mac-btn--tint' : ''"
                    @click="toggleRefine(card)"
                  >
                    <SlidersHorizontal class="h-2.5 w-2.5" />
                    <span>{{ refiningRiskId === card.id ? t("memo.refine_done") : t("memo.refine_framing") }}</span>
                  </button>
                </div>

                <!-- Inline refinement panel (Mac workbench) -->
                <div
                  v-if="refiningRiskId === card.id"
                  class="mt-2 flex flex-col gap-2 rounded-md p-2.5"
                  style="background: color-mix(in srgb, var(--mac-secondary) 4%, transparent)"
                >
                  <div class="flex flex-wrap items-center gap-2.5">
                    <span class="mac-t-caption10 font-semibold">{{ t("memo.framing_override") }}</span>
                    <div class="mac-popup">
                      <select v-model="refineFraming">
                        <option v-for="[value, key] in FRAMING_OPTIONS" :key="value" :value="value">
                          {{ t(key) }}
                        </option>
                      </select>
                    </div>
                  </div>
                  <input
                    v-model="refineNote"
                    type="text"
                    class="mac-field w-full"
                    :placeholder="t('memo.steering_ph')"
                  />
                  <div class="flex items-center">
                    <span class="flex-1" />
                    <button
                      type="button"
                      class="mac-btn mac-btn--sm mac-btn--prominent"
                      :disabled="refineBusy"
                      @click="applyRefinement(card)"
                    >
                      <Loader2 v-if="refineBusy" class="h-3 w-3 animate-spin" />
                      <span>{{ t("memo.apply_refinement") }}</span>
                    </button>
                  </div>
                </div>

                <MemoStudioBulletTree
                  v-if="card.expanded"
                  class="mt-2.5"
                  :company-id="companyId"
                  section-id="risks_mitigations"
                  :card-id="card.id"
                  :card-title="card.title"
                  :bullets="card.bullets || []"
                  :focus-bullet-id="focusedBulletId"
                  @updated="applyState"
                  @discuss="discuss"
                />
              </div>
              <span class="flex shrink-0 items-center gap-0.5">
                <button
                  type="button"
                  class="mac-c-secondary border-none bg-transparent p-0.5 disabled:opacity-30"
                  :disabled="cardIndex === 0"
                  :aria-label="t('memo.move_up')"
                  @click="moveCard('risks_mitigations', card, 'up')"
                >
                  <ChevronUp class="h-3 w-3" />
                </button>
                <button
                  type="button"
                  class="mac-c-secondary border-none bg-transparent p-0.5 disabled:opacity-30"
                  :disabled="cardIndex === riskCards.length - 1"
                  :aria-label="t('memo.move_down')"
                  @click="moveCard('risks_mitigations', card, 'down')"
                >
                  <ChevronDown class="h-3 w-3" />
                </button>
                <button
                  type="button"
                  class="mac-c-secondary border-none bg-transparent p-0.5"
                  :aria-label="t('memo.remove_card')"
                  @click="removeCard('risks_mitigations', card)"
                >
                  <X class="h-3 w-3" />
                </button>
              </span>
            </div>
          </article>
        </TransitionGroup>
      </section>

      <!-- 04 · Conclusion -->
      <section :id="`memo-sec-conclusion`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-accent)' }">04</span>
          <h3 class="mac-t-headline">{{ t("memo.conclusion") }}</h3>
          <span class="min-w-2 flex-1" />
          <button type="button" class="mac-btn mac-btn--mini" @click="rerunSection('conclusion')">
            {{ t("memo.rerun") }}
          </button>
        </div>
        <div class="grid gap-2.5 md:grid-cols-3">
          <button
            v-for="option in conclusion.options || []"
            :key="option.id"
            type="button"
            class="flex flex-col gap-1.5 p-3 text-left"
            :class="conclusion.selected_option_id === option.id ? 'mac-tile-tint' : 'mac-tile'"
            :style="
              conclusion.selected_option_id === option.id
                ? { '--tint': 'var(--mac-accent)', borderRadius: '10px', boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--mac-accent) 40%, transparent)' }
                : { borderRadius: '10px' }
            "
            @click="selectConclusion(option)"
          >
            <span class="mac-t-subhead flex items-center gap-1.5 font-semibold">
              <component
                :is="conclusion.selected_option_id === option.id ? CheckCircle2 : Circle"
                class="h-3.5 w-3.5 shrink-0"
                :style="{ color: conclusion.selected_option_id === option.id ? 'var(--mac-accent)' : 'var(--mac-secondary)' }"
              />
              {{ option.label }}
            </span>
            <p class="mac-t-caption mac-c-secondary" style="line-height: 1.45">{{ option.text }}</p>
            <span class="mac-t-caption10 mac-c-tertiary font-semibold">{{ sourceLabel(option) }}</span>
          </button>
        </div>
      </section>

      <!-- 05 · Appendix -->
      <section :id="`memo-sec-appendix`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-accent)' }">05</span>
          <h3 class="mac-t-headline">{{ t("memo.appendix") }}</h3>
          <span class="min-w-2 flex-1" />
          <span class="mac-t-caption mac-c-secondary">{{ t("memo.collapsed_default") }}</span>
          <button type="button" class="mac-btn mac-btn--mini" @click="rerunSection('appendix')">
            {{ t("memo.rerun") }}
          </button>
        </div>
        <div class="mac-tile flex flex-col" style="border-radius: 10px">
          <div
            v-for="(block, blockIndex) in appendixBlocks"
            :key="block.id"
            class="p-2.5"
            :class="blockIndex > 0 ? 'mac-hairline-t' : ''"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between gap-3 border-none bg-transparent p-0 text-left"
              @click="toggleAppendix(block)"
            >
              <span class="flex min-w-0 flex-wrap items-center gap-1.5">
                <span class="mac-t-subhead font-semibold">{{ block.title }}</span>
                <span class="mac-status-tag" :style="{ '--tint': statusTone(block.status) }">
                  {{ humanizeStatus(block.status, t("memo.pending"), appLanguage) }}
                </span>
                <span class="mac-status-tag" :style="{ '--tint': 'var(--mac-secondary)' }">{{ sourceLabel(block) }}</span>
              </span>
              <ChevronDown v-if="block.expanded" class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
              <ChevronRight v-else class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
            </button>
            <ul v-if="block.expanded" class="mt-2 flex list-disc flex-col gap-1 pl-5">
              <li v-for="fact in block.facts || []" :key="fact" class="mac-t-caption mac-c-secondary">{{ fact }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- 06 · Readiness Gates (Mac workbench tab; loads with the editor) -->
      <section :id="`memo-sec-readiness_gates`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-accent)' }">06</span>
          <h3 class="mac-t-headline flex items-center gap-1.5">
            <ListChecks class="mac-c-accent h-3.5 w-3.5" />
            {{ t("memo.readiness_gates") }}
          </h3>
          <span class="min-w-2 flex-1" />
          <span v-if="gatesBusy" class="mac-spinner" />
          <button type="button" class="mac-btn mac-btn--mini" :disabled="gatesBusy" @click="loadGatesAndEvidence">
            {{ analysisData ? t("common.refresh") : t("memo.gates_load") }}
          </button>
        </div>
        <span v-if="!analysisData" class="mac-t-caption mac-c-secondary">{{ t("memo.gates_hint") }}</span>
        <template v-else>
          <div v-if="readinessAreas.length === 0" class="flex flex-col items-center gap-1 py-5 text-center">
            <ListChecks class="mac-c-tertiary h-6 w-6" stroke-width="1.5" />
            <span class="mac-t-subhead mac-c-secondary">{{ t("memo.gates_empty_title") }}</span>
            <span class="mac-t-caption mac-c-tertiary">{{ t("memo.gates_empty_hint") }}</span>
          </div>
          <div
            v-for="area in readinessAreas"
            :key="area.id"
            class="mac-tile flex items-center gap-2.5 p-2.5"
            style="border-radius: 8px"
          >
            <component :is="areaIcon(area.status)" class="h-3.5 w-3.5 shrink-0" :style="{ color: areaTint(area.status) }" />
            <span class="flex min-w-0 flex-1 flex-col gap-0.5">
              <span class="mac-t-subhead font-semibold">{{ area.area || area.id }}</span>
              <span v-if="area.rationale || area.why_it_matters" class="mac-t-caption mac-c-secondary line-clamp-2">
                {{ area.rationale || area.why_it_matters }}
              </span>
            </span>
            <span class="mac-status-tag shrink-0" :style="{ '--tint': areaTint(area.status) }">
              {{ (area.status || "open").replace(/^./, (c) => c.toUpperCase()) }}
            </span>
          </div>
        </template>
      </section>

      <!-- 07 · Evidence Claims (Mac workbench tab) -->
      <section :id="`memo-sec-evidence_claims`" class="flex flex-col gap-2.5 scroll-mt-4">
        <div class="mac-hairline-b flex flex-wrap items-center gap-2 pb-2">
          <span class="mac-mono mac-t-caption10 font-bold" :style="{ color: 'var(--mac-accent)' }">07</span>
          <h3 class="mac-t-headline flex items-center gap-1.5">
            <FileSearch class="mac-c-accent h-3.5 w-3.5" />
            {{ t("memo.evidence_claims") }}
          </h3>
          <span class="min-w-2 flex-1" />
          <span v-if="evidenceData" class="mac-t-caption mac-mono mac-c-secondary">{{ evidenceClaims.length }}</span>
        </div>
        <span v-if="!evidenceData" class="mac-t-caption mac-c-secondary">{{ t("memo.evidence_hint") }}</span>
        <template v-else>
          <div v-if="evidenceClaims.length === 0" class="flex flex-col items-center gap-1 py-5 text-center">
            <FileSearch class="mac-c-tertiary h-6 w-6" stroke-width="1.5" />
            <span class="mac-t-subhead mac-c-secondary">{{ t("memo.evidence_empty_title") }}</span>
            <span class="mac-t-caption mac-c-tertiary">{{ t("memo.evidence_empty_hint") }}</span>
          </div>
          <div
            v-for="claim in evidenceClaims"
            :key="claim.claim"
            class="mac-tile flex flex-col gap-1.5 p-2.5"
            style="border-radius: 8px"
          >
            <span class="flex items-start gap-2">
              <span
                class="mt-px shrink-0 rounded-full px-1.5 py-[2px] text-[9px] font-bold"
                :style="{
                  background: `color-mix(in srgb, ${claimTint(claim.status)} 12%, transparent)`,
                  color: claimTint(claim.status),
                }"
              >
                {{ claimLabel(claim.status) }}
              </span>
              <span class="mac-t-subhead min-w-0 font-semibold">{{ claim.claim }}</span>
            </span>
            <span
              v-for="(entry, entryIndex) in (claim.supporting_evidence || []).slice(0, 3)"
              :key="entryIndex"
              class="mac-t-caption mac-c-secondary line-clamp-2 pl-3"
            >
              {{ entry.excerpt }}
            </span>
          </div>
        </template>
      </section>

      <!-- Tasks from Warren + Recoverable history -->
      <section class="grid gap-3 lg:grid-cols-[1.1fr_0.9fr]">
        <div class="mac-tile flex flex-col gap-2.5 p-3" style="border-radius: 10px">
          <div class="flex items-center gap-2">
            <span class="flex min-w-0 flex-col gap-0.5">
              <span class="mac-t-label mac-c-secondary">{{ t("memo.copilot_tasks") }}</span>
              <span class="mac-t-headline" style="font-size: 15px">{{ t("memo.action_queue") }}</span>
            </span>
            <span class="flex-1" />
            <span class="mac-t-caption mac-mono mac-c-secondary">{{ memoTasks.length }}</span>
          </div>
          <span v-if="memoTasks.length === 0" class="mac-t-caption mac-c-secondary">
            {{ t("memo.action_queue_empty") }}
          </span>
          <article
            v-for="task in memoTasks"
            :key="task.id"
            class="mac-tile flex flex-col gap-2 p-2.5"
            style="border-radius: 8px"
          >
            <div class="flex flex-wrap items-start justify-between gap-2">
              <span class="flex min-w-0 flex-col gap-0.5">
                <span class="mac-t-subhead font-semibold">{{ task.title }}</span>
                <span v-if="task.description" class="mac-t-caption mac-c-secondary" style="line-height: 1.4">
                  {{ task.description }}
                </span>
              </span>
              <span class="mac-status-tag shrink-0" :style="{ '--tint': task.status === 'accepted' || task.status === 'completed' ? 'var(--mac-green)' : task.status === 'rejected' ? 'var(--mac-red)' : 'var(--mac-secondary)' }">
                {{ humanizeStatus(task.status, t("memo.pending"), appLanguage) }}
              </span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <button
                type="button"
                class="mac-btn mac-btn--mini mac-btn--prominent"
                :disabled="savingId === `task:${task.id}` || task.status === 'accepted'"
                @click="setTaskStatus(task, 'accepted')"
              >
                {{ t("memo.accept") }}
              </button>
              <button
                type="button"
                class="mac-btn mac-btn--mini"
                :disabled="savingId === `task:${task.id}` || task.status === 'rejected'"
                @click="setTaskStatus(task, 'rejected')"
              >
                {{ t("memo.reject") }}
              </button>
              <button
                type="button"
                class="mac-btn mac-btn--mini"
                :disabled="savingId === `task:${task.id}` || task.status === 'completed'"
                @click="setTaskStatus(task, 'completed')"
              >
                {{ t("memo.complete") }}
              </button>
            </div>
          </article>
          <span v-if="historyError" class="mac-t-caption10" :style="{ color: 'var(--mac-red)' }">{{ historyErrorMessage }}</span>
        </div>

        <div class="mac-tile flex flex-col gap-2.5 p-3" style="border-radius: 10px">
          <span class="flex flex-col gap-0.5">
            <span class="mac-t-label mac-c-secondary">{{ t("memo.audit_versions") }}</span>
            <span class="mac-t-headline" style="font-size: 15px">{{ t("memo.recoverable_history") }}</span>
          </span>
          <div class="grid gap-2 sm:grid-cols-2">
            <div class="mac-tile flex flex-col gap-0.5 p-2.5" style="border-radius: 8px">
              <span class="mac-t-label mac-c-secondary">{{ t("memo.revisions") }}</span>
              <span class="mac-t-metric-sm">{{ versions.length }}</span>
            </div>
            <div class="mac-tile flex flex-col gap-0.5 p-2.5" style="border-radius: 8px">
              <span class="mac-t-label mac-c-secondary">{{ t("memo.audit_events") }}</span>
              <span class="mac-t-metric-sm">{{ auditRecords.length }}</span>
            </div>
          </div>
          <div v-if="versions.length" class="mac-scroll mac-tile max-h-48 overflow-y-auto" style="border-radius: 8px">
            <div
              v-for="(run, runIndex) in versionRuns.slice(0, 6)"
              :key="run.first.revision_id"
              class="px-2.5 py-1.5"
              :class="runIndex > 0 ? 'mac-hairline-t' : ''"
              data-testid="version-row"
            >
              <div class="flex items-center justify-between gap-3">
                <span class="mac-t-caption10 font-semibold">
                  {{ run.count > 1 ? `${run.last.revision_id} – ${run.first.revision_id}` : run.first.revision_id }}
                </span>
                <span class="mac-t-caption10 mac-c-secondary">
                  {{ humanizeStatus(run.first.event, t("memo.pending"), appLanguage) }}{{ run.count > 1 ? ` ×${run.count}` : "" }}
                </span>
              </div>
              <span class="mac-t-caption10 mac-mono mac-c-tertiary">{{ formatRelativeTime(run.first.created_at) || formatIsoDate(run.first.created_at) }}</span>
            </div>
          </div>
          <div v-if="auditRecords.length" class="mac-scroll flex max-h-44 flex-col gap-1 overflow-y-auto">
            <div
              v-for="run in auditRuns.slice(0, 8)"
              :key="run.first.id"
              class="mac-tile px-2 py-1"
              style="border-radius: 6px"
              data-testid="audit-row"
            >
              <span class="mac-t-caption10 mac-c-secondary font-semibold">{{ humanizeStatus(run.first.event, t("memo.pending"), appLanguage) }}{{ run.count > 1 ? ` ×${run.count}` : "" }}</span>
              <span class="mac-t-caption10 mac-mono mac-c-tertiary"> · {{ formatIsoDate(run.first.created_at) }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
/* TransitionGroup move class: cards slide to their live-preview slots
   while dragging (and settle after a commit). */
.card-drag-move {
  transition: transform 0.18s ease;
}
</style>
