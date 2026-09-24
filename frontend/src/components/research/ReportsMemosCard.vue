<script setup>
// Web twin of the "Research Reports & Memos" card and MemoRowView in
// MacResearchDeskView.swift: doc icon, title with language/status chips,
// "Updated … · Audience" line, and the per-state action buttons. Rows read
// the real ReportSummary the way MacReport does (ResearchDeskModels.swift):
// the title is the report type, complete means a finished status, and a row
// opens when a document is on file.
import { computed } from "vue";
import { useT } from "../../i18n.js";
import { FileText, FileCog, Sparkles, BookOpen, Activity, Compass } from "lucide-vue-next";
import AiMark from "../AiMark.vue";
import { formatIsoDate } from "../../formatters.js";
import {
  reportCanOpen,
  reportIsComplete,
  reportIsDocless,
  reportIsFailed,
  reportIsHidden,
  reportState,
  reportStatusLabel,
  reportTypeLabel,
  reviewChip,
  useTwoStepArm,
  verdictChip,
} from "../../reportStatus.js";
import { appLanguage } from "../../state.js";

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
  // The report whose Synthesize the desk is starting, and why it failed.
  synthesizingId: {
    type: String,
    default: "",
  },
  synthesizeError: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["open-memo", "open-customizer", "synthesize"]);
const t = useT();

// Cleared failures and runs a newer run replaced stay off the desk, as they
// do on the Reports list.
const sortedReports = computed(() => {
  return [...props.reports]
    .filter((rep) => !reportIsHidden(rep))
    .sort((a, b) => {
      const da = new Date(a.created_at || a.date || 0).getTime();
      const db = new Date(b.created_at || b.date || 0).getTime();
      return db - da;
    });
});

const isComplete = reportIsComplete;
const isFailed = reportIsFailed;
const canOpen = reportCanOpen;

function isAwaitingStudio(rep) {
  return reportState(rep) === "cards_ready";
}

// StatusTag tone: complete → green, failed → red, a finished record with
// nothing to read → gray, everything else → orange.
function statusTone(rep) {
  if (reportIsDocless(rep)) return "var(--mac-gray)";
  if (reportState(rep) === "complete") return "var(--mac-green)";
  if (isFailed(rep)) return "var(--mac-red)";
  return "var(--mac-orange)";
}

function statusText(rep) {
  return reportIsDocless(rep) ? t("reports.status_no_document") : reportStatusLabel(rep, t);
}

// The memo's call and its review, tinted the way the Reports list tints them.
const MAC_TINTS = {
  success: "var(--mac-green)",
  notice: "var(--mac-orange)",
  teal: "var(--mac-teal)",
  purple: "var(--mac-purple)",
  info: "var(--mac-indigo)",
  warning: "var(--mac-orange)",
  danger: "var(--mac-red)",
  accent: "var(--mac-blue)",
  neutral: "var(--mac-gray)",
};

function macTint(tone) {
  return MAC_TINTS[tone] || MAC_TINTS.neutral;
}

function verdict(rep) {
  return verdictChip(rep, t, appLanguage.value);
}

function review(rep) {
  return reviewChip(rep, t, appLanguage.value);
}

function typeLabel(rep) {
  return reportTypeLabel(rep, t);
}

// The documents on file, as language chips (every memo run writes both).
function languages(rep) {
  return Object.keys(rep.download_urls || {}).filter((key) => key === "en" || key === "zh");
}

const AUDIENCE_KEYS = {
  Internal: "customizer.aud_internal_title",
  Partner: "customizer.aud_partner_title",
  LP: "customizer.aud_lp_title",
  Assistant: "customizer.aud_assistant_title",
};

function audienceLabel(rep) {
  const key = AUDIENCE_KEYS[rep.audience];
  return key ? t(key) : rep.audience || t("research_desk.internal_audience");
}

// Synthesize starts a paid run, so it asks twice: the first click arms it
// for four seconds, the second starts the memo.
const arm = useTwoStepArm();

function synthesizeLabel(rep) {
  if (props.synthesizingId === rep.id) return t("research_desk.synthesizing");
  if (arm.armed.value === rep.id) return t("research_desk.synthesize_confirm");
  return t("research_desk.synthesize_memo");
}

function requestSynthesize(rep) {
  if (props.synthesizingId) return;
  if (arm.trigger(rep.id)) emit("synthesize", rep);
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
        <span v-if="sortedReports.length" class="mac-t-caption mac-c-secondary">
          {{ t("research_desk.dossiers_on_file", { count: sortedReports.length }) }}
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
    <div v-if="sortedReports.length === 0" class="flex flex-col items-center gap-2 py-6">
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
        :data-report-id="rep.id"
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
            <span class="mac-t-body truncate" style="font-weight: 600" data-testid="memo-row-title">
              {{ typeLabel(rep) }}
            </span>

            <span
              v-for="lang in languages(rep)"
              :key="lang"
              class="mac-mono mac-c-secondary shrink-0 rounded-[3px] px-1 py-px text-[10px] uppercase"
              style="background: color-mix(in srgb, var(--mac-secondary) 12%, transparent)"
            >
              {{ lang }}
            </span>

            <span class="mac-status-tag shrink-0" :style="{ '--tint': statusTone(rep) }" data-testid="memo-row-status">
              {{ statusText(rep) }}
            </span>
          </div>

          <span class="mac-t-caption10 mac-mono mac-c-secondary truncate">
            {{ t("research_desk.updated_at") }} {{ formatIsoDate(rep.updated_at || rep.created_at || rep.date) }}
            · {{ audienceLabel(rep) }}
          </span>
          <span v-if="verdict(rep) || review(rep)" class="flex min-w-0 flex-wrap items-center gap-1">
            <span
              v-if="verdict(rep)"
              class="mac-status-tag shrink-0"
              :style="{ '--tint': macTint(verdict(rep).tone) }"
              :title="verdict(rep).title"
              data-testid="memo-row-verdict"
            >
              {{ verdict(rep).label }}
            </span>
            <span
              v-if="review(rep)"
              class="mac-status-tag shrink-0"
              :style="{ '--tint': macTint(review(rep).tone) }"
              :title="review(rep).title"
              data-testid="memo-row-review"
            >
              {{ review(rep).label }}
            </span>
          </span>
          <span
            v-if="synthesizeError && isAwaitingStudio(rep)"
            class="mac-t-caption10"
            style="color: var(--mac-red)"
            role="alert"
          >
            {{ synthesizeError }}
          </span>
        </div>

        <span class="min-w-1 flex-1" />

        <!-- Per-state action, then the open-on-web button -->
        <button
          v-if="isAwaitingStudio(rep)"
          type="button"
          class="mac-btn mac-btn--sm mac-btn--prominent mac-btn--tinted shrink-0"
          :style="{ '--tint': 'var(--mac-orange)' }"
          :title="t('memo.synthesize_help')"
          :disabled="Boolean(synthesizingId)"
          data-testid="memo-row-synthesize"
          @click="requestSynthesize(rep)"
        >
          <Sparkles class="h-3 w-3" />
          <span>{{ synthesizeLabel(rep) }}</span>
        </button>
        <button
          v-else-if="canOpen(rep)"
          type="button"
          class="mac-btn mac-btn--sm mac-btn--prominent shrink-0"
          data-testid="memo-row-read"
          @click="emit('open-memo', rep)"
        >
          <BookOpen class="h-3 w-3" />
          <span>{{ t("research_desk.read_memo") }}</span>
        </button>
        <button
          v-else-if="!isFailed(rep) && !isComplete(rep)"
          type="button"
          class="mac-btn mac-btn--sm shrink-0"
          data-testid="memo-row-follow"
          @click="emit('open-memo', rep)"
        >
          <Activity class="h-3 w-3" />
          <span>{{ t("research_desk.follow_run") }}</span>
        </button>

        <button
          type="button"
          class="mac-btn mac-btn--sm shrink-0"
          :title="t('research_desk.open_memo_web')"
          :aria-label="t('research_desk.open_memo_web')"
          @click="openMemoWeb(rep)"
        >
          <Compass class="h-3 w-3" />
        </button>
      </div>
    </div>
  </div>
</template>
