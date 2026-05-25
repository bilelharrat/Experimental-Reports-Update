<script setup>
import { computed, ref } from "vue";
import { RouterLink } from "vue-router";
import {
  FileText,
  Loader2,
  Home,
  Globe,
  LogOut,
  Newspaper,
  ScrollText,
  ClipboardList,
  User,
} from "lucide-vue-next";
import { appLanguage, setAppLanguage } from "../state.js";
import { sessionEmail, signOut } from "../auth.js";
import { useT } from "../i18n.js";

const signingOut = ref(false);
async function onSignOut() {
  if (signingOut.value) return;
  signingOut.value = true;
  try {
    await signOut();
  } finally {
    signingOut.value = false;
  }
}

const t = useT();

const props = defineProps({
  reports: { type: Array, default: () => [] },
  news: { type: Array, default: () => [] },
  externalResearch: { type: Array, default: () => [] },
  hormuz: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: null },
});

function fmtAge(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const sec = Math.max(0, Math.round((Date.now() - d.getTime()) / 1000));
  if (sec < 60) return "now";
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  if (sec < 86400) return `${Math.round(sec / 3600)}h`;
  return `${Math.round(sec / 86400)}d`;
}

function routeFor(item) {
  if (item.kind === "news") return { name: "external-news", params: { id: item.id } };
  if (item.kind === "external_research")
    return { name: "external-research", params: { id: item.id } };
  if (item.kind === "hormuz_research")
    return { name: "hormuz-research", params: { id: item.id } };
  return { name: "home" };
}

// /api/reports can include non-company reports, but this sidebar section
// links into /research/:companyId. Keep those unrouteable records out of the
// RouterLink render path so a null company_id cannot crash Vue Router.
const reports = computed(() => props.reports.filter((r) => r?.company_id));
</script>

<template>
  <aside
    class="w-72 shrink-0 border-r border-subtle bg-surface flex flex-col h-screen sticky top-0"
  >
    <div class="px-5 py-3 border-b border-subtle">
      <RouterLink
        to="/"
        class="flex items-center gap-3 text-ink-primary font-display text-base font-semibold focus-ring rounded"
      >
        <img
          src="/app-icon.png"
          alt="BSH"
          class="h-12 w-12 rounded-lg object-cover shrink-0"
        />
        <span class="leading-tight">{{ t("nav.research_center") }}</span>
      </RouterLink>
    </div>

    <div class="mx-3 mt-3 flex items-center gap-2">
      <RouterLink
        to="/"
        class="flex-1 min-w-0 flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-ink-secondary hover:bg-surface-muted focus-ring"
      >
        <Home class="h-4 w-4" />
        <span>{{ t("nav.home") }}</span>
      </RouterLink>
      <div
        class="shrink-0 inline-flex rounded-md border border-subtle overflow-hidden text-xs"
        role="group"
        :aria-label="t('lang.app_language')"
      >
        <button
          type="button"
          @click="setAppLanguage('en')"
          :class="[
            'px-2 py-1 focus-ring transition-colors',
            appLanguage === 'en'
              ? 'bg-accent text-white'
              : 'text-ink-secondary hover:bg-surface-muted',
          ]"
          :aria-pressed="appLanguage === 'en'"
        >
          EN
        </button>
        <button
          type="button"
          @click="setAppLanguage('zh')"
          :class="[
            'px-2 py-1 focus-ring transition-colors border-l border-subtle',
            appLanguage === 'zh'
              ? 'bg-accent text-white'
              : 'text-ink-secondary hover:bg-surface-muted',
          ]"
          :aria-pressed="appLanguage === 'zh'"
        >
          中
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-y-auto px-2 pb-4">
      <!-- Recent Reports -->
      <div
        class="px-3 pt-5 pb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted flex items-center gap-1.5"
      >
        <ClipboardList class="h-3 w-3" />
        {{ t("section.recent_reports") }}
      </div>
      <div class="space-y-1">
        <div
          v-if="loading && reports.length === 0"
          class="px-3 py-2 text-sm text-ink-muted flex items-center gap-2"
        >
          <Loader2 class="h-4 w-4 animate-spin" /> Loading…
        </div>
        <div v-else-if="error" class="px-3 py-2 text-sm text-danger">
          {{ error }}
        </div>
        <div
          v-else-if="reports.length === 0"
          class="px-3 py-2 text-xs text-ink-subtle"
        >
          {{ t("empty.no_reports") }}
        </div>
        <RouterLink
          v-for="r in reports"
          :key="r.id"
          :to="{
            name: 'research',
            params: { companyId: r.company_id },
            query: { report: r.id },
          }"
          class="block px-3 py-2 rounded-lg hover:bg-surface-muted focus-ring"
        >
          <div class="flex items-start gap-2">
            <FileText class="h-4 w-4 mt-0.5 text-ink-muted shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-ink-primary truncate">
                {{ r.company_name || r.company_id }}
              </div>
              <div class="text-xs text-ink-muted truncate">
                {{ r.report_type }} · {{ r.audience }}
              </div>
              <div class="mt-1 flex items-center gap-2 text-xs">
                <span
                  v-if="r.status === 'complete'"
                  class="px-1.5 py-0.5 rounded bg-success-soft text-success-ink"
                  >{{ t("status.done") }}</span
                >
                <span
                  v-else-if="r.status === 'running'"
                  class="px-1.5 py-0.5 rounded bg-warning-soft text-warning-ink"
                  >{{ r.progress }}%</span
                >
                <span
                  v-else
                  class="px-1.5 py-0.5 rounded bg-surface-muted text-ink-muted"
                  >{{ r.status }}</span
                >
              </div>
            </div>
          </div>
        </RouterLink>
      </div>

      <!-- News -->
      <div
        class="px-3 pt-6 pb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted flex items-center gap-1.5"
      >
        <Newspaper class="h-3 w-3" />
        {{ t("section.news") }}
      </div>
      <div class="max-h-[26rem] overflow-y-auto pr-1 space-y-1">
        <div
          v-if="news.length === 0"
          class="px-3 py-2 text-xs text-ink-subtle"
        >
          {{ t("empty.no_news") }}
        </div>
        <RouterLink
          v-for="item in news"
          :key="item.id"
          :to="routeFor(item)"
          class="block px-3 py-2 rounded-lg hover:bg-surface-muted focus-ring"
        >
          <div class="flex items-start gap-2">
            <Globe
              class="h-4 w-4 mt-0.5 text-ink-muted shrink-0"
            />
            <div class="min-w-0 flex-1">
              <div class="text-[15px] font-semibold leading-snug text-ink-primary line-clamp-2">
                {{ item.title || item.source_url || "Untitled" }}
              </div>
              <div class="mt-0.5 text-[11px] text-ink-muted truncate">
                <span>{{ item.domain || item.site_name || "link" }}</span>
                <span class="text-ink-subtle">
                  · {{ fmtAge(item.captured_at) }} ago</span
                >
                <span
                  v-if="item.language"
                  class="ml-1 px-1 py-0.5 rounded bg-surface-muted text-ink-muted font-mono text-[10px] uppercase"
                  >{{ item.language }}</span
                >
              </div>
              <div
                v-if="item.summary"
                class="mt-0.5 text-[11px] text-ink-secondary line-clamp-2"
              >
                {{ item.summary }}
              </div>
              <div
                v-if="
                  item.status &&
                  item.status !== 'ready' &&
                  item.status !== 'complete'
                "
                class="mt-1 flex items-center gap-1"
              >
                <span
                  v-if="
                    item.status === 'analyzing' ||
                    item.status === 'fetching' ||
                    item.status === 'extracting' ||
                    item.status === 'queued'
                  "
                  class="px-1 py-0.5 rounded bg-warning-soft text-warning-ink text-[10px] inline-flex items-center gap-0.5"
                >
                  <Loader2 class="h-2.5 w-2.5 animate-spin" />
                  {{ item.status }}
                </span>
                <span
                  v-else-if="item.status === 'failed'"
                  class="px-1 py-0.5 rounded bg-danger-soft text-danger-ink text-[10px]"
                  >Failed</span
                >
              </div>
            </div>
          </div>
        </RouterLink>
      </div>

      <!-- External Research -->
      <div
        class="px-3 pt-6 pb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted flex items-center gap-1.5"
      >
        <Globe class="h-3 w-3" />
        {{ t("section.external_research") }}
      </div>
      <div class="max-h-[26rem] overflow-y-auto pr-1 space-y-1">
        <div
          v-if="externalResearch.length === 0"
          class="px-3 py-2 text-xs text-ink-subtle"
        >
          {{ t("empty.no_external_research") }}
        </div>
        <RouterLink
          v-for="item in externalResearch"
          :key="item.id"
          :to="routeFor(item)"
          class="block px-3 py-2 rounded-lg hover:bg-surface-muted focus-ring"
        >
          <div class="flex items-start gap-2">
            <FileText class="h-4 w-4 mt-0.5 text-ink-muted shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="text-[15px] font-semibold leading-snug text-ink-primary line-clamp-2">
                {{ item.title || "Untitled" }}
              </div>
              <div class="mt-0.5 text-[11px] text-ink-muted truncate">
                <span>{{ item.source_company || "external" }}</span>
                <span class="text-ink-subtle">
                  · {{ fmtAge(item.captured_at) }} ago</span
                >
                <span
                  v-if="item.language"
                  class="ml-1 px-1 py-0.5 rounded bg-surface-muted text-ink-muted font-mono text-[10px] uppercase"
                  >{{ item.language }}</span
                >
              </div>
              <div
                v-if="item.summary"
                class="mt-0.5 text-[11px] text-ink-secondary line-clamp-2"
              >
                {{ item.summary }}
              </div>
              <div
                v-if="
                  item.status &&
                  item.status !== 'ready' &&
                  item.status !== 'complete'
                "
                class="mt-1 flex items-center gap-1"
              >
                <span
                  v-if="
                    item.status === 'analyzing' ||
                    item.status === 'extracting' ||
                    item.status === 'queued'
                  "
                  class="px-1 py-0.5 rounded bg-warning-soft text-warning-ink text-[10px] inline-flex items-center gap-0.5"
                >
                  <Loader2 class="h-2.5 w-2.5 animate-spin" />
                  {{ item.status }}
                </span>
                <span
                  v-else-if="item.status === 'failed'"
                  class="px-1 py-0.5 rounded bg-danger-soft text-danger-ink text-[10px]"
                  >Failed</span
                >
              </div>
            </div>
          </div>
        </RouterLink>
      </div>

      <!-- Hormuz Research -->
      <div
        class="px-3 pt-6 pb-2 text-xs font-semibold uppercase tracking-wide text-ink-muted flex items-center gap-1.5"
      >
        <ScrollText class="h-3 w-3" />
        {{ t("section.hormuz_research") }}
      </div>
      <div class="space-y-1 pb-2">
        <div
          v-if="hormuz.length === 0"
          class="px-3 py-2 text-xs text-ink-subtle"
        >
          {{ t("empty.no_hormuz") }}
        </div>
        <RouterLink
          v-for="item in hormuz"
          :key="item.id"
          :to="routeFor(item)"
          class="block px-3 py-2 rounded-lg hover:bg-surface-muted focus-ring"
        >
          <div class="flex items-start gap-2">
            <ScrollText class="h-4 w-4 mt-0.5 text-ink-muted shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-ink-primary truncate">
                {{ item.title }}
              </div>
              <div class="text-xs text-ink-muted truncate">
                {{ fmtAge(item.captured_at) }} ago
              </div>
            </div>
          </div>
        </RouterLink>
      </div>
    </div>

    <div
      v-if="sessionEmail"
      class="border-t border-subtle px-3 py-3 flex items-center gap-2"
    >
      <User class="h-4 w-4 text-ink-muted shrink-0" />
      <div class="min-w-0 flex-1">
        <div class="text-[10px] uppercase tracking-wide text-ink-muted">
          {{ t("auth.signed_in_as") }}
        </div>
        <div class="text-xs text-ink-secondary truncate" :title="sessionEmail">
          {{ sessionEmail }}
        </div>
      </div>
      <button
        type="button"
        @click="onSignOut"
        :disabled="signingOut"
        class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring disabled:opacity-50"
        :title="t('auth.sign_out')"
        :aria-label="t('auth.sign_out')"
      >
        <LogOut class="h-4 w-4" />
      </button>
    </div>
  </aside>
</template>
