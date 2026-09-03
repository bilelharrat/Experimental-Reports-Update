import { api } from "./api.js";
import { trackedCompanyIds } from "./state.js";

let pushTimer = null;

export async function hydrateTrackingWatchlist() {
  try {
    const remote = await api.getTrackingWatchlist();
    const remoteIds = new Set((remote?.company_ids || []).map(String));
    const localIds = new Set([...trackedCompanyIds.value].map(String));
    const merged = new Set([...remoteIds, ...localIds]);
    trackedCompanyIds.value = merged;
    await pushTrackingWatchlist();
  } catch {
    // Offline or unauthenticated — keep browser-local follows only.
  }
}

export function schedulePushTrackingWatchlist() {
  if (pushTimer) clearTimeout(pushTimer);
  pushTimer = setTimeout(() => {
    pushTimer = null;
    pushTrackingWatchlist();
  }, 400);
}

export async function pushTrackingWatchlist() {
  try {
    const ids = [...trackedCompanyIds.value].map(String).filter(Boolean);
    await api.putTrackingWatchlist({ company_ids: ids });
  } catch {
    // Best-effort mirror for the server background sync loop.
  }
}
