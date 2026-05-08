<script setup>
import { computed, nextTick, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Search, Loader2, ArrowRight, Sparkles, Building2 } from "lucide-vue-next";
import { api } from "../api.js";
import CompanyCard from "../components/CompanyCard.vue";

const router = useRouter();
const query = ref("");
const suggestions = ref([]);
const showSuggestions = ref(false);
const autocompleting = ref(false);
const error = ref(null);

const searchResults = ref(null); // { source, matches } | null
const searching = ref(false);

let debounceId = null;

watch(query, (q) => {
  clearTimeout(debounceId);
  error.value = null;
  if (!q.trim() || q.trim().length < 2) {
    suggestions.value = [];
    autocompleting.value = false;
    showSuggestions.value = false;
    return;
  }
  autocompleting.value = true;
  showSuggestions.value = true;
  debounceId = setTimeout(async () => {
    try {
      suggestions.value = await api.autocompleteCompanies(q.trim());
    } catch (e) {
      error.value = e.message;
    } finally {
      autocompleting.value = false;
    }
  }, 220);
});

async function pickSuggestion(s) {
  showSuggestions.value = false;
  let id = s.id;
  if (!id) {
    const upserted = await api.selectCompany({
      name: s.name,
      ticker: s.ticker,
      description: s.description,
      sector: s.sector,
      industry: s.industry,
      exchange: s.exchange,
    });
    id = upserted.id;
  }
  router.push({ name: "research", params: { companyId: id } });
}

async function runDeepSearch({ refresh = false } = {}) {
  if (!query.value.trim()) return;
  showSuggestions.value = false;
  searching.value = true;
  error.value = null;
  try {
    searchResults.value = await api.deepSearchCompanies(query.value.trim(), {
      refresh,
    });
  } catch (e) {
    error.value = e.message;
  } finally {
    searching.value = false;
  }
}

function formatCachedAt(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const now = Date.now();
  const ageSec = Math.max(0, Math.round((now - d.getTime()) / 1000));
  const ageStr =
    ageSec < 60
      ? "just now"
      : ageSec < 3600
      ? `${Math.round(ageSec / 60)}m ago`
      : ageSec < 86400
      ? `${Math.round(ageSec / 3600)}h ago`
      : `${Math.round(ageSec / 86400)}d ago`;
  return { full: d.toLocaleString(), age: ageStr };
}

function pickResult(match) {
  if (match.id) router.push({ name: "research", params: { companyId: match.id } });
}

function onCardRefreshed(updated) {
  if (!searchResults.value) return;
  const idx = searchResults.value.matches.findIndex((m) => m.id === updated.id);
  if (idx >= 0) {
    searchResults.value.matches.splice(idx, 1, updated);
  }
}

const hasResults = computed(
  () => searchResults.value && searchResults.value.matches.length > 0,
);

function onBlur() {
  // Delay so click on a suggestion can register first.
  setTimeout(() => (showSuggestions.value = false), 150);
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-8 py-12">
    <header class="mb-10">
      <div class="text-xs uppercase tracking-wider text-ink-muted mb-2">
        BSH Research
      </div>
      <h1 class="font-display text-3xl font-semibold text-ink-primary">
        Find a company
      </h1>
      <p class="mt-2 text-ink-secondary">
        Type company name and press enter for search. Existing researched
        companies or public companies will autocomplete.
      </p>
    </header>

    <form @submit.prevent="runDeepSearch" class="relative">
      <Search
        class="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-ink-muted"
      />
      <input
        v-model="query"
        type="search"
        autofocus
        placeholder="Search companies (e.g. Apple, Stripe, NVDA)"
        class="w-full pl-12 pr-32 py-3 rounded-card border border-subtle bg-surface text-ink-primary placeholder:text-ink-subtle focus-ring shadow-card"
        @focus="suggestions.length && (showSuggestions = true)"
        @blur="onBlur"
      />
      <button
        type="submit"
        :disabled="!query.trim() || searching"
        class="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent text-white text-sm font-medium hover:bg-accent-hover disabled:opacity-60 focus-ring"
      >
        <Sparkles class="h-3.5 w-3.5" />
        <span>{{ searching ? "Searching…" : "Search" }}</span>
      </button>

      <div
        v-if="showSuggestions && (suggestions.length || autocompleting)"
        class="absolute left-0 right-0 top-full mt-2 bg-surface border border-subtle rounded-card shadow-card-raised z-10 overflow-hidden"
      >
        <div
          v-if="autocompleting && suggestions.length === 0"
          class="px-4 py-3 text-sm text-ink-muted flex items-center gap-2"
        >
          <Loader2 class="h-4 w-4 animate-spin" /> Looking up…
        </div>
        <button
          v-for="s in suggestions"
          :key="(s.id || '') + (s.ticker || '') + s.name"
          type="button"
          @mousedown.prevent="pickSuggestion(s)"
          class="w-full text-left px-4 py-2.5 hover:bg-surface-muted focus-ring flex items-center gap-3 border-b border-subtle last:border-b-0"
        >
          <Building2 class="h-4 w-4 text-ink-muted shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-ink-primary truncate">
              {{ s.name }}
            </div>
            <div class="text-xs text-ink-muted truncate">
              <span v-if="s.ticker" class="font-mono">{{ s.ticker }}</span>
              <span v-if="s.exchange"> · {{ s.exchange }}</span>
              <span v-if="s.sector"> · {{ s.sector }}</span>
              <span
                v-if="s.source === 'local'"
                class="ml-2 px-1 py-0.5 rounded bg-accent-soft text-accent-ink"
                >Tracked</span
              >
              <span
                v-else-if="s.source === 'researched'"
                class="ml-2 px-1 py-0.5 rounded bg-success-soft text-success-ink"
                title="Seen in a previous AI search"
                >Researched</span
              >
            </div>
          </div>
          <ArrowRight class="h-3.5 w-3.5 text-ink-muted shrink-0" />
        </button>
      </div>
    </form>

    <div v-if="error" class="mt-4 text-sm text-danger">{{ error }}</div>

    <div v-if="searching" class="mt-10 flex items-center gap-3 text-ink-secondary">
      <Loader2 class="h-5 w-5 animate-spin text-accent" />
      <span>Searching the web for matches…</span>
    </div>

    <div v-else-if="searchResults" class="mt-10 space-y-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <h2 class="font-display text-lg font-semibold text-ink-primary">
          {{ hasResults ? `Results for "${query}"` : `No matches for "${query}"` }}
        </h2>
        <div class="flex items-center gap-3">
          <span class="text-xs text-ink-muted flex items-center gap-1.5">
            <span>
              {{
                searchResults.source === "openai"
                  ? "AI-Search"
                  : searchResults.source === "cache"
                  ? "Cached"
                  : "Local matches only"
              }}
            </span>
            <span
              v-if="formatCachedAt(searchResults.cached_at)"
              :title="formatCachedAt(searchResults.cached_at).full"
            >
              · {{ formatCachedAt(searchResults.cached_at).age }}
            </span>
          </span>
          <button
            v-if="searchResults.source !== 'fallback'"
            type="button"
            @click="runDeepSearch({ refresh: true })"
            :disabled="searching"
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary focus-ring"
          >
            Refresh
          </button>
        </div>
      </div>
      <div
        v-if="searchResults.source === 'fallback' && searchResults.reason"
        class="text-sm text-warning-ink bg-warning-soft border border-warning/40 rounded-lg px-3 py-2"
      >
        Deep search unavailable — {{ searchResults.reason }}.
      </div>
      <CompanyCard
        v-for="m in searchResults.matches"
        :key="m.id"
        :company="m"
        @select="pickResult"
        @refreshed="(updated) => onCardRefreshed(updated)"
      />
    </div>
  </div>
</template>
