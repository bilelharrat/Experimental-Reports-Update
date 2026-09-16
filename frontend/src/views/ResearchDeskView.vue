<script setup>
import { ref, computed, watch, onMounted, inject } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useT } from "../i18n.js";
import {
  Sparkles,
  Search,
  ChevronDown,
  X,
  FileText,
  Building2,
  ChevronRight,
} from "lucide-vue-next";
import MacMonogram from "../components/research/MacMonogram.vue";
import CompanyDossierView from "../components/research/CompanyDossierView.vue";
import PitchDeckIntakeModal from "../components/research/PitchDeckIntakeModal.vue";
import { api } from "../api.js";

const openReportCustomizer = inject("openReportCustomizer", () => {});

const props = defineProps({
  companies: {
    type: Array,
    default: () => [],
  },
  companyId: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["open-copilot", "reports-changed"]);

const route = useRoute();
const router = useRouter();
const t = useT();

const internalCompanies = ref([]);
const loadingCompanies = ref(false);

const searchText = ref("");
const selectedSector = ref("All");
const showOnlyModified = ref(false);
const mobileView = ref("directory"); // 'directory' | 'dossier'

// Pitch Deck Intake state
const showDeckModal = ref(false);
const droppedDeckFile = ref(null);
const fileInputRef = ref(null);
const isDeckDragTargeted = ref(false);

// Visited storage for modified diffs tracking
const VISITED_KEY = "bsh.visitedCompanies";
function loadVisited() {
  try {
    const raw = localStorage.getItem(VISITED_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}
const visitedCompanies = ref(loadVisited());

function markVisited(cid) {
  if (!cid) return;
  visitedCompanies.value.add(cid);
  try {
    localStorage.setItem(VISITED_KEY, JSON.stringify(Array.from(visitedCompanies.value)));
  } catch {
    // ignore
  }
}

async function loadCompaniesIfNeeded() {
  if (props.companies && props.companies.length > 0) return;
  loadingCompanies.value = true;
  try {
    const res = await api.listCompanies();
    internalCompanies.value = Array.isArray(res) ? res : (res?.companies || []);
  } catch {
    internalCompanies.value = [];
  } finally {
    loadingCompanies.value = false;
  }
}

onMounted(async () => {
  await loadCompaniesIfNeeded();
  syncSelectionFromRoute();
});

const allCompanies = computed(() => {
  return props.companies?.length ? props.companies : internalCompanies.value;
});

// Sector list matching macOS: ["All", ...sortedUniqueSectors]
const sectors = computed(() => {
  const set = new Set();
  for (const c of allCompanies.value) {
    if (c.sector && typeof c.sector === "string" && c.sector.trim()) {
      set.add(c.sector.trim());
    }
  }
  return ["All", ...Array.from(set).sort()];
});

function isCompanyModified(company) {
  if (!company) return false;
  if (company.is_modified || company.has_updates || company.modified) return true;
  if (!visitedCompanies.value.has(company.id) && (company.reports_count > 0 || company.priority === "high")) {
    return true;
  }
  return false;
}

const filteredCompanies = computed(() => {
  const q = searchText.value.trim().toLowerCase();
  const sec = selectedSector.value;

  return allCompanies.value.filter((company) => {
    if (showOnlyModified.value && !isCompanyModified(company)) {
      return false;
    }

    if (sec !== "All" && company.sector !== sec) {
      return false;
    }

    if (!q) return true;

    const nameMatch = (company.name || "").toLowerCase().includes(q);
    const tickerMatch = (company.ticker || "").toLowerCase().includes(q);
    const idMatch = (company.id || "").toLowerCase().includes(q);

    return nameMatch || tickerMatch || idMatch;
  });
});

const selectedCompanyId = ref("");

const selectedCompany = computed(() => {
  if (!selectedCompanyId.value) return null;
  return allCompanies.value.find((c) => c.id === selectedCompanyId.value) || null;
});

function selectCompany(company) {
  if (!company) return;
  selectedCompanyId.value = company.id;
  markVisited(company.id);
  mobileView.value = "dossier";

  if (route.params.companyId !== company.id) {
    router.replace({
      name: "research-desk-company",
      params: { companyId: company.id },
    });
  }
}

function syncSelectionFromRoute() {
  const targetId = props.companyId || route.params.companyId || route.query.company;
  if (targetId) {
    const found = allCompanies.value.find((c) => c.id === targetId);
    if (found) {
      selectedCompanyId.value = found.id;
      markVisited(found.id);
      mobileView.value = "dossier";
      return;
    }
  }

  if (!selectedCompanyId.value && allCompanies.value.length > 0 && window.innerWidth >= 768) {
    selectedCompanyId.value = allCompanies.value[0].id;
    markVisited(allCompanies.value[0].id);
  }
}

watch(
  () => [props.companyId, route.params.companyId, allCompanies.value.length],
  () => {
    syncSelectionFromRoute();
  },
);

function secondaryLine(company) {
  const parts = [];
  if (company.ticker) parts.push(company.ticker.toUpperCase());
  if (company.sector) parts.push(company.sector);
  return parts.join(" · ") || company.id;
}

function onStageUpdated(newStage) {
  if (selectedCompany.value) {
    selectedCompany.value.deal_stage = newStage;
  }
}

function triggerBrowseDeck() {
  if (fileInputRef.value) {
    fileInputRef.value.value = "";
    fileInputRef.value.click();
  }
}

function onFileInputChange(event) {
  const file = event.target.files?.[0];
  if (file) {
    droppedDeckFile.value = file;
    showDeckModal.value = true;
  }
}

function onDeckDragOver(e) {
  e.preventDefault();
  isDeckDragTargeted.value = true;
}

function onDeckDragLeave() {
  isDeckDragTargeted.value = false;
}

function onDeckDrop(e) {
  e.preventDefault();
  isDeckDragTargeted.value = false;
  const file = e.dataTransfer?.files?.[0];
  if (file) {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext === "pdf" || ext === "pptx") {
      droppedDeckFile.value = file;
      showDeckModal.value = true;
    }
  }
}
</script>

<template>
  <div class="flex h-[calc(100vh-4rem)] w-full flex-col overflow-hidden bg-background">
    <!-- Mobile Segmented Bar -->
    <div class="flex shrink-0 items-center border-b border-border/40 bg-surface/80 p-2 md:hidden">
      <div class="grid w-full grid-cols-2 gap-1 rounded-lg bg-muted/40 p-1">
        <button
          type="button"
          class="rounded-md py-1.5 text-xs font-medium transition"
          :class="
            mobileView === 'directory'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground'
          "
          @click="mobileView = 'directory'"
        >
          {{ t("research_desk.view_directory") }} ({{ filteredCompanies.length }})
        </button>
        <button
          type="button"
          class="rounded-md py-1.5 text-xs font-medium transition"
          :class="
            mobileView === 'dossier'
              ? 'bg-background text-foreground shadow-sm'
              : 'text-muted-foreground'
          "
          @click="mobileView = 'dossier'"
        >
          {{ t("research_desk.view_dossier") }}
        </button>
      </div>
    </div>

    <!-- Hidden file input for pitch deck browse -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".pdf,.pptx"
      class="hidden"
      @change="onFileInputChange"
    />

    <!-- Main Two-Pane Split -->
    <div class="flex min-h-0 flex-1 divide-x divide-border/40">
      <!-- Left: Directory Pane (MacResearchDeskView.swift) -->
      <aside
        class="flex flex-col border-r border-border/40 bg-surface/80 dark:bg-[#161618]/80 backdrop-blur-xl transition-all duration-200"
        :class="[
          mobileView === 'directory' ? 'flex w-full md:w-[270px] md:min-w-[240px] md:max-w-[340px]' : 'hidden md:flex md:w-[270px] md:min-w-[240px] md:max-w-[340px]',
        ]"
      >
        <!-- Toolbar Strip: Sector Filter + Diffs Sparkle + Monospace Count -->
        <div class="flex shrink-0 items-center justify-between gap-2 border-b border-border/40 px-3 py-2 bg-surface/90 dark:bg-[#1a1a1c]/90">
          <!-- Sector Pop-up Menu -->
          <div class="relative flex-1">
            <select
              v-model="selectedSector"
              class="w-full appearance-none rounded-md border border-border/40 bg-surface/80 hover:bg-muted/40 py-1 pl-2 pr-6 text-[11px] font-medium text-foreground focus:border-accent focus:outline-none"
              :aria-label="t('research_desk.sector')"
            >
              <option v-for="s in sectors" :key="s" :value="s">
                {{ s === "All" ? t("research_desk.all_sectors") : s }}
              </option>
            </select>
            <ChevronDown class="pointer-events-none absolute right-1.5 top-2 h-3 w-3 text-muted-foreground" />
          </div>

          <!-- Diffs Toggle Button (.buttonStyle(.bordered).controlSize(.mini)) -->
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-all"
            :class="
              showOnlyModified
                ? 'border-accent/40 bg-accent/15 text-accent shadow-2xs'
                : 'border-border/40 bg-surface/80 text-muted-foreground hover:bg-muted/40 hover:text-foreground'
            "
            :title="t('research_desk.diffs_help')"
            @click="showOnlyModified = !showOnlyModified"
          >
            <Sparkles class="h-3 w-3" />
            <span>{{ t("research_desk.diffs") }}</span>
          </button>

          <!-- Monospace Count (Mac caption.monospacedDigit()) -->
          <span class="text-[11px] font-mono text-muted-foreground tabular-nums select-none shrink-0">
            {{ filteredCompanies.length }}
          </span>
        </div>

        <!-- Search Input (Mac searchable toolbar style) -->
        <div class="shrink-0 border-b border-border/30 px-2.5 py-2">
          <div class="relative flex items-center">
            <Search class="pointer-events-none absolute left-2.5 h-3.5 w-3.5 text-muted-foreground" />
            <input
              v-model="searchText"
              type="text"
              :placeholder="t('research_desk.search_placeholder')"
              class="w-full rounded-md border border-border/40 bg-black/[0.03] dark:bg-white/[0.04] py-1 pl-8 pr-7 text-[12px] text-foreground placeholder:text-muted-foreground/60 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
            />
            <button
              v-if="searchText"
              type="button"
              class="absolute right-2 p-0.5 text-muted-foreground hover:text-foreground"
              @click="searchText = ''"
            >
              <X class="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        <!-- Directory List (CompanyListRow with glassListRow modifier) -->
        <div class="min-h-0 flex-1 overflow-y-auto px-1.5 py-1 space-y-0.5">
          <button
            v-for="company in filteredCompanies"
            :key="company.id"
            type="button"
            class="group flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-all duration-150 select-none outline-none"
            :class="
              selectedCompanyId === company.id
                ? 'bg-black/[0.06] dark:bg-white/[0.12] border border-black/[0.08] dark:border-white/[0.20] shadow-[0_1px_3px_rgba(0,0,0,0.06)] dark:shadow-[0_1px_3px_rgba(0,0,0,0.35)] text-foreground font-medium'
                : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.04] border border-transparent text-foreground/85'
            "
            @click="selectCompany(company)"
          >
            <!-- 30x30 Monogram + Modified unread badge -->
            <div class="relative shrink-0">
              <MacMonogram :company="company" :name="company.name || company.id" :ticker="company.ticker" :size="30" :indicator="isCompanyModified(company)" />
            </div>

            <!-- Name + Secondary line -->
            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] leading-snug" :class="selectedCompanyId === company.id ? 'font-semibold' : 'font-medium'">
                {{ company.name || company.id }}
              </div>

              <div class="truncate text-[11px] text-neutral-400 leading-tight mt-0.5">
                {{ secondaryLine(company) }}
              </div>
            </div>

            <!-- Private Indicator Dot (6x6 purple dot, matching MacDot(color: .purple)) -->
            <span
              v-if="company.status?.toLowerCase() === 'private'"
              class="h-1.5 w-1.5 shrink-0 rounded-full bg-purple-500"
              :title="t('research_desk.private_badge')"
            />
          </button>

          <!-- Empty Search State -->
          <div v-if="filteredCompanies.length === 0" class="py-12 text-center text-xs text-neutral-400">
            {{ t("sidebar.no_filter_matches") }}
          </div>
        </div>

        <!-- Pitch Deck Intake Drop Banner (MacPitchDeckDropBanner.swift) -->
        <div
          class="shrink-0 border-t border-white/[0.08] px-3 py-2 transition-colors relative bg-[#18181a]"
          :class="isDeckDragTargeted ? 'bg-[#0a84ff]/15 border-t-[#0a84ff]' : ''"
          @dragover="onDeckDragOver"
          @dragleave="onDeckDragLeave"
          @drop="onDeckDrop"
        >
          <div
            v-if="isDeckDragTargeted"
            class="absolute top-0 left-0 right-0 h-[2px] bg-[#0a84ff]"
          />

          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2 min-w-0">
              <FileText
                class="h-3.5 w-3.5 shrink-0 transition-colors"
                :class="isDeckDragTargeted ? 'text-[#0a84ff]' : 'text-neutral-400'"
              />
              <span
                class="text-[11px] truncate text-neutral-400"
                :class="isDeckDragTargeted ? 'text-[#0a84ff] font-medium' : ''"
              >
                {{ isDeckDragTargeted ? t("research_desk.drop_deck_release") : t("research_desk.drop_deck_instruction") }}
              </span>
            </div>

            <button
              type="button"
              class="rounded-md border border-white/10 bg-white/5 hover:bg-white/10 px-2.5 py-1 text-[11px] font-medium text-white transition-all shrink-0"
              @click="triggerBrowseDeck"
            >
              {{ t("research_desk.browse_files") }}
            </button>
          </div>
        </div>
      </aside>

      <!-- Right: Detail Dossier Pane (Mac DS Page Layout) -->
      <main
        class="min-h-0 flex-1 overflow-y-auto p-5 md:p-6"
        :class="[
          mobileView === 'dossier' ? 'block' : 'hidden md:block',
        ]"
      >
        <!-- When Company Selected -->
        <CompanyDossierView
          v-if="selectedCompany"
          :company-id="selectedCompany.id"
          :company="selectedCompany"
          @open-copilot="emit('open-copilot', $event)"
          @stage-updated="onStageUpdated"
        />

        <!-- Empty State When No Company Selected -->
        <div
          v-else
          class="flex h-full min-h-[30rem] flex-col items-center justify-center rounded-xl border border-dashed border-border/50 bg-card/20 p-8 text-center"
        >
          <div class="flex h-14 w-14 items-center justify-center rounded-xl bg-muted/50 text-muted-foreground">
            <Building2 class="h-7 w-7 text-accent/80" />
          </div>

          <h2 class="mt-4 text-base font-bold text-foreground">
            {{ t("research_desk.no_company_selected") }}
          </h2>

          <p class="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">
            {{ t("research_desk.select_prompt") }}
          </p>

          <button
            v-if="filteredCompanies.length > 0"
            type="button"
            class="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white shadow-xs transition hover:opacity-90"
            @click="selectCompany(filteredCompanies[0])"
          >
            <span>{{ t("research_desk.select_company_action", { name: filteredCompanies[0].name || filteredCompanies[0].id }) }}</span>
            <ChevronRight class="h-3.5 w-3.5" />
          </button>
        </div>
      </main>
    </div>

    <!-- Pitch Deck Intake Modal -->
    <PitchDeckIntakeModal
      :is-open="showDeckModal"
      :initial-file="droppedDeckFile"
      :company-id="selectedCompanyId"
      :companies="allCompanies"
      @close="showDeckModal = false"
      @intake-complete="emit('reports-changed')"
    />
  </div>
</template>
