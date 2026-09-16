<script setup>
import { computed } from "vue";
import { useT } from "../../i18n.js";
import {
  FileSpreadsheet,
  ChevronRight,
  Sparkles,
} from "lucide-vue-next";
import AiMark from "../AiMark.vue";
import { formatIsoDate } from "../../formatters.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
  reports: {
    type: Array,
    default: () => [],
  },
  pipelines: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["open-memo", "open-customizer"]);
const t = useT();

const sortedReports = computed(() => {
  return [...props.reports].sort((a, b) => {
    const da = new Date(b.created_at || b.date || 0).getTime();
    const db = new Date(a.created_at || a.date || 0).getTime();
    return da - db;
  });
});
</script>

<template>
  <div class="rounded-xl border border-white/[0.08] bg-[#1c1c1f] p-3.5 shadow-xs transition-all text-white">
    <!-- Header (MacResearchDeskView.swift:360-375) -->
    <div class="flex items-center justify-between pb-3 border-b border-white/[0.06]">
      <div class="flex items-center gap-2">
        <FileSpreadsheet class="h-4 w-4 text-[#0a84ff]" />
        <span class="font-semibold text-white text-xs">
          {{ t("research_desk.reports_title") }}
        </span>
        <span class="text-xs text-neutral-400">
          · {{ reports.length }} {{ t("research_desk.on_file") }}
        </span>
      </div>

      <!-- Generate Report Button matching other pages -->
      <button
        type="button"
        class="btn-filled btn-sm focus-ring inline-flex items-center gap-1.5"
        :title="`${t('memo.generate_report')} (⌘N)`"
        @click="emit('open-customizer')"
      >
        <AiMark class="h-3.5 w-3.5 shrink-0" />
        <span>{{ t("memo.generate_report") }}</span>
      </button>
    </div>

    <!-- Active pipelines banner if running -->
    <div
      v-if="pipelines.length > 0"
      class="mt-3 rounded-lg bg-blue-500/10 border border-blue-500/20 p-2.5 flex items-center justify-between text-xs"
    >
      <div class="flex items-center gap-2 text-blue-400 font-medium">
        <Sparkles class="h-3.5 w-3.5 animate-pulse" />
        <span>{{ t("research_desk.active_pipelines") }} ({{ pipelines.length }})</span>
      </div>
      <span class="text-xs text-blue-300">
        {{ pipelines[0].stage || pipelines[0].status || "Running" }}
      </span>
    </div>

    <!-- Reports list (MacResearchDeskView.swift:377-410) -->
    <div class="mt-3 space-y-1.5">
      <div
        v-for="rep in sortedReports"
        :key="rep.id"
        class="group flex items-center justify-between gap-3 rounded-lg bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.04] px-3 py-2 transition-colors cursor-pointer"
        @click="emit('open-memo', rep)"
      >
        <div class="flex items-center gap-2.5 min-w-0">
          <span
            class="rounded px-1.5 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider"
            :class="
              rep.language === 'zh'
                ? 'bg-purple-500/20 text-purple-400'
                : 'bg-blue-500/20 text-blue-400'
            "
          >
            {{ rep.language || 'EN' }}
          </span>

          <div class="min-w-0">
            <div class="truncate text-xs font-medium text-white group-hover:text-blue-400 transition-colors">
              {{ rep.title || rep.displayTitle || rep.id }}
            </div>
            <div class="truncate text-[11px] text-neutral-400 mt-0.5 font-mono">
              {{ t("research_desk.updated_at") }} {{ formatIsoDate(rep.created_at || rep.date) }}
            </div>
          </div>
        </div>

        <div class="flex items-center gap-1 text-xs text-blue-400 font-medium shrink-0">
          <span>{{ t("research_desk.read_memo") }}</span>
          <ChevronRight class="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
        </div>
      </div>

      <!-- Empty state matching MacEmptyState (Swift: lines 390-405) -->
      <div
        v-if="reports.length === 0 && pipelines.length === 0"
        class="rounded-lg border border-dashed border-white/10 p-6 text-center"
      >
        <p class="text-xs text-neutral-400 mb-2.5">
          {{ t("research_desk.no_reports") }}
        </p>
        <button
          type="button"
          class="btn-filled btn-sm focus-ring mt-3 inline-flex items-center gap-1.5"
          :title="`${t('memo.generate_report')} (⌘N)`"
          @click="emit('open-customizer')"
        >
          <AiMark class="h-3.5 w-3.5 shrink-0" />
          <span>{{ t("memo.generate_report") }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
