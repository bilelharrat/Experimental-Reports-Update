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
import EarningsFilingsCard from "./EarningsFilingsCard.vue";
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
import FactLedgerCard from "./FactLedgerCard.vue";
import ThesisTrackerCard from "./ThesisTrackerCard.vue";
import CompanyCommentsCard from "./CompanyCommentsCard.vue";
import UnifiedDocumentsView from "../UnifiedDocumentsView.vue";
import api from "../../api.js";
import { formatIsoDate } from "../../formatters.js";
import { toggleFollowCompany, trackedCompanyIds } from "../../state.js";
import { refreshActiveJobs } from "../../activeJobs.js";
import {
  reportCanOpen,
  reportIsHidden,
  reportIsRunning,
  reportTypeLabel,
} from "../../reportStatus.js";
import {
  DOSSIER_SECTIONS,
  SECTION_LABEL_KEYS,
  canonicalDossierQuery,
  queryText,
  sameQuery,
  sectionFromQuery,
} from "../../dossierSections.js";

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
// Both are undefined outside a router (some tests); the tab is local then.
const route = useRoute();
const router = useRouter();

const activeSection = ref("overview");
const showMoreMenu = ref(false);
const isDecisionModalOpen = ref(false);
const companyReports = ref([]);
// Follow is the sidebar's follow list (state.js), which mirrors to the
// server's tracking watchlist — the same list the Mac's Follow edits.
const isFollowed = computed(() => trackedCompanyIds.value.has(String(props.companyId)));
// Bumped after an upload, a delete or an Analyze run so the list reloads.
const documentsRefresh = ref(0);
const decisionsVersion = ref(0);
// What a link asked this desk to show: a file (a citation Warren made, a
// deck summary job's result) or a memo point (one Warren just edited).
// Held here because the URL drops the ask as soon as it is read.
const filesFocus = ref(null);
const memoFocus = ref(null);
let focusCount = 0;

const tabItems = computed(() =>
  DOSSIER_SECTIONS.map((id) => ({ id, label: t(SECTION_LABEL_KEYS[id]) })),
);

// The router's routes that render the Research Desk. Any other route is the
// desk on its way out (the view transition keeps it mounted a moment), and
// its URL is not the desk's to read or rewrite.
const DESK_ROUTES = new Set(["research", "research-desk", "research-desk-company"]);
let routeCompanyId = route?.params?.companyId;

// The URL picks the tab on every navigation, not only the first (see
// dossierSections.js): a link into this company — the toolbar's Add,
// Warren's citations, a job's View result — moves the tab of a desk that
// is already open.
function followRoute(firstVisit) {
  if (!DESK_ROUTES.has(route.name)) return;
  const query = route.query || {};
  const companyChanged = route.params?.companyId !== routeCompanyId;
  routeCompanyId = route.params?.companyId;
  // Another company keeps the tab, as the Mac's dossier does. Anything else
  // that names none (Back to the bare company URL) is Overview.
  const section =
    sectionFromQuery(query) || (companyChanged ? activeSection.value : "overview");
  activeSection.value = section;
  if (companyChanged) {
    filesFocus.value = null;
    memoFocus.value = null;
  }
  if (query.previewFile || query.file) {
    filesFocus.value = {
      key: ++focusCount,
      id: queryText(query.previewFile || query.file),
      page: queryText(query.previewPage),
      action: query.previewFile ? "preview" : "summary",
    };
  }
  if (query.memoSection || query.memoBullet) {
    memoFocus.value = {
      key: ++focusCount,
      section: queryText(query.memoSection),
      bullet: queryText(query.memoBullet),
    };
  }
  // A fresh desk loads both lists anyway.
  if (!firstVisit && query.files) documentsRefresh.value += 1;
  if (!firstVisit && query.report) loadCompanyReports();
  writeSection(section);
}

function writeSection(section) {
  if (!router || !DESK_ROUTES.has(route.name)) return;
  const query = canonicalDossierQuery(route.query, section);
  if (sameQuery(query, route.query)) return;
  // replace, as the Markets desk does: a tab is not a step for the back
  // button. By path, not name, so the /research/:id alias keeps its URL.
  router.replace({ path: route.path, query, hash: route.hash });
}

if (route) {
  watch(
    () => route.fullPath,
    (_path, previous) => followRoute(previous === undefined),
    { immediate: true },
  );
}

function selectSection(id) {
  filesFocus.value = null;
  memoFocus.value = null;
  activeSection.value = id;
  if (route) writeSection(id);
}

// DossierSection.shows(_:) — a card renders in its own sections and in All.
function shows(...sections) {
  return activeSection.value === "all" || sections.includes(activeSection.value);
}

// Listed on an exchange — a ticker or a public status, unless the record
// says private — the same rule as server/company_profile.py. A public name's
// Overview leads with earnings and filings, not a VC deal pipeline; the
// pipeline stays one tab away for anyone tracking it as a deal.
const isPublic = computed(() => {
  const status = String(props.company?.status || "").toLowerCase();
  if (status === "private") return false;
  return Boolean(String(props.company?.ticker || "").trim()) || status === "public";
});

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
    const res = await api.listCompanyReports(props.companyId);
    companyReports.value = Array.isArray(res) ? res : [];
  } catch {
    companyReports.value = [];
  }
}

watch(() => props.companyId, loadCompanyReports, { immediate: true });

function reportTitle(rep) {
  return `${reportTypeLabel(rep, t)} · ${formatIsoDate(rep.created_at)}`;
}

// Runs still working: not finished, not failed, not parked for review, and
// not a run someone cleared or a newer run replaced.
const runningReports = computed(() =>
  companyReports.value.filter((r) => reportIsRunning(r) && !reportIsHidden(r)),
);

const latestOpenableReport = computed(() => companyReports.value.find(reportCanOpen));

// Memo Studio and the decision sheet still read `title` and `can_open`;
// hand them the report's label and whether a document is on file.
const reportsForStudio = computed(() =>
  companyReports.value.map((rep) => ({
    ...rep,
    title: reportTitle(rep),
    can_open: reportCanOpen(rep),
  })),
);

// Synthesize from the report card starts the parked studio run's memo (a
// paid run; the card asks twice before it emits).
const synthesizingId = ref("");
const synthesizeError = ref("");

async function synthesizeReport(rep) {
  if (!rep?.id || synthesizingId.value) return;
  synthesizingId.value = rep.id;
  synthesizeError.value = "";
  try {
    await api.studioGenerate(rep.id);
    refreshActiveJobs();
    await loadCompanyReports();
  } catch {
    synthesizeError.value = t("research_desk.synthesize_failed");
  } finally {
    synthesizingId.value = "";
  }
}

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

function toggleFollow() {
  showMoreMenu.value = false;
  toggleFollowCompany(props.companyId);
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
          @click="selectSection('decisions')"
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

    <MacTabBar
      :model-value="activeSection"
      :items="tabItems"
      @update:model-value="selectSection"
    />

    <!-- Card stack in the Mac body order, one guard per card -->
    <template v-if="shows('overview')">
      <UnifiedProfileCard :company-id="companyId" :company="company" />
      <SignalScoreCard :company-id="companyId" />
    </template>

    <EarningsFilingsCard
      v-if="isPublic && shows('overview')"
      :key="`earnings-${companyId}`"
      :company-id="companyId"
    />

    <DealPipelineCard
      v-if="isPublic ? shows('pipeline') : shows('pipeline', 'overview')"
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
      :focus="filesFocus"
      @open-report="openMemo"
      @files-changed="documentsRefresh += 1"
    />

    <FactLedgerCard v-if="shows('files')" :key="`ledger-${companyId}`" :company-id="companyId" />

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
          {{ reportTitle(rep) }}
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
        :synthesizing-id="synthesizingId"
        :synthesize-error="synthesizeError"
        @open-memo="openMemo"
        @open-customizer="handleCustomReport"
        @synthesize="synthesizeReport"
      />
      <MemoStudioEditor
        :company-id="companyId"
        :is-public="isPublic"
        :generate-available="true"
        :reports="reportsForStudio"
        :focus="memoFocus"
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
      :reports="reportsForStudio"
      @close="isDecisionModalOpen = false"
      @saved="decisionsVersion += 1"
    />
  </div>
</template>
