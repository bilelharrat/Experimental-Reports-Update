<script setup>
import { ref, computed, watch } from "vue";
import { useT } from "../../i18n.js";
import {
  Users,
  RotateCw,
  GitFork,
  Star,
  ExternalLink,
  Award,
  Briefcase,
  GraduationCap,
  Link as LinkIcon,
  AlertTriangle,
  Code2,
  Megaphone,
  Settings2,
} from "lucide-vue-next";
import { api } from "../../api.js";
import { confirmTokenSpend } from "../../confirmTokens.js";

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
const searching = ref(false);
const loadFailed = ref(false);
const founderData = ref(null);

async function loadFounders() {
  if (!props.companyId) return;
  loading.value = true;
  loadFailed.value = false;
  try {
    founderData.value = await api.getFounderDossier(props.companyId);
  } catch {
    founderData.value = null;
    loadFailed.value = true;
  } finally {
    loading.value = false;
  }
}

async function deepSearch() {
  if (!props.companyId || searching.value) return;
  if (!confirmTokenSpend()) return;
  searching.value = true;
  try {
    founderData.value = await api.deepSearchFounder(props.companyId);
    loadFailed.value = false;
  } catch {
    // Keep whatever is already on screen; the record read is the fallback.
    if (!founderData.value) loadFailed.value = true;
  } finally {
    searching.value = false;
  }
}

watch(() => props.companyId, loadFounders, { immediate: true });

// The dossier is the source of truth; the company record's own people lists
// are the fallback while it loads or when the request failed.
const foundersList = computed(() => {
  if (founderData.value?.founders?.length) return founderData.value.founders;
  if (founderData.value) return [];
  if (props.company?.team_profiles?.length) return props.company.team_profiles;
  if (props.company?.key_people?.length) return props.company.key_people;
  if (props.company?.leadership?.length) return props.company.leadership;
  return [];
});

const boardList = computed(() => {
  if (founderData.value?.advisors_and_board?.length) return founderData.value.advisors_and_board;
  if (founderData.value) return [];
  return props.company?.board_investors || [];
});

const headcount = computed(() => founderData.value?.team_headcount || null);

const traction = computed(
  () => founderData.value?.developer_traction || props.company?.developer_traction || null,
);

const hasPeople = computed(
  () => foundersList.value.length > 0 || boardList.value.length > 0 || Boolean(headcount.value) || Boolean(traction.value),
);

const headcountPills = computed(() => {
  const h = headcount.value;
  if (!h) return [];
  const pct = (v) => (v == null ? "—" : `${v}%`);
  return [
    {
      id: "total",
      icon: Users,
      tone: "text-sky-400",
      title: t("research_desk.total_team"),
      value: h.employee_count_estimate || "—",
      delta: h.open_roles_count != null ? t("research_desk.open_roles", { count: h.open_roles_count }) : (h.hiring_velocity || "—"),
    },
    { id: "eng", icon: Code2, tone: "text-indigo-400", title: t("research_desk.engineering"), value: pct(h.engineering_pct), delta: t("research_desk.of_headcount") },
    { id: "gtm", icon: Megaphone, tone: "text-emerald-400", title: t("research_desk.gtm_sales"), value: pct(h.gtm_sales_pct), delta: t("research_desk.of_headcount") },
    { id: "ops", icon: Settings2, tone: "text-amber-400", title: t("research_desk.operations"), value: pct(h.operations_pct), delta: t("research_desk.of_headcount") },
  ];
});

function personLink(person) {
  return person?.linkedin_url || person?.linkedin || person?.profile_url || person?.url || null;
}

function priorCompanies(person) {
  const list = person?.past_companies || person?.prior_companies || person?.previous_companies;
  return Array.isArray(list) ? list.filter(Boolean) : [];
}

function hasExit(person) {
  return Boolean(person?.prior_exits || person?.exits?.length);
}

function initials(name) {
  const parts = String(name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return String(name || "?").slice(0, 2).toUpperCase();
}
</script>

<template>
  <div class="rounded-xl border border-border/40 bg-card/60 p-5 backdrop-blur-md" data-testid="founder-radar-card">
    <!-- Header -->
    <div class="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/40 pb-3">
      <div>
        <h3 class="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Users class="h-4 w-4 text-primary" />
          {{ t("research_desk.founders_team_radar") }}
        </h3>
        <p class="text-xs text-muted-foreground">
          {{ t("research_desk.founders_subtitle") }}
        </p>
      </div>

      <button
        type="button"
        class="inline-flex items-center gap-1.5 rounded-md border border-border/50 bg-background/50 px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted disabled:opacity-50"
        :disabled="searching || loading"
        data-testid="founder-refresh"
        @click="deepSearch"
      >
        <RotateCw class="h-3 w-3" :class="{ 'animate-spin': searching || loading }" />
        <span>{{ t("research_desk.refresh") }}</span>
      </button>
    </div>

    <!-- Load failure -->
    <div
      v-if="loadFailed && !hasPeople"
      class="flex flex-col items-start gap-2 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs"
      data-testid="founder-load-failed"
    >
      <div class="flex items-center gap-1.5 font-medium text-red-300">
        <AlertTriangle class="h-3.5 w-3.5" />
        <span>{{ t("research_desk.founders_load_failed") }}</span>
      </div>
      <button
        type="button"
        class="rounded-md border border-border/50 bg-background/50 px-2.5 py-1 text-xs font-medium text-foreground transition hover:bg-muted"
        @click="loadFounders"
      >
        {{ t("research_desk.retry") }}
      </button>
    </div>

    <template v-else>
      <!-- Developer traction banner -->
      <div
        v-if="traction"
        class="mb-4 flex flex-wrap items-center gap-4 rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs"
      >
        <div class="flex items-center gap-1.5 font-medium text-foreground">
          <GitFork class="h-3.5 w-3.5 text-primary" />
          <span>{{ t("research_desk.open_source_traction") }}:</span>
        </div>
        <div v-if="traction.stars != null" class="flex items-center gap-1 font-mono text-muted-foreground">
          <Star class="h-3 w-3 text-amber-400" />
          <span>{{ traction.stars }} {{ t("research_desk.stars") }}</span>
        </div>
        <div v-if="traction.velocity || traction.commit_cadence" class="font-mono text-muted-foreground">
          {{ t("research_desk.velocity") }}: {{ traction.velocity || traction.commit_cadence }}
        </div>
        <div v-if="traction.repo || traction.repo_url" class="ml-auto">
          <a
            :href="traction.repo || traction.repo_url"
            target="_blank"
            rel="noopener noreferrer"
            class="inline-flex items-center gap-1 text-primary hover:underline"
          >
            <span>{{ t("research_desk.repository") }}</span>
            <ExternalLink class="h-3 w-3" />
          </a>
        </div>
      </div>

      <!-- Leadership -->
      <section v-if="foundersList.length" class="mb-4" data-testid="founder-leadership">
        <div class="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          <span>{{ t("research_desk.leadership") }}</span>
          <span class="font-mono normal-case tracking-normal">{{ t("research_desk.key_people_count", { count: foundersList.length }) }}</span>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <article
            v-for="(person, idx) in foundersList"
            :key="person.name || idx"
            class="flex flex-col justify-between rounded-lg border border-border/40 bg-background/40 p-3.5 transition hover:border-border/80"
          >
            <div>
              <div class="flex items-start gap-2.5">
                <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[11px] font-bold text-primary">
                  {{ initials(person.name) }}
                </span>
                <div class="min-w-0 flex-1">
                  <h4 class="truncate text-sm font-semibold text-foreground">{{ person.name }}</h4>
                  <p class="text-xs text-muted-foreground">{{ person.role || person.title || "Founder" }}</p>
                </div>
                <span
                  v-if="hasExit(person)"
                  class="inline-flex shrink-0 items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400"
                >
                  <Award class="h-2.5 w-2.5" />
                  {{ t("research_desk.prior_exit") }}
                </span>
                <a
                  v-if="personLink(person)"
                  :href="personLink(person)"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="shrink-0 text-muted-foreground transition hover:text-primary"
                  :title="t('research_desk.profile_link')"
                >
                  <LinkIcon class="h-3.5 w-3.5" />
                </a>
              </div>

              <div v-if="person.pedigree_tags?.length" class="mt-2 flex flex-wrap gap-1">
                <span
                  v-for="tag in person.pedigree_tags"
                  :key="tag"
                  class="rounded-full bg-sky-500/10 px-2 py-0.5 text-[10px] font-medium text-sky-300"
                >
                  {{ tag }}
                </span>
              </div>

              <p v-if="person.bio || person.background" class="mt-2 text-xs leading-relaxed text-muted-foreground">
                {{ person.bio || person.background }}
              </p>
            </div>

            <div
              v-if="priorCompanies(person).length || person.education || person.prior_exits"
              class="mt-3 space-y-1 border-t border-border/30 pt-2 text-[11px] text-muted-foreground"
            >
              <div v-if="priorCompanies(person).length" class="flex items-center gap-1">
                <Briefcase class="h-3 w-3 shrink-0" />
                <span>Ex-{{ priorCompanies(person).join(", ") }}</span>
              </div>
              <div v-if="person.education" class="flex items-center gap-1">
                <GraduationCap class="h-3 w-3 shrink-0" />
                <span class="truncate">{{ person.education }}</span>
              </div>
              <div v-if="person.prior_exits" class="flex items-center gap-1 text-emerald-400">
                <Award class="h-3 w-3 shrink-0" />
                <span>{{ t("research_desk.prior_exit") }}: {{ person.prior_exits }}</span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <!-- Board & advisors -->
      <section v-if="boardList.length" class="mb-4" data-testid="founder-board">
        <div class="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          <span>{{ t("research_desk.board_advisors") }}</span>
          <span class="font-mono normal-case tracking-normal">{{ t("research_desk.members_count", { count: boardList.length }) }}</span>
        </div>
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <article
            v-for="(person, idx) in boardList"
            :key="person.name || idx"
            class="flex items-start gap-2.5 rounded-lg border border-border/40 bg-background/40 p-3.5 transition hover:border-border/80"
          >
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-[11px] font-bold text-muted-foreground">
              {{ initials(person.name) }}
            </span>
            <div class="min-w-0 flex-1">
              <h4 class="truncate text-sm font-semibold text-foreground">{{ person.name }}</h4>
              <p class="text-xs text-muted-foreground">{{ person.role || person.title || "Board / Investor" }}</p>
              <p v-if="person.bio" class="mt-1.5 text-xs leading-relaxed text-muted-foreground">{{ person.bio }}</p>
            </div>
            <a
              v-if="personLink(person)"
              :href="personLink(person)"
              target="_blank"
              rel="noopener noreferrer"
              class="shrink-0 text-muted-foreground transition hover:text-primary"
              :title="t('research_desk.profile_link')"
            >
              <LinkIcon class="h-3.5 w-3.5" />
            </a>
          </article>
        </div>
      </section>

      <!-- Headcount -->
      <section v-if="headcountPills.length" class="mb-4" data-testid="founder-headcount">
        <div class="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
          <span>{{ t("research_desk.headcount") }}</span>
          <span v-if="headcount?.hiring_velocity" class="font-mono normal-case tracking-normal">{{ headcount.hiring_velocity }}</span>
        </div>
        <div class="flex gap-2.5 overflow-x-auto pb-1">
          <div
            v-for="pill in headcountPills"
            :key="pill.id"
            class="w-[118px] shrink-0 rounded-lg border border-border/40 bg-background/40 p-2.5"
          >
            <div class="flex items-center gap-1 text-[10px] text-muted-foreground">
              <component :is="pill.icon" class="h-3 w-3" :class="pill.tone" />
              <span>{{ pill.title }}</span>
            </div>
            <div class="mt-1 font-mono text-sm font-semibold text-foreground">{{ pill.value }}</div>
            <div class="truncate text-[10px]" :class="pill.tone">{{ pill.delta }}</div>
          </div>
        </div>
      </section>

      <!-- Empty state -->
      <div v-if="!hasPeople && !loading" class="py-8 text-center text-xs text-muted-foreground" data-testid="founder-empty">
        {{ t("research_desk.no_team_profiles") }}
      </div>

      <p v-if="founderData && hasPeople" class="text-[10px] text-muted-foreground/70">
        {{ t("research_desk.built_from_record") }}
      </p>
    </template>
  </div>
</template>
