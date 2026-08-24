<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink } from "vue-router";
import { Activity, BarChart3, Bell, Database, FlaskConical, Languages, Loader2, Moon, RefreshCw, SlidersHorizontal, Sun, SunMoon } from "lucide-vue-next";
import { api } from "../api.js";
import AiMark from "../components/AiMark.vue";
import { APPEARANCES, appearance, setAppearance } from "../appearance.js";
import { accountInitials } from "../formatters.js";
import { useT } from "../i18n.js";
import { appLanguage, setAppLanguage } from "../state.js";

const t = useT();

const settings = ref(null);
const profile = ref(null);
const loading = ref(true);
const error = ref("");
const saving = ref("");
const regeneratingAll = ref(false);
const refreshingStockViews = ref(false);
const operationsMessage = ref("");
const operationsError = ref("");

const prefs = computed(() => settings.value?.preferences || {});
const account = computed(() => profile.value?.account || settings.value?.account || {});
const team = computed(() => profile.value?.team || {});
const usage = computed(() => profile.value?.usage || {});
const status = computed(() => profile.value?.status || {});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [workspace, user] = await Promise.allSettled([
      api.workspaceSettings(),
      api.userCenter(),
    ]);
    if (workspace.status === "fulfilled") settings.value = workspace.value;
    if (user.status === "fulfilled") profile.value = user.value;
    if (workspace.status === "rejected" && user.status === "rejected") {
      error.value = workspace.reason?.message || String(workspace.reason);
    }
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

async function patchPreference(key, value) {
  saving.value = key;
  error.value = "";
  try {
    settings.value = await api.updateWorkspaceSettings({ [key]: value });
    if (key === "language" && value) setAppLanguage(value);
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    saving.value = "";
  }
}

onMounted(load);

async function regenAllCompanies() {
  if (regeneratingAll.value) return;
  regeneratingAll.value = true;
  operationsMessage.value = "";
  operationsError.value = "";
  try {
    const result = await api.regenAllCompanies();
    const total = result.total_count ?? 0;
    if (!total) operationsMessage.value = t("home.regen_all_none");
    else if (result.status === "already_running") {
      operationsMessage.value = t("home.regen_all_running", { total });
    } else {
      operationsMessage.value = t("home.regen_all_started", {
        total,
        public: result.public_trader_count ?? 0,
      });
    }
  } catch {
    operationsError.value = t("home.regen_all_failed");
  } finally {
    regeneratingAll.value = false;
  }
}

async function refreshAllStockViews() {
  if (refreshingStockViews.value) return;
  refreshingStockViews.value = true;
  operationsMessage.value = "";
  operationsError.value = "";
  try {
    const result = await api.trader.refreshAll();
    const total = result.total_count ?? 0;
    if (!total) operationsMessage.value = t("home.refresh_stock_views_none");
    else if (result.status === "already_running") {
      operationsMessage.value = t("home.refresh_stock_views_running", { total });
    } else {
      operationsMessage.value = t("home.refresh_stock_views_started", {
        queued: result.queued_count ?? 0,
        total,
      });
    }
  } catch {
    operationsError.value = t("home.refresh_stock_views_failed");
  } finally {
    refreshingStockViews.value = false;
  }
}

function appearanceLabel(value) {
  if (value === "light") return t("settings.appearance_light");
  if (value === "dark") return t("settings.appearance_dark");
  return t("settings.appearance_auto");
}

function appearanceIcon(value) {
  if (value === "light") return Sun;
  if (value === "dark") return Moon;
  return SunMoon;
}
</script>

<template>
  <div class="mx-auto max-w-5xl px-8 py-10">
    <header class="mb-6">
      <h1 class="font-display text-title3 text-ink-primary">
        {{ t("settings.title") }}
      </h1>
    </header>

    <div v-if="loading" class="rounded-card bg-surface p-5 text-callout text-ink-muted">
      {{ t("settings.loading") }}
    </div>
    <div v-else-if="error" class="rounded-card bg-danger-soft p-5 text-callout text-danger-ink">
      {{ error }}
    </div>

    <div v-else class="space-y-4">
      <section class="group-card p-5">
        <div class="flex items-start gap-4">
          <div class="grid h-11 w-11 place-items-center rounded-subbox bg-fill-tertiary text-callout font-semibold tracking-tight text-ink-secondary">
            {{ accountInitials(account.name || account.email) }}
          </div>
          <div class="min-w-0 flex-1">
            <h2 class="font-display text-title3 text-ink-primary">
              {{ t("settings.profile") }}
            </h2>
            <div class="mt-0.5 text-callout text-ink-primary">{{ account.name || account.email }}</div>
            <div class="text-footnote text-ink-muted">{{ account.email }}</div>
            <div class="mt-2 flex flex-wrap gap-2 text-caption1 text-ink-muted">
              <span v-if="account.workspace">{{ account.workspace }}</span>
              <span v-if="account.role">{{ account.role }}</span>
              <span v-if="account.plan">{{ account.plan }}</span>
            </div>
          </div>
        </div>
        <dl class="mt-4 grid gap-2 text-callout sm:grid-cols-3">
          <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
            <dt class="text-caption1 text-ink-muted">{{ t("settings.permissions") }}</dt>
            <dd class="mt-0.5 font-medium text-ink-primary">
              {{ t("settings.permission_grants", { n: account.permissions?.length || 0 }) }}
            </dd>
          </div>
          <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
            <dt class="text-caption1 text-ink-muted">{{ t("settings.seats") }}</dt>
            <dd class="mt-0.5 font-medium text-ink-primary">
              {{ t("settings.licensed_seats", { n: team.licensed_seats || 0 }) }}
            </dd>
          </div>
          <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
            <dt class="text-caption1 text-ink-muted">{{ t("settings.usage") }}</dt>
            <dd class="mt-0.5 font-medium text-ink-primary">
              {{ t("settings.usage_events", { n: usage.analytics_events || 0 }) }}
            </dd>
          </div>
        </dl>
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Languages class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.preferences") }}
          </h2>
        </div>
        <div class="mt-4">
          <div class="vogue-label mb-2">{{ t("settings.language") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.language_group')"
          >
            <button
              type="button"
              @click="patchPreference('language', 'en')"
              class="segmented-item focus-ring"
              :data-selected="(prefs.language || appLanguage) === 'en'"
            >
              EN
            </button>
            <button
              type="button"
              @click="patchPreference('language', 'zh')"
              class="segmented-item focus-ring"
              :data-selected="(prefs.language || appLanguage) === 'zh'"
            >
              中文
            </button>
          </div>
        </div>
        <div class="mt-5">
          <div class="vogue-label mb-2">{{ t("settings.appearance") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.appearance')"
          >
            <button
              v-for="option in APPEARANCES"
              :key="option"
              type="button"
              @click="setAppearance(option)"
              class="segmented-item focus-ring inline-flex items-center gap-1"
              :data-selected="appearance === option"
            >
              <component :is="appearanceIcon(option)" class="h-3.5 w-3.5" />
              {{ appearanceLabel(option) }}
            </button>
          </div>
        </div>
        <label class="mt-5 flex items-center justify-between gap-3 rounded-subbox px-1 py-2 text-callout text-ink-secondary">
          <span>{{ t("settings.compact_density") }}</span>
          <input
            type="checkbox"
            :checked="prefs.compact_density"
            :disabled="saving === 'compact_density'"
            class="memo-checkbox focus-ring"
            @change="patchPreference('compact_density', $event.target.checked)"
          />
        </label>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Bell class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.notifications") }}
          </h2>
        </div>
        <div class="mt-4 space-y-1 text-callout text-ink-secondary">
          <label class="flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
            <span>{{ t("settings.weekly_summary") }}</span>
            <input
              type="checkbox"
              :checked="prefs.weekly_summary"
              :disabled="saving === 'weekly_summary'"
              class="memo-checkbox focus-ring"
              @change="patchPreference('weekly_summary', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
            <span>{{ t("settings.stock_auto_refresh") }}</span>
            <input
              type="checkbox"
              :checked="prefs.stock_auto_refresh"
              :disabled="saving === 'stock_auto_refresh'"
              class="memo-checkbox focus-ring"
              @change="patchPreference('stock_auto_refresh', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
            <span>{{ t("settings.agent_alerts") }}</span>
            <input
              type="checkbox"
              :checked="prefs.agent_alerts"
              :disabled="saving === 'agent_alerts'"
              class="memo-checkbox focus-ring"
              @change="patchPreference('agent_alerts', $event.target.checked)"
            />
          </label>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Database class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.system") }}
          </h2>
        </div>
        <div class="mt-4 grid gap-1.5 text-callout">
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="text-ink-secondary">{{ t("settings.workspace_role") }}</span>
            <span class="min-w-0 truncate font-semibold text-accent-ink">{{ account.role || t("settings.role_adapter") }}</span>
          </div>
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="shrink-0 text-ink-secondary">{{ t("settings.account") }}</span>
            <span class="min-w-0 truncate font-semibold text-ink-primary">{{ account.email }}</span>
          </div>
        </div>
        <details class="mt-3">
          <summary class="cursor-pointer text-footnote text-ink-muted focus-ring rounded-subbox px-1 py-1">
            {{ t("settings.system_details") }}
          </summary>
          <div class="mt-2 space-y-1 text-footnote text-ink-muted">
            <div v-if="settings?.adapter_scope" class="rounded-row bg-fill-tertiary px-3 py-2">
              {{ settings.adapter_scope }}
            </div>
            <div v-for="(value, key) in status" :key="key" class="flex justify-between gap-3 px-1 py-1">
              <span>{{ String(key).replaceAll("_", " ") }}</span>
              <span class="text-ink-primary">{{ value }}</span>
            </div>
          </div>
        </details>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <SlidersHorizontal class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.usage") }}
          </h2>
        </div>
        <div class="mt-4 grid gap-1.5 text-callout">
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="text-ink-secondary">{{ t("settings.plan") }}</span>
            <span class="min-w-0 truncate font-semibold text-ink-primary">{{ account.plan }}</span>
          </div>
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="text-ink-secondary">{{ t("settings.permissions") }}</span>
            <span class="mono-data font-semibold text-ink-primary">
              {{ t("settings.permission_grants", { n: account.permissions?.length || 0 }) }}
            </span>
          </div>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card lg:col-span-2">
        <h2 class="font-display text-title3 text-ink-primary">
          {{ t("settings.advanced_tools") }}
        </h2>
        <p class="mt-1 text-footnote text-ink-muted">{{ t("settings.advanced_tools_help") }}</p>
        <div class="mt-4 grid gap-2 sm:grid-cols-3">
          <RouterLink
            :to="{ name: 'stock-research' }"
            class="flex items-center gap-3 rounded-row bg-fill-tertiary px-3 py-3 text-callout font-medium text-ink-primary hover:bg-fill-secondary focus-ring"
          >
            <Activity class="h-4 w-4 shrink-0 text-accent" />
            {{ t("sidebar.markets_workbench") }}
          </RouterLink>
          <RouterLink
            :to="{ name: 'trader-stats' }"
            class="flex items-center gap-3 rounded-row bg-fill-tertiary px-3 py-3 text-callout font-medium text-ink-primary hover:bg-fill-secondary focus-ring"
          >
            <BarChart3 class="h-4 w-4 shrink-0 text-accent" />
            {{ t("sidebar.markets_stats") }}
          </RouterLink>
          <RouterLink
            :to="{ name: 'innovation-lab' }"
            class="flex items-center gap-3 rounded-row bg-fill-tertiary px-3 py-3 text-callout font-medium text-ink-primary hover:bg-fill-secondary focus-ring"
          >
            <FlaskConical class="h-4 w-4 shrink-0 text-accent" />
            {{ t("sidebar.markets_labs") }}
          </RouterLink>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card lg:col-span-2">
        <h2 class="font-display text-title3 text-ink-primary">
          {{ t("settings.operations") }}
        </h2>
        <p class="mt-1 text-footnote text-ink-muted">{{ t("home.operations_help") }}</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            :disabled="regeneratingAll"
            class="btn-bordered focus-ring"
            @click="regenAllCompanies"
          >
            <Loader2 v-if="regeneratingAll" class="h-4 w-4 animate-spin" />
            <AiMark v-else class="h-4 w-4" />
            {{ regeneratingAll ? t("home.regenerating_all") : t("home.regen_all") }}
          </button>
          <button
            type="button"
            :disabled="refreshingStockViews"
            class="btn-bordered focus-ring"
            @click="refreshAllStockViews"
          >
            <Loader2 v-if="refreshingStockViews" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            {{ refreshingStockViews ? t("home.refreshing_stock_views") : t("home.refresh_stock_views") }}
          </button>
        </div>
        <p v-if="operationsMessage" class="mt-2 text-footnote text-ink-muted">{{ operationsMessage }}</p>
        <p v-if="operationsError" class="mt-2 text-footnote text-danger">{{ operationsError }}</p>
      </section>
    </div>
    </div>
  </div>
</template>
