<script setup>
import { CheckCircle2, FileText, Loader2 } from "lucide-vue-next";

defineProps({
  session: { type: Object, default: null },
  approved: { type: Boolean, default: false },
  approving: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
  readyForApproval: { type: Boolean, default: false },
  canGenerateMemo: { type: Boolean, default: false },
  approvalTitle: { type: String, default: "Approve analysis" },
});

const emit = defineEmits(["approve", "generate-memo"]);
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
        class="inline-flex items-center gap-2 rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring"
        @click="emit('approve')"
      >
        <Loader2 v-if="approving" class="h-4 w-4 animate-spin" />
        <CheckCircle2 v-else class="h-4 w-4" />
        <span>{{ approved ? "Approved" : "Approve analysis" }}</span>
      </button>
      <button
        type="button"
        :disabled="!canGenerateMemo"
        :title="canGenerateMemo ? 'Generate memo with current Memo Studio context' : 'Memo Studio session is loading'"
        class="inline-flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm text-white hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50 focus-ring"
        @click="emit('generate-memo')"
      >
        <FileText class="h-4 w-4" />
        <span>Generate memo</span>
      </button>
    </div>
  </div>
</template>
