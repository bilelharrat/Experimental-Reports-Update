import { ref } from "vue";
import { copilotTabFromQuery } from "./dossierSections.js";

/** Shared Co-Pilot workspace context (what the analyst is looking at). */
export const copilotSelection = ref(null);
export const copilotAttention = ref(null);
export const copilotJob = ref(null);
export const copilotSurface = ref(null);
export const copilotTab = ref(null);
export const copilotMode = ref("quick"); // quick | deep
export const copilotPendingPrompt = ref("");
// A question to leave in Warren's composer unsent (it has no company of its
// own, so the analyst picks where it goes).
export const copilotDraftPrompt = ref("");
export const copilotCompanyOverride = ref(null);
export const copilotDocumentIds = ref([]);
export const copilotDragTell = ref(false);

export function buildClientContext() {
  return {
    surface: copilotSurface.value || null,
    tab: copilotTab.value || null,
    selection: copilotSelection.value || {},
    attention: copilotAttention.value || {},
    job: copilotJob.value || {},
    document_ids: [...(copilotDocumentIds.value || [])],
  };
}

export function mergeCopilotContext(patch = {}) {
  if (!patch || typeof patch !== "object") return;
  if (patch.surface != null) copilotSurface.value = patch.surface;
  if (patch.tab != null) copilotTab.value = patch.tab;
  if (patch.selection != null) copilotSelection.value = patch.selection;
  if (patch.attention != null) copilotAttention.value = patch.attention;
  if (patch.job != null) copilotJob.value = patch.job;
  if (patch.mode != null) copilotMode.value = patch.mode;
  if (patch.document_ids != null) copilotDocumentIds.value = patch.document_ids;
}

export function clearCopilotJobContext() {
  copilotJob.value = null;
}

/** Drop what was handed to Warren from a page (a memo point, a flag, a job). */
export function clearCopilotFocus() {
  copilotSelection.value = null;
  copilotAttention.value = null;
  copilotJob.value = null;
}

export function resetCopilotContext() {
  copilotSelection.value = null;
  copilotAttention.value = null;
  copilotJob.value = null;
  copilotSurface.value = null;
  copilotTab.value = null;
  copilotPendingPrompt.value = "";
  copilotDraftPrompt.value = "";
  copilotDocumentIds.value = [];
  copilotDragTell.value = false;
}

export function syncCopilotFromRoute(route, company) {
  if (!company?.id) {
    copilotSurface.value = route.name === "tracking" ? "tracking" : "home";
    copilotTab.value = null;
    return;
  }
  copilotSurface.value = "research";
  // The desk keeps its tab in ?section=, older links in ?tab=.
  copilotTab.value = copilotTabFromQuery(route.query);
}
