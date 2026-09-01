<script setup>
import { CheckCircle2, FileSearch, FileText, Loader2 } from "lucide-vue-next";
import { useT } from "../../i18n.js";

defineProps({
  session: { type: Object, default: null },
  approved: { type: Boolean, default: false },
  approving: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  readyForApproval: { type: Boolean, default: false },
  canGenerateMemo: { type: Boolean, default: false },
  hasRiskCards: { type: Boolean, default: false },
  investigationRunning: { type: Boolean, default: false },
  approvalTitle: { type: String, default: "Approve analysis" },
});

const emit = defineEmits(["approve", "start-investigation", "generate-memo"]);
const t = useT();
</script>

<template>
  <div class="flex flex-wrap items-start justify-between gap-4">
    <div>
      <h2 class="font-display text-xl font-semibold text-ink-primary">
        Memo Studio
      </h2>
      <div v-if="session" class="mt-1 font-mono text-xs text-ink-muted">
        {{ session.id }} · {{ session.status }}
      </div>
    </div>
    <div class="flex items-center gap-2">
      <button
        type="button"
        :disabled="approving || loading || approved || !readyForApproval"
        :title="approvalTitle"
        class="btn-bordered focus-ring"
        @click="emit('approve')"
      >
        <Loader2 v-if="approving" class="h-4 w-4 animate-spin" />
        <CheckCircle2 v-else class="h-4 w-4" />
        <span>{{ approved ? t("memo.approved") : t("memo.approve_analysis") }}</span>
      </button>
      <button
        v-if="!hasRiskCards"
        type="button"
        :disabled="loading || investigationRunning || !canGenerateMemo"
        :title="t('memo.start_investigation_title')"
        class="btn-filled disabled:cursor-not-allowed focus-ring"
        @click="emit('start-investigation')"
      >
        <Loader2 v-if="investigationRunning" class="h-4 w-4 animate-spin" />
        <FileSearch v-else class="h-4 w-4" />
        <span>{{ investigationRunning ? t("memo.investigation_running") : t("memo.start_investigation") }}</span>
      </button>
      <button
        v-else
        type="button"
        :disabled="!canGenerateMemo || loading || investigationRunning"
        :title="canGenerateMemo ? t('memo.generate_report_title') : t('memo.session_loading')"
        class="btn-filled disabled:cursor-not-allowed focus-ring"
        @click="emit('generate-memo')"
      >
        <FileText class="h-4 w-4" />
        <span>{{ t("memo.generate_report") }}</span>
      </button>
    </div>
  </div>
</template>
