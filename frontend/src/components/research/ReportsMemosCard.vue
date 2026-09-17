<script setup>
// Web twin of the "Research Reports & Memos" card and MemoRowView in
// MacResearchDeskView.swift: doc icon, title with NEW/language/status chips,
// "Updated … · Audience" line, and the per-state action buttons.
import { computed } from "vue";
import { useT } from "../../i18n.js";
import { FileText, FileCog, Sparkles, BookOpen, Activity, Compass } from "lucide-vue-next";
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
});

const emit = defineEmits(["open-memo", "open-customizer", "synthesize"]);
const t = useT();

const sortedReports = computed(() => {
  return [...props.reports].sort((a, b) => {
    const da = new Date(a.created_at || a.date || 0).getTime();
    const db = new Date(b.created_at || b.date || 0).getTime();
    return db - da;
  });
});

function isComplete(rep) {
  return rep.status === "complete";
}

function isFailed(rep) {
  return rep.status === "failed" || rep.status === "error";
}

function canOpen(rep) {
  return isComplete(rep) || rep.can_open === true;
}

// StatusTag tone: complete → green, failed → red, everything else → orange.
function statusTone(rep) {
  if (isComplete(rep)) return "var(--mac-green)";
  if (isFailed(rep)) return "var(--mac-red)";
  return "var(--mac-orange)";
}

function statusText(rep) {
  return rep.status_label || rep.status || "";
}

function openMemoWeb(rep) {
  const url = `${window.location.origin}${import.meta.env.BASE_URL || "/"}`.replace(/\/$/, "")
    + `/reports?id=${encodeURIComponent(rep.id)}&company=${encodeURIComponent(props.companyId)}`;
  window.open(url, "_blank", "noopener");
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-3.5">
    <!-- MacCardHeader("Research Reports & Memos", …, doc.text.fill) + Generate -->
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><FileText class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.reports_title") }}</span>
        <span v-if="reports.length" class="mac-t-caption mac-c-secondary">
          {{ t("research_desk.dossiers_on_file", { count: reports.length }) }}
        </span>
      </div>
      <span class="min-w-2 flex-1" />
      <button
        type="button"
        class="mac-btn mac-btn--sm mac-btn--prominent"
        :title="`${t('memo.generate_report')} (⌘N)`"
        @click="emit('open-customizer')"
      >
        <AiMark class="h-[13px] w-[13px] shrink-0" />
        <span>{{ t("memo.generate_report") }}</span>
      </button>
    </div>

    <!-- Empty state -->
    <div v-if="reports.length === 0" class="flex flex-col items-center gap-2 py-6">
      <p class="mac-t-subhead mac-c-secondary">{{ t("research_desk.no_reports") }}</p>
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        @click="emit('open-customizer')"
      >
        <AiMark class="h-[13px] w-[13px] shrink-0" />
        <span>{{ t("memo.generate_report") }}</span>
      </button>
    </div>

    <!-- MemoRowView list -->
    <div v-else class="flex flex-col gap-2">
      <div
        v-for="rep in sortedReports"
        :key="rep.id"
        class="mac-tile flex items-center gap-3 p-2.5"
        style="border-radius: 10px"
      >
        <span class="flex w-8 shrink-0 justify-center">
          <component
            :is="isComplete(rep) ? FileText : FileCog"
            class="h-[17px] w-[17px]"
            :style="{ color: isComplete(rep) ? 'var(--mac-blue)' : 'var(--mac-orange)' }"
          />
        </span>

        <div class="flex min-w-0 flex-col gap-[3px]">
          <div class="flex min-w-0 items-center gap-2">
            <span class="mac-t-body truncate" style="font-weight: 600">
              {{ rep.title || rep.id }}
            </span>

            <span
              v-if="rep.is_new"
              class="shrink-0 rounded-full px-[5px] py-[1.5px] text-[10px] font-bold text-white"
              :style="{ background: 'var(--mac-accent)' }"
            >
              {{ t("research_desk.new_badge") }}
            </span>

            <span
              v-if="rep.language"
              class="mac-mono mac-c-secondary shrink-0 rounded-[3px] px-1 py-px text-[10px] uppercase"
              style="background: color-mix(in srgb, var(--mac-secondary) 12%, transparent)"
            >
              {{ rep.language }}
            </span>

            <span class="mac-status-tag shrink-0" :style="{ '--tint': statusTone(rep) }">
              {{ statusText(rep) }}
            </span>
          </div>

          <span class="mac-t-caption10 mac-mono mac-c-secondary truncate">
            {{ t("research_desk.updated_at") }} {{ formatIsoDate(rep.created_at || rep.date) }}
            · {{ rep.audience || t("research_desk.internal_audience") }}
          </span>
        </div>

        <span class="min-w-1 flex-1" />

        <!-- Per-state action, then the open-on-web button -->
        <button
          v-if="rep.status === 'awaiting_studio'"
          type="button"
          class="mac-btn mac-btn--sm mac-btn--prominent mac-btn--tinted shrink-0"
          :style="{ '--tint': 'var(--mac-orange)' }"
          :title="t('memo.synthesize_help')"
          @click="emit('synthesize', rep)"
        >
          <Sparkles class="h-3 w-3" />
          <span>{{ t("research_desk.synthesize_memo") }}</span>
        </button>
        <button
          v-else-if="canOpen(rep)"
          type="button"
          class="mac-btn mac-btn--sm mac-btn--prominent shrink-0"
          @click="emit('open-memo', rep)"
        >
          <BookOpen class="h-3 w-3" />
          <span>{{ t("research_desk.read_memo") }}</span>
        </button>
        <button
          v-else-if="!isFailed(rep)"
          type="button"
          class="mac-btn mac-btn--sm shrink-0"
          @click="emit('open-memo', rep)"
        >
          <Activity class="h-3 w-3" />
          <span>{{ t("research_desk.follow_run") }}</span>
        </button>

        <button
          type="button"
          class="mac-btn mac-btn--sm shrink-0"
          :title="t('research_desk.open_memo_web')"
          @click="openMemoWeb(rep)"
        >
          <Compass class="h-3 w-3" />
        </button>
      </div>
    </div>
  </div>
</template>
