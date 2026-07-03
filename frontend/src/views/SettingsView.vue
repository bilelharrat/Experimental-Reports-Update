<script setup>
import { computed, onMounted, ref } from "vue";
import { Bell, Database, Languages, SlidersHorizontal } from "lucide-vue-next";
import { api } from "../api.js";
import { appLanguage, setAppLanguage } from "../state.js";

const settings = ref(null);
const loading = ref(true);
const error = ref("");
const saving = ref("");

const prefs = computed(() => settings.value?.preferences || {});
const account = computed(() => settings.value?.account || {});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    settings.value = await api.workspaceSettings();
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
</script>

<template>
  <div class="mx-auto max-w-5xl px-8 py-10">
    <header class="mb-8">
      <div class="vogue-label">Workspace</div>
      <h1 class="mt-2 font-display text-3xl font-bold text-ink-primary">
        Settings
      </h1>
    </header>

    <div v-if="loading" class="rounded-card border border-subtle bg-surface p-5 text-sm text-ink-muted">
      Loading settings…
    </div>
    <div v-else-if="error" class="rounded-card border border-danger/30 bg-danger/10 p-5 text-sm text-danger">
      {{ error }}
    </div>

    <div v-else class="grid gap-4 lg:grid-cols-2">
      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Languages class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            Preferences
          </h2>
        </div>
        <div class="mt-4">
          <div class="vogue-label mb-2">Language</div>
          <div
            class="inline-flex overflow-hidden rounded-full border border-subtle bg-surface text-sm"
            role="group"
            aria-label="App language"
          >
            <button
              type="button"
              @click="patchPreference('language', 'en')"
              :class="[
                'px-4 py-2 focus-ring',
                (prefs.language || appLanguage) === 'en'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
            >
              EN
            </button>
            <button
              type="button"
              @click="patchPreference('language', 'zh')"
              :class="[
                'border-l border-subtle px-4 py-2 focus-ring',
                (prefs.language || appLanguage) === 'zh'
                  ? 'bg-accent text-white'
                  : 'text-ink-secondary hover:bg-surface-muted',
              ]"
            >
              中文
            </button>
          </div>
        </div>
      </section>

      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Bell class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            Alerts
          </h2>
        </div>
        <div class="mt-4 space-y-3 text-sm text-ink-secondary">
          <label class="flex items-center justify-between gap-3">
            <span>Weekly summary</span>
            <input
              type="checkbox"
              :checked="prefs.weekly_summary"
              :disabled="saving === 'weekly_summary'"
              class="h-4 w-4 accent-[var(--tiffany)] focus-ring"
              @change="patchPreference('weekly_summary', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3">
            <span>Stock auto-refresh</span>
            <input
              type="checkbox"
              :checked="prefs.stock_auto_refresh"
              :disabled="saving === 'stock_auto_refresh'"
              class="h-4 w-4 accent-[var(--tiffany)] focus-ring"
              @change="patchPreference('stock_auto_refresh', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3">
            <span>Agent task alerts</span>
            <input
              type="checkbox"
              :checked="prefs.agent_alerts"
              :disabled="saving === 'agent_alerts'"
              class="h-4 w-4 accent-[var(--tiffany)] focus-ring"
              @change="patchPreference('agent_alerts', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3">
            <span>Compact density</span>
            <input
              type="checkbox"
              :checked="prefs.compact_density"
              :disabled="saving === 'compact_density'"
              class="h-4 w-4 accent-[var(--tiffany)] focus-ring"
              @change="patchPreference('compact_density', $event.target.checked)"
            />
          </label>
        </div>
      </section>

      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Database class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            System Status
          </h2>
        </div>
        <div class="mt-4 grid gap-2 text-sm">
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Workspace role</span>
            <span class="font-semibold text-accent-ink">{{ account.role || "adapter" }}</span>
          </div>
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Account</span>
            <span class="font-semibold text-ink-primary">{{ account.email }}</span>
          </div>
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Adapter scope</span>
            <span class="font-semibold text-accent-ink">Ready</span>
          </div>
        </div>
      </section>

      <section class="rounded-card border border-subtle bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <SlidersHorizontal class="h-4 w-4 text-accent" />
          <h2 class="font-display text-lg font-bold text-ink-primary">
            Usage
          </h2>
        </div>
        <div class="mt-4 grid gap-2 text-sm">
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Plan</span>
            <span class="font-semibold text-ink-primary">{{ account.plan }}</span>
          </div>
          <div class="flex justify-between rounded-row bg-surface-muted px-3 py-2">
            <span>Permissions</span>
            <span class="mono-data font-semibold text-ink-primary">{{ account.permissions?.length || 0 }}</span>
          </div>
          <div class="rounded-row bg-surface-muted px-3 py-2 text-xs text-ink-muted">
            {{ settings.adapter_scope }}
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
