<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  Activity,
  Bell,
  ChevronDown,
  ChevronRight,
  FlaskConical,
  Home,
  Link as LinkIcon,
  LogOut,
  Newspaper,
  ScrollText,
  UploadCloud,
} from "lucide-vue-next";
import brandLogoUrl from "../assets/berkeley-summit-house.svg";
import { sessionEmail, signOut } from "../auth.js";
import { useT } from "../i18n.js";

const t = useT();

const props = defineProps({
  reports: { type: Array, default: () => [] },
  news: { type: Array, default: () => [] },
  externalResearch: { type: Array, default: () => [] },
  hormuz: { type: Array, default: () => [] },
  companies: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

const signingOut = ref(false);
const expandedBuckets = ref(new Set());

async function onSignOut() {
  if (signingOut.value) return;
  signingOut.value = true;
  try {
    await signOut();
  } finally {
    signingOut.value = false;
  }
}

function monogram(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function fmtAge(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return t("sidebar.age_now");
  if (sec < 3600) return t("sidebar.age_minutes", { n: Math.round(sec / 60) });
  if (sec < 86400) return t("sidebar.age_hours", { n: Math.round(sec / 3600) });
  return t("sidebar.age_days", { n: Math.round(sec / 86400) });
}

function bucketFor(company) {
  const explicit = String(
    company.investment_bucket || company.bucket || company.pipeline_stage || "",
  ).toLowerCase();
  if (explicit.includes("pipeline") || explicit.includes("review")) return "pipeline";
  if (explicit.includes("watch") || explicit.includes("top")) return "watchlist";
  if (explicit.includes("portfolio")) return "portfolio";
  if (company.company_type === "public" || company.status === "public") return "watchlist";
  return "portfolio";
}

const companyBuckets = computed(() => {
  const buckets = {
    portfolio: [],
    pipeline: [],
    watchlist: [],
  };
  for (const company of props.companies || []) {
    if (!company?.id) continue;
    const key = bucketFor(company);
    buckets[key].push(company);
  }
  for (const key of Object.keys(buckets)) {
    buckets[key].sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));
  }
  // Labels resolved inside the computed (not a module constant) so they
  // stay reactive when the app language changes.
  return [
    { id: "portfolio", label: t("sidebar.portfolio"), items: buckets.portfolio },
    { id: "pipeline", label: t("sidebar.pipeline"), items: buckets.pipeline },
    { id: "watchlist", label: t("sidebar.top_players"), items: buckets.watchlist },
  ];
});

function visibleCompanies(bucket) {
  if (expandedBuckets.value.has(bucket.id)) return bucket.items;
  return bucket.items.slice(0, 4);
}

function toggleBucket(id) {
  const next = new Set(expandedBuckets.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedBuckets.value = next;
}

const marketRadar = computed(() => {
  const rows = [...props.news, ...props.externalResearch]
    .filter((item) => item?.id)
    .sort((a, b) => String(b.captured_at || "").localeCompare(String(a.captured_at || "")));
  return rows.slice(0, 5);
});

function radarRoute(item) {
  if (item.kind === "external_research") {
    return { name: "external-research", params: { id: item.id } };
  }
  return { name: "external-news", params: { id: item.id } };
}

function researchStatus(company) {
  const raw = String(company.research_status || company.analysis_status || company.status || "")
    .toLowerCase();
  if (/analyz|running|progress|queued/.test(raw)) {
    return { label: t("sidebar.status_analyzing"), classes: "bg-warning-soft text-warning-ink" };
  }
  if (/review|draft|pending/.test(raw)) {
    return { label: t("sidebar.status_review"), classes: "bg-danger-soft text-danger-ink" };
  }
  return { label: t("sidebar.status_researched"), classes: "bg-accent-soft text-accent-ink" };
}

function companyCategory(company) {
  const translated = company.translation || {};
  return translated.industry || translated.sector || company.industry || company.sector || t("sidebar.tracked");
}

const userName = computed(() => {
  const localPart = String(sessionEmail.value || "").split("@")[0] || t("sidebar.researcher");
  return localPart
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
});
</script>

<template>
  <aside
    class="rail-gradient flex max-h-[26rem] w-full shrink-0 flex-col overflow-hidden border-b border-subtle lg:sticky lg:top-0 lg:h-screen lg:max-h-none lg:w-[288px] lg:border-b-0 lg:border-r"
  >
    <div class="px-5 pb-4 pt-4">
      <RouterLink
        to="/"
        class="block rounded focus-ring"
      >
        <img
          :src="brandLogoUrl"
          alt="Berkeley Summit House"
          class="h-auto w-[66px] max-w-full brightness-0 invert"
        />
        <span class="mt-1 block text-xs font-medium text-white/80">{{ t("nav.research_center") }}</span>
      </RouterLink>
    </div>

    <div class="flex-1 overflow-y-auto px-3 pb-4">
      <RouterLink
        :to="{ name: 'home' }"
        class="mb-3 flex items-center gap-2 rounded-row border border-white/40 bg-white/80 px-3 py-2 text-sm font-semibold text-ink-primary shadow-card hover:bg-white focus-ring"
      >
        <Home class="h-4 w-4 text-accent-ink" />
        <span>{{ t("nav.home") }}</span>
      </RouterLink>

      <section class="rounded-row border border-subtle bg-white/[0.88] p-3 shadow-card">
        <div class="vogue-label mb-2">{{ t("sidebar.quick_intake") }}</div>
        <div class="grid gap-2">
          <RouterLink
            :to="{ name: 'home', query: { intake: 'link' } }"
            class="flex items-center gap-2 rounded-row border border-subtle bg-surface px-3 py-2 text-left text-sm text-ink-primary hover:border-accent hover:bg-accent-soft focus-ring"
          >
            <span class="grid h-7 w-7 place-items-center rounded-chip bg-accent-soft"><LinkIcon class="h-4 w-4 text-accent" /></span>
            <span>{{ t("sidebar.submit_link") }}</span>
          </RouterLink>
          <RouterLink
            :to="{ name: 'home', query: { intake: 'upload' } }"
            class="flex items-center gap-2 rounded-row border border-subtle bg-surface px-3 py-2 text-left text-sm text-ink-primary hover:border-accent hover:bg-accent-soft focus-ring"
          >
            <span class="grid h-7 w-7 place-items-center rounded-chip bg-ink-primary"><UploadCloud class="h-4 w-4 text-white" /></span>
            <span>{{ t("sidebar.upload_research") }}</span>
          </RouterLink>
          <RouterLink
            :to="{ name: 'home', query: { intake: 'note' } }"
            class="flex items-center gap-2 rounded-row border border-subtle bg-surface px-3 py-2 text-left text-sm text-ink-primary hover:border-accent hover:bg-accent-soft focus-ring"
          >
            <span class="grid h-7 w-7 place-items-center rounded-chip bg-danger-soft"><ScrollText class="h-4 w-4 text-danger" /></span>
            <span>{{ t("sidebar.add_note") }}</span>
          </RouterLink>
        </div>
      </section>

      <section class="mt-5">
        <div class="mb-2 flex items-center justify-between px-1">
          <div class="vogue-label">{{ t("sidebar.companies") }}</div>
          <span class="mono-data text-[11px] text-ink-muted">{{
            loading && companies.length === 0 ? "—" : companies.length
          }}</span>
        </div>
        <div v-if="loading && companies.length === 0" class="px-3 py-2 text-sm text-ink-muted">
          {{ t("common.loading") }}
        </div>
        <div v-else-if="error" class="px-3 py-2 text-sm text-danger">
          {{ t("sidebar.load_error") }}
        </div>
        <div v-else class="space-y-4">
          <div v-for="bucket in companyBuckets" :key="bucket.id">
            <div class="mb-1 flex items-center justify-between px-1">
              <div class="text-xs font-semibold text-ink-primary">{{ bucket.label }}</div>
              <span class="mono-data rounded-full bg-white/[0.70] px-2 py-0.5 text-[10px] text-ink-muted">
                {{ bucket.items.length }}
              </span>
            </div>
            <div
              v-if="bucket.items.length === 0"
              class="rounded-row border border-dashed border-subtle bg-white/50 px-3 py-2 text-xs text-ink-muted"
            >
              {{ t("sidebar.no_companies") }}
            </div>
            <div v-else class="space-y-1">
              <RouterLink
                v-for="company in visibleCompanies(bucket)"
                :key="company.id"
                :to="{ name: 'research', params: { companyId: company.id } }"
                class="flex min-w-0 items-center gap-2 rounded-row px-2 py-2 text-sm text-ink-secondary hover:bg-white/[0.78] hover:text-ink-primary focus-ring"
              >
                <span
                  class="mono-data grid h-7 w-7 shrink-0 place-items-center rounded-chip bg-surface text-[11px] font-bold text-accent-ink ring-1 ring-subtle"
                >
                  {{ monogram(company.name) }}
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate font-semibold">{{ company.name }}</span>
                  <span class="block truncate text-[11px] text-ink-muted">
                    {{ companyCategory(company) }}
                  </span>
                </span>
                <span
                  class="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold"
                  :class="researchStatus(company).classes"
                >
                  {{ researchStatus(company).label }}
                </span>
              </RouterLink>
              <button
                v-if="bucket.items.length > 4"
                type="button"
                @click="toggleBucket(bucket.id)"
                class="ml-1 inline-flex items-center gap-1 rounded-full px-2 py-1 text-xs text-ink-muted hover:bg-white/[0.70] hover:text-ink-primary focus-ring"
              >
                <ChevronDown v-if="expandedBuckets.has(bucket.id)" class="h-3 w-3" />
                <ChevronRight v-else class="h-3 w-3" />
                <span>
                  {{
                    expandedBuckets.has(bucket.id)
                      ? t("sidebar.show_less")
                      : t("sidebar.show_all", { count: bucket.items.length })
                  }}
                </span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="mt-5">
        <div class="mb-2 flex items-center gap-1.5 px-1">
          <Bell class="h-3.5 w-3.5 text-ink-muted" />
          <div class="vogue-label">{{ t("sidebar.market_radar") }}</div>
        </div>
        <div class="space-y-1">
          <div
            v-if="marketRadar.length === 0"
            class="rounded-row border border-dashed border-subtle bg-white/50 px-3 py-2 text-xs text-ink-muted"
          >
            {{ t("empty.no_news") }}
          </div>
          <RouterLink
            v-for="item in marketRadar"
            :key="item.id"
            :to="radarRoute(item)"
            class="block rounded-row px-3 py-2 hover:bg-white/[0.78] focus-ring"
          >
            <div class="line-clamp-2 text-sm font-semibold leading-snug text-ink-primary">
              {{ item.title || item.source_url || t("sidebar.untitled_signal") }}
            </div>
            <div class="mt-0.5 flex items-center gap-1 text-[11px] text-ink-muted">
              <Newspaper class="h-3 w-3" />
              <span>{{ item.domain || item.source_company || t("sidebar.market_signal") }}</span>
              <span>· {{ fmtAge(item.captured_at) }}</span>
            </div>
          </RouterLink>
        </div>
      </section>

      <section class="mt-5 space-y-1">
        <RouterLink
          :to="{ name: 'stock-research' }"
          class="flex items-center gap-2 rounded-row px-3 py-2 text-sm font-semibold text-ink-primary hover:bg-white/[0.78] focus-ring"
        >
          <Activity class="h-4 w-4 text-accent" />
          <span>{{ t("sidebar.stock") }}</span>
          <span class="ml-auto text-[11px] font-normal text-ink-muted">{{ t("sidebar.public_market_research") }}</span>
        </RouterLink>
        <RouterLink
          :to="{ name: 'innovation-lab' }"
          class="flex items-center gap-2 rounded-row px-3 py-2 text-sm font-semibold text-ink-primary hover:bg-white/[0.78] focus-ring"
        >
          <FlaskConical class="h-4 w-4 text-accent" />
          <span>{{ t("sidebar.innovation_lab") }}</span>
        </RouterLink>
      </section>
    </div>

    <div class="border-t border-subtle bg-white/[0.65] px-3 py-3">
      <div v-if="sessionEmail" class="flex items-center gap-2">
        <div class="mono-data grid h-9 w-9 shrink-0 place-items-center rounded-full bg-ink-primary text-xs font-bold text-white">
          {{ monogram(userName) }}
        </div>
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-semibold text-ink-primary">{{ userName }}</div>
          <div class="truncate text-[11px] text-ink-muted" :title="sessionEmail">
            {{ sessionEmail }}
          </div>
        </div>
        <button
          type="button"
          @click="onSignOut"
          :disabled="signingOut"
          class="rounded-full p-1.5 text-ink-muted hover:bg-surface hover:text-ink-primary focus-ring disabled:opacity-50"
          :title="t('auth.sign_out')"
          :aria-label="t('auth.sign_out')"
        >
          <LogOut class="h-4 w-4" />
        </button>
      </div>
    </div>
  </aside>
</template>
