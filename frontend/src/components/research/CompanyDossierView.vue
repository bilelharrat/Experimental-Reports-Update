<script setup>
import { ref, computed, inject, onMounted, onUnmounted, watch } from "vue";
import { useT } from "../../i18n.js";
import {
  ShieldCheck,
  FileSpreadsheet,
  MoreHorizontal,
  ExternalLink,
  MessageSquare,
  Star,
  Globe,
} from "lucide-vue-next";
import AiMark from "../AiMark.vue";
import MacMonogram from "./MacMonogram.vue";
import MacTabBar from "./MacTabBar.vue";
import UnifiedProfileCard from "./UnifiedProfileCard.vue";
import SignalScoreCard from "./SignalScoreCard.vue";
import DealPipelineCard from "./DealPipelineCard.vue";
import FounderRadarCard from "./FounderRadarCard.vue";
import CapTableCard from "./CapTableCard.vue";
import CompsRailCard from "./CompsRailCard.vue";
import VCRatiosCard from "./VCRatiosCard.vue";
import DecisionsCard from "./DecisionsCard.vue";
import ReportsMemosCard from "./ReportsMemosCard.vue";
import RecordDecisionModal from "./RecordDecisionModal.vue";
import MemoStudioEditor from "../MemoStudioEditor.vue";
import ICPrepCard from "./ICPrepCard.vue";
import ICRoomCard from "./ICRoomCard.vue";
import NumberLintCard from "./NumberLintCard.vue";
import ThesisTrackerCard from "./ThesisTrackerCard.vue";
import CompanyCommentsCard from "./CompanyCommentsCard.vue";
import api from "../../api.js";

const openReportCustomizer = inject("openReportCustomizer", () => {});

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(["open-copilot", "stage-updated", "open-memo"]);

const t = useT();

const activeSection = ref("overview");
const showMoreMenu = ref(false);
const isDecisionModalOpen = ref(false);
const isFollowed = ref(false);
const companyReports = ref([]);

const tabItems = computed(() => [
  { id: "overview", label: t("research_desk.section_overview") },
  { id: "memos", label: t("research_desk.section_memo_studio") },
  { id: "decisions", label: t("research_desk.section_decisions") },
  { id: "team", label: t("research_desk.section_team") },
  { id: "pipeline", label: t("research_desk.section_pipeline") },
  { id: "capTable", label: t("research_desk.section_cap_table") },
  { id: "comps", label: t("research_desk.section_comps") },
  { id: "ratios", label: t("research_desk.section_ratios") },
  { id: "all", label: t("research_desk.section_all") },
]);

// Match Swift MacResearchDeskView.swift:437: secondaryLine
const headerSubtitle = computed(() => {
  const parts = [];
  if (props.company?.ticker) parts.push(props.company.ticker.toUpperCase());
  const isPub = Boolean(props.company?.ticker || props.company?.is_public);
  parts.push(isPub ? t("research_desk.public_tag") : (props.company?.sector || t("research_desk.private_tag")));
  return parts.join(" · ");
});

async function loadCompanyReports() {
  if (!props.companyId) return;
  try {
    const res = await api.getReports({ company_id: props.companyId });
    companyReports.value = Array.isArray(res) ? res : (res.reports || []);
  } catch {
    companyReports.value = [];
  }
}

watch(() => props.companyId, loadCompanyReports, { immediate: true });

const latestOpenableReport = computed(() => {
  return companyReports.value.find((r) => r.status === "complete" || r.can_open || r.isComplete);
});

function handleCustomReport() {
  openReportCustomizer(props.companyId);
}

function handleAskWarren() {
  showMoreMenu.value = false;
  emit("open-copilot", {
    companyId: props.companyId,
    prompt: `Give me the one-paragraph state of play and core investment thesis for ${props.company?.name || props.companyId}.`,
  });
}

async function checkFollowState() {
  try {
    const list = await api.getFollowedCompanies();
    if (Array.isArray(list)) {
      isFollowed.value = list.some((item) => (typeof item === "string" ? item === props.companyId : item?.id === props.companyId));
    }
  } catch {
    // ignore
  }
}

async function toggleFollow() {
  showMoreMenu.value = false;
  try {
    if (isFollowed.value) {
      await api.unfollowCompany(props.companyId);
      isFollowed.value = false;
    } else {
      await api.followCompany(props.companyId);
      isFollowed.value = true;
    }
  } catch {
    // ignore
  }
}

function onKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "d") {
    e.preventDefault();
    isDecisionModalOpen.value = true;
  } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "n") {
    e.preventDefault();
    handleCustomReport();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  checkFollowState();
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="flex flex-col gap-4 max-w-[1180px] mx-auto w-full text-ink-primary">
    <!-- Unboxed macOS Page Header (MacResearchDeskView.swift:233-289) -->
    <div class="flex flex-wrap items-center justify-between gap-4 pb-1">
      <!-- Left: MacMonogram + Title Block -->
      <div class="flex items-center gap-3.5 min-w-0">
        <MacMonogram
          :company="company"
          :name="company?.name || companyId"
          :ticker="company?.ticker"
          :size="48"
        />

        <div class="flex flex-col min-w-0 justify-center">
          <div class="flex items-center gap-2">
            <h1 class="text-[22px] font-bold tracking-tight text-ink-primary truncate">
              {{ company?.name || companyId }}
            </h1>

            <!-- Stage pill (MacStatusPill) -->
            <span class="rounded-full bg-blue-500/20 px-2.5 py-0.5 text-xs font-semibold text-blue-400 shrink-0">
              {{ company?.deal_stage || "Sourced" }}
            </span>

            <Star
              v-if="isFollowed"
              class="h-3.5 w-3.5 fill-amber-400 text-amber-400 shrink-0"
            />
          </div>

          <p class="text-[13px] text-ink-muted mt-0.5 truncate leading-tight">
            {{ headerSubtitle }}
          </p>
        </div>
      </div>

      <!-- Right: Action Buttons (MacResearchDeskView.swift:263-288) -->
      <div class="flex items-center gap-2">
        <!-- Generate Report Button (⌘N) matching other pages -->
        <button
          type="button"
          class="btn-filled btn-sm focus-ring inline-flex items-center gap-1.5"
          :title="`${t('memo.generate_report')} (⌘N)`"
          @click="handleCustomReport"
        >
          <AiMark class="h-3.5 w-3.5 shrink-0" />
          <span>{{ t("memo.generate_report") }}</span>
        </button>

        <!-- Decision Button (⌘D) (.bordered) -->
        <button
          type="button"
          class="btn-bordered btn-sm focus-ring inline-flex items-center gap-1.5"
          :title="t('research_desk.decision_tooltip')"
          @click="isDecisionModalOpen = true"
        >
          <ShieldCheck class="h-3.5 w-3.5 text-emerald-400" />
          <span>{{ t("research_desk.decision_btn") }}</span>
        </button>

        <!-- IC Review Button (Shown ONLY if openable report exists, matching Swift line 280) -->
        <button
          v-if="latestOpenableReport"
          type="button"
          class="btn-bordered btn-sm focus-ring inline-flex items-center gap-1.5"
          :title="t('research_desk.ic_review_tooltip')"
          @click="activeSection = 'decisions'"
        >
          <FileSpreadsheet class="h-3.5 w-3.5 text-sky-400" />
          <span>{{ t("research_desk.ic_review_btn") }}</span>
        </button>

        <!-- Ellipsis More Menu (.ellipsis.circle) -->
        <div class="relative">
          <button
            type="button"
            class="flex h-[26px] w-[26px] items-center justify-center rounded-full border border-subtle bg-surface-muted text-ink-muted transition hover:bg-surface-hover hover:text-ink-primary focus-ring"
            :title="t('research_desk.more_actions')"
            @click="showMoreMenu = !showMoreMenu"
          >
            <MoreHorizontal class="h-3.5 w-3.5" />
          </button>

          <div
            v-if="showMoreMenu"
            class="absolute right-0 z-50 mt-1 w-56 rounded-xl border border-white/10 bg-[#242428] p-1.5 shadow-2xl backdrop-blur-2xl text-xs"
            @click="showMoreMenu = false"
          >
            <!-- Toggle Follow on Pipeline -->
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-white transition hover:bg-white/10"
              @click="toggleFollow"
            >
              <Star class="h-3.5 w-3.5" :class="isFollowed ? 'fill-amber-400 text-amber-400' : 'text-neutral-400'" />
              <span>{{ isFollowed ? t("research_desk.unfollow") : t("research_desk.follow") }}</span>
            </button>

            <!-- Open in Research Browser -->
            <RouterLink
              :to="{ name: 'research', params: { companyId } }"
              class="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-white transition hover:bg-white/10"
            >
              <Globe class="h-3.5 w-3.5 text-neutral-400" />
              <span>{{ t("research_desk.open_browser") }}</span>
            </RouterLink>

            <!-- Open on Web (if URL) -->
            <a
              v-if="company?.web_url || company?.website"
              :href="company.web_url || company.website"
              target="_blank"
              rel="noopener noreferrer"
              class="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-white transition hover:bg-white/10"
            >
              <ExternalLink class="h-3.5 w-3.5 text-neutral-400" />
              <span>{{ t("research_desk.open_web") }}</span>
            </a>

            <div class="my-1 border-t border-white/10" />

            <!-- Ask Warren -->
            <button
              type="button"
              class="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-white transition hover:bg-white/10"
              @click="handleAskWarren"
            >
              <MessageSquare class="h-3.5 w-3.5 text-neutral-400" />
              <span>{{ t("research_desk.ask_warren") }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Apple MacTabBar (Exact macOS System Tab Bar) -->
    <MacTabBar
      :items="tabItems"
      v-model="activeSection"
    />

    <!-- Tab Contents Container (Exact card sequence matching MacResearchDeskView.swift) -->
    <div class="space-y-3.5">
      <!-- Overview -->
      <template v-if="activeSection === 'overview'">
        <UnifiedProfileCard :company-id="companyId" :company="company" />
        <SignalScoreCard :company-id="companyId" />
        <DealPipelineCard :company-id="companyId" :company="company" @stage-updated="emit('stage-updated', $event)" />
        <ReportsMemosCard :company-id="companyId" :company="company" @open-memo="emit('open-memo', $event)" @open-customizer="handleCustomReport" />
        <MemoStudioEditor :company-id="companyId" :generate-available="true" @generate="handleCustomReport" />
        <DecisionsCard :company-id="companyId" :company="company" />
      </template>

      <!-- Memo Studio -->
      <template v-else-if="activeSection === 'memos'">
        <ReportsMemosCard :company-id="companyId" :company="company" @open-memo="emit('open-memo', $event)" @open-customizer="handleCustomReport" />
        <MemoStudioEditor :company-id="companyId" :generate-available="true" @generate="handleCustomReport" />
      </template>

      <!-- Decisions (Full IC Suite) -->
      <template v-else-if="activeSection === 'decisions'">
        <DecisionsCard :company-id="companyId" :company="company" />
        <ICPrepCard :company-id="companyId" :company="company" />
        <ICRoomCard :company-id="companyId" :company="company" />
        <NumberLintCard :company-id="companyId" />
        <ThesisTrackerCard :company-id="companyId" />
        <CompanyCommentsCard :company-id="companyId" />
      </template>

      <!-- Team -->
      <template v-else-if="activeSection === 'team'">
        <FounderRadarCard :company-id="companyId" :company="company" />
      </template>

      <!-- Pipeline -->
      <template v-else-if="activeSection === 'pipeline'">
        <DealPipelineCard :company-id="companyId" :company="company" @stage-updated="emit('stage-updated', $event)" />
      </template>

      <!-- Cap Table -->
      <template v-else-if="activeSection === 'capTable'">
        <CapTableCard :company-id="companyId" :company="company" />
      </template>

      <!-- Comps -->
      <template v-else-if="activeSection === 'comps'">
        <CompsRailCard :company-id="companyId" :company="company" />
      </template>

      <!-- Ratios -->
      <template v-else-if="activeSection === 'ratios'">
        <VCRatiosCard :company-id="companyId" :company="company" />
      </template>

      <!-- All: Stack all cards in complete order -->
      <template v-else-if="activeSection === 'all'">
        <UnifiedProfileCard :company-id="companyId" :company="company" />
        <SignalScoreCard :company-id="companyId" />
        <DealPipelineCard :company-id="companyId" :company="company" @stage-updated="emit('stage-updated', $event)" />
        <ReportsMemosCard :company-id="companyId" :company="company" @open-memo="emit('open-memo', $event)" @open-customizer="handleCustomReport" />
        <MemoStudioEditor :company-id="companyId" :generate-available="true" @generate="handleCustomReport" />
        <DecisionsCard :company-id="companyId" :company="company" />
        <ICPrepCard :company-id="companyId" :company="company" />
        <ICRoomCard :company-id="companyId" :company="company" />
        <NumberLintCard :company-id="companyId" />
        <ThesisTrackerCard :company-id="companyId" />
        <CompanyCommentsCard :company-id="companyId" />
        <FounderRadarCard :company-id="companyId" :company="company" />
        <CapTableCard :company-id="companyId" :company="company" />
        <CompsRailCard :company-id="companyId" :company="company" />
        <VCRatiosCard :company-id="companyId" :company="company" />
      </template>
    </div>

    <!-- Record Decision Modal (⌘D) -->
    <RecordDecisionModal
      :is-open="isDecisionModalOpen"
      :company="company"
      @close="isDecisionModalOpen = false"
      @saved="activeSection = 'decisions'"
    />
  </div>
</template>
