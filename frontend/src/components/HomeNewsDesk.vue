<script setup>
import { computed, inject, nextTick, ref, unref, watch } from "vue";
import {
  Building2,
  ChartColumn,
  GitMerge,
  Loader2,
  Maximize2,
  Minimize2,
  Newspaper,
  Package,
  RefreshCw,
  Search,
  Sparkles,
  Users,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import {
  assembleDeskNews,
  filterDeskNews,
  newsAgeParts,
  newsToneKey,
} from "../homeDesk.js";
import { briefCacheKey, cacheBrief, loadCachedBrief } from "../offlineCache.js";

const props = defineProps({
  bookIds: { type: Array, default: () => [] },
  expanded: { type: Boolean, default: false },
});
const emit = defineEmits(["open-company", "open-copilot", "open-news", "toggle-expand"]);

const t = useT();
const workspaceNews = inject("workspaceNews", ref([]));
const workspaceResearch = inject("workspaceResearch", ref([]));
const workspaceCompanies = inject("workspaceCompanies", ref([]));
const workspaceLiveNews = inject("workspaceLiveNews", ref([]));

const scope = ref("all");
const query = ref("");
const selectedId = ref("");
const leadEl = ref(null);

const brief = ref(null);
const briefLoading = ref(false);
const briefError = ref("");
let briefRequestId = 0;
let lastPrewarmKey = "";

const feed = computed(() => [
  ...(unref(workspaceNews) || []),
  ...(unref(workspaceResearch) || []),
]);
const companies = computed(() => unref(workspaceCompanies) || []);
const live = computed(() => unref(workspaceLiveNews) || []);
const assembled = computed(() =>
  assembleDeskNews({
    feed: feed.value,
    companies: companies.value,
    live: live.value,
  }),
);
const rows = computed(() =>
  filterDeskNews(assembled.value, {
    scope: scope.value,
    category: "",
    query: query.value,
    bookIds: props.bookIds,
  }),
);
const selected = computed(
  () => rows.value.find((row) => row.id === selectedId.value) || rows.value[0] || null,
);
const rest = computed(() =>
  rows.value.filter((row) => row.id !== selected.value?.id),
);

watch(rows, (list) => {
  if (!list.length) {
    selectedId.value = "";
    return;
  }
  if (!list.some((row) => row.id === selectedId.value)) {
    selectedId.value = list[0].id;
  }
});

watch(
  assembled,
  (list) => {
    maybePrewarm(list || []);
  },
  { immediate: true },
);

watch(
  selected,
  (row) => {
    openBriefing(row);
  },
  { immediate: true },
);

watch(appLanguage, () => {
  openBriefing(selected.value);
  lastPrewarmKey = "";
  maybePrewarm(assembled.value);
});

const scopes = computed(() => [
  { id: "all", label: t("home.desk_scope_all") },
  { id: "book", label: t("home.desk_scope_book") },
  { id: "market", label: t("home.desk_scope_market") },
]);

function storyByline(row) {
  const source = row?.source || row?.companyName || row?.companies?.[0]?.name || "";
  const age = newsAgeParts(row?.ts);
  let when = "";
  if (age?.unit === "now") when = t("home.cache_just_now");
  else if (age?.unit === "minutes") when = t("home.cache_minutes_ago", { n: age.n });
  else if (age?.unit === "hours") when = t("home.cache_hours_ago", { n: age.n });
  else if (age?.unit === "days") when = t("home.cache_days_ago", { n: age.n });
  return [source, when].filter(Boolean).join(" · ");
}

function leadTone(row) {
  return newsToneKey(row?.title || "", { withMint: false });
}

function thumbTone(row) {
  return newsToneKey(row?.title || "", { withMint: true });
}

function categorySymbol(category) {
  const c = String(category || "").toLowerCase();
  if (c.includes("earning")) return ChartColumn;
  if (c.includes("deal") || c.includes("m&a")) return GitMerge;
  if (c.includes("product")) return Package;
  if (c.includes("regulat") || c.includes("legal")) return Building2;
  if (c.includes("partner")) return Users;
  return Newspaper;
}

function briefField(payload, key) {
  if (!payload) return "";
  const lang = appLanguage.value || "en";
  const localized = payload[`${key}_${lang}`];
  if (Array.isArray(localized) && localized.length) return localized;
  if (typeof localized === "string" && localized.trim()) return localized;
  return payload[key] || (key.endsWith("s") ? [] : "");
}

function briefPayloadFor(row) {
  return {
    title: row.title,
    summary: row.summary || null,
    source: row.source || null,
    published_at: row.ts || null,
    company: row.companyName || row.companies?.[0]?.name || null,
    ticker: row.ticker || null,
    url: row.url || null,
    lang: appLanguage.value || "en",
  };
}

function maybePrewarm(list) {
  const top = (list || []).slice(0, 16);
  if (!top.length) return;
  const key = `${appLanguage.value || "en"}|${top.map((row) => row.title).join("|")}`;
  if (key === lastPrewarmKey) return;
  lastPrewarmKey = key;
  api
    .prewarmNewsBriefs({
      items: top.map((row) => ({
        title: row.title,
        summary: row.summary || null,
        source: row.source || null,
        published_at: row.ts || null,
        company: row.companyName || row.companies?.[0]?.name || null,
        ticker: row.ticker || null,
        url: row.url || null,
      })),
      lang: appLanguage.value || "en",
      limit: 16,
    })
    .catch(() => {});
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function openBriefing(row) {
  const requestId = ++briefRequestId;
  brief.value = null;
  briefError.value = "";
  if (!row?.title) {
    briefLoading.value = false;
    return;
  }
  const cacheKey = briefCacheKey(
    row.title,
    row.companyName || row.companies?.[0]?.name || null,
  );
  const cachedLocal = loadCachedBrief(cacheKey);
  if (cachedLocal) brief.value = cachedLocal;
  briefLoading.value = true;
  const company = row.companyName || row.companies?.[0]?.name || null;
  const lang = appLanguage.value || "en";
  try {
    const cached = await api.getNewsBrief({
      title: row.title,
      company,
      lang,
    });
    if (requestId !== briefRequestId) return;
    brief.value = cached;
    cacheBrief(cacheKey, cached);
    briefLoading.value = false;
  } catch (err) {
    if (requestId !== briefRequestId) return;
    if (err?.status !== 404) {
      // Fall through to generate; soft-fail only if generate also fails.
    }
    // Race: blocking generate (joins in-flight prewarm) vs polling the
    // cache so a sibling worker's finish shows up without waiting on our
    // own HTTP call's full timeout path.
    const payload = { ...briefPayloadFor(row), refresh: false };
    const generatePromise = api.postNewsBrief(payload).then((generated) => ({
      ok: true,
      brief: generated,
    }));
    const pollPromise = (async () => {
      for (let i = 0; i < 60; i += 1) {
        await sleep(1500);
        if (requestId !== briefRequestId) return { ok: false };
        try {
          const hit = await api.getNewsBrief({ title: row.title, company, lang });
          if (hit) return { ok: true, brief: hit };
        } catch {
          /* still missing */
        }
      }
      return { ok: false };
    })();
    try {
      const winner = await Promise.any([
        generatePromise,
        pollPromise.then((result) => {
          if (!result?.ok || !result.brief) {
            return Promise.reject(new Error("poll miss"));
          }
          return result;
        }),
      ]);
      if (requestId !== briefRequestId) return;
      brief.value = winner.brief;
      cacheBrief(cacheKey, winner.brief);
    } catch (genErr) {
      if (requestId !== briefRequestId) return;
      if (!brief.value) {
        const message =
          genErr?.errors?.[0]?.message ||
          genErr?.message ||
          t("news.briefing_failed");
        briefError.value = message;
      }
    } finally {
      if (requestId === briefRequestId) briefLoading.value = false;
    }
  }
}

async function regenerateBrief() {
  const row = selected.value;
  if (!row?.title || briefLoading.value) return;
  const requestId = ++briefRequestId;
  briefLoading.value = true;
  briefError.value = "";
  try {
    const generated = await api.postNewsBrief({
      ...briefPayloadFor(row),
      refresh: true,
    });
    if (requestId !== briefRequestId) return;
    brief.value = generated;
  } catch (err) {
    if (requestId !== briefRequestId) return;
    briefError.value = err?.message || t("news.briefing_failed");
  } finally {
    if (requestId === briefRequestId) briefLoading.value = false;
  }
}

function scrollLeadIntoView() {
  nextTick(() => {
    const node = leadEl.value;
    if (node && typeof node.scrollIntoView === "function") {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
}

function selectRow(row) {
  if (!row?.id) return;
  const same = selectedId.value === row.id;
  selectedId.value = row.id;
  if (!same) scrollLeadIntoView();
}

function openSelectedSource() {
  const row = selected.value;
  if (!row) return;
  emit("open-news", row);
}

function openCompany(company) {
  if (company?.id) emit("open-company", company);
}

function askCopilot() {
  const row = selected.value;
  if (!row) return;
  const company = row.companies[0];
  emit("open-copilot", {
    companyId: company?.id || null,
    prompt: t("home.desk_copilot_prompt", { title: row.title }),
    context: {
      surface: "home_desk",
      tab: "news",
      selection: {
        title: row.title,
        summary: row.summary,
        url: row.url,
        company_id: company?.id,
      },
    },
  });
}

function onListKeydown(event) {
  const list = rows.value;
  if (!list.length) return;
  const index = Math.max(
    0,
    list.findIndex((row) => row.id === selected.value?.id),
  );
  if (event.key === "ArrowDown") {
    event.preventDefault();
    selectRow(list[Math.min(list.length - 1, index + 1)]);
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    selectRow(list[Math.max(0, index - 1)]);
  } else if (event.key === "Enter") {
    event.preventDefault();
    openSelectedSource();
  }
}

function canRead(row) {
  return Boolean(
    row?.url ||
      row?.kind === "news" ||
      row?.kind === "external_research" ||
      row?.kind === "live_news",
  );
}

const briefHeadline = computed(() => String(briefField(brief.value, "headline") || "").trim());
const briefWhat = computed(() => String(briefField(brief.value, "what_happened") || "").trim());
const briefWhy = computed(() => String(briefField(brief.value, "why_it_matters") || "").trim());
const briefContext = computed(() => {
  const rows = briefField(brief.value, "context");
  return Array.isArray(rows) ? rows.filter(Boolean) : [];
});
const briefWatch = computed(() => {
  const rows = briefField(brief.value, "watch_next");
  return Array.isArray(rows) ? rows.filter(Boolean) : [];
});
const briefSources = computed(() =>
  Array.isArray(brief.value?.sources) ? brief.value.sources.filter((s) => s?.url) : [],
);
</script>

<template>
  <section class="min-w-0">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div
        class="segmented"
        role="tablist"
        :aria-label="t('home.desk_scope_label')"
      >
        <button
          v-for="item in scopes"
          :key="item.id"
          type="button"
          class="segmented-item focus-ring"
          :data-selected="scope === item.id"
          :aria-selected="scope === item.id"
          role="tab"
          @click="scope = item.id"
        >
          {{ item.label }}
        </button>
      </div>
      <div class="flex min-w-[12rem] max-w-md flex-1 items-center gap-2">
        <label class="relative min-w-0 flex-1">
          <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
          <input
            v-model="query"
            type="search"
            class="news-search-field focus-ring"
            :placeholder="t('home.desk_search_placeholder')"
            :aria-label="t('home.desk_search_placeholder')"
          />
        </label>
        <button
          type="button"
          class="yf-range-item inline-flex shrink-0 items-center gap-1 focus-ring"
          :data-selected="expanded"
          :aria-pressed="expanded"
          :aria-label="expanded ? t('radar.collapse_desk') : t('radar.expand_desk')"
          :title="expanded ? t('radar.collapse_desk') : t('radar.expand_desk')"
          @click="emit('toggle-expand')"
        >
          <Minimize2 v-if="expanded" class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <Maximize2 v-else class="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>{{ expanded ? t("radar.collapse_desk") : t("radar.expand_desk") }}</span>
        </button>
      </div>
    </div>

    <article
      v-if="selected"
      ref="leadEl"
      class="news-lead mt-5 overflow-hidden scroll-mt-4"
    >
      <div class="news-lead-banner" :data-tone="leadTone(selected)">
        <component
          :is="categorySymbol(selected.category)"
          class="news-lead-glyph"
          aria-hidden="true"
        />
        <div class="relative z-[1] flex flex-col gap-1.5 p-3.5">
          <span
            v-if="selected.ticker || selected.companyName || selected.companies[0]?.name"
            class="news-lead-badge"
          >
            {{ (selected.ticker || selected.companyName || selected.companies[0]?.name || "").toUpperCase() }}
          </span>
          <h2 class="news-lead-title">{{ selected.title }}</h2>
        </div>
      </div>
      <div class="space-y-3 p-3.5 sm:p-4">
        <p
          v-if="selected.summary"
          class="text-callout leading-relaxed text-ink-secondary line-clamp-8"
        >
          {{ selected.summary }}
        </p>
        <p class="text-caption1 text-ink-muted">{{ storyByline(selected) }}</p>
        <div class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="btn-filled focus-ring"
            :disabled="!canRead(selected)"
            @click="openSelectedSource"
          >
            {{ t("home.desk_open_source") }}
          </button>
          <button
            v-if="selected.companies[0]"
            type="button"
            class="btn-bordered focus-ring"
            @click="openCompany(selected.companies[0])"
          >
            {{ selected.companies[0].name }}
          </button>
          <button type="button" class="btn-bordered focus-ring" @click="askCopilot">
            {{ t("home.desk_ask_copilot") }}
          </button>
          <button
            type="button"
            class="btn-bordered focus-ring inline-flex items-center gap-1.5"
            :disabled="briefLoading"
            @click="regenerateBrief"
          >
            <RefreshCw class="h-3.5 w-3.5" :class="briefLoading ? 'animate-spin' : ''" />
            {{ t("news.regenerate") }}
          </button>
        </div>
      </div>

      <div class="news-brief-panel border-t border-border-subtle/70 px-3.5 py-4 sm:px-4">
        <div v-if="brief" class="space-y-5">
          <p
            v-if="briefHeadline && briefHeadline !== selected.title"
            class="font-display text-title3 text-ink-secondary"
          >
            {{ briefHeadline }}
          </p>
          <section v-if="briefWhat">
            <h3 class="news-brief-kicker">{{ t("news.what_happened") }}</h3>
            <p class="news-brief-body mt-2 whitespace-pre-wrap">{{ briefWhat }}</p>
          </section>
          <section v-if="briefWhy">
            <h3 class="news-brief-kicker">{{ t("news.why_it_matters") }}</h3>
            <p class="news-brief-body mt-2 whitespace-pre-wrap">{{ briefWhy }}</p>
          </section>
          <section v-if="briefContext.length">
            <h3 class="news-brief-kicker">{{ t("news.context") }}</h3>
            <ul class="mt-2 space-y-2">
              <li
                v-for="(line, idx) in briefContext"
                :key="`ctx-${idx}`"
                class="news-brief-bullet"
              >
                <span class="news-brief-dot" aria-hidden="true" />
                <span>{{ line }}</span>
              </li>
            </ul>
          </section>
          <section v-if="briefWatch.length">
            <h3 class="news-brief-kicker">{{ t("news.watch_next") }}</h3>
            <ul class="mt-2 space-y-2">
              <li
                v-for="(line, idx) in briefWatch"
                :key="`watch-${idx}`"
                class="news-brief-bullet"
              >
                <span class="news-brief-dot" aria-hidden="true" />
                <span>{{ line }}</span>
              </li>
            </ul>
          </section>
          <section v-if="briefSources.length">
            <h3 class="news-brief-kicker">{{ t("news.sources") }}</h3>
            <ul class="mt-2 space-y-1.5">
              <li v-for="(source, idx) in briefSources" :key="`src-${idx}`">
                <a
                  class="text-footnote text-accent hover:underline"
                  :href="source.url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {{ source.title || source.url }}
                </a>
              </li>
            </ul>
          </section>
          <p
            v-if="brief.confidence"
            class="news-confidence"
            :data-confidence="String(brief.confidence).toLowerCase()"
          >
            {{ brief.confidence }}
          </p>
        </div>
        <div v-else-if="briefLoading" class="news-brief-status">
          <Loader2 class="h-4 w-4 animate-spin text-accent" />
          <span>{{ t("news.briefing_auto") }}</span>
        </div>
        <div v-else class="news-brief-status flex-col items-start gap-2">
          <div class="flex items-center gap-2 text-headline text-ink-primary">
            <Sparkles class="h-4 w-4 text-accent" />
            {{ t("news.full_briefing") }}
          </div>
          <p class="text-footnote text-ink-secondary">{{ t("news.full_briefing_hint") }}</p>
          <button type="button" class="btn-filled focus-ring" @click="openBriefing(selected)">
            {{ t("news.read_briefing") }}
          </button>
        </div>
        <p v-if="briefError" class="mt-3 text-footnote text-danger">{{ briefError }}</p>
      </div>
    </article>
    <div v-else class="news-grouped mt-5 px-5 py-10 text-center text-callout text-ink-muted">
      {{ t("home.desk_news_empty") }}
    </div>

    <div v-if="rest.length" class="mt-5">
      <h3 class="mb-2 px-1 text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
        {{ t("news.latest") }}
      </h3>
      <div
        class="news-grouped overflow-hidden"
        role="listbox"
        tabindex="0"
        :aria-label="t('home.desk_more_stories')"
        @keydown="onListKeydown"
      >
        <button
          v-for="row in rest"
          :key="row.id"
          type="button"
          role="option"
          class="news-magazine-row focus-ring"
          :aria-selected="selected?.id === row.id"
          @click="selectRow(row)"
        >
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-1.5 text-caption2">
              <span
                v-if="row.ticker || row.companyName || row.companies[0]?.name"
                class="font-bold text-accent"
              >
                {{ row.ticker || row.companyName || row.companies[0]?.name }}
              </span>
              <span
                v-if="row.source && row.source !== row.companyName"
                class="text-ink-muted"
              >
                {{ row.source }}
              </span>
            </div>
            <div class="mt-1 text-headline text-ink-primary">{{ row.title }}</div>
            <p
              v-if="row.summary"
              class="mt-1.5 text-subhead leading-snug text-ink-secondary line-clamp-6"
            >
              {{ row.summary }}
            </p>
            <div class="mt-1.5 text-caption2 text-ink-subtle">{{ storyByline(row) }}</div>
          </div>
          <div class="news-thumb" :data-tone="thumbTone(row)" aria-hidden="true">
            <component :is="categorySymbol(row.category)" class="h-5 w-5 text-white/90" />
          </div>
        </button>
      </div>
    </div>
  </section>
</template>
