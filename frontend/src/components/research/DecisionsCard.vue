<script setup>
// Web twin of the "Decision record" card in MacResearchDeskView.swift:
// MacCardHeader with the lifecycle stage, then MacDecisionTimeline — verdict
// pill, date, author, memo link, explanation, and the retrospectives the
// tracking sync appends. Recording happens in the ⌘D sheet, not inline.
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { useT } from "../../i18n.js";
import { BadgeCheck, Trash2, FileText, CheckCircle2, OctagonX, HelpCircle } from "lucide-vue-next";
import api from "../../api.js";
import { formatRelativeTime } from "../../formatters.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
  reloadToken: {
    type: Number,
    default: 0,
  },
});

const t = useT();
const router = useRouter();

const loading = ref(false);
const decisions = ref([]);

async function loadDecisions() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.decisionRecords.list(props.companyId);
    decisions.value = Array.isArray(res) ? res : (res?.decisions || res?.items || []);
  } catch {
    decisions.value = [];
  } finally {
    loading.value = false;
  }
}

watch(() => [props.companyId, props.reloadToken], loadDecisions, { immediate: true });

async function removeDecision(decision) {
  if (!props.companyId || !decision?.id) return;
  const when = String(decision.decided_at || "").slice(0, 10);
  const ok = window.confirm(
    t("research_desk.decision_delete_confirm", { verdict: verdictLabel(decision.verdict), date: when }),
  );
  if (!ok) return;
  try {
    await api.decisionRecords.remove(props.companyId, decision.id);
    await loadDecisions();
  } catch {
    // leave the row; the next reload shows the truth
  }
}

function verdictLabel(verdict) {
  const v = (verdict || "").toLowerCase();
  if (v === "invest") return t("research_desk.invest");
  if (v === "pass") return t("research_desk.pass");
  return t("research_desk.watch");
}

function verdictTint(verdict) {
  const v = (verdict || "").toLowerCase();
  if (v === "invest") return "var(--mac-green)";
  if (v === "pass") return "var(--mac-red)";
  return "var(--mac-orange)";
}

function retroIcon(verdict) {
  if (verdict === "still_right") return CheckCircle2;
  if (verdict === "looks_wrong") return OctagonX;
  return HelpCircle;
}

function retroTint(verdict) {
  if (verdict === "still_right") return "var(--mac-green)";
  if (verdict === "looks_wrong") return "var(--mac-red)";
  return "var(--mac-orange)";
}

function retroLabel(verdict) {
  if (verdict === "still_right") return t("research_desk.retro_still_right");
  if (verdict === "looks_wrong") return t("research_desk.retro_looks_wrong");
  return t("research_desk.retro_questionable");
}

function openMemo(reportId) {
  router.push({ name: "reports", query: { id: reportId, company: props.companyId } });
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-3">
    <!-- MacCardHeader("Decision record", stage, checkmark.seal) -->
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><BadgeCheck class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.decision_record_title") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ company?.deal_stage || "Sourced" }}</span>
      </div>
    </div>

    <!-- MacDecisionTimeline -->
    <div class="flex flex-col gap-2.5">
      <p v-if="decisions.length === 0 && !loading" class="mac-t-caption mac-c-secondary">
        {{ t("research_desk.decisions_empty") }}
      </p>

      <div
        v-for="dec in decisions"
        :key="dec.id || dec.created_at"
        class="flex flex-col gap-1.5 rounded-lg p-2.5"
        style="background: color-mix(in srgb, var(--mac-secondary) 4%, transparent)"
      >
        <div class="flex flex-wrap items-center gap-2">
          <span class="mac-status-pill" :style="{ '--tint': verdictTint(dec.verdict || dec.type) }">
            {{ verdictLabel(dec.verdict || dec.type) }}
          </span>
          <span class="mac-t-caption10 mac-mono mac-c-secondary">
            {{ String(dec.decided_at || dec.created_at || "").slice(0, 10) }}
          </span>
          <span v-if="dec.created_by || dec.author" class="mac-t-caption10 mac-c-secondary">
            · {{ dec.created_by || dec.author }}
          </span>
          <button
            v-if="dec.report_id"
            type="button"
            class="mac-c-accent flex items-center gap-1 border-none bg-transparent p-0"
            @click="openMemo(dec.report_id)"
          >
            <FileText class="h-3 w-3" />
            <span class="mac-t-caption10">{{ t("research_desk.decision_view_memo") }}</span>
          </button>
          <span class="flex-1" />
          <button
            v-if="dec.id"
            type="button"
            class="mac-c-secondary border-none bg-transparent p-0.5"
            :title="t('research_desk.delete_decision')"
            @click="removeDecision(dec)"
          >
            <Trash2 class="h-3 w-3" />
          </button>
        </div>

        <p class="mac-t-callout select-text whitespace-pre-wrap">
          {{ dec.explanation || dec.rationale }}
        </p>

        <!-- Retrospectives from the tracking sync -->
        <div
          v-for="retro in dec.retrospectives || []"
          :key="retro.id"
          class="flex items-start gap-1.5 rounded-md p-2"
          style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
        >
          <component
            :is="retroIcon(retro.verdict)"
            class="mt-px h-3.5 w-3.5 shrink-0"
            :style="{ color: retroTint(retro.verdict) }"
          />
          <span class="flex min-w-0 flex-col gap-0.5">
            <span class="mac-t-caption10 font-semibold">
              {{ retroLabel(retro.verdict) }} · {{ formatRelativeTime(retro.assessed_at) }}
            </span>
            <span v-if="retro.rationale_en" class="mac-t-caption10 mac-c-secondary">
              {{ retro.rationale_en }}
            </span>
            <span v-if="retro.news_titles?.length" class="mac-t-caption10 mac-c-tertiary line-clamp-2">
              {{ retro.news_titles.slice(0, 2).join(" · ") }}
            </span>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
