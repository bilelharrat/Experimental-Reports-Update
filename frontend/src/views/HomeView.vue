<script setup>
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { Search, Loader2, ArrowRight } from "lucide-vue-next";
import { api } from "../api.js";

const router = useRouter();
const query = ref("");
const results = ref([]);
const searching = ref(false);
const error = ref(null);
let debounceId = null;

watch(query, (q) => {
  clearTimeout(debounceId);
  error.value = null;
  if (!q.trim()) {
    results.value = [];
    searching.value = false;
    return;
  }
  searching.value = true;
  debounceId = setTimeout(async () => {
    try {
      results.value = await api.searchCompanies(q.trim());
    } catch (e) {
      error.value = e.message;
    } finally {
      searching.value = false;
    }
  }, 200);
});

function selectCompany(c) {
  router.push({ name: "research", params: { companyId: c.id } });
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-8 py-12">
    <header class="mb-10">
      <div class="text-xs uppercase tracking-wider text-ink-muted mb-2">
        BSH Research
      </div>
      <h1 class="font-display text-3xl font-semibold text-ink-primary">
        Find a company
      </h1>
      <p class="mt-2 text-ink-secondary">
        Search by name or ticker. Pick the right match to open its research page.
      </p>
    </header>

    <div class="relative">
      <Search
        class="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-ink-muted"
      />
      <input
        v-model="query"
        type="search"
        autofocus
        placeholder="Search companies (e.g. Acme, ACME, Globex)"
        class="w-full pl-12 pr-4 py-3 rounded-card border border-subtle bg-surface text-ink-primary placeholder:text-ink-subtle focus-ring shadow-card"
      />
    </div>

    <div v-if="error" class="mt-4 text-sm text-danger">{{ error }}</div>

    <div class="mt-6 space-y-2">
      <div
        v-if="searching && results.length === 0"
        class="px-4 py-3 text-sm text-ink-muted flex items-center gap-2"
      >
        <Loader2 class="h-4 w-4 animate-spin" /> Searching…
      </div>
      <div
        v-else-if="!searching && query && results.length === 0"
        class="px-4 py-3 text-sm text-ink-muted"
      >
        No companies match “{{ query }}”.
      </div>
      <button
        v-for="c in results"
        :key="c.id"
        @click="selectCompany(c)"
        class="w-full text-left px-4 py-3 rounded-card border border-subtle bg-surface hover:bg-surface-muted hover:border-strong shadow-card focus-ring transition flex items-start gap-3"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <div class="font-display font-semibold text-ink-primary">
              {{ c.name }}
            </div>
            <span
              v-if="c.ticker"
              class="text-xs font-mono px-1.5 py-0.5 rounded bg-accent-soft text-accent-ink"
              >{{ c.ticker }}</span
            >
          </div>
          <div v-if="c.sector" class="text-xs text-ink-muted mt-0.5">
            {{ c.sector }}
          </div>
          <div v-if="c.description" class="text-sm text-ink-secondary mt-1 line-clamp-2">
            {{ c.description }}
          </div>
        </div>
        <ArrowRight class="h-4 w-4 text-ink-muted mt-1 shrink-0" />
      </button>
    </div>
  </div>
</template>
