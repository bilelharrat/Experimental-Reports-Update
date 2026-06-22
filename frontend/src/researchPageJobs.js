import { api } from "./api.js";

const TERMINAL_TYPES = new Set(["done", "error"]);

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function terminalEvent(events) {
  if (!Array.isArray(events)) return null;
  for (let i = events.length - 1; i >= 0; i -= 1) {
    const entry = events[i];
    if (entry && TERMINAL_TYPES.has(entry.type)) return entry;
  }
  return null;
}

export async function waitForJobTerminal(logUrl, { timeoutMs = 60000, pollMs = 750 } = {}) {
  if (!logUrl) return null;
  const deadline = Date.now() + timeoutMs;
  do {
    try {
      const events = await api.jobLog(logUrl);
      const terminal = terminalEvent(events);
      if (terminal) return terminal;
    } catch {
      // The progress file can lag the queued response briefly.
    }
    if (Date.now() >= deadline) break;
    await sleep(Math.min(pollMs, Math.max(0, deadline - Date.now())));
  } while (Date.now() < deadline);
  return null;
}

async function waitForJobTerminals(jobs, options) {
  const withLogs = jobs.filter((job) => job?.log_url);
  const terminals = await Promise.all(
    withLogs.map(async (job) => ({
      job,
      terminal: await waitForJobTerminal(job.log_url, options),
    })),
  );
  return terminals;
}

export async function runFullStockResearchRefresh() {
  const trackers = await api.stockResearch.listTrackers({ includeArchived: false });
  const activeTrackerIds = trackers
    .filter((tracker) => tracker?.status === "active")
    .map((tracker) => tracker.id)
    .filter(Boolean);
  let trackerResult = { launched: [], errors: [] };
  let trackerTerminals = [];
  if (activeTrackerIds.length) {
    trackerResult = await api.stockResearch.runSelectedTrackers(activeTrackerIds);
    trackerTerminals = await waitForJobTerminals(trackerResult.launched || [], {
      timeoutMs: 75000,
      pollMs: 1000,
    });
  }
  const aggregateResult = await api.stockResearch.runAggregate({ force: true });
  const aggregateTerminal = await waitForJobTerminal(aggregateResult?.log_url, {
    timeoutMs: 45000,
    pollMs: 750,
  });
  if (aggregateTerminal?.type === "error") {
    throw new Error(aggregateTerminal.error || "Weekly aggregate refresh failed.");
  }
  const trackerErrors = trackerTerminals.filter(({ terminal }) => !terminal || terminal.type === "error");
  return {
    activeTrackerCount: activeTrackerIds.length,
    launchedTrackerCount: (trackerResult.launched || []).length,
    trackerErrorCount: (trackerResult.errors || []).length + trackerErrors.length,
    aggregateCompleted: aggregateTerminal?.type === "done",
  };
}
