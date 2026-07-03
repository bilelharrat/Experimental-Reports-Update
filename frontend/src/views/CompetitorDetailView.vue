<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ArrowLeft, ExternalLink, Loader2 } from "lucide-vue-next";
import { api } from "../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
  competitorId: { type: String, required: true },
});

const router = useRouter();
const payload = ref(null);
const loading = ref(true);
const error = ref("");

function monogram(name) {
  return String(name || "?")
    .replace(/[,.]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

const competitor = computed(() => payload.value?.competitor || {});
const company = computed(() => payload.value?.company || {});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    payload.value = await api.getCompetitorDetail(props.companyId, props.competitorId);
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
watch(() => [props.companyId, props.competitorId], load);
</script>

<template>
  <div class="mx-auto max-w-6xl px-8 py-10">
    <button
      type="button"
      @click="router.push({ name: 'research', params: { companyId }, query: { tab: 'overview' } })"
      class="inline-flex items-center gap-1 rounded text-sm text-ink-muted hover:text-ink-primary focus-ring"
    >
      <ArrowLeft class="h-4 w-4" />
      Back to workspace
    </button>

    <div v-if="loading" class="mt-8 flex items-center gap-2 text-sm text-ink-muted">
      <Loader2 class="h-4 w-4 animate-spin" />
      Loading competitor detail…
    </div>
    <div v-else-if="error" class="mt-8 rounded-card border border-danger/30 bg-danger/10 p-4 text-sm text-danger">
      {{ error }}
    </div>

    <template v-else-if="payload">
      <header class="mt-6 rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div class="flex min-w-0 items-start gap-4">
            <div
              class="mono-data grid h-16 w-16 shrink-0 place-items-center rounded-glass bg-accent-soft text-xl font-bold text-accent-ink ring-1 ring-subtle"
            >
              {{ monogram(competitor.name) }}
            </div>
            <div class="min-w-0">
              <div class="vogue-label">Competitor Detail</div>
              <div class="mt-1 flex flex-wrap items-center gap-2">
                <h1 class="font-display text-3xl font-bold text-ink-primary">
                  {{ company.name }} vs {{ competitor.name }}
                </h1>
                <span class="rounded-full bg-surface-muted px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-ink-muted">
                  {{ competitor.status || "Private" }}
                </span>
                <span
                  v-if="competitor.ticker"
                  class="mono-data rounded-full bg-accent-soft px-2 py-1 text-[11px] font-semibold text-accent-ink"
                >
                  {{ competitor.exchange ? `${competitor.exchange}:` : "" }}{{ competitor.ticker }}
                </span>
              </div>
              <p class="mt-3 max-w-3xl text-sm leading-relaxed text-ink-secondary">
                {{ competitor.description }}
              </p>
            </div>
          </div>
          <RouterLink
            :to="{ name: 'research', params: { companyId }, query: { tab: 'memo' } }"
            class="pill-button border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            Back to memo
          </RouterLink>
        </div>
      </header>

      <section class="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div
          v-for="metric in competitor.metrics || []"
          :key="metric.label"
          class="rounded-card border border-subtle bg-surface p-5 shadow-card"
        >
          <div class="vogue-label">{{ metric.label }}</div>
          <div class="mono-data mt-2 text-2xl font-bold text-ink-primary">
            {{ metric.value || "Pending" }}
          </div>
          <div class="mt-2 text-[11px] text-ink-muted">
            {{ metric.source_class || "source pending" }}
          </div>
        </div>
      </section>

      <section class="mt-6 rounded-card border border-subtle bg-surface p-6 shadow-card">
        <div class="vogue-label">Head-to-head</div>
        <div class="mt-4 overflow-x-auto">
          <table class="min-w-full text-left text-sm">
            <thead class="text-xs uppercase tracking-wide text-ink-muted">
              <tr>
                <th class="border-b border-subtle py-2 pr-4">Dimension</th>
                <th class="border-b border-subtle px-4 py-2">{{ company.name }}</th>
                <th class="border-b border-subtle px-4 py-2">{{ competitor.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in payload.head_to_head || []" :key="row.label">
                <td class="border-b border-subtle py-3 pr-4 font-semibold text-ink-primary">
                  {{ row.label }}
                </td>
                <td class="border-b border-subtle px-4 py-3 text-ink-secondary">
                  {{ row.company || "Pending" }}
                </td>
                <td class="border-b border-subtle px-4 py-3 text-ink-secondary">
                  {{ row.competitor || "Pending" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="mt-6 grid gap-4 lg:grid-cols-3">
        <article
          v-for="item in payload.placeholders || []"
          :key="item.id"
          class="rounded-card border border-subtle bg-surface p-5 shadow-card"
        >
          <div class="flex items-center justify-between gap-3">
            <h2 class="font-display text-lg font-semibold text-ink-primary">
              {{ item.title }}
            </h2>
            <span class="rounded-full bg-surface-muted px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
              {{ item.status }}
            </span>
          </div>
          <p class="mt-3 text-sm leading-relaxed text-ink-secondary">
            {{ item.body }}
          </p>
        </article>
      </section>

      <section class="mt-6 rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="vogue-label">Evidence links</div>
        <div class="mt-3 flex flex-wrap gap-2">
          <a
            v-for="sourceRef in competitor.source_refs || []"
            :key="`${sourceRef.title}-${sourceRef.url}`"
            :href="sourceRef.url || '#'"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1 rounded-full border border-subtle bg-surface-muted px-3 py-1.5 text-xs font-semibold text-ink-secondary hover:bg-surface focus-ring"
          >
            <span>{{ sourceRef.title || sourceRef.source_class || "Source" }}</span>
            <ExternalLink v-if="sourceRef.url" class="h-3 w-3" />
          </a>
        </div>
      </section>
    </template>
  </div>
</template>
