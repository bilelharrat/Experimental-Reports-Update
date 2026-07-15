// Shared active-jobs poller.
//
// ActiveJobsRail and ResearchUploads used to each run their own
// setInterval against /api/jobs/active (3s and 2s). That endpoint is
// expensive server-side, so two independent pollers doubled the load and
// never coordinated. This module owns ONE reference-counted poll and
// exposes the result as a reactive ref every consumer shares. It also
// pauses while the tab is hidden.

import { ref } from "vue";
import { api } from "./api.js";

const jobs = ref([]);
const lastError = ref(null);

let subscribers = 0;
let timer = null;
let inFlight = false;

const POLL_MS = 3000;

async function poll() {
  if (inFlight) return;
  if (typeof document !== "undefined" && document.hidden) return;
  inFlight = true;
  try {
    jobs.value = await api.listActiveJobs();
    lastError.value = null;
  } catch (e) {
    lastError.value = e;
    // Keep the previous value on a network blip.
  } finally {
    inFlight = false;
  }
}

function onVisibilityChange() {
  if (typeof document !== "undefined" && !document.hidden) poll();
}

export function subscribeActiveJobs() {
  subscribers += 1;
  if (timer == null) {
    poll();
    timer = window.setInterval(poll, POLL_MS);
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange);
    }
  }
  return jobs;
}

export function unsubscribeActiveJobs() {
  subscribers = Math.max(0, subscribers - 1);
  if (subscribers === 0 && timer != null) {
    window.clearInterval(timer);
    timer = null;
    if (typeof document !== "undefined") {
      document.removeEventListener("visibilitychange", onVisibilityChange);
    }
  }
}

// Force an immediate refresh (e.g. right after launching a job) without
// waiting for the next interval.
export function refreshActiveJobs() {
  return poll();
}

export { jobs as activeJobs, lastError as activeJobsError };
