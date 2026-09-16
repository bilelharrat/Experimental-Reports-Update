<script setup>
// Web twin of MacThesisTrackerView.swift: one row per thesis claim, joining
// the thesis spine, the evidence matrix and tracked news by keyword overlap
// (words of 5+ letters minus stopwords, two shared words to match), with the
// standing decision pill in the header.
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { Waypoints, RotateCw, ArrowUpRightFromCircle, ShieldAlert, Newspaper } from "lucide-vue-next";
import { formatRelativeTime } from "../../formatters.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
});

const analysis = ref(null);
const evidence = ref(null);
const tracking = ref(null);
const decision = ref(null);
const busy = ref(false);

const STOPWORDS = new Set([
  "about", "above", "after", "again", "against", "their", "there", "these", "those", "which", "while",
  "would", "could", "should", "because", "before", "between", "through", "under", "where", "other",
  "company", "market", "business", "revenue", "growth", "customers", "product", "products", "still",
]);

function keywords(text) {
  const words = String(text || "")
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length >= 5 && !STOPWORDS.has(w));
  return new Set(words);
}

function overlap(a, b) {
  let n = 0;
  for (const w of a) if (b.has(w)) n += 1;
  return n;
}

const spine = computed(() => analysis.value?.artifacts?.thesis_spine || null);

const rows = computed(() => {
  if (!spine.value) return [];
  const claims = [
    ...(spine.value.investment_highlights || []).map((c) => ["highlight", c]),
    ...(spine.value.investment_risks || []).map((c) => ["risk", c]),
  ];
  const evidenceRows = evidence.value?.claims || [];
  const news = tracking.value?.items || [];

  return claims
    .map(([kind, claim], index) => {
      const text = claim?.claim || "";
      if (!text) return null;
      const words = keywords(`${text} ${claim?.detail || ""}`);
      const matches = evidenceRows.filter((row) => overlap(keywords(row.claim), words) >= 2);
      let status = "missing";
      if (matches.some((m) => m.status === "contradicted")) status = "contradicted";
      else if (matches.some((m) => m.status === "mixed")) status = "mixed";
      else if (matches.some((m) => m.status === "supported" || m.status === "partial")) status = "supported";
      const hit = news
        .filter((item) => overlap(keywords(`${item.title || ""} ${item.summary || ""}`), words) >= 2)
        .sort((a, b) => String(b.published_at || "").localeCompare(String(a.published_at || "")))[0];
      return {
        id: `${claim?.id || index}-${kind}`,
        kind,
        claim: text,
        status,
        matches: matches.length,
        news: hit || null,
      };
    })
    .filter(Boolean);
});

async function load() {
  if (!props.companyId) return;
  busy.value = true;
  try {
    const [analysisRes, evidenceRes, trackingRes, decisionsRes] = await Promise.allSettled([
      api.memoAnalysis.get(props.companyId),
      api.memoAnalysis.getEvidenceMatrix(props.companyId),
      api.listTrackingUpdates(props.companyId),
      api.decisionRecords.list(props.companyId),
    ]);
    if (analysisRes.status === "fulfilled") analysis.value = analysisRes.value;
    if (evidenceRes.status === "fulfilled") evidence.value = evidenceRes.value;
    if (trackingRes.status === "fulfilled") tracking.value = trackingRes.value;
    if (decisionsRes.status === "fulfilled") {
      const list = Array.isArray(decisionsRes.value)
        ? decisionsRes.value
        : decisionsRes.value?.decisions || decisionsRes.value?.items || [];
      decision.value = list[0] || null;
    }
  } finally {
    busy.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    analysis.value = null;
    evidence.value = null;
    tracking.value = null;
    decision.value = null;
  },
);

function statusLabel(status) {
  if (status === "supported") return t("research_desk.thesis_supported");
  if (status === "contradicted") return t("research_desk.thesis_contradicted");
  if (status === "mixed") return t("research_desk.thesis_mixed");
  return t("research_desk.thesis_no_evidence");
}

function statusTint(status) {
  if (status === "supported") return "var(--mac-green)";
  if (status === "contradicted") return "var(--mac-red)";
  if (status === "mixed") return "var(--mac-orange)";
  return "var(--mac-secondary)";
}

function verdictTint(verdict) {
  if (verdict === "invest") return "var(--mac-green)";
  if (verdict === "pass") return "var(--mac-red)";
  return "var(--mac-orange)";
}

function verdictLabel(verdict) {
  if (verdict === "invest") return t("research_desk.invest");
  if (verdict === "pass") return t("research_desk.pass");
  return t("research_desk.watch");
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-2.5">
    <!-- Label("Thesis tracker") · decision pill · load/refresh -->
    <div class="flex items-center gap-2">
      <span class="mac-t-headline flex items-center gap-2">
        <Waypoints class="mac-c-accent h-4 w-4" stroke-width="2.2" />
        {{ t("research_desk.thesis_title") }}
      </span>
      <span class="flex-1" />
      <span
        v-if="decision"
        class="mac-status-pill"
        :style="{ '--tint': verdictTint(decision.verdict || decision.type) }"
      >
        {{ verdictLabel(decision.verdict || decision.type) }}
      </span>
      <button type="button" class="mac-btn mac-btn--sm" :disabled="busy" @click="load">
        <span v-if="busy" class="mac-spinner" style="width: 11px; height: 11px" />
        <RotateCw v-else class="h-3 w-3" />
        <span>{{ analysis == null ? t("research_desk.thesis_load") : t("research_desk.refresh") }}</span>
      </button>
    </div>

    <span v-if="analysis == null" class="mac-t-caption10 mac-c-secondary">
      {{ t("research_desk.thesis_hint") }}
    </span>
    <span v-else-if="rows.length === 0" class="mac-t-caption10 mac-c-secondary">
      {{ t("research_desk.thesis_empty") }}
    </span>

    <div
      v-for="row in rows"
      :key="row.id"
      class="flex items-start gap-2.5 rounded-lg p-2"
      style="background: color-mix(in srgb, var(--mac-secondary) 4%, transparent)"
    >
      <component
        :is="row.kind === 'highlight' ? ArrowUpRightFromCircle : ShieldAlert"
        class="mt-px h-3.5 w-[18px] shrink-0"
        :style="{ color: row.kind === 'highlight' ? 'var(--mac-green)' : 'var(--mac-red)' }"
      />
      <span class="flex min-w-0 flex-1 flex-col gap-[3px]">
        <span class="mac-t-subheadline font-medium">{{ row.claim }}</span>
        <span class="flex items-center gap-2">
          <span class="mac-status-pill" :style="{ '--tint': statusTint(row.status) }">
            {{ statusLabel(row.status) }}
          </span>
          <span v-if="row.matches > 0" class="mac-t-caption10 mac-c-secondary">
            {{ t("research_desk.thesis_evidence_claims", { count: row.matches }) }}
          </span>
        </span>
        <span v-if="row.news" class="mac-c-secondary flex items-center gap-1">
          <Newspaper class="h-3 w-3 shrink-0" />
          <span class="mac-t-caption10 min-w-0 truncate">{{ row.news.title }}</span>
          <span class="mac-t-caption10 mac-c-tertiary shrink-0">
            {{ formatRelativeTime(row.news.published_at || row.news.captured_at) }}
          </span>
          <span
            v-if="row.news.impact"
            class="mac-status-pill shrink-0"
            :style="{
              '--tint':
                row.news.impact === 'high'
                  ? 'var(--mac-red)'
                  : row.news.impact === 'medium'
                    ? 'var(--mac-orange)'
                    : 'var(--mac-secondary)',
            }"
          >
            {{ row.news.impact.replace(/^./, (c) => c.toUpperCase()) }}
          </span>
        </span>
      </span>
    </div>
  </div>
</template>
