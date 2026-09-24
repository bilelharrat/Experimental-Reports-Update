<script setup>
// Web twin of MacDecisionSheet (⌘D): a 520pt sheet with bar-material header
// and footer, a grouped form (verdict glass segments, decided date, memo
// picker, required rationale), submitting {verdict, explanation, decided_at,
// report_id} — decided_at as the picked day at midnight UTC, like
// MacDecisionDate.dayInstant.
import { computed, ref, watch, onMounted, onUnmounted } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { sessionName } from "../../auth.js";
import { formatIsoDate } from "../../formatters.js";
import { reportCanOpen, reportIsHidden, reportTypeLabel } from "../../reportStatus.js";
import { CheckCircle2, Eye, XCircle } from "lucide-vue-next";

const props = defineProps({
  isOpen: {
    type: Boolean,
    default: false,
  },
  company: {
    type: Object,
    required: true,
  },
  reports: {
    type: Array,
    default: () => [],
  },
  seedReportId: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["close", "saved"]);

const verdict = ref("watch");
const explanation = ref("");
const decidedAt = ref(new Date().toISOString().slice(0, 10));
const reportId = ref("");
const submitting = ref(false);
const error = ref(null);

// A decision rests on a memo someone can open: a document on file (with or
// without quality warnings), newest first. The API sends no `title` or
// `can_open`, so the picker names each memo by its type and date.
const openableReports = computed(() =>
  (props.reports || [])
    .filter((r) => reportCanOpen(r) && !reportIsHidden(r))
    .sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))),
);

function reportOptionLabel(r) {
  const date = formatIsoDate(r.report_ready_at || r.created_at, "");
  return date ? `${reportTypeLabel(r, t)} · ${date}` : reportTypeLabel(r, t);
}

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      verdict.value = "watch";
      explanation.value = "";
      decidedAt.value = new Date().toISOString().slice(0, 10);
      reportId.value = props.seedReportId || openableReports.value[0]?.id || "";
      error.value = null;
    }
  },
  { immediate: true },
);

const verdictLabel = computed(() => {
  if (verdict.value === "invest") return t("research_desk.invest");
  if (verdict.value === "pass") return t("research_desk.pass");
  return t("research_desk.watch");
});

const userDisplayName = computed(() => sessionName.value || t("research_desk.recorded_you"));

const canSubmit = computed(
  () => !submitting.value && explanation.value.trim().length > 0 && props.company?.id,
);

async function submitDecision() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;

  try {
    const res = await api.decisionRecords.add(props.company.id, {
      verdict: verdict.value,
      explanation: explanation.value.trim(),
      // The picked calendar day as midnight UTC (MacDecisionDate.dayInstant).
      decided_at: decidedAt.value ? `${decidedAt.value}T00:00:00Z` : undefined,
      report_id: reportId.value || undefined,
    });
    emit("saved", res);
    emit("close");
  } catch (err) {
    error.value = err?.message || t("desk.decision_save_failed");
  } finally {
    submitting.value = false;
  }
}

function onKeydown(e) {
  if (!props.isOpen) return;
  if (e.key === "Escape") {
    e.preventDefault();
    emit("close");
  }
}

onMounted(() => window.addEventListener("keydown", onKeydown));
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <div
    v-if="isOpen"
    class="mac-desk fixed inset-0 z-50 flex items-center justify-center p-4"
    style="background: transparent"
    role="dialog"
    aria-modal="true"
  >
    <!-- Sheet scrim -->
    <div class="fixed inset-0" style="background: rgba(0, 0, 0, 0.28)" @click="emit('close')" />

    <!-- Sheet -->
    <div
      class="relative flex w-full max-w-[520px] flex-col overflow-hidden rounded-[12px]"
      style="background: var(--mac-canvas); box-shadow: 0 0 0 1px var(--mac-hairline), 0 24px 60px rgba(0, 0, 0, 0.35)"
    >
      <!-- Header on bar material -->
      <div class="mac-bar-material flex items-center px-4 py-3">
        <div class="flex min-w-0 flex-col gap-0.5">
          <span class="mac-t-headline-sys">{{ t("research_desk.record_decision_title") }}</span>
          <span class="mac-t-caption mac-c-secondary truncate">{{ company.name || company.title || company.id }}</span>
        </div>
        <span class="flex-1" />
        <button type="button" class="mac-btn" @click="emit('close')">
          {{ t("research_desk.cancel") }}
        </button>
      </div>
      <div class="mac-divider" />

      <!-- Grouped form -->
      <form class="mac-scroll flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4" @submit.prevent="submitDecision">
        <div class="mac-tile flex flex-col" style="border-radius: 10px">
          <!-- Verdict -->
          <div class="flex items-center gap-4 px-2.5 py-2">
            <span class="mac-t-body shrink-0">{{ t("research_desk.verdict_label") }}</span>
            <span class="flex-1" />
            <div class="mac-segmented w-[280px]">
              <button
                type="button"
                class="mac-segment flex items-center justify-center gap-1"
                :class="{ 'is-selected': verdict === 'invest' }"
                @click="verdict = 'invest'"
              >
                <CheckCircle2 class="h-3 w-3" />
                {{ t("research_desk.invest") }}
              </button>
              <button
                type="button"
                class="mac-segment flex items-center justify-center gap-1"
                :class="{ 'is-selected': verdict === 'watch' }"
                @click="verdict = 'watch'"
              >
                <Eye class="h-3 w-3" />
                {{ t("research_desk.watch") }}
              </button>
              <button
                type="button"
                class="mac-segment flex items-center justify-center gap-1"
                :class="{ 'is-selected': verdict === 'pass' }"
                @click="verdict = 'pass'"
              >
                <XCircle class="h-3 w-3" />
                {{ t("research_desk.pass") }}
              </button>
            </div>
          </div>
          <div class="mac-divider mx-2.5" />

          <!-- Decided -->
          <div class="flex items-center gap-4 px-2.5 py-2">
            <span class="mac-t-body shrink-0">{{ t("research_desk.decided_date") }}</span>
            <span class="flex-1" />
            <input v-model="decidedAt" type="date" class="mac-field mac-mono" style="font-size: 12px" />
          </div>
          <div class="mac-divider mx-2.5" />

          <!-- Based on memo -->
          <div class="flex items-center gap-4 px-2.5 py-2">
            <span class="mac-t-body shrink-0">{{ t("research_desk.based_on_memo") }}</span>
            <span class="flex-1" />
            <div class="mac-popup max-w-[280px]">
              <select v-model="reportId">
                <option value="">{{ t("research_desk.none") }}</option>
                <option v-for="r in openableReports" :key="r.id" :value="r.id">
                  {{ reportOptionLabel(r) }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <!-- Rationale -->
        <div class="flex flex-col gap-1.5">
          <span class="mac-t-label mac-c-secondary">{{ t("research_desk.rationale_required") }}</span>
          <textarea
            v-model="explanation"
            rows="6"
            required
            class="mac-field w-full resize-y"
            style="min-height: 140px; line-height: 1.4"
            :placeholder="t('research_desk.rationale_placeholder')"
          />
        </div>

        <span v-if="error" class="mac-t-caption" :style="{ color: 'var(--mac-red)' }">{{ error }}</span>
      </form>

      <div class="mac-divider" />

      <!-- Footer on bar material -->
      <div class="mac-bar-material flex items-center px-4 py-3">
        <span class="mac-t-caption10 mac-c-secondary">
          {{ t("research_desk.recorded_as", { user: userDisplayName }) }}
        </span>
        <span class="flex-1" />
        <button
          type="button"
          class="mac-btn mac-btn--prominent"
          :disabled="!canSubmit"
          @click="submitDecision"
        >
          {{ submitting ? t("research_desk.saving") : t("research_desk.record_action", { verdict: verdictLabel }) }}
        </button>
      </div>
    </div>
  </div>
</template>
