import { computed, ref, unref, watch } from "vue";
import { api } from "./api.js";

function readIds(source) {
  const value = typeof source === "function" ? source() : unref(source);
  return (Array.isArray(value) ? value : []).map((id) => String(id)).filter(Boolean);
}

export function useTrackingRollup(idsSource) {
  const rollup = ref(null);
  const rollupError = ref(false);
  const rollupLoading = ref(false);

  async function loadRollup() {
    const ids = readIds(idsSource);
    if (ids.length === 0) {
      rollup.value = null;
      rollupError.value = false;
      rollupLoading.value = false;
      return;
    }
    rollupLoading.value = true;
    rollupError.value = false;
    try {
      rollup.value = await api.trackingRollup(ids);
    } catch {
      rollupError.value = true;
    } finally {
      rollupLoading.value = false;
    }
  }

  const work = computed(() => {
    const ids = new Set(readIds(idsSource));
    return (rollup.value?.attention || []).filter((item) =>
      ids.has(String(item.company_id)),
    );
  });

  watch(() => readIds(idsSource).join(","), loadRollup, { immediate: true });

  return { rollup, rollupError, rollupLoading, loadRollup, work };
}
