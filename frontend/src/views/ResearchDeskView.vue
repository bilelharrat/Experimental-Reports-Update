<script setup>
// Web twin of MacResearchDeskView.swift, now detail-only: the company
// directory that used to sit in a left pane here is the sidebar's company
// list, so this view is the dossier and the width it was sharing. Chrome,
// metrics and copy mirror the Mac desk; see .mac-desk in style.css.
import { ref, computed, watch, onMounted } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useT } from "../i18n.js";
import { Building2 } from "lucide-vue-next";
import CompanyDossierView from "../components/research/CompanyDossierView.vue";
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


const selectedCompanyId = ref("");

const selectedCompany = computed(() => {
  if (!selectedCompanyId.value) return null;
  return allCompanies.value.find((c) => c.id === selectedCompanyId.value) || null;
});

function selectCompany(company) {
  if (!company) return;
  selectedCompanyId.value = company.id;

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
          return;
    }
  }

  if (!selectedCompanyId.value && allCompanies.value.length > 0 && window.innerWidth >= 768) {
    selectedCompanyId.value = allCompanies.value[0].id;
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


</script>

<template>
  <div
    class="mac-desk flex h-[calc(100vh-4rem)] w-full flex-col overflow-hidden md:-mt-[52px] md:h-[calc(100vh-0.75rem)]"
  >
<!-- HSplitView -->
    <div class="flex min-h-0 flex-1">
<!-- Detail pane -->
      <main
        class="mac-scroll block min-h-0 min-w-0 flex-1 overflow-y-auto md:pt-[52px]"
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
  </div>
</template>
