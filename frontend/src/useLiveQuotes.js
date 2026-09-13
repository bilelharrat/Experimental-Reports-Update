import { onMounted, onUnmounted, ref, unref, watch } from "vue";
import { api } from "./api.js";
import { cacheQuotes, loadCachedQuotes } from "./offlineCache.js";

export const QUOTE_POLL_MS = 45000;

function readTickers(source) {
  const value = typeof source === "function" ? source() : unref(source);
  return Array.isArray(value) ? value : [];
}

export function useLiveQuotes(tickersSource) {
  const quotes = ref({});
  const offline = ref(false);
  let timer = null;
  let inFlight = false;

  async function loadQuotes() {
    if (inFlight) return;
    const tickers = readTickers(tickersSource);
    if (tickers.length === 0) {
      quotes.value = {};
      offline.value = false;
      return;
    }
    inFlight = true;
    try {
      const payload = await api.liveQuotes(tickers);
      quotes.value = payload?.quotes || {};
      offline.value = false;
      cacheQuotes(quotes.value, { asOf: payload?.generated_at || null });
    } catch {
      // Keep the last good tape rather than flashing empty on a blip.
      if (!Object.keys(quotes.value || {}).length) {
        const cached = loadCachedQuotes();
        if (cached?.quotes) {
          quotes.value = cached.quotes;
          offline.value = true;
        }
      } else {
        offline.value = true;
      }
    } finally {
      inFlight = false;
    }
  }

  function stopQuotePoll() {
    if (timer != null) {
      window.clearInterval(timer);
      timer = null;
    }
  }

  function startQuotePoll() {
    stopQuotePoll();
    loadQuotes();
    timer = window.setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      loadQuotes();
    }, QUOTE_POLL_MS);
  }

  watch(() => readTickers(tickersSource).join(","), loadQuotes);
  onMounted(startQuotePoll);
  onUnmounted(stopQuotePoll);

  return { quotes, offline, loadQuotes };
}
