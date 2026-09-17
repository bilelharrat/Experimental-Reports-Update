<script setup>
// Web twin of CompanyDossierView in MacResearchDeskView.swift: header with
// monogram, title, stage pill and actions; the underline tab bar; then the
// card stack in the exact Mac body order, gated by the same shows() logic.
import { ref, computed, inject, onMounted, onUnmounted, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useT } from "../../i18n.js";
import {
  BadgeCheck,
  Columns2,
  CircleEllipsis,
  MessageSquare,
  Star,
  Globe,
  Compass,
  RefreshCw,
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
import UnifiedDocumentsView from "../UnifiedDocumentsView.vue";
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

const emit = defineEmits(["open-copilot", "stage-updated"]);

const t = useT();
const route = useRoute();
const router = useRouter();

// Web twin of the bsh.launchDossierSection launch arg: ?section= picks the
// tab, and the Mac's webCompanyMemoURL deep link (?tab=memo) lands on memos.
const SECTIONS = ["overview", "memos", "files", "decisions", "team", "pipeline", "capTable", "comps", "ratios", "all"];
function initialSection() {
  // The desk renders outside a router in tests, so read the query defensively.
  const query = route?.query ?? {};
  const q = String(query.section || "");
  if (SECTIONS.includes(q)) return q;
  if (query.tab === "memo") return "memos";
  return "overview";
}

const activeSection = ref(initialSection());
const showMoreMenu = ref(false);
const isDecisionModalOpen = ref(false);
const isFollowed = ref(false);
const companyReports = ref([]);
// Bumped after an upload, a delete or an Analyze run so the list reloads.
const documentsRefresh = ref(0);
const decisionsVersion = ref(0);

const tabItems = computed(() => [
  { id: "overview", label: t("research_desk.section_overview") },
  { id: "memos", label: t("research_desk.section_memo_studio") },
  { id: "files", label: t("research_desk.section_files") },
  { id: "decisions", label: t("research_desk.section_decisions") },
  { id: "team", label: t("research_desk.section_team") },
  { id: "pipeline", label: t("research_desk.section_pipeline") },
  { id: "capTable", label: t("research_desk.section_cap_table") },
  { id: "comps", label: t("research_desk.section_comps") },
  { id: "ratios", label: t("research_desk.section_ratios") },
  { id: "all", label: t("research_desk.section_all") },
]);

// DossierSection.shows(_:) — a card renders in its own sections and in All.
function shows(...sections) {
  return activeSection.value === "all" || sections.includes(activeSection.value);
}

// headerLine: ticker · sector-or-industry · status capitalized.
const headerSubtitle = computed(() => {
  const parts = [];
  if (props.company?.ticker) parts.push(String(props.company.ticker).toUpperCase());
  if (props.company?.sector) parts.push(props.company.sector);
  else if (props.company?.industry) parts.push(props.company.industry);
  const status = props.company?.status;
  if (status) parts.push(status.charAt(0).toUpperCase() + status.slice(1));
  return parts.join(" · ") || props.company?.subtitle || "";
});

const stagePill = computed(() => props.company?.deal_stage || "");

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

function isComplete(rep) {
  return rep.status === "complete";
}

function isFailed(rep) {
  return rep.status === "failed" || rep.status === "error";
}

function canOpen(rep) {
  return isComplete(rep) || rep.can_open === true;
}

const runningReports = computed(() =>
  companyReports.value.filter((r) => !isComplete(r) && !isFailed(r)),
);

const latestOpenableReport = computed(() => companyReports.value.find(canOpen));

function handleCustomReport() {
  openReportCustomizer(props.companyId);
}

function openMemo(rep) {
  router.push({ name: "reports", query: { id: rep.id, company: props.companyId } });
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
  <!-- dsPage: 20pt padding, 1180pt content column, 20pt section rhythm -->
  <div class="mx-auto flex w-full max-w-[1180px] flex-col gap-5 p-5">
    <!-- Header (MacResearchDeskView.swift dossier header) -->
    <div class="flex flex-wrap items-center gap-3.5 pb-1">
      <MacMonogram
        :company="company"
        :name="company?.name || companyId"
        :ticker="company?.ticker"
        :size="48"
      />

      <div class="flex min-w-0 flex-col justify-center gap-1">
        <div class="flex items-center gap-2.5">
          <h1 class="mac-t-title truncate">
            {{ company?.name || companyId }}
          </h1>

          <span v-if="stagePill" class="mac-status-pill shrink-0">{{ stagePill }}</span>

          <Star
            v-if="isFollowed"
            class="h-3 w-3 shrink-0"
            :style="{ color: 'var(--mac-yellow)', fill: 'var(--mac-yellow)' }"
            :title="t('research_desk.follow')"
          />
        </div>

        <p class="mac-t-body mac-c-secondary truncate">
          {{ headerSubtitle }}
        </p>
      </div>

      <div class="min-w-3 flex-1" />

      <!-- Action buttons -->
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="mac-btn mac-btn--prominent"
          :title="`${t('memo.generate_report')} (⌘N)`"
          @click="handleCustomReport"
        >
          <AiMark class="h-3.5 w-3.5 shrink-0" />
          <span>{{ t("memo.generate_report") }}</span>
        </button>

        <button
          type="button"
          class="mac-btn"
          :title="t('research_desk.decision_tooltip')"
          @click="isDecisionModalOpen = true"
        >
          <BadgeCheck class="h-3.5 w-3.5" />
          <span>{{ t("research_desk.decision_btn") }}</span>
        </button>

        <button
          v-if="latestOpenableReport"
          type="button"
          class="mac-btn"
          :title="t('research_desk.ic_review_tooltip')"
          @click="activeSection = 'decisions'"
        >
          <Columns2 class="h-3.5 w-3.5" />
          <span>{{ t("research_desk.ic_review_btn") }}</span>
        </button>

        <!-- Menu { … } label: ellipsis.circle -->
        <div class="relative">
          <button
            type="button"
            class="mac-btn"
            :title="t('research_desk.more_actions')"
            @click="showMoreMenu = !showMoreMenu"
          >
            <CircleEllipsis class="h-[15px] w-[15px]" />
          </button>

          <div v-if="showMoreMenu" class="fixed inset-0 z-40" @click="showMoreMenu = false" />
          <div
            v-if="showMoreMenu"
            class="mac-menu absolute right-0 z-50 mt-1 w-56"
            @click="showMoreMenu = false"
          >
            <button type="button" class="mac-menu-item" @click="toggleFollow">
              <Star
                class="mac-menu-icon h-3.5 w-3.5"
                :style="isFollowed ? { color: 'var(--mac-yellow)', fill: 'var(--mac-yellow)' } : {}"
              />
              <span>{{ isFollowed ? t("research_desk.unfollow") : t("research_desk.follow") }}</span>
            </button>

            <RouterLink
              :to="{ name: 'research', params: { companyId } }"
              class="mac-menu-item"
            >
              <Globe class="mac-menu-icon h-3.5 w-3.5" />
              <span>{{ t("research_desk.open_browser") }}</span>
            </RouterLink>

            <a
              v-if="company?.web_url || company?.website"
              :href="company.web_url || company.website"
              target="_blank"
              rel="noopener noreferrer"
              class="mac-menu-item"
            >
              <Compass class="mac-menu-icon h-3.5 w-3.5" />
              <span>{{ t("research_desk.open_web") }}</span>
            </a>

            <div class="mac-menu-sep" />

            <button type="button" class="mac-menu-item" @click="handleAskWarren">
              <MessageSquare class="mac-menu-icon h-3.5 w-3.5" />
              <span>{{ t("research_desk.ask_warren") }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <MacTabBar v-model="activeSection" :items="tabItems" />

    <!-- Card stack in the Mac body order, one guard per card -->
    <template v-if="shows('overview')">
      <UnifiedProfileCard :company-id="companyId" :company="company" />
      <SignalScoreCard :company-id="companyId" />
    </template>

    <DealPipelineCard
      v-if="shows('pipeline', 'overview')"
      :company-id="companyId"
      :company="company"
      @stage-updated="emit('stage-updated', $event)"
    />

    <CompsRailCard v-if="shows('comps')" :key="`comps-${companyId}`" :company-id="companyId" :company="company" />

    <CapTableCard v-if="shows('capTable')" :key="`cap-${companyId}`" :company-id="companyId" :company="company" />

    <!-- Files: uploads, folders and their analyses. These land in the
         company's research folder, which is the same folder every Phase-2
         memo pass reads, so anything uploaded here feeds the next report. -->
    <UnifiedDocumentsView
      v-if="shows('files')"
      :company-id="companyId"
      :refresh-key="documentsRefresh"
      @open-report="openMemo"
      @files-changed="documentsRefresh += 1"
    />

    <FounderRadarCard v-if="shows('team')" :company-id="companyId" :company="company" />

    <VCRatiosCard v-if="shows('ratios')" :key="`ratios-${companyId}`" :company-id="companyId" :company="company" />

    <!-- Active Analysis Pipelines (runs in progress) -->
    <div
      v-if="shows('memos', 'overview') && runningReports.length"
      class="flex flex-col gap-2.5 rounded-[10px] p-4"
      style="background: color-mix(in srgb, var(--mac-secondary) 5%, transparent)"
    >
      <div class="mac-t-headline-sys flex items-center gap-2">
        <RefreshCw class="mac-c-accent h-3.5 w-3.5" />
        <span>{{ t("research_desk.active_pipelines") }}</span>
      </div>
      <div
        v-for="rep in runningReports"
        :key="rep.id"
        class="flex items-center gap-2.5 rounded-md p-2.5"
        style="background: color-mix(in srgb, var(--mac-orange) 8%, transparent)"
      >
        <span class="mac-spinner" />
        <span class="mac-t-subheadline truncate" style="font-weight: 500">
          {{ rep.title || rep.id }}
        </span>
        <span class="flex-1" />
        <span class="mac-t-caption10 mac-mono mac-c-secondary shrink-0">
          {{ rep.stage || t("research_desk.processing") }}
        </span>
      </div>
    </div>

    <template v-if="shows('memos', 'overview')">
      <ReportsMemosCard
        :company-id="companyId"
        :company="company"
        :reports="companyReports"
        @open-memo="openMemo"
        @open-customizer="handleCustomReport"
      />
      <MemoStudioEditor
        :company-id="companyId"
        :generate-available="true"
        :reports="companyReports"
        @generate="handleCustomReport"
        @synthesized="loadCompanyReports"
      />
    </template>

    <DecisionsCard
      v-if="shows('decisions', 'overview')"
      :company-id="companyId"
      :company="company"
      :reload-token="decisionsVersion"
    />

    <template v-if="shows('decisions')">
      <ICPrepCard :company-id="companyId" :company="company" />
      <ICRoomCard :key="`ic-${companyId}`" :company-id="companyId" :company="company" />
      <NumberLintCard :company-id="companyId" />
      <ThesisTrackerCard :company-id="companyId" />
      <CompanyCommentsCard :key="`comments-${companyId}`" :company-id="companyId" :company="company" />
    </template>

    <!-- Record Decision Modal (⌘D) -->
    <RecordDecisionModal
      :is-open="isDecisionModalOpen"
      :company="company"
      :reports="companyReports"
      @close="isDecisionModalOpen = false"
      @saved="decisionsVersion += 1"
    />
  </div>
</template>
