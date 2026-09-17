<script setup>
// Web twin of MacResearchDeskView.swift: HSplitView with the company directory
// on the left (toolbar strip, list with the levitating glass selection, pitch
// deck drop banner) and the company dossier on the right. Chrome, metrics and
// copy mirror the Mac desk; see .mac-desk in style.css for the token layer.
import { ref, computed, watch, onMounted, onBeforeUnmount } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useT } from "../i18n.js";
import {
  Sparkles,
  Sparkle,
  Search,
  ChevronsUpDown,
  X,
  FilePlus2,
  FileDown,
  AlertTriangle,
  Building2,
} from "lucide-vue-next";
import MacMonogram from "../components/research/MacMonogram.vue";
import CompanyDossierView from "../components/research/CompanyDossierView.vue";
import PitchDeckIntakeModal from "../components/research/PitchDeckIntakeModal.vue";
import { api } from "../api.js";

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

// HSplitView: directory pane min 230, ideal 270, max 380.
const paneWidth = ref(270);
let dragState = null;

function onSplitPointerDown(e) {
  dragState = { startX: e.clientX, startWidth: paneWidth.value };
  window.addEventListener("pointermove", onSplitPointerMove);
  window.addEventListener("pointerup", onSplitPointerUp);
  e.preventDefault();
}

function onSplitPointerMove(e) {
  if (!dragState) return;
  const next = dragState.startWidth + (e.clientX - dragState.startX);
  paneWidth.value = Math.min(380, Math.max(230, next));
}

function onSplitPointerUp() {
  dragState = null;
  window.removeEventListener("pointermove", onSplitPointerMove);
  window.removeEventListener("pointerup", onSplitPointerUp);
}

onBeforeUnmount(onSplitPointerUp);

// Pitch Deck Intake state (MacPitchDeckDropBanner)
const showDeckModal = ref(false);
const droppedDeckFile = ref(null);
const fileInputRef = ref(null);
const isDeckDragTargeted = ref(false);
const deckNotice = ref("");
let deckNoticeTimer = null;

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

// CompanyListRow.secondaryLine: ticker · sector-or-industry · non-public/private
// status capitalized, joined with middle dots.
function secondaryLine(company) {
  const parts = [];
  if (company.ticker) parts.push(String(company.ticker).toUpperCase());
  if (company.sector) parts.push(company.sector);
  else if (company.industry) parts.push(company.industry);
  const status = (company.status || "").toLowerCase();
  if (status && status !== "public" && status !== "private") {
    parts.push(status.charAt(0).toUpperCase() + status.slice(1));
  }
  return parts.join(" · ");
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

function showDeckNotice(text) {
  deckNotice.value = text;
  if (deckNoticeTimer) clearTimeout(deckNoticeTimer);
  deckNoticeTimer = setTimeout(() => {
    deckNotice.value = "";
  }, 6000);
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
  const files = Array.from(e.dataTransfer?.files || []);
  if (!files.length) return;
  const deck = files.find((f) => {
    const ext = f.name.split(".").pop()?.toLowerCase();
    return ext === "pdf" || ext === "pptx";
  });
  if (deck) {
    droppedDeckFile.value = deck;
    showDeckModal.value = true;
  } else {
    const names = files.map((f) => f.name).join(", ");
    showDeckNotice(t("research_desk.deck_rejected", { names }));
  }
}
</script>

<template>
  <div class="mac-desk flex h-[calc(100vh-4rem)] w-full flex-col overflow-hidden">
    <!-- Compact-width segmented switcher (iPad compact analog) -->
    <div class="mac-hairline-b flex shrink-0 items-center px-2 py-1.5 md:hidden">
      <div class="mac-segmented w-full">
        <button
          type="button"
          class="mac-segment"
          :class="{ 'is-selected': mobileView === 'directory' }"
          @click="mobileView = 'directory'"
        >
          {{ t("research_desk.view_directory") }} ({{ filteredCompanies.length }})
        </button>
        <button
          type="button"
          class="mac-segment"
          :class="{ 'is-selected': mobileView === 'dossier' }"
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

    <!-- HSplitView -->
    <div class="flex min-h-0 flex-1">
      <!-- Directory pane -->
      <aside
        class="mac-hairline-r relative flex min-h-0 flex-col"
        :class="mobileView === 'directory' ? 'flex w-full md:w-auto' : 'hidden md:flex'"
        :style="{ '--pane-w': `${paneWidth}px` }"
      >
        <div class="flex min-h-0 flex-1 w-full flex-col md:w-[var(--pane-w)]">
          <!-- directoryToolbar: sector popup · spacer · Diffs · count -->
          <div class="mac-toolbar-strip mac-bar-material mac-hairline-b shrink-0">
            <div class="mac-popup min-w-0 max-w-[55%]">
              <select v-model="selectedSector" :aria-label="t('research_desk.sector')">
                <option v-for="s in sectors" :key="s" :value="s">
                  {{ s === "All" ? t("research_desk.all_sectors") : s }}
                </option>
              </select>
              <ChevronsUpDown class="mac-popup-chevron h-2.5 w-2.5" />
            </div>

            <div class="flex-1" />

            <button
              type="button"
              class="mac-btn mac-btn--mini"
              :class="showOnlyModified ? 'mac-btn--tint' : ''"
              :title="t('research_desk.diffs_help')"
              @click="showOnlyModified = !showOnlyModified"
            >
              <component :is="showOnlyModified ? Sparkle : Sparkles" class="h-3 w-3" />
              <span>{{ t("research_desk.diffs") }}</span>
            </button>

            <span class="mac-t-caption mac-mono mac-c-secondary shrink-0 select-none">
              {{ filteredCompanies.length }}
            </span>
          </div>

          <!-- Toolbar search field (.searchable placement: .toolbar) -->
          <div class="mac-bar-material mac-hairline-b shrink-0 px-2.5 py-1.5">
            <div class="mac-search relative px-2">
              <Search class="mac-c-secondary h-3.5 w-3.5 shrink-0" />
              <input
                v-model="searchText"
                type="text"
                :placeholder="t('research_desk.search_placeholder')"
                class="ml-1.5 min-w-0 flex-1"
              />
              <button
                v-if="searchText"
                type="button"
                class="mac-c-secondary shrink-0 border-none bg-transparent p-0.5"
                @click="searchText = ''"
              >
                <X class="h-3 w-3" />
              </button>
            </div>
          </div>

          <!-- List(selection:) with glassListRow -->
          <div class="mac-scroll min-h-0 flex-1 overflow-y-auto py-1">
            <button
              v-for="company in filteredCompanies"
              :key="company.id"
              type="button"
              class="mac-row"
              :class="{ 'is-selected': selectedCompanyId === company.id }"
              @click="selectCompany(company)"
            >
              <!-- 30pt monogram + modified pip -->
              <MacMonogram
                :company="company"
                :name="company.name || company.id"
                :ticker="company.ticker"
                :size="30"
                :indicator="isCompanyModified(company)"
              />

              <span class="min-w-0 flex-1">
                <span class="mac-t-subhead block truncate">
                  {{ company.name || company.id }}
                </span>
                <span class="mac-t-caption mac-c-secondary mt-0.5 block truncate">
                  {{ secondaryLine(company) || " " }}
                </span>
              </span>

              <!-- MacDot(.purple) for private companies -->
              <span
                v-if="company.status?.toLowerCase() === 'private'"
                class="mac-dot"
                :style="{ background: 'var(--mac-purple)' }"
                :title="t('research_desk.private_badge')"
              />
            </button>

            <div
              v-if="filteredCompanies.length === 0"
              class="mac-t-caption mac-c-secondary py-12 text-center"
            >
              {{ t("sidebar.no_filter_matches") }}
            </div>
          </div>

          <!-- MacPitchDeckDropBanner on the bar material -->
          <div
            class="mac-bar-material mac-hairline-t relative shrink-0"
            :style="isDeckDragTargeted ? { background: 'color-mix(in srgb, var(--mac-accent) 10%, transparent)' } : {}"
            @dragover="onDeckDragOver"
            @dragleave="onDeckDragLeave"
            @drop="onDeckDrop"
          >
            <div
              v-if="isDeckDragTargeted"
              class="absolute left-0 right-0 top-0 h-[2px]"
              :style="{ background: 'var(--mac-accent)' }"
            />

            <div class="flex items-center gap-2 px-3 py-[7px]">
              <component
                :is="isDeckDragTargeted ? FileDown : (deckNotice ? AlertTriangle : FilePlus2)"
                class="h-3.5 w-3.5 shrink-0"
                :style="{
                  color: isDeckDragTargeted
                    ? 'var(--mac-accent)'
                    : (deckNotice ? 'var(--mac-orange)' : 'var(--mac-secondary)'),
                }"
              />
              <span
                class="mac-t-caption min-w-0 flex-1 truncate"
                :style="{
                  color: isDeckDragTargeted
                    ? 'var(--mac-accent)'
                    : (deckNotice ? 'var(--mac-orange)' : 'var(--mac-secondary)'),
                }"
              >
                {{
                  isDeckDragTargeted
                    ? t("research_desk.drop_deck_release")
                    : (deckNotice || t("research_desk.drop_deck_instruction"))
                }}
              </span>

              <button type="button" class="mac-btn mac-btn--sm shrink-0" @click="triggerBrowseDeck">
                {{ t("research_desk.browse_files") }}
              </button>
            </div>
          </div>
        </div>

        <!-- HSplitView drag handle -->
        <div
          class="absolute -right-[3px] top-0 z-10 hidden h-full w-[6px] md:block"
          style="cursor: col-resize"
          @pointerdown="onSplitPointerDown"
        />
      </aside>

      <!-- Detail pane -->
      <main
        class="mac-scroll min-h-0 min-w-0 flex-1 overflow-y-auto"
        :class="mobileView === 'dossier' ? 'block' : 'hidden md:block'"
      >
        <CompanyDossierView
          v-if="selectedCompany"
          :company-id="selectedCompany.id"
          :company="selectedCompany"
          @open-copilot="emit('open-copilot', $event)"
          @stage-updated="onStageUpdated"
        />

        <!-- ContentUnavailableView("No Company Selected", systemImage: building.2) -->
        <div
          v-else
          class="flex h-full min-h-[24rem] flex-col items-center justify-center px-8 text-center"
        >
          <Building2 class="mac-c-secondary h-11 w-11" stroke-width="1.25" />
          <h2 class="mac-t-headline mt-4" style="font-size: 17px">
            {{ t("research_desk.no_company_selected") }}
          </h2>
          <p class="mac-t-body mac-c-secondary mt-1.5 max-w-sm">
            {{ t("research_desk.select_prompt") }}
          </p>
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
