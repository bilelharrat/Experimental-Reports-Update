<script setup>
import { computed, inject, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  AlertCircle,
  Building2,
  Check,
  ChevronDown,
  Cpu,
  Database,
  FileText,
  Loader2,
  Search,
  Target,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import AiMark from "./AiMark.vue";
import Monogram from "./Monogram.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  initialCompanyId: { type: String, default: null },
});

const emit = defineEmits(["close", "created"]);
const router = useRouter();
const t = useT();

// Available companies from App.vue
const workspaceCompanies = inject("workspaceCompanies", ref([]));

// Target Company
const selectedCompanyId = ref(props.initialCompanyId || "");
const companySearch = ref("");
const companyPickerOpen = ref(false);

// Active Tab
const activeTab = ref("blueprint");
const tabs = computed(() => [
  { id: "blueprint", label: t("customizer.tab_blueprint"), icon: FileText },
  { id: "engine", label: t("customizer.tab_engine"), icon: Cpu },
  { id: "directives", label: t("customizer.tab_directives"), icon: Target },
  { id: "evidence", label: t("customizer.tab_evidence"), icon: Database },
]);

// Submission state
const generating = ref(false);
const error = ref(null);

watch(
  () => props.initialCompanyId,
  (newId) => {
    if (newId) selectedCompanyId.value = newId;
  },
  { immediate: true },
);

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && !selectedCompanyId.value && workspaceCompanies.value.length > 0) {
      selectedCompanyId.value = props.initialCompanyId || workspaceCompanies.value[0]?.id || "";
    }
    if (isOpen) {
      error.value = null;
      generating.value = false;
    }
  },
);

const currentCompany = computed(() => {
  return (
    workspaceCompanies.value.find((c) => c.id === selectedCompanyId.value) ||
    workspaceCompanies.value[0] ||
    null
  );
});

const filteredCompanies = computed(() => {
  const q = companySearch.value.trim().toLowerCase();
  if (!q) return workspaceCompanies.value;
  return workspaceCompanies.value.filter(
    (c) =>
      String(c.name || "").toLowerCase().includes(q) ||
      String(c.ticker || "").toLowerCase().includes(q) ||
      String(c.id || "").toLowerCase().includes(q),
  );
});

// Tab 1: Blueprint Options
const archetypes = [
  {
    id: "auto",
    reportType: "memo_late_stage",
    title: "Auto Full IC",
    badge: "Recommended",
    desc: "Stage-calibrated institutional memorandum synthesized across all analysis pipelines.",
  },
  {
    id: "investment_memo_late_stage",
    reportType: "investment_memo_late_stage",
    title: "Late-Stage IC",
    badge: "Institutional",
    desc: "Growth & late-stage institutional thesis, unit economics, and exit roadmap.",
  },
  {
    id: "buffett_memo",
    reportType: "buffett_memo",
    title: "Buffett Fundamental",
    badge: "Value Moat",
    desc: "Margin of safety, durable moats, cash return, and circle of competence.",
  },
  {
    id: "deep_dive",
    reportType: "deep_dive",
    title: "Financial Audit",
    badge: "Forensic",
    desc: "Forensic balance sheet, quality of earnings, and cash flow bridges.",
  },
  {
    id: "market_analysis",
    reportType: "market_analysis",
    title: "Market Analysis",
    badge: "Industry",
    desc: "TAM/SAM, competitive matrix, pricing power, and headwind sensitivity.",
  },
  {
    id: "background",
    reportType: "background",
    title: "Background Dossier",
    badge: "Diligence",
    desc: "Management track record, cap table evolution, and regulatory scrutiny.",
  },
];
const selectedArchetype = ref("auto");

const audiences = [
  { id: "internal", title: "Internal IC", desc: "Direct, unvarnished analytical rigor for investment partners" },
  { id: "gp", title: "General Partner", desc: "High-conviction executive summary and strategic dilemmas" },
  { id: "lp", title: "LP Advisory", desc: "Institutional LP perspective, portfolio fit, risk-adjusted returns" },
  { id: "diligence", title: "Diligence Lead", desc: "Deep forensic focus on claims, data integrity, and verification" },
];
const selectedAudience = ref("internal");

const reportModes = [
  { id: "full", title: "Full Institutional IC", desc: "10–15 pages of deep forensic analysis and supporting evidence" },
  { id: "compact", title: "Executive Brief", desc: "3–5 page partner-level investment synthesis" },
];
const selectedReportMode = ref("full");

const languages = [
  { id: "en", label: "English", desc: "Institutional global English" },
  { id: "zh", label: "中文", desc: "Mandarin translation & localization" },
  { id: "dual", label: "Bilingual (EN + ZH)", desc: "Synchronized dual-language outputs" },
];
const selectedLanguage = ref("en");

// Tab 2: Engine & Quality Options
const generationModes = [
  {
    id: "studio_review",
    title: "Interactive Studio Review",
    badge: "Recommended",
    desc: "Pauses after Phase 2 (Research & Dilemma formulation) so analysts can curate thesis spine cards and adjust risk framing before synthesizing the final memo.",
  },
  {
    id: "one_click",
    title: "One-Click Autonomous",
    badge: "Direct Run",
    desc: "Runs start-to-finish without stopping. Best for quick exploratory reads or overnight batches.",
  },
];
const selectedGenerationMode = ref("studio_review");

const qualities = [
  {
    id: "best",
    title: "Best Frontier",
    badge: "Frontier",
    desc: "Deep multi-pass reasoning, maximum evidence cross-examination, and frontier-grade synthesis.",
  },
  {
    id: "balanced",
    title: "Balanced Pipeline",
    badge: "Fast",
    desc: "Optimal trade-off between turnaround speed and analytical thoroughness.",
  },
  {
    id: "economy",
    title: "Economy Draft",
    badge: "Light",
    desc: "Rapid reconnaissance run for initial screening and preliminary structuring.",
  },
];
const selectedQuality = ref("best");

// Tab 3: Directives & Focus Options
const directives = ref("");
const suggestionChips = [
  "Scrutinize pricing power against open-source threats",
  "Stress test international expansion cap table",
  "Analyze gross margin compression in downcycle",
  "Evaluate enterprise churn vs net dollar retention",
];

function applySuggestion(suggestion) {
  if (!directives.value.trim()) {
    directives.value = suggestion;
  } else if (!directives.value.includes(suggestion)) {
    directives.value += `\n• ${suggestion}`;
  }
}

const diligencePillars = [
  "Moat Durability",
  "Cap Table Dilution",
  "Big Tech Threat",
  "Unit Economics",
  "Churn & Cohorts",
  "Regulatory Moat",
  "Key-Man Risk",
  "Valuation Multiples",
];
const selectedPillars = ref(["Moat Durability", "Unit Economics"]);

function togglePillar(pillar) {
  if (selectedPillars.value.includes(pillar)) {
    selectedPillars.value = selectedPillars.value.filter((p) => p !== pillar);
  } else {
    selectedPillars.value.push(pillar);
  }
}

const sectorLenses = [
  { id: "b2b_saas", label: "Enterprise B2B SaaS" },
  { id: "deep_tech", label: "Deep Tech & AI Hardware" },
  { id: "consumer", label: "Consumer & Marketplaces" },
  { id: "fintech", label: "Fintech & Regulated Platforms" },
];
const selectedSectorLens = ref("b2b_saas");

// Tab 4: Evidence Sources
const evidenceSources = ref([
  { id: "filings", label: "Company SEC & Regulatory Filings", checked: true },
  { id: "decks", label: "Data Room Pitch Decks & PDFs", checked: true },
  { id: "transcripts", label: "Earnings Call Transcripts & Releases", checked: true },
  { id: "news", label: "External Research & Verified News Feed", checked: true },
]);

const activeArchetypeObj = computed(() => {
  return archetypes.find((a) => a.id === selectedArchetype.value) || archetypes[0];
});

async function launchReport() {
  if (!currentCompany.value?.id) {
    error.value = "Please select a target company.";
    return;
  }

  generating.value = true;
  error.value = null;

  try {
    const companyId = currentCompany.value.id;
    const reportTypeVal = activeArchetypeObj.value.reportType;

    if (selectedGenerationMode.value === "studio_review") {
      // Launch studio deep investigation
      await api.studioInvestigate({
        company_id: companyId,
        report_type: reportTypeVal,
      });

      emit("created");
      emit("close");

      // Navigate to memo studio for the company
      router.push({
        name: "research",
        params: { companyId },
        query: { tab: "memo", memoStage: "studio" },
      });
    } else {
      // Launch one-click autonomous report
      const rep = await api.generateReport({
        company_id: companyId,
        report_type: reportTypeVal,
        audience: selectedAudience.value,
        language: selectedLanguage.value === "zh" ? "zh" : "en",
        report_mode: selectedReportMode.value,
        quality: selectedQuality.value,
      });

      emit("created", rep);
      emit("close");

      // Navigate to the research page with the new report active
      router.push({
        name: "research",
        params: { companyId },
        query: { report: rep.id },
      });
    }
  } catch (err) {
    error.value = err?.message || "Failed to launch report generation.";
  } finally {
    generating.value = false;
  }
}
</script>

<template>
  <div v-if="open" class="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 md:p-8">
    <!-- Scrim backdrop -->
    <div
      class="sheet-scrim fixed inset-0 backdrop-blur-sm"
      @click="emit('close')"
    />

    <!-- Main Summit Glass Panel -->
    <div
      class="sheet-panel relative z-10 flex h-[92vh] w-[96vw] max-w-[1040px] flex-col overflow-hidden rounded-2xl bg-canvas shadow-2xl border border-hairline"
    >
      <!-- Hero Monogram Header -->
      <header class="flex shrink-0 items-center justify-between border-b border-subtle bg-surface px-5 py-3.5">
        <div class="flex items-center gap-3.5 min-w-0">
          <Monogram
            v-if="currentCompany"
            :company="currentCompany"
            :size="38"
            tinted
          />
          <div v-else class="flex h-[38px] w-[38px] items-center justify-center rounded-xl bg-accent/10 text-accent font-bold">
            <Building2 class="h-5 w-5" />
          </div>

          <div class="min-w-0">
            <!-- Company Title with Selector Dropdown -->
            <div class="flex items-center gap-2">
              <div class="relative">
                <button
                  type="button"
                  class="flex items-center gap-1.5 text-base font-semibold text-ink-primary hover:text-accent-ink transition-colors"
                  @click="companyPickerOpen = !companyPickerOpen"
                >
                  <span class="truncate max-w-[280px] sm:max-w-[400px]">
                    {{ currentCompany?.name || t("customizer.select_company") }}
                  </span>
                  <ChevronDown class="h-4 w-4 text-ink-muted" />
                </button>

                <!-- Floating Company Picker -->
                <div
                  v-if="companyPickerOpen"
                  class="absolute left-0 top-full mt-2 z-50 w-72 rounded-xl bg-surface p-2 shadow-card border border-subtle backdrop-blur-md"
                >
                  <div class="relative mb-2">
                    <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
                    <input
                      v-model="companySearch"
                      type="text"
                      :placeholder="t('customizer.search_company')"
                      class="field field-sm w-full !pl-8"
                      @click.stop
                    />
                  </div>
                  <div class="max-h-56 overflow-y-auto space-y-0.5">
                    <button
                      v-for="c in filteredCompanies"
                      :key="c.id"
                      type="button"
                      class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-muted transition-colors"
                      :class="{ 'bg-accent/10 text-accent-ink font-medium': c.id === currentCompany?.id }"
                      @click="selectedCompanyId = c.id; companyPickerOpen = false"
                    >
                      <Monogram :company="c" :size="20" tinted />
                      <span class="truncate flex-1">{{ c.name }}</span>
                      <span v-if="c.ticker" class="text-xs text-ink-muted uppercase">{{ c.ticker }}</span>
                    </button>
                  </div>
                </div>
              </div>

              <span
                v-if="currentCompany?.ticker"
                class="rounded-md border border-subtle bg-surface-muted px-2 py-0.5 text-xs font-mono font-semibold uppercase text-ink-secondary"
              >
                {{ currentCompany.ticker }}
              </span>

              <span
                v-if="currentCompany?.sector || currentCompany?.industry"
                class="hidden sm:inline-block rounded-md border border-subtle bg-surface-muted px-2 py-0.5 text-xs text-ink-muted truncate max-w-[140px]"
              >
                {{ currentCompany.sector || currentCompany.industry }}
              </span>
            </div>

            <!-- Blueprint Status Tagline -->
            <p class="text-xs text-ink-muted mt-0.5 truncate">
              {{ activeArchetypeObj.title }} · {{ selectedAudience }} · {{ selectedReportMode === 'full' ? '10-15p' : '3-5p' }} · {{ selectedGenerationMode === 'studio_review' ? 'Studio Paused' : 'Autonomous' }}
            </p>
          </div>
        </div>

        <!-- Close Button -->
        <button
          type="button"
          class="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink-primary transition-colors focus-ring"
          :aria-label="t('customizer.close')"
          @click="emit('close')"
        >
          <X class="h-5 w-5" />
        </button>
      </header>

      <!-- Glass Tab Navigation -->
      <nav class="flex shrink-0 gap-1 border-b border-subtle bg-surface/80 px-4 py-2 overflow-x-auto">
        <button
          v-for="tItem in tabs"
          :key="tItem.id"
          type="button"
          class="flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all focus-ring whitespace-nowrap"
          :class="[
            activeTab === tItem.id
              ? 'bg-accent text-white shadow-sm'
              : 'text-ink-secondary hover:bg-surface-muted hover:text-ink-primary',
          ]"
          @click="activeTab = tItem.id"
        >
          <component :is="tItem.icon" class="h-3.5 w-3.5" />
          <span>{{ tItem.label }}</span>
        </button>
      </nav>

      <!-- Tab Content Area -->
      <div class="flex-1 min-h-0 overflow-y-auto p-5 md:p-6 space-y-6">
        <!-- ================= TAB 1: BLUEPRINT & FRAMING ================= -->
        <div v-if="activeTab === 'blueprint'" class="space-y-6">
          <!-- Archetypes Grid -->
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="vogue-label">{{ t("customizer.archetype_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.archetype_desc") }}</span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <button
                v-for="arch in archetypes"
                :key="arch.id"
                type="button"
                class="flex flex-col text-left p-3.5 rounded-xl border transition-all text-sm focus-ring relative"
                :class="[
                  selectedArchetype === arch.id
                    ? 'border-accent bg-accent/5 ring-1 ring-accent'
                    : 'border-subtle bg-surface hover:border-strong',
                ]"
                @click="selectedArchetype = arch.id"
              >
                <div class="flex items-center justify-between w-full mb-1">
                  <span class="font-semibold text-ink-primary">{{ arch.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      selectedArchetype === arch.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ arch.badge }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted line-clamp-2 mt-0.5">{{ arch.desc }}</p>
              </button>
            </div>
          </div>

          <!-- Audience & Depth Split -->
          <div class="grid grid-cols-1 gap-6 md:grid-cols-2">
            <!-- Target Audience -->
            <div>
              <span class="vogue-label block mb-2.5">{{ t("customizer.audience_title") }}</span>
              <div class="space-y-2">
                <button
                  v-for="aud in audiences"
                  :key="aud.id"
                  type="button"
                  class="flex w-full items-start gap-3 p-3 rounded-xl border text-left text-sm transition-all focus-ring"
                  :class="[
                    selectedAudience === aud.id
                      ? 'border-accent bg-accent/5 ring-1 ring-accent'
                      : 'border-subtle bg-surface hover:border-strong',
                  ]"
                  @click="selectedAudience = aud.id"
                >
                  <div
                    class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border"
                    :class="[
                      selectedAudience === aud.id
                        ? 'border-accent bg-accent text-white'
                        : 'border-strong bg-surface',
                    ]"
                  >
                    <Check v-if="selectedAudience === aud.id" class="h-2.5 w-2.5 stroke-[3]" />
                  </div>
                  <div class="min-w-0">
                    <div class="font-medium text-ink-primary">{{ aud.title }}</div>
                    <div class="text-xs text-ink-muted">{{ aud.desc }}</div>
                  </div>
                </button>
              </div>
            </div>

            <!-- Depth and Language -->
            <div class="space-y-5">
              <!-- Report Depth -->
              <div>
                <span class="vogue-label block mb-2.5">{{ t("customizer.scope_title") }}</span>
                <div class="grid grid-cols-2 gap-2">
                  <button
                    v-for="mode in reportModes"
                    :key="mode.id"
                    type="button"
                    class="flex flex-col text-left p-3 rounded-xl border transition-all focus-ring"
                    :class="[
                      selectedReportMode === mode.id
                        ? 'border-accent bg-accent/5 ring-1 ring-accent'
                        : 'border-subtle bg-surface hover:border-strong',
                    ]"
                    @click="selectedReportMode = mode.id"
                  >
                    <span class="font-semibold text-xs text-ink-primary">{{ mode.title }}</span>
                    <span class="text-[11px] text-ink-muted mt-1">{{ mode.desc }}</span>
                  </button>
                </div>
              </div>

              <!-- Language Selection -->
              <div>
                <span class="vogue-label block mb-2">{{ t("customizer.language_title") }}</span>
                <div class="grid grid-cols-3 gap-2">
                  <button
                    v-for="lang in languages"
                    :key="lang.id"
                    type="button"
                    class="flex flex-col items-center justify-center p-2.5 rounded-xl border text-center transition-all focus-ring"
                    :class="[
                      selectedLanguage === lang.id
                        ? 'border-accent bg-accent/5 ring-1 ring-accent'
                        : 'border-subtle bg-surface hover:border-strong',
                    ]"
                    @click="selectedLanguage = lang.id"
                  >
                    <span class="text-xs font-semibold text-ink-primary">{{ lang.label }}</span>
                    <span class="text-[10px] text-ink-muted mt-0.5">{{ lang.desc }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ================= TAB 2: ENGINE & COMPUTE QUALITY ================= -->
        <div v-if="activeTab === 'engine'" class="space-y-6">
          <!-- Generation Workflow Mode -->
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="vogue-label">{{ t("customizer.workflow_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.workflow_desc") }}</span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                v-for="mode in generationModes"
                :key="mode.id"
                type="button"
                class="flex flex-col text-left p-4 rounded-xl border transition-all focus-ring"
                :class="[
                  selectedGenerationMode === mode.id
                    ? 'border-accent bg-accent/5 ring-1 ring-accent'
                    : 'border-subtle bg-surface hover:border-strong',
                ]"
                @click="selectedGenerationMode = mode.id"
              >
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-semibold text-sm text-ink-primary">{{ mode.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      selectedGenerationMode === mode.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ mode.badge }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted leading-relaxed">{{ mode.desc }}</p>
              </button>
            </div>
          </div>

          <!-- Compute Quality Tier -->
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="vogue-label">{{ t("customizer.quality_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.quality_desc") }}</span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <button
                v-for="q in qualities"
                :key="q.id"
                type="button"
                class="flex flex-col text-left p-3.5 rounded-xl border transition-all focus-ring"
                :class="[
                  selectedQuality === q.id
                    ? 'border-accent bg-accent/5 ring-1 ring-accent'
                    : 'border-subtle bg-surface hover:border-strong',
                ]"
                @click="selectedQuality = q.id"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-semibold text-xs text-ink-primary">{{ q.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      selectedQuality === q.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ q.badge }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted leading-relaxed">{{ q.desc }}</p>
              </button>
            </div>
          </div>
        </div>

        <!-- ================= TAB 3: DIRECTIVES & STRATEGIC FOCUS ================= -->
        <div v-if="activeTab === 'directives'" class="space-y-6">
          <!-- Freeform Analyst Steering Directives -->
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="vogue-label">{{ t("customizer.directives_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.directives_desc") }}</span>
            </div>
            <textarea
              v-model="directives"
              rows="4"
              :placeholder="t('customizer.directives_placeholder')"
              class="field w-full !text-sm !p-3 resize-none focus-ring"
            />
            <!-- Quick Suggestions -->
            <div class="mt-2.5 flex flex-wrap items-center gap-1.5">
              <span class="text-xs text-ink-muted mr-1">{{ t("customizer.suggestions") }}</span>
              <button
                v-for="sug in suggestionChips"
                :key="sug"
                type="button"
                class="rounded-full border border-subtle bg-surface px-2.5 py-1 text-xs text-ink-secondary hover:border-accent hover:text-accent-ink transition-colors"
                @click="applySuggestion(sug)"
              >
                + {{ sug }}
              </button>
            </div>
          </div>

          <!-- Diligence Focus Pillars -->
          <div>
            <div class="flex items-center justify-between mb-2">
              <span class="vogue-label">{{ t("customizer.pillars_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.pillars_desc") }}</span>
            </div>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="pillar in diligencePillars"
                :key="pillar"
                type="button"
                class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium border transition-all focus-ring"
                :class="[
                  selectedPillars.includes(pillar)
                    ? 'border-accent bg-accent text-white shadow-sm'
                    : 'border-subtle bg-surface text-ink-secondary hover:border-strong',
                ]"
                @click="togglePillar(pillar)"
              >
                <Check v-if="selectedPillars.includes(pillar)" class="h-3 w-3 stroke-[3]" />
                <span>{{ pillar }}</span>
              </button>
            </div>
          </div>

          <!-- Sector Diligence Lens -->
          <div>
            <span class="vogue-label block mb-2">{{ t("customizer.sector_lens_title") }}</span>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                v-for="lens in sectorLenses"
                :key="lens.id"
                type="button"
                class="p-2.5 rounded-xl border text-center text-xs font-medium transition-all focus-ring"
                :class="[
                  selectedSectorLens === lens.id
                    ? 'border-accent bg-accent/5 ring-1 ring-accent text-accent-ink font-semibold'
                    : 'border-subtle bg-surface text-ink-secondary hover:border-strong',
                ]"
                @click="selectedSectorLens = lens.id"
              >
                {{ lens.label }}
              </button>
            </div>
          </div>
        </div>

        <!-- ================= TAB 4: EVIDENCE SOURCES ================= -->
        <div v-if="activeTab === 'evidence'" class="space-y-4">
          <div class="flex items-center justify-between mb-2">
            <span class="vogue-label">{{ t("customizer.evidence_title") }}</span>
            <span class="text-xs text-ink-muted">{{ t("customizer.evidence_desc") }}</span>
          </div>

          <div class="space-y-2">
            <label
              v-for="src in evidenceSources"
              :key="src.id"
              class="flex items-center justify-between p-3.5 rounded-xl border border-subtle bg-surface hover:border-strong cursor-pointer transition-colors"
            >
              <div class="flex items-center gap-3">
                <input
                  v-model="src.checked"
                  type="checkbox"
                  class="rounded border-subtle text-accent focus:ring-accent h-4 w-4"
                />
                <span class="text-sm font-medium text-ink-primary">{{ src.label }}</span>
              </div>
              <span class="text-xs text-ink-muted">{{ t("customizer.available_in_dossier") }}</span>
            </label>
          </div>
        </div>
      </div>

      <!-- Error Banner -->
      <div
        v-if="error"
        class="flex items-center gap-2 border-t border-danger/20 bg-danger/10 px-5 py-2.5 text-xs text-danger"
      >
        <AlertCircle class="h-4 w-4 shrink-0" />
        <span class="flex-1 truncate">{{ error }}</span>
      </div>

      <!-- Bottom Glass Action Bar -->
      <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-subtle bg-surface px-5 py-3.5">
        <!-- Live Parameter Badges -->
        <div class="hidden sm:flex flex-wrap items-center gap-1.5 text-xs">
          <span class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium">
            {{ activeArchetypeObj.title }}
          </span>
          <span class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium">
            {{ selectedAudience }}
          </span>
          <span class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium">
            {{ selectedReportMode === 'full' ? 'Full IC' : 'Compact' }}
          </span>
          <span class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium">
            {{ selectedQuality }}
          </span>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center gap-2 ml-auto">
          <button
            type="button"
            class="btn-bordered btn-sm focus-ring"
            :disabled="generating"
            @click="emit('close')"
          >
            {{ t("customizer.cancel") }}
          </button>

          <button
            type="button"
            class="btn-filled btn-sm focus-ring inline-flex items-center gap-2"
            :disabled="generating || !currentCompany"
            @click="launchReport"
          >
            <Loader2 v-if="generating" class="h-4 w-4 animate-spin" />
            <AiMark v-else class="h-4 w-4 shrink-0" />
            <span>
              {{
                generating
                  ? t("customizer.initializing")
                  : selectedGenerationMode === "studio_review"
                    ? t("customizer.launch_studio")
                    : t("customizer.generate_memo")
              }}
            </span>
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>
