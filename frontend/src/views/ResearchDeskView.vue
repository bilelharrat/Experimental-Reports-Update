<script setup>
// Web twin of MacResearchDeskView.swift: HSplitView with the company directory
// on the left (toolbar strip, list with the levitating glass selection, pitch
// deck drop banner) and the company dossier on the right. Chrome, metrics and
// copy mirror the Mac desk; see .mac-desk in style.css for the token layer.
//
// The directory was folded into the sidebar on 2026-09-19 (be474b3) and is
// back by request: the desk's own list, search, sector popup and Diffs sit
// beside the dossier again. It shares the sidebar's sort, "modified" rule
// (state.js) and deck intake sheet (App.vue) rather than keeping copies.
import { ref, computed, watch, watchEffect, onMounted, onBeforeUnmount, inject } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { useT } from "../i18n.js";
import { chromeLeftInset, useMediaQuery } from "../chrome.js";
import {
  Sparkles,
  Sparkle,
  Search,
  SearchX,
  ChevronsUpDown,
  X,
  FilePlus2,
  FileDown,
  AlertTriangle,
  Building2,
  PanelLeftClose,
  PanelLeftOpen,
} from "lucide-vue-next";
import MacMonogram from "../components/research/MacMonogram.vue";
import Monogram from "../components/Monogram.vue";
import CompanyDossierView from "../components/research/CompanyDossierView.vue";
import { api } from "../api.js";
import { sortCompanies } from "../companyLists.js";
import {
  companySort,
  companyViews,
  isCompanyModified,
  lastCompanyId,
  trackedCompanyIds,
} from "../state.js";

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

// The deck intake sheet lives in App.vue beside every view; a drop or a
// browse here opens that one rather than a second copy.
const openDeckIntake = inject("openDeckIntake", () => {});

const route = useRoute();
const router = useRouter();
const t = useT();

const internalCompanies = ref([]);
const loadingCompanies = ref(false);
// Whether the company list is known: handed in, or fetched. A route id is
// only called missing once it is, so a deep link never flashes "not found"
// while the list is still on its way.
const companiesReady = ref(false);
// The first load has finished, whether or not it succeeded.
const listSettled = ref(false);
// A route id that names no company in the loaded list.
const notFoundId = ref("");

const searchText = ref("");
const selectedSector = ref("All");
const showOnlyModified = ref(false);
const mobileView = ref("directory"); // 'directory' | 'dossier'

// HSplitView: directory pane min 230, ideal 270, max 380.
const paneWidth = ref(270);
let dragState = null;

// Collapsed, the directory becomes a slim rail holding just the reopen
// chevron — the same move the iOS master lists make to give the detail the
// full width. Only above `md`: narrower windows already swap panes with the
// segmented control, so there is nothing to collapse.
const DIRECTORY_COLLAPSED_KEY = "bsh.researchDirectoryCollapsed";
const DIRECTORY_RAIL_WIDTH = 44;
// `md:ml-2` — the floating pane's own gutter, which the toolbar must clear too.
const DIRECTORY_PANE_MARGIN = 8;
// The toolbar's height: what the desk rises by, and what the dossier column
// pads back so its content is not swallowed by the bar it now runs under.
const CHROME_BAR_HEIGHT = 52;

const isSplitWidth = useMediaQuery("(min-width: 768px)");

function _initialDirectoryCollapsed() {
  try {
    return window.localStorage.getItem(DIRECTORY_COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

const directoryCollapsedPref = ref(_initialDirectoryCollapsed());
const directoryCollapsed = computed(
  () => directoryCollapsedPref.value && isSplitWidth.value,
);

watch(directoryCollapsedPref, (collapsed) => {
  try {
    window.localStorage.setItem(DIRECTORY_COLLAPSED_KEY, collapsed ? "1" : "0");
  } catch {
    // ignore — localStorage unavailable
  }
});

function toggleDirectory() {
  directoryCollapsedPref.value = !directoryCollapsedPref.value;
}

const directoryPaneStyle = computed(() => ({
  "--pane-w": directoryCollapsed.value
    ? `${DIRECTORY_RAIL_WIDTH}px`
    : `${paneWidth.value}px`,
}));

// The directory runs the full height of the window, so the toolbar starts
// where the dossier does. Below `md` the two panes swap instead of sharing
// the width, so there is no band to claim and the toolbar spans as usual.
const directoryWidth = computed(() =>
  directoryCollapsed.value ? DIRECTORY_RAIL_WIDTH : paneWidth.value,
);
watchEffect(() => {
  chromeLeftInset.value = isSplitWidth.value
    ? directoryWidth.value + DIRECTORY_PANE_MARGIN
    : 0;
});
onBeforeUnmount(() => {
  chromeLeftInset.value = 0;
});

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

// Pitch Deck drop banner state (MacPitchDeckDropBanner)
const fileInputRef = ref(null);
const isDeckDragTargeted = ref(false);
const deckNotice = ref("");
let deckNoticeTimer = null;

async function fetchCompanies() {
  loadingCompanies.value = true;
  try {
    const res = await api.listCompanies();
    internalCompanies.value = Array.isArray(res) ? res : (res?.companies || []);
    companiesReady.value = true;
  } catch {
    // An unreachable list says nothing about whether a company exists, so
    // it never turns into "Company not found".
    if (!companiesReady.value) internalCompanies.value = [];
  } finally {
    loadingCompanies.value = false;
    listSettled.value = true;
  }
}

async function loadCompaniesIfNeeded() {
  if (props.companies && props.companies.length > 0) {
    companiesReady.value = true;
    listSettled.value = true;
    return;
  }
  await fetchCompanies();
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

const filteredCompanies = computed(() => {
  const q = searchText.value.trim().toLowerCase();
  const sec = selectedSector.value;

  // Sorted as the sidebar is, so the two lists agree on what comes first.
  const sorted = sortCompanies(allCompanies.value, {
    sort: companySort.value,
    views: companyViews.value,
    favorites: trackedCompanyIds.value,
  });
  return sorted.filter((company) => {
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
  mobileView.value = "dossier";

  if (route.params.companyId !== company.id) {
    router.replace({
      name: "research-desk-company",
      params: { companyId: company.id },
    });
  }
}

// The id this desk was linked to, if any.
function routeCompanyId() {
  const raw = props.companyId || route.params.companyId || route.query.company;
  return typeof raw === "string" ? raw : "";
}
const linkedCompanyId = computed(routeCompanyId);
// Linked to a company whose fate is not known yet (the list is loading, or
// being looked through again): the pane stays quiet rather than show "No
// company selected" or "not found" for a moment. A list that failed to load
// falls back to the plain empty state.
const resolvingLink = computed(
  () =>
    Boolean(linkedCompanyId.value) &&
    !notFoundId.value &&
    !selectedCompany.value &&
    (loadingCompanies.value || !listSettled.value),
);

// The link target last looked up again after a miss: a company added since
// this desk fetched its list (the toolbar's Add, a search pick) is looked
// for once more, per link, before it is called missing.
let refetchedFor = "";

async function syncSelectionFromRoute() {
  const targetId = routeCompanyId();
  if (targetId) {
    const found = allCompanies.value.find((c) => c.id === targetId);
    if (found) {
      notFoundId.value = "";
      refetchedFor = "";
      selectedCompanyId.value = found.id;
      mobileView.value = "dossier";
      return;
    }
    // Still loading: decide once the list lands (the watch below re-runs).
    if (!companiesReady.value) return;
    // Never another company's dossier under this URL, even for a moment.
    selectedCompanyId.value = "";
    if (!props.companies?.length && refetchedFor !== targetId) {
      refetchedFor = targetId;
      await fetchCompanies();
      if (routeCompanyId() !== targetId) return;
      if (allCompanies.value.some((c) => c.id === targetId)) {
        syncSelectionFromRoute();
        return;
      }
    }
    // A link to a company this workspace does not have. Say so, rather than
    // open another company's dossier under this URL.
    notFoundId.value = targetId;
    selectedCompanyId.value = "";
    mobileView.value = "dossier";
    return;
  }

  notFoundId.value = "";
  refetchedFor = "";
  if (!selectedCompanyId.value && allCompanies.value.length > 0) {
    selectedCompanyId.value = defaultCompanyId(window.innerWidth >= 768);
  }
}

// Which company the bare Research Desk opens: the one you were last working
// on, on any screen. Failing that — first visit, or that company is gone —
// the top of the list as you have it sorted, so the desk opens on the
// company you can see first rather than whatever the API returned first.
// On a phone the list and dossier swap, so it waits for a pick.
function defaultCompanyId(wideScreen) {
  const last = lastCompanyId.value;
  if (last && allCompanies.value.some((c) => c.id === last)) return last;
  if (!wideScreen) return "";
  const [first] = sortCompanies(allCompanies.value, {
    sort: companySort.value,
    views: companyViews.value,
    favorites: trackedCompanyIds.value,
  });
  return first?.id || "";
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
  if (file) openDeckIntake(file);
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
    openDeckIntake(deck);
  } else {
    const names = files.map((f) => f.name).join(", ");
    showDeckNotice(t("research_desk.deck_rejected", { names }));
  }
}
</script>

<template>
  <div
    class="mac-desk flex h-[calc(100vh-4rem)] w-full flex-col overflow-hidden md:-mt-[52px] md:h-[calc(100vh-0.75rem)]"
  >
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
        class="glass-panel relative z-40 flex min-h-0 flex-col md:my-2 md:ml-2 md:rounded-[18px]"
        :class="mobileView === 'directory' ? 'flex w-full md:w-auto' : 'hidden md:flex'"
        :style="directoryPaneStyle"
      >
        <div
          class="mac-directory-pane flex min-h-0 w-full flex-1 flex-col md:w-[var(--pane-w)] md:overflow-hidden md:rounded-[18px]"
        >
          <!-- Collapsed: a rail of the companies' logos, as the Reports list
               collapses to its own. The open company's logo sits lifted;
               each opens its dossier; the button at the top brings the
               directory back. -->
          <div
            v-if="directoryCollapsed"
            class="flex h-full w-full flex-col items-center gap-1 py-2"
          >
            <button
              type="button"
              class="icon-btn !h-7 !w-7 shrink-0"
              :aria-label="t('research_desk.expand_directory')"
              :title="t('research_desk.expand_directory')"
              :aria-expanded="false"
              data-testid="research-directory-expand"
              @click="toggleDirectory"
            >
              <PanelLeftOpen class="h-4 w-4" />
            </button>
            <div class="reports-rail" data-testid="research-directory-rail">
              <button
                v-for="company in filteredCompanies"
                :key="company.id"
                type="button"
                class="reports-rail-mark focus-ring"
                :data-selected="company.id === selectedCompanyId ? 'true' : 'false'"
                :title="company.name || company.id"
                :aria-label="company.name || company.id"
                :aria-current="company.id === selectedCompanyId ? 'true' : undefined"
                @click="selectCompany(company)"
              >
                <Monogram :company="company" :size="26" tinted aria-hidden="true" />
              </button>
            </div>
          </div>

          <template v-else>
          <!-- directoryToolbar: sector popup · spacer · Diffs · count -->
          <div class="mac-toolbar-strip shrink-0">
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

            <button
              type="button"
              class="mac-btn mac-btn--plain shrink-0 !px-1.5"
              :aria-label="t('research_desk.collapse_directory')"
              :title="t('research_desk.collapse_directory')"
              :aria-expanded="true"
              data-testid="research-directory-collapse"
              @click="toggleDirectory"
            >
              <PanelLeftClose class="h-3.5 w-3.5" />
            </button>
          </div>

          <!-- Toolbar search field (.searchable placement: .toolbar) -->
          <div class="mac-hairline-b shrink-0 px-2.5 py-1.5">
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
            class="mac-hairline-t relative shrink-0"
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
                class="mac-t-caption min-w-0 flex-1 leading-snug"
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
          </template>
        </div>

        <!-- HSplitView drag handle -->
        <div
          v-if="!directoryCollapsed"
          class="absolute -right-[3px] top-0 z-10 hidden h-full w-[6px] md:block"
          style="cursor: col-resize"
          @pointerdown="onSplitPointerDown"
        />
      </aside>

      <!-- Detail pane. It runs up under the toolbar, so its scroll padding
           keeps a card scrolled into view (Memo Studio's section jumps, a
           point Warren edited) below the bar instead of behind it. -->
      <main
        class="mac-scroll min-h-0 min-w-0 flex-1 overflow-y-auto md:scroll-pt-[52px] md:pt-[52px]"
        :class="mobileView === 'dossier' ? 'block' : 'hidden md:block'"
      >
        <CompanyDossierView
          v-if="selectedCompany"
          :company-id="selectedCompany.id"
          :company="selectedCompany"
          @open-copilot="emit('open-copilot', $event)"
          @stage-updated="onStageUpdated"
        />

        <!-- A link to a company this workspace does not have (most reports
             belong to companies that were never added). Its reports may
             still be on file, so the way out is the Reports desk filtered
             to it. -->
        <div
          v-else-if="notFoundId"
          class="flex h-full min-h-[24rem] flex-col items-center justify-center px-8 text-center"
          data-testid="desk-company-not-found"
        >
          <SearchX class="mac-c-secondary h-11 w-11" stroke-width="1.25" />
          <h2 class="mac-t-headline mt-4" style="font-size: 17px">
            {{ t("desk.company_not_found_title") }}
          </h2>
          <p class="mac-t-body mac-c-secondary mt-1.5 max-w-sm">
            {{ t("desk.company_not_found_body", { id: notFoundId }) }}
          </p>
          <RouterLink
            :to="{ name: 'reports', query: { company: notFoundId } }"
            class="mac-btn mac-btn--prominent mt-4"
            data-testid="desk-company-not-found-reports"
          >
            {{ t("desk.company_not_found_reports") }}
          </RouterLink>
        </div>

        <!-- Following a link: quiet until the company list says who it is. -->
        <div v-else-if="resolvingLink" class="h-full min-h-[24rem]" aria-busy="true" />

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
  </div>
</template>
