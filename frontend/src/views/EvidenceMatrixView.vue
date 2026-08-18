<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import {
  AlertTriangle,
  CheckCircle2,
  FileSearch,
  Link2,
  Loader2,
  MessageSquarePlus,
  RefreshCw,
  ShieldCheck,
  Table2,
} from "lucide-vue-next";
import { api } from "../api.js";
import ResearchPagesNav from "../components/research-pages/ResearchPagesNav.vue";
import { runFullStockResearchRefresh } from "../researchPageJobs.js";

const route = useRoute();
const payload = ref(null);
const loading = ref(true);
const refreshing = ref(false);
const error = ref("");
const actionMessage = ref("");
const statusFilter = ref("all");

const companyId = computed(() => route.query.company_id || route.query.companyId || "");
const summary = computed(() => payload.value?.summary || {});
const sections = computed(() => payload.value?.sections || {});
const issues = computed(() => payload.value?.doctor_issues || []);
const health = computed(() => payload.value?.source_health || {});
const claims = computed(() => sections.value.claim_table || []);
const matrix = computed(() => sections.value.evidence_strength_matrix || []);
const provenance = computed(() => sections.value.source_provenance || []);
const contradictions = computed(() => sections.value.contradictions_lane || []);
const filters = computed(() => sections.value.unsupported_filters || {});

const filteredClaims = computed(() => {
  if (statusFilter.value === "all") return claims.value;
  if (statusFilter.value === "unsupported") {
    return claims.value.filter((claim) => claim.source_count === 0 || claim.status === "unsupported");
  }
  if (statusFilter.value === "contradicted") {
    return claims.value.filter((claim) => claim.contradiction_count > 0 || claim.status === "contradicted");
  }
  if (statusFilter.value === "weak") {
    return claims.value.filter(
      (claim) =>
        claim.source_count > 0 &&
        claim.primary_source_count === 0 &&
        claim.weak_source_count >= claim.source_count,
    );
  }
  return claims.value.filter((claim) => claim.status === statusFilter.value);
});

async function load({ showLoading = true } = {}) {
  if (showLoading) loading.value = true;
  error.value = "";
  try {
    payload.value = await api.researchPages.evidenceMatrix({
      companyId: companyId.value || undefined,
    });
  } catch (e) {
    error.value = e.message || "Could not load Evidence Matrix.";
  } finally {
    loading.value = false;
  }
}

async function refreshPage() {
  if (refreshing.value || loading.value) return;
  refreshing.value = true;
  error.value = "";
  actionMessage.value = "";
  try {
    if (!companyId.value) {
      actionMessage.value = "Running active trackers, then rebuilding global evidence.";
      const result = await runFullStockResearchRefresh();
      await load({ showLoading: false });
      actionMessage.value = evidenceRefreshMessage(result);
      return;
    } else {
      actionMessage.value = "Evidence Matrix reloaded from current company evidence.";
    }
    await load({ showLoading: false });
  } catch (e) {
    error.value = e.message || "Could not refresh Evidence Matrix.";
  } finally {
    refreshing.value = false;
  }
}

function plural(count, singular, pluralText = `${singular}s`) {
  return `${count} ${count === 1 ? singular : pluralText}`;
}

function sourceTraceGapText(count, singular) {
  if (count === 1) return `1 ${singular} still lacks source traces`;
  return `${count} ${singular}s still need source traces`;
}

function evidenceRefreshMessage(result) {
  const trackerText = plural(result.activeTrackerCount, "tracker");
  if (!result.activeTrackerCount) {
    return "No active trackers are configured; rebuilt global evidence from existing outputs.";
  }
  if (result.trackerErrorCount) {
    return `Full refresh ran ${trackerText}, but ${plural(result.trackerErrorCount, "tracker")} had errors. Review Stock Research runs.`;
  }
  if (!result.aggregateCompleted) {
    return `Full refresh ran ${trackerText}; the aggregate is still running. Results will update after it completes.`;
  }
  if (!summary.value.claim_count) {
    return `Full refresh ran ${trackerText}, but no global evidence claims were produced. Add tracker sources or review tracker outputs.`;
  }
  if (health.value.missing_trace_count || summary.value.unsupported_claim_count) {
    return `Full refresh ran ${trackerText} and rebuilt ${plural(summary.value.claim_count, "claim")}, but ${sourceTraceGapText(summary.value.unsupported_claim_count || health.value.missing_trace_count, "claim")}.`;
  }
  return `Full refresh complete: ran ${trackerText} and rebuilt ${plural(summary.value.claim_count, "claim")}.`;
}

function fmtDateTime(iso) {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

watch(companyId, load);
onMounted(load);

function fmtPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "n/a";
  return `${Math.round(number * 100)}%`;
}

function issueClass(severity) {
  if (severity === "error") return "border-danger/30 bg-danger-soft text-danger-ink";
  if (severity === "warning") return "border-warning/30 bg-warning-soft text-warning-ink";
  return "border-subtle bg-surface-muted text-ink-secondary";
}

function statusClass(status) {
  if (status === "supported") return "bg-success-soft text-success-ink";
  if (status === "contradicted") return "bg-danger-soft text-danger-ink";
  if (status === "unsupported") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function matrixClass(row) {
  if (row.status === "contradicted" || row.contradiction_count) return "bg-danger";
  if (row.evidence_quality === "high") return "bg-success";
  if (row.evidence_quality === "medium") return "bg-accent";
  return "bg-warning";
}

function matrixStyle(row) {
  const count = Math.max(1, Number(row.claim_count) || 1);
  return { opacity: Math.min(1, 0.25 + count * 0.18) };
}

function sourceClass(sourceRef) {
  if (sourceRef?.source_id && sourceRef?.source_exists === false) {
    return "border-danger/30 bg-danger-soft text-danger-ink";
  }
  return "border-subtle bg-surface-muted text-ink-secondary";
}

function sourceKey(claim, sourceRef, prefix) {
  return `${claim.claim_id}-${prefix}-${sourceRef?.source_id || sourceRef?.source_title || sourceRef?.locator}`;
}
</script>

<template>
  <div>
    <div>
      <div class="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-5">
        <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div class="vogue-label">
              Research Pages
            </div>
            <h1 class="font-display text-large-title text-ink-primary">
              Evidence Matrix
            </h1>
            <div class="mt-1 text-sm text-ink-muted">
              {{ companyId ? `Company ${companyId}` : "Global claims" }} · {{ payload?.status || "loading" }}
              <span v-if="payload?.generated_at"> · Generated {{ fmtDateTime(payload.generated_at) }}</span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <ResearchPagesNav />
            <button
              type="button"
              class="btn-bordered focus-ring"
              :disabled="loading || refreshing"
              @click="refreshPage"
            >
              <Loader2 v-if="refreshing" class="h-4 w-4 animate-spin" />
              <RefreshCw v-else class="h-4 w-4" />
              {{ refreshing ? "Refreshing" : "Refresh" }}
            </button>
          </div>
        </div>
        <div
          v-if="actionMessage"
          class="rounded-md border border-success/30 bg-success-soft px-3 py-2 text-sm text-success-ink"
        >
          {{ actionMessage }}
        </div>
      </div>
    </div>

    <div class="mx-auto max-w-7xl px-5 py-6">
      <div v-if="loading" class="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 class="h-4 w-4 animate-spin" />
        Loading Evidence Matrix
      </div>
      <div v-else-if="error" class="rounded-md border border-danger/30 bg-danger-soft p-4 text-sm text-danger-ink">
        {{ error }}
      </div>
      <div v-else class="space-y-6">
        <div class="grid gap-3 md:grid-cols-5">
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Claims</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.claim_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Unsupported</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.unsupported_claim_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Contradicted</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.contradicted_claim_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Memo eligible</div>
            <div class="mt-2 text-2xl font-semibold">{{ summary.memo_eligible_claim_count || 0 }}</div>
          </div>
          <div class="rounded-card bg-surface shadow-card p-4">
            <div class="text-footnote font-semibold text-ink-muted">Sources</div>
            <div class="mt-2 text-2xl font-semibold">{{ health.source_trace_count || 0 }}</div>
          </div>
        </div>

        <section class="rounded-card bg-surface shadow-card">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-subtle px-4 py-3">
            <div class="flex items-center gap-2">
              <Table2 class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-title3">Evidence Strength Matrix</h2>
            </div>
            <div class="flex items-center gap-1 rounded-md border border-subtle bg-surface-muted p-1">
              <button
                v-for="filter in ['all', 'unsupported', 'weak', 'contradicted']"
                :key="filter"
                type="button"
                class="rounded px-2 py-1 text-xs capitalize focus-ring"
                :class="statusFilter === filter ? 'bg-surface text-ink-primary shadow-sm' : 'text-ink-muted hover:text-ink-primary'"
                @click="statusFilter = filter"
              >
                {{ filter }}
              </button>
            </div>
          </div>
          <div v-if="matrix.length === 0" class="p-6 text-sm text-ink-muted">
            No matrix cells yet. Add sourced company evidence or Stock Research signals.
          </div>
          <div v-else class="grid gap-3 p-4 md:grid-cols-3 lg:grid-cols-4">
            <div
              v-for="cell in matrix"
              :key="`${cell.evidence_quality}-${cell.claim_importance}-${cell.status}`"
              class="min-h-28 rounded-md p-3 text-white"
              :class="matrixClass(cell)"
              :style="matrixStyle(cell)"
            >
              <div class="text-xs">{{ cell.claim_importance }} importance</div>
              <div class="mt-2 text-lg font-semibold">{{ cell.claim_count }} claims</div>
              <div class="mt-1 text-sm">{{ cell.evidence_quality }} evidence · {{ cell.status }}</div>
              <div class="mt-2 text-xs">{{ cell.contradiction_count }} contradictions</div>
            </div>
          </div>
        </section>

        <section class="overflow-hidden rounded-card bg-surface shadow-card">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b border-subtle px-4 py-3">
            <h2 class="font-display text-title3">Claim Table</h2>
            <div class="text-sm text-ink-muted">
              {{ filteredClaims.length }} shown · {{ filters.no_source_trace || 0 }} no source
            </div>
          </div>
          <div v-if="claims.length === 0" class="p-6 text-sm text-ink-muted">
            No claims are available for this scope.
          </div>
          <div v-else class="overflow-x-auto">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-left text-footnote font-semibold text-ink-muted">
                <tr>
                  <th class="px-3 py-2">Claim</th>
                  <th class="px-3 py-2">Type</th>
                  <th class="px-3 py-2">Status</th>
                  <th class="px-3 py-2 text-right">Strength</th>
                  <th class="px-3 py-2 text-right">Sources</th>
                  <th class="px-3 py-2 text-right">Primary</th>
                  <th class="px-3 py-2 text-right">Contradictions</th>
                  <th class="px-3 py-2">Eligibility</th>
                  <th class="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="claim in filteredClaims"
                  :key="claim.claim_id"
                  class="border-b border-subtle align-top last:border-0"
                >
                  <td class="max-w-2xl px-3 py-3">
                    <div class="font-medium text-ink-primary">{{ claim.claim }}</div>
                    <div class="mt-1 text-xs text-ink-muted">{{ claim.company_name || claim.company_id }} · {{ claim.claim_id }}</div>
                    <div v-if="claim.source_refs?.length" class="mt-2 space-y-1">
                      <div
                        v-for="sourceRef in claim.source_refs.slice(0, 2)"
                        :key="sourceKey(claim, sourceRef, 'support')"
                        class="rounded border px-2 py-1 text-xs"
                        :class="sourceClass(sourceRef)"
                      >
                        <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span class="font-medium text-ink-primary">{{ sourceRef.source_title || "Source" }}</span>
                          <span>{{ sourceRef.source_type || "unknown" }}</span>
                          <span>{{ sourceRef.locator || "locator missing" }}</span>
                          <span>{{ sourceRef.published_at || "date unknown" }}</span>
                          <span>{{ fmtPct(sourceRef.confidence) }}</span>
                        </div>
                        <div class="mt-1 line-clamp-2">
                          {{ sourceRef.excerpt || "No excerpt provided." }}
                        </div>
                      </div>
                    </div>
                    <div v-else class="mt-2 rounded border border-danger/30 bg-danger-soft px-2 py-1 text-xs text-danger-ink">
                      Missing source trace.
                    </div>
                    <div v-if="claim.contradictions?.length" class="mt-2 space-y-1">
                      <div
                        v-for="sourceRef in claim.contradictions.slice(0, 1)"
                        :key="sourceKey(claim, sourceRef, 'contradiction')"
                        class="rounded border border-warning/30 bg-warning-soft px-2 py-1 text-xs text-warning-ink"
                      >
                        Contradiction: {{ sourceRef.source_title || "Source" }} · {{ sourceRef.source_type || "unknown" }}
                      </div>
                    </div>
                  </td>
                  <td class="px-3 py-3">{{ claim.claim_type }}</td>
                  <td class="px-3 py-3">
                    <span class="rounded-full px-2 py-0.5 text-xs font-medium" :class="statusClass(claim.status)">
                      {{ claim.status }}
                    </span>
                  </td>
                  <td class="px-3 py-3 text-right">{{ fmtPct(claim.evidence_strength) }}</td>
                  <td class="px-3 py-3 text-right">{{ claim.source_count }}</td>
                  <td class="px-3 py-3 text-right">{{ claim.primary_source_count }}</td>
                  <td class="px-3 py-3 text-right">{{ claim.contradiction_count }}</td>
                  <td class="px-3 py-3 text-xs text-ink-secondary">
                    <div>{{ claim.eligible_for_memo ? "memo" : "memo blocked" }}</div>
                    <div class="mt-1 max-w-56">{{ claim.memo_eligibility_reason || "Memo eligibility pending." }}</div>
                    <div>{{ claim.eligible_for_hypothesis ? "hypothesis" : "hypothesis blocked" }}</div>
                    <div class="mt-1 max-w-56">{{ claim.hypothesis_eligibility_reason || "Hypothesis eligibility pending." }}</div>
                  </td>
                  <td class="px-3 py-3 text-right">
                    <div class="inline-flex items-center gap-1">
                      <button
                        type="button"
                        class="rounded-md border border-subtle p-1.5 text-ink-muted opacity-60 focus-ring disabled:cursor-not-allowed"
                        :title="claim.eligible_for_memo ? 'Planned action; no durable endpoint is wired yet.' : claim.memo_eligibility_reason"
                        disabled
                      >
                        <ShieldCheck class="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        class="rounded-md border border-subtle p-1.5 text-ink-muted opacity-60 focus-ring disabled:cursor-not-allowed"
                        title="Planned action; no durable endpoint is wired yet."
                        disabled
                      >
                        <FileSearch class="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        class="rounded-md border border-subtle p-1.5 text-ink-muted opacity-60 focus-ring disabled:cursor-not-allowed"
                        title="Planned action; no durable endpoint is wired yet."
                        disabled
                      >
                        <MessageSquarePlus class="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(20rem,0.8fr)]">
          <section class="rounded-card bg-surface shadow-card">
            <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
              <Link2 class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-title3">Source Provenance</h2>
            </div>
            <div v-if="provenance.length === 0" class="p-4 text-sm text-ink-muted">
              No source provenance rows.
            </div>
            <div v-else class="divide-y divide-subtle">
              <div v-for="source in provenance.slice(0, 8)" :key="source.source_id || source.source_title" class="p-4 text-sm">
                <div class="font-medium">{{ source.source_title }}</div>
                <div class="mt-1 text-xs text-ink-muted">
                  {{ source.source_type }} · {{ source.trace_count }} traces · {{ source.claims_supported }} claims
                </div>
              </div>
            </div>
          </section>

          <section class="rounded-card bg-surface shadow-card">
            <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
              <AlertTriangle class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-title3">Contradictions Lane</h2>
            </div>
            <div v-if="contradictions.length === 0" class="p-4 text-sm text-ink-muted">
              No unresolved contradictions.
            </div>
            <div v-else class="divide-y divide-subtle">
              <div v-for="item in contradictions" :key="`${item.claim_id}-${item.contradicting_source?.source_id}`" class="p-4 text-sm">
                <div class="font-medium">{{ item.claim }}</div>
                <div class="mt-2 text-xs text-ink-muted">{{ item.analyst_action }}</div>
              </div>
            </div>
          </section>

          <section class="rounded-card bg-surface shadow-card">
            <div class="flex items-center gap-2 border-b border-subtle px-4 py-3">
              <AlertTriangle class="h-4 w-4 text-ink-muted" />
              <h2 class="font-display text-title3">Doctor Issues</h2>
            </div>
            <div v-if="issues.length === 0" class="flex items-center gap-2 p-4 text-sm text-success-ink">
              <CheckCircle2 class="h-4 w-4" />
              No Evidence Matrix issues.
            </div>
            <div v-else class="space-y-2 p-4">
              <div
                v-for="issue in issues"
                :key="`${issue.type}-${issue.artifact_id || issue.message}`"
                class="rounded-md border px-3 py-2 text-sm"
                :class="issueClass(issue.severity)"
              >
                <div class="font-medium">{{ issue.type }}</div>
                <div class="mt-1">{{ issue.message }}</div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
