<script setup>
// The public-company counterpart of the deal pipeline on a dossier's
// Overview. A listed name is not moving through Sourced → Term Sheet; what
// matters is when it next reports, how its recent quarters landed against
// the estimate, and what it has filed. Everything here comes from
// /api/companies/:id/earnings-filings (SEC EDGAR + Nasdaq, cached 6h).
import { computed, ref, watch } from "vue";
import { useT } from "../../i18n.js";
import { CalendarClock, ExternalLink, FileText, RotateCw, TrendingUp } from "lucide-vue-next";
import api from "../../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
});

const t = useT();
const data = ref(null);
const loading = ref(false);
const failed = ref(false);

async function load({ refresh = false } = {}) {
  if (!props.companyId) return;
  const forCompany = props.companyId;
  loading.value = true;
  failed.value = false;
  try {
    const res = await api.getCompanyEarningsFilings(forCompany, { refresh });
    if (forCompany === props.companyId) data.value = res;
  } catch {
    if (forCompany === props.companyId) failed.value = true;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    data.value = null;
    load();
  },
  { immediate: true },
);

const earnings = computed(() => data.value?.earnings || null);
const history = computed(() => earnings.value?.history || []);
// Five rows, material filings first in line for them, shown newest-first.
const filings = computed(() => {
  const rows = data.value?.filings || [];
  const material = rows.filter((f) => f.material);
  const rest = rows.filter((f) => !f.material);
  return [...material.slice(0, 5), ...rest.slice(0, Math.max(0, 5 - material.length))].sort(
    (a, b) => String(b.filed || "").localeCompare(String(a.filed || "")),
  );
});

// EDGAR's own description is often just the form again ("FORM 4").
const FORM_LABELS = {
  "4": "Insider transaction",
  "8-K": "Current report",
  "10-Q": "Quarterly report",
  "10-K": "Annual report",
  "DEF 14A": "Proxy statement",
  "S-1": "Registration statement",
  "S-1/A": "Registration amendment",
  "424B4": "Prospectus",
  "SC 13D": "Ownership stake · active",
  "SC 13D/A": "Ownership stake · active, amended",
  "SC 13G": "Ownership stake · passive",
  "SC 13G/A": "Ownership stake · passive, amended",
  "6-K": "Foreign issuer report",
  "20-F": "Foreign annual report",
};

function filingLabel(f) {
  const desc = String(f.description || "").trim();
  const bare = desc.replace(/^form\s+/i, "").toUpperCase();
  if (desc && bare !== String(f.form || "").toUpperCase()) return desc;
  return FORM_LABELS[f.form] || desc || f.form;
}

const nextWhen = computed(() => {
  const days = earnings.value?.days_to_next;
  if (days == null) return "";
  if (days === 0) return t("research_desk.today");
  return days > 0
    ? t("research_desk.in_days", { days })
    : t("research_desk.days_ago", { days: Math.abs(days) });
});

function eps(value) {
  return value == null ? "—" : `$${Number(value).toFixed(2)}`;
}

function surpriseTone(pct) {
  if (pct == null || Number(pct) === 0) return "var(--mac-secondary)";
  return Number(pct) > 0 ? "var(--mac-green)" : "var(--mac-red)";
}

function surpriseText(pct) {
  if (pct == null) return "—";
  const n = Number(pct);
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-3.5" data-testid="earnings-filings">
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><TrendingUp class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.earnings_filings") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.earnings_filings_subtitle") }}</span>
      </div>
      <span class="min-w-2 flex-1" />
      <button
        type="button"
        class="mac-btn mac-btn--mini mac-btn--plain"
        :title="t('research_desk.refresh')"
        :disabled="loading"
        @click="load({ refresh: true })"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <div v-if="failed" class="flex items-center gap-2">
      <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.earnings_unavailable") }}</span>
      <button type="button" class="mac-btn mac-btn--mini" @click="load()">{{ t("research_desk.retry") }}</button>
    </div>
    <div v-else-if="!data" class="py-1"><span class="mac-spinner" /></div>

    <template v-else>
      <div class="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
        <!-- Next report -->
        <div
          class="mac-tile-tint flex flex-col gap-1 p-2.5"
          style="border-radius: 10px; --tint: var(--mac-accent)"
          data-testid="next-earnings"
        >
          <span class="mac-t-label mac-c-accent flex items-center gap-1.5">
            <CalendarClock class="h-3 w-3" />
            {{ t("research_desk.next_earnings") }}
          </span>
          <span v-if="earnings?.next_date" class="mac-t-subhead mac-mono font-semibold">
            {{ earnings.next_date }}
          </span>
          <span v-else class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.not_set") }}</span>
          <span v-if="earnings?.next_date" class="mac-t-caption10 mac-c-secondary">
            {{ nextWhen }}<template v-if="earnings.next_estimated"> · {{ t("research_desk.estimated") }}</template>
          </span>
        </div>

        <!-- Recent quarters: actual EPS against the consensus estimate -->
        <div class="mac-tile flex flex-col gap-1 p-2.5" style="border-radius: 10px">
          <span class="mac-t-label mac-c-secondary">{{ t("research_desk.quarters_vs_estimates") }}</span>
          <span v-if="!history.length" class="mac-t-caption10 mac-c-secondary">{{ t("research_desk.no_earnings") }}</span>
          <div
            v-for="q in history"
            :key="q.period || q.reported"
            class="flex items-center gap-2"
            data-testid="earnings-quarter"
          >
            <span class="mac-t-caption10 mac-c-secondary w-[64px] shrink-0 truncate">{{ q.period || q.reported }}</span>
            <span class="mac-t-caption10 mac-mono min-w-0 flex-1 truncate">
              {{ t("research_desk.eps_vs_estimate", { eps: eps(q.eps), estimate: eps(q.estimate) }) }}
            </span>
            <span class="mac-t-caption10 mac-mono shrink-0 font-semibold" :style="{ color: surpriseTone(q.surprise_pct) }">
              {{ surpriseText(q.surprise_pct) }}
            </span>
          </div>
        </div>
      </div>

      <!-- SEC filings, newest first -->
      <div class="flex flex-col gap-1">
        <span class="mac-t-label mac-c-secondary">{{ t("research_desk.recent_filings") }}</span>
        <span v-if="!filings.length" class="mac-t-caption10 mac-c-secondary">
          {{ data.error || t("research_desk.no_filings") }}
        </span>
        <a
          v-for="f in filings"
          :key="f.url + f.filed"
          :href="f.url"
          target="_blank"
          rel="noopener noreferrer"
          class="mac-tile flex items-center gap-2 px-2.5 py-1.5"
          style="border-radius: 8px"
          data-testid="filing-row"
        >
          <FileText class="mac-c-secondary h-3 w-3 shrink-0" />
          <span class="mac-t-caption10 mac-mono w-[52px] shrink-0 font-semibold">{{ f.form }}</span>
          <span class="mac-t-caption10 mac-c-secondary min-w-0 flex-1 truncate">{{ filingLabel(f) }}</span>
          <span
            v-if="f.material"
            class="mac-status-tag shrink-0"
            :style="{ '--tint': 'var(--mac-orange)' }"
          >
            {{ t("research_desk.material") }}
          </span>
          <span class="mac-t-caption10 mac-mono mac-c-tertiary shrink-0">{{ f.filed }}</span>
          <ExternalLink class="mac-c-tertiary h-3 w-3 shrink-0" />
        </a>
      </div>
    </template>
  </div>
</template>
