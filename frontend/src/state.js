// Shared reactive state across components — small ad-hoc store, no Pinia
// dependency. Keeps the surface tiny: anything global goes here.

import { ref } from "vue";

// The currently-open deck-summary modal target, or null.
// Shape: { companyId: string, file: object } where `file` matches the
// records returned by /api/companies/<id>/files. Setting this opens the
// modal globally (mounted once in App.vue); setting it back to null
// closes it.
export const activeSummaryTarget = ref(null);

export function openSummary(companyId, file) {
  activeSummaryTarget.value = { companyId, file };
}

export function closeSummary() {
  activeSummaryTarget.value = null;
}
