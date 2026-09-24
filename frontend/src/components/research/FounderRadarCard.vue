<script setup>
// Web twin of MacFounderRadarView.swift: leadership and board card grids
// (initials avatar, pedigree pill flow, education / past companies / prior
// exit rows), the headcount tile with four metric pills and the department
// split bar, and the open-source velocity section with the traction callout.
import { ref, computed, watch } from "vue";
import { useT } from "../../i18n.js";
import {
  Users,
  RotateCw,
  Briefcase,
  GraduationCap,
  Building2,
  CircleDollarSign,
  Link as LinkIcon,
  Star,
  GitFork,
  ArrowDownCircle,
  History,
  Flame,
  Code,
  Megaphone,
  Settings,
  ArrowUpRight,
  AlertTriangle,
  BarChartHorizontal,
} from "lucide-vue-next";
import { api } from "../../api.js";
import { researchTeam, researchingCompanies } from "../../founderResearch.js";

const t = useT();

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

const loading = ref(false);
const loadFailed = ref(false);
const refreshError = ref(null);
const founderData = ref(null);
// Research in flight is per company (see founderResearch.js): this card's
// spinner belongs to the company it is showing, not to the last click.
const searching = computed(() => researchingCompanies.has(props.companyId));
// The company whose research this card started, so the watcher below does
// not re-read over the response it is about to receive itself.
const ownRun = ref(null);

async function loadFounders() {
  const companyId = props.companyId;
  if (!companyId) return;
  loading.value = true;
  loadFailed.value = false;
  try {
    const data = await api.getFounderDossier(companyId);
    if (props.companyId === companyId) founderData.value = data;
  } catch {
    if (props.companyId === companyId) {
      founderData.value = null;
      loadFailed.value = true;
    }
  } finally {
    if (props.companyId === companyId) loading.value = false;
  }
}

async function researchTeamNow() {
  // This spends a Gemini call: web-grounded research merged over the record
  // (server/founder_dossier.py). It runs the cheapest, fastest Gemini tier
  // (flash-lite), so unlike the desk's other paid buttons it doesn't stop to
  // confirm — the tooltip already says it searches the web. It degrades
  // rather than throwing — a failed pass returns 200 with `research_error`
  // set, shown below the grid.
  const companyId = props.companyId;
  if (!companyId || searching.value) return;
  refreshError.value = null;
  ownRun.value = companyId;
  try {
    const data = await researchTeam(companyId);
    // By now the card may show another company. The server cached the
    // result, so that company shows it the next time it is opened.
    if (data && props.companyId === companyId) founderData.value = data;
  } catch (err) {
    if (props.companyId === companyId) refreshError.value = err?.message || String(err);
  } finally {
    if (ownRun.value === companyId) ownRun.value = null;
  }
}

watch(
  () => props.companyId,
  () => {
    refreshError.value = null;
    loadFounders();
  },
  { immediate: true },
);

// Research started from another card (before a company or tab switch)
// finished for the company this card shows: read the cached result.
watch(searching, (now, was) => {
  if (was && !now && ownRun.value !== props.companyId) loadFounders();
});

const founders = computed(() => founderData.value?.founders || []);
const board = computed(() => founderData.value?.advisors_and_board || []);
const headcount = computed(() => founderData.value?.team_headcount || null);
const traction = computed(() => founderData.value?.developer_traction || null);

// Why a refresh produced nothing. The server degrades instead of throwing,
// so without this the button just stops spinning and the card looks
// unchanged — indistinguishable from "there was nothing new to find".
const researchError = computed(() => founderData.value?.research_error || null);

// Which engine answered and what it read. A Claude fallback reports no
// sources, so the two are shown together rather than letting "researched"
// stand on its own.
const provenance = computed(() => {
  const data = founderData.value;
  if (!data?.engine || researchError.value) return null;
  return {
    engine: data.engine,
    model: data.model || "",
    sources: Array.isArray(data.sources) ? data.sources : [],
  };
});

const hasPeople = computed(
  () => founders.value.length || board.value.length || headcount.value || traction.value,
);

/** LinkedIn if the record has one, otherwise whatever profile it does have. */
function personLink(person) {
  return person?.linkedin_url || person?.profile_url || null;
}

function initials(name) {
  const parts = String(name || "").split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return String(name || "?").slice(0, 2).toUpperCase();
}

// PedigreeBadgeView tint rules
function pedigreeTint(tag) {
  const lower = String(tag).toLowerCase();
  if (lower.includes("openai") || lower.includes("deepmind") || lower.includes("fair")) return "var(--mac-purple)";
  if (lower.includes("stanford") || lower.includes("mit") || lower.includes("berkeley")) return "var(--mac-red)";
  if (lower.includes("founder") || lower.includes("exit")) return "var(--mac-green)";
  if (lower.includes("yc") || lower.includes("stripe")) return "var(--mac-orange)";
  return "var(--mac-blue)";
}

const deptBar = computed(() => {
  const eng = headcount.value?.engineering_pct || 0;
  const gtm = headcount.value?.gtm_sales_pct || 0;
  const ops = headcount.value?.operations_pct || 0;
  const total = Math.max(1, eng + gtm + ops);
  return {
    eng: (eng / total) * 100,
    gtm: (gtm / total) * 100,
    ops: (ops / total) * 100,
  };
});

function repoLabel(url) {
  return String(url || "").replace("https://github.com/", "");
}
</script>

<template>
  <div class="mac-card mac-card-pad flex flex-col gap-[18px]">
    <!-- MacCardHeader("Founders & team", …, person.3) + refresh -->
    <div class="mac-cardheader">
      <span class="mac-cardheader-icon"><Users class="h-[13px] w-[13px]" stroke-width="2.4" /></span>
      <div class="flex min-w-0 flex-col gap-0.5">
        <span class="mac-t-headline">{{ t("research_desk.founders_team_radar") }}</span>
        <span class="mac-t-caption mac-c-secondary">{{ t("research_desk.founders_subtitle") }}</span>
      </div>
      <span class="min-w-2 flex-1" />
      <button
        type="button"
        class="mac-btn mac-btn--sm"
        :disabled="searching"
        :title="t('research_desk.founders_refresh_help')"
        data-testid="founder-research"
        @click="researchTeamNow"
      >
        <span v-if="searching" class="mac-spinner" style="width: 12px; height: 12px" />
        <RotateCw v-else class="h-3 w-3" />
        <span>{{ searching ? t("research_desk.founders_refreshing") : t("research_desk.founders_refresh") }}</span>
      </button>
    </div>

    <template v-if="founderData">
      <!-- ContentUnavailableView when the record lists no people -->
      <div v-if="!hasPeople" class="flex flex-col items-center gap-2 py-8 text-center">
        <Users class="mac-c-secondary h-9 w-9" stroke-width="1.25" />
        <span class="mac-t-headline" style="font-size: 15px">{{ t("research_desk.founders_none_title") }}</span>
        <span class="mac-t-body mac-c-secondary max-w-sm">{{ t("research_desk.founders_none_desc") }}</span>
      </div>

      <!-- Leadership -->
      <div v-if="founders.length" class="flex flex-col gap-3">
        <div class="flex items-center">
          <span class="mac-t-label mac-c-secondary flex items-center gap-1.5">
            <Users class="h-3 w-3" />
            {{ t("research_desk.founders_leadership") }}
          </span>
          <span class="flex-1" />
          <span class="mac-t-caption10 mac-mono mac-c-tertiary">
            {{ t("research_desk.founders_key_execs", { count: founders.length }) }}
          </span>
        </div>

        <div class="grid grid-cols-1 gap-3.5 md:grid-cols-2">
          <div
            v-for="(person, idx) in founders"
            :key="person.name || idx"
            class="mac-tile flex flex-col gap-2.5 p-3"
            style="border-radius: 10px"
          >
            <div class="flex items-center gap-2.5">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px] font-bold"
                :style="{
                  background: 'color-mix(in srgb, var(--mac-accent) 15%, transparent)',
                  color: 'var(--mac-accent)',
                }"
              >
                {{ initials(person.name) }}
              </span>
              <span class="flex min-w-0 flex-col gap-0.5">
                <span class="mac-t-subheadline truncate font-bold">{{ person.name }}</span>
                <span class="mac-t-caption10 mac-c-secondary truncate font-medium">
                  {{ person.role || person.title || "Founder" }}
                </span>
              </span>
              <span class="flex-1" />
              <a
                v-if="personLink(person)"
                :href="personLink(person)"
                target="_blank"
                rel="noopener noreferrer"
                class="mac-c-secondary shrink-0"
                :title="t('research_desk.founders_linkedin')"
              >
                <LinkIcon class="h-4 w-4" />
              </a>
            </div>

            <!-- Pedigree pill flow -->
            <div v-if="person.pedigree_tags?.length" class="flex flex-wrap gap-1.5">
              <span
                v-for="tag in person.pedigree_tags"
                :key="tag"
                class="mac-status-pill"
                :style="{ '--tint': pedigreeTint(tag) }"
              >
                {{ tag }}
              </span>
            </div>

            <p v-if="person.bio" class="mac-t-caption10 mac-c-secondary line-clamp-2">
              {{ person.bio }}
            </p>

            <div class="mac-divider" />

            <div class="flex flex-col gap-[5px]">
              <span v-if="person.education" class="flex items-start gap-1.5">
                <GraduationCap class="mac-c-secondary mt-px h-3 w-3.5 shrink-0" />
                <span class="mac-t-caption10 mac-c-secondary truncate">{{ person.education }}</span>
              </span>
              <span v-if="person.past_companies?.length" class="flex items-start gap-1.5">
                <Building2 class="mac-c-secondary mt-px h-3 w-3.5 shrink-0" />
                <span class="mac-t-caption10 mac-c-secondary truncate">{{ person.past_companies.join(", ") }}</span>
              </span>
              <span v-if="person.prior_exits" class="flex items-start gap-1.5">
                <CircleDollarSign class="mt-px h-3 w-3.5 shrink-0" :style="{ color: 'var(--mac-green)' }" />
                <span class="mac-t-caption10 truncate font-semibold" :style="{ color: 'var(--mac-green)' }">
                  {{ t("research_desk.founders_prior_exit") }}: {{ person.prior_exits }}
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Board & advisors -->
      <div v-if="board.length" class="flex flex-col gap-3">
        <div class="flex items-center">
          <span class="mac-t-label mac-c-secondary flex items-center gap-1.5">
            <Briefcase class="h-3 w-3" />
            {{ t("research_desk.founders_board") }}
          </span>
          <span class="flex-1" />
          <span class="mac-t-caption10 mac-mono mac-c-tertiary">
            {{ t("research_desk.founders_board_count", { count: board.length }) }}
          </span>
        </div>

        <div class="grid grid-cols-1 gap-3.5 md:grid-cols-2">
          <div
            v-for="(person, idx) in board"
            :key="person.name || idx"
            class="mac-tile flex flex-col gap-2.5 p-3"
            style="border-radius: 10px"
          >
            <div class="flex items-center gap-2.5">
              <span
                class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[13px] font-bold"
                :style="{
                  background: 'color-mix(in srgb, var(--mac-accent) 15%, transparent)',
                  color: 'var(--mac-accent)',
                }"
              >
                {{ initials(person.name) }}
              </span>
              <span class="flex min-w-0 flex-col gap-0.5">
                <span class="mac-t-subheadline truncate font-bold">{{ person.name }}</span>
                <span class="mac-t-caption10 mac-c-secondary truncate font-medium">
                  {{ person.role || person.title || "Advisor" }}
                </span>
              </span>
              <span class="flex-1" />
              <a
                v-if="personLink(person)"
                :href="personLink(person)"
                target="_blank"
                rel="noopener noreferrer"
                class="mac-c-secondary shrink-0"
                :title="t('research_desk.founders_linkedin')"
              >
                <LinkIcon class="h-4 w-4" />
              </a>
            </div>

            <div v-if="person.pedigree_tags?.length" class="flex flex-wrap gap-1.5">
              <span
                v-for="tag in person.pedigree_tags"
                :key="tag"
                class="mac-status-pill"
                :style="{ '--tint': pedigreeTint(tag) }"
              >
                {{ tag }}
              </span>
            </div>

            <p v-if="person.bio" class="mac-t-caption10 mac-c-secondary line-clamp-2">
              {{ person.bio }}
            </p>
          </div>
        </div>
      </div>

      <!-- Headcount -->
      <div v-if="headcount" class="mac-tile flex flex-col gap-2.5 p-3" style="border-radius: 10px">
        <div class="flex items-center">
          <span class="mac-t-label mac-c-secondary flex items-center gap-1.5">
            <BarChartHorizontal class="h-3 w-3" />
            {{ t("research_desk.founders_headcount") }}
          </span>
          <span class="flex-1" />
          <span class="mac-t-caption10 font-semibold" :style="{ color: 'var(--mac-green)' }">
            {{ headcount.hiring_velocity || "" }}
          </span>
        </div>

        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <Users class="h-2.5 w-2.5" :style="{ color: 'var(--mac-blue)' }" />
              {{ t("research_desk.founders_total_headcount") }}
            </span>
            <span class="mac-t-metric-sm">{{ headcount.employee_count_estimate || "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-blue)' }">
              {{ headcount.open_roles_count != null ? t("research_desk.founders_open_roles", { count: headcount.open_roles_count }) : t("research_desk.founders_open_roles_unknown") }}
            </span>
          </div>
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <Code class="h-2.5 w-2.5" :style="{ color: 'var(--mac-indigo)' }" />
              {{ t("research_desk.founders_engineering") }}
            </span>
            <span class="mac-t-metric-sm">{{ headcount.engineering_pct != null ? `${headcount.engineering_pct}%` : "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-indigo)' }">{{ t("research_desk.founders_of_headcount") }}</span>
          </div>
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <Megaphone class="h-2.5 w-2.5" :style="{ color: 'var(--mac-green)' }" />
              {{ t("research_desk.founders_gtm") }}
            </span>
            <span class="mac-t-metric-sm">{{ headcount.gtm_sales_pct != null ? `${headcount.gtm_sales_pct}%` : "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-green)' }">{{ t("research_desk.founders_of_headcount") }}</span>
          </div>
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <Settings class="h-2.5 w-2.5" :style="{ color: 'var(--mac-orange)' }" />
              {{ t("research_desk.founders_operations") }}
            </span>
            <span class="mac-t-metric-sm">{{ headcount.operations_pct != null ? `${headcount.operations_pct}%` : "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-orange)' }">{{ t("research_desk.founders_of_headcount") }}</span>
          </div>
        </div>

        <!-- Department split bar -->
        <div class="flex h-[7px] w-full gap-[2px]">
          <span class="rounded-[3px]" :style="{ background: 'color-mix(in srgb, var(--mac-indigo) 85%, transparent)', width: `${Math.max(1, deptBar.eng)}%` }" />
          <span class="rounded-[3px]" :style="{ background: 'color-mix(in srgb, var(--mac-green) 85%, transparent)', width: `${Math.max(1, deptBar.gtm)}%` }" />
          <span class="rounded-[3px]" :style="{ background: 'color-mix(in srgb, var(--mac-orange) 85%, transparent)', width: `${Math.max(1, deptBar.ops)}%` }" />
        </div>
      </div>

      <!-- Open source velocity -->
      <div v-if="traction" class="flex flex-col gap-2.5">
        <div class="flex items-center">
          <span class="mac-t-label mac-c-secondary flex items-center gap-1.5">
            <Code class="h-3 w-3" />
            {{ t("research_desk.founders_oss_velocity") }}
          </span>
          <span class="flex-1" />
          <a
            v-if="traction.repo_url"
            :href="traction.repo_url"
            target="_blank"
            rel="noopener noreferrer"
            class="mac-c-accent flex items-center gap-1"
          >
            <span class="mac-t-caption10 mac-mono">{{ repoLabel(traction.repo_url) }}</span>
            <ArrowUpRight class="h-2.5 w-2.5" />
          </a>
        </div>

        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <Star class="h-2.5 w-2.5" :style="{ color: 'var(--mac-yellow)' }" />
              {{ t("research_desk.founders_stars") }}
            </span>
            <span class="mac-t-metric-sm">{{ traction.stars != null ? Number(traction.stars).toLocaleString() : "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-yellow)' }">
              {{ traction.stars_growth_weekly || t("research_desk.founders_not_tracked") }}
            </span>
          </div>
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <GitFork class="h-2.5 w-2.5" :style="{ color: 'var(--mac-blue)' }" />
              {{ t("research_desk.founders_forks") }}
            </span>
            <span class="mac-t-metric-sm">{{ traction.forks != null ? Number(traction.forks).toLocaleString() : "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-blue)' }">{{ t("research_desk.founders_forks") }}</span>
          </div>
          <div v-if="traction.weekly_downloads" class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <ArrowDownCircle class="h-2.5 w-2.5" :style="{ color: 'var(--mac-green)' }" />
              {{ t("research_desk.founders_downloads") }}
            </span>
            <span class="mac-t-metric-sm">{{ traction.weekly_downloads }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-green)' }">{{ t("research_desk.founders_weekly") }}</span>
          </div>
          <div class="mac-tile flex flex-col gap-[3px] p-2">
            <span class="mac-t-label mac-c-secondary flex items-center gap-1">
              <History class="h-2.5 w-2.5" :style="{ color: 'var(--mac-purple)' }" />
              {{ t("research_desk.founders_commit_cadence") }}
            </span>
            <span class="mac-t-metric-sm">{{ traction.commit_cadence || "—" }}</span>
            <span class="mac-t-caption10 truncate" :style="{ color: 'var(--mac-purple)' }">{{ t("research_desk.founders_commit_cadence") }}</span>
          </div>
        </div>

        <!-- Traction signal callout -->
        <div
          class="mac-tile-tint flex items-center gap-2 p-2.5"
          style="--tint: var(--mac-orange)"
        >
          <Flame class="h-3.5 w-3.5 shrink-0" :style="{ color: 'var(--mac-orange)' }" />
          <span class="mac-t-label" :style="{ color: 'var(--mac-orange)' }">{{ t("research_desk.founders_traction_signal") }}</span>
          <span class="mac-t-caption10 font-semibold">{{ traction.inflection_signal || "—" }}</span>
        </div>
      </div>

      <span v-if="refreshError" class="mac-t-caption flex items-center gap-1.5" :style="{ color: 'var(--mac-red)' }">
        <AlertTriangle class="h-3 w-3 shrink-0" />
        {{ t("research_desk.founders_refresh_failed", { error: refreshError }) }}
      </span>

      <span
        v-if="researchError"
        class="mac-t-caption flex items-center gap-1.5"
        :style="{ color: 'var(--mac-orange)' }"
        data-testid="founder-research-error"
      >
        <AlertTriangle class="h-3 w-3 shrink-0" />
        {{ t("research_desk.research_failed") }} — {{ researchError }}
      </span>

      <span
        v-else-if="provenance"
        class="mac-t-caption10 mac-c-tertiary"
        data-testid="founder-provenance"
      >
        {{ t("research_desk.researched_by", { engine: provenance.engine }) }}
        <template v-if="provenance.model">({{ provenance.model }})</template>
        <template v-if="provenance.sources.length">
          · {{ t("research_desk.read_sources", { count: provenance.sources.length }) }}
        </template>
        <template v-else>· {{ t("research_desk.no_sources_reported") }}</template>
      </span>

      <span v-else class="mac-t-caption10 mac-c-tertiary">{{ t("research_desk.founders_built_from_record") }}</span>
    </template>

    <!-- Load failed -->
    <div v-else-if="loadFailed && !loading" class="flex flex-col items-center gap-2 py-8 text-center">
      <AlertTriangle class="mac-c-secondary h-8 w-8" stroke-width="1.5" />
      <span class="mac-t-headline" style="font-size: 15px">{{ t("research_desk.founders_load_failed") }}</span>
      <span class="mac-t-body mac-c-secondary max-w-sm">{{ t("research_desk.founders_load_failed_desc") }}</span>
      <button type="button" class="mac-btn mac-btn--sm" @click="loadFounders">
        {{ t("research_desk.retry") }}
      </button>
    </div>

    <!-- Loading -->
    <div v-else class="flex items-center justify-center gap-3 py-5">
      <span class="mac-spinner" />
      <span class="mac-t-subheadline mac-c-secondary">{{ t("research_desk.founders_loading") }}</span>
    </div>
  </div>
</template>
