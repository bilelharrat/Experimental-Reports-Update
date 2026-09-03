<script setup>
import { computed, inject, ref, unref, watch } from "vue";
import { ChevronRight, Search } from "lucide-vue-next";
import { useT } from "../i18n.js";
import { assembleDeskNews, filterDeskNews, newsAgeParts } from "../homeDesk.js";

const props = defineProps({
  bookIds: { type: Array, default: () => [] },
});
const emit = defineEmits(["open-company", "open-copilot", "open-news"]);

const t = useT();
const workspaceNews = inject("workspaceNews", ref([]));
const workspaceResearch = inject("workspaceResearch", ref([]));
const workspaceCompanies = inject("workspaceCompanies", ref([]));

const scope = ref("all");
const query = ref("");
const selectedId = ref("");

const feed = computed(() => [
  ...(unref(workspaceNews) || []),
  ...(unref(workspaceResearch) || []),
]);
const companies = computed(() => unref(workspaceCompanies) || []);
const assembled = computed(() =>
  assembleDeskNews({ feed: feed.value, companies: companies.value }),
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

const scopes = computed(() => [
  { id: "all", label: t("home.desk_scope_all") },
  { id: "book", label: t("home.desk_scope_book") },
  { id: "market", label: t("home.desk_scope_market") },
]);

function storyByline(row) {
  const source = row?.source || row?.companies?.[0]?.name || "";
  const age = newsAgeParts(row?.ts);
  let when = "";
  if (age?.unit === "now") when = t("home.cache_just_now");
  else if (age?.unit === "minutes") when = t("home.cache_minutes_ago", { n: age.n });
  else if (age?.unit === "hours") when = t("home.cache_hours_ago", { n: age.n });
  else if (age?.unit === "days") when = t("home.cache_days_ago", { n: age.n });
  return [source, when].filter(Boolean).join(" · ");
}

function selectRow(row) {
  selectedId.value = row.id;
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
    selectedId.value = list[Math.min(list.length - 1, index + 1)].id;
  } else if (event.key === "ArrowUp") {
    event.preventDefault();
    selectedId.value = list[Math.max(0, index - 1)].id;
  } else if (event.key === "Enter") {
    event.preventDefault();
    openSelectedSource();
  }
}

function canRead(row) {
  return Boolean(row?.url || row?.kind === "news" || row?.kind === "external_research");
}
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
      <label class="relative min-w-[12rem] max-w-xs flex-1">
        <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-muted" />
        <input
          v-model="query"
          type="search"
          class="news-search-field focus-ring"
          :placeholder="t('home.desk_search_placeholder')"
          :aria-label="t('home.desk_search_placeholder')"
        />
      </label>
    </div>

    <article v-if="selected" class="news-grouped mt-5 p-5 sm:p-6">
      <p class="text-caption1 font-semibold uppercase tracking-[0.04em] text-ink-muted">
        {{ storyByline(selected) }}
      </p>
      <h2 class="news-hero-title mt-2 text-ink-primary">
        {{ selected.title }}
      </h2>
      <p v-if="selected.summary" class="mt-3 max-w-2xl text-callout leading-relaxed text-ink-secondary">
        {{ selected.summary }}
      </p>
      <div class="mt-5 flex flex-wrap items-center gap-2">
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
      </div>
    </article>
    <div v-else class="news-grouped mt-5 px-5 py-10 text-center text-callout text-ink-muted">
      {{ t("home.desk_news_empty") }}
    </div>

    <div
      v-if="rest.length"
      class="news-grouped mt-4 overflow-hidden"
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
        class="news-story-row focus-ring"
        :aria-selected="selected?.id === row.id"
        @click="selectRow(row)"
      >
        <div class="min-w-0 flex-1">
          <div class="text-caption1 text-ink-muted">{{ storyByline(row) }}</div>
          <div class="mt-0.5 text-headline text-ink-primary">{{ row.title }}</div>
        </div>
        <ChevronRight class="h-4 w-4 shrink-0 text-ink-subtle" />
      </button>
    </div>
  </section>
</template>
