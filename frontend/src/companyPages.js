/**
 * A company's pages: its reports, its news and its Research Desk. Opening a
 * company in the sidebar lists them under it, like a folder, with how much
 * each holds (Sidebar.vue). These helpers find what each page will show, the
 * same way the page builds it, from data the app already holds or a plain
 * quotes call — never an AI call.
 */
import { ref, unref, watch } from "vue";
import { api } from "./api.js";
import { assembleDeskNews } from "./homeDesk.js";

/** The company's reports, newest first — the rows its Reports page lists. */
export function companyReports(reports = [], companyId = "") {
  const id = String(companyId || "");
  if (!id) return [];
  return (reports || [])
    .filter((report) => report && String(report.company_id || "") === id)
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || "")));
}

/** The company's headlines, built exactly as the News desk builds them. */
export function companyHeadlines({ feed = [], companies = [], live = [], companyId = "", limit = 30, now } = {}) {
  if (!companyId) return [];
  return assembleDeskNews({ feed, companies, live, focusCompanyId: companyId, limit, now });
}

/**
 * Live headlines for one ticker, and whether the answer is in. The app polls
 * the wire for the first ten tickers only, so a company further down the list
 * would show no news at all; asking for its own ticker fills that in. A plain
 * quotes call — no AI. `settled` stays false until the call comes back (it is
 * true at once with no ticker), so a count can wait instead of reading 0.
 */
export function useTickerNewsFeed(tickerSource, { limit = 30 } = {}) {
  const items = ref([]);
  const settled = ref(false);
  let request = 0;
  watch(
    () => String(unref(tickerSource) || "").trim().toUpperCase(),
    async (ticker) => {
      const id = ++request;
      items.value = [];
      settled.value = !ticker;
      if (!ticker) return;
      try {
        const payload = await api.quotesNews({ tickers: [ticker], limit });
        if (id === request) items.value = Array.isArray(payload?.items) ? payload.items : [];
      } catch {
        // The desk's own tape still shows; this only adds to it.
      } finally {
        if (id === request) settled.value = true;
      }
    },
    { immediate: true },
  );
  return { items, settled };
}

/** The headlines alone, for a view that has no count to hold back. */
export function useTickerNews(tickerSource, options) {
  return useTickerNewsFeed(tickerSource, options).items;
}
