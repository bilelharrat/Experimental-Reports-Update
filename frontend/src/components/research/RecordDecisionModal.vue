<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";

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

watch(
  () => props.isOpen,
  (open) => {
    if (open) {
      verdict.value = "watch";
      explanation.value = "";
      decidedAt.value = new Date().toISOString().slice(0, 10);
      reportId.value = props.seedReportId || (props.reports?.[0]?.id ?? "");
      error.value = null;
    }
  },
);

const verdictLabel = computed(() => {
  if (verdict.value === "invest") return t("research_desk.invest");
  if (verdict.value === "pass") return t("research_desk.pass");
  return t("research_desk.watch");
});

const userDisplayName = computed(() => {
  return "You";
});

const canSubmit = computed(() => {
  return (
    !submitting.value &&
    explanation.value.trim().length > 0 &&
    props.company?.id
  );
});

async function submitDecision() {
  if (!canSubmit.value) return;
  submitting.value = true;
  error.value = null;

  try {
    const payload = {
      type: verdict.value,
      rationale: explanation.value.trim(),
      decided_at: decidedAt.value ? new Date(decidedAt.value).toISOString() : new Date().toISOString(),
      report_id: reportId.value || undefined,
    };
    const res = await api.decisionRecords.add(props.company.id, payload);
    emit("saved", res);
    emit("close");
  } catch (err) {
    error.value = err?.message || "Failed to record decision";
  } finally {
    submitting.value = false;
  }
}

function handleClose() {
  emit("close");
}
</script>

<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4"
    role="dialog"
    aria-modal="true"
  >
    <!-- Scrim -->
    <div
      class="fixed inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
      @click="handleClose"
    />

    <!-- Modal Box -->
    <div
      class="relative w-full max-w-lg overflow-hidden rounded-2xl border border-border/60 bg-surface/95 dark:bg-[#1c1c1e]/95 shadow-2xl backdrop-blur-2xl transition-all"
    >
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-border/40 px-5 py-3.5 bg-muted/20">
        <div>
          <h3 class="font-semibold text-foreground text-sm">
            {{ t("research_desk.record_decision_title") }}
          </h3>
          <p class="text-[11px] text-muted-foreground mt-0.5">
            {{ company.name || company.title }}
          </p>
        </div>
        <button
          type="button"
          class="rounded px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors"
          @click="handleClose"
        >
          {{ t("research_desk.cancel") }}
        </button>
      </div>

      <!-- Form Content -->
      <form class="p-5 space-y-4 text-xs" @submit.prevent="submitDecision">
        <!-- Verdict Segmented Control -->
        <div class="space-y-1.5">
          <label class="block font-medium text-muted-foreground">
            {{ t("research_desk.verdict_label") }}
          </label>
          <div class="grid grid-cols-3 gap-2 rounded-xl border border-border/40 bg-muted/30 p-1">
            <button
              type="button"
              class="flex items-center justify-center gap-1.5 rounded-lg py-2 font-medium text-xs transition-all"
              :class="
                verdict === 'invest'
                  ? 'bg-emerald-600 text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              "
              @click="verdict = 'invest'"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
              <span>{{ t("research_desk.invest") }}</span>
            </button>

            <button
              type="button"
              class="flex items-center justify-center gap-1.5 rounded-lg py-2 font-medium text-xs transition-all"
              :class="
                verdict === 'watch'
                  ? 'bg-amber-500 text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              "
              @click="verdict = 'watch'"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
                <circle cx="12" cy="12" r="3" />
              </svg>
              <span>{{ t("research_desk.watch") }}</span>
            </button>

            <button
              type="button"
              class="flex items-center justify-center gap-1.5 rounded-lg py-2 font-medium text-xs transition-all"
              :class="
                verdict === 'pass'
                  ? 'bg-rose-600 text-white shadow-sm'
                  : 'text-muted-foreground hover:text-foreground'
              "
              @click="verdict = 'pass'"
            >
              <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
              <span>{{ t("research_desk.pass") }}</span>
            </button>
          </div>
        </div>

        <!-- Date & Memo Fields in Grid -->
        <div class="grid grid-cols-2 gap-3">
          <div class="space-y-1.5">
            <label class="block font-medium text-muted-foreground">
              {{ t("research_desk.decided_date") }}
            </label>
            <input
              v-model="decidedAt"
              type="date"
              class="w-full rounded-lg border border-border/60 bg-surface dark:bg-muted/30 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
            />
          </div>

          <div class="space-y-1.5">
            <label class="block font-medium text-muted-foreground">
              {{ t("research_desk.based_on_memo") }}
            </label>
            <select
              v-model="reportId"
              class="w-full rounded-lg border border-border/60 bg-surface dark:bg-muted/30 px-3 py-1.5 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option value="">{{ t("research_desk.none") }}</option>
              <option v-for="r in reports" :key="r.id" :value="r.id">
                {{ r.title || r.displayTitle || r.id }}
              </option>
            </select>
          </div>
        </div>

        <!-- Rationale text area -->
        <div class="space-y-1.5">
          <label class="block font-medium text-muted-foreground">
            {{ t("research_desk.rationale_required") }}
          </label>
          <textarea
            v-model="explanation"
            rows="5"
            required
            class="w-full rounded-xl border border-border/60 bg-surface dark:bg-muted/20 p-3 text-xs leading-relaxed text-foreground placeholder-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-accent"
            :placeholder="t('research_desk.rationale_placeholder')"
          />
        </div>

        <div v-if="error" class="rounded-lg border border-rose-500/20 bg-rose-500/10 p-2 text-[11px] text-rose-600 dark:text-rose-400">
          {{ error }}
        </div>
      </form>

      <!-- Footer -->
      <div class="flex items-center justify-between border-t border-border/40 px-5 py-3 bg-muted/20">
        <span class="text-[11px] text-muted-foreground">
          {{ t("research_desk.recorded_as", { user: userDisplayName }) }}
        </span>

        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/40 transition-colors"
            @click="handleClose"
          >
            {{ t("research_desk.cancel") }}
          </button>
          <button
            type="button"
            class="btn-filled rounded-lg px-4 py-1.5 text-xs font-medium text-white transition-all disabled:opacity-50"
            :disabled="!canSubmit"
            @click="submitDecision"
          >
            {{ submitting ? t("research_desk.saving") : t("research_desk.record_action", { verdict: verdictLabel }) }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
