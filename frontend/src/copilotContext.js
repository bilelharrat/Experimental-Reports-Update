import { ref } from "vue";

/** Shared Co-Pilot workspace context (what the analyst is looking at). */
export const copilotSelection = ref(null);
export const copilotAttention = ref(null);
export const copilotJob = ref(null);
export const copilotSurface = ref(null);
export const copilotTab = ref(null);
export const copilotMode = ref("quick"); // quick | deep
export const copilotPendingPrompt = ref("");
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

export function resetCopilotContext() {
  copilotSelection.value = null;
  copilotAttention.value = null;
  copilotJob.value = null;
  copilotSurface.value = null;
  copilotTab.value = null;
  copilotPendingPrompt.value = "";
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
  copilotTab.value = String(route.query?.tab || "overview");
}
