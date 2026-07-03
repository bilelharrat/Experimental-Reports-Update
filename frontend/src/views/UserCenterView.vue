<script setup>
import { computed, onMounted, ref } from "vue";
import { Activity, ShieldCheck, UserRound } from "lucide-vue-next";
import { api } from "../api.js";

const profile = ref(null);
const loading = ref(true);
const error = ref("");

const account = computed(() => profile.value?.account || {});
const team = computed(() => profile.value?.team || {});
const usage = computed(() => profile.value?.usage || {});
const status = computed(() => profile.value?.status || {});
const analytics = computed(() => profile.value?.analytics || {});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    profile.value = await api.userCenter();
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="mx-auto max-w-4xl px-8 py-10">
    <header class="mb-8">
      <div class="vogue-label">Account</div>
      <h1 class="mt-2 font-display text-3xl font-bold text-ink-primary">
        User Center
      </h1>
    </header>

    <div v-if="loading" class="rounded-card border border-subtle bg-surface p-5 text-sm text-ink-muted">
      Loading user center…
    </div>
    <div v-else-if="error" class="rounded-card border border-danger/30 bg-danger/10 p-5 text-sm text-danger">
      {{ error }}
    </div>

    <section v-else class="rounded-card border border-subtle bg-surface p-6 shadow-card">
      <div class="flex items-start gap-4">
        <div
          class="grid h-14 w-14 place-items-center rounded-glass bg-accent-soft text-accent-ink"
        >
          <UserRound class="h-6 w-6" />
        </div>
        <div class="min-w-0">
          <div class="text-lg font-bold text-ink-primary">{{ account.name }}</div>
          <div class="text-sm text-ink-muted">{{ account.email }}</div>
          <div class="mt-3 flex flex-wrap gap-2">
            <span class="rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-ink-secondary">
              {{ account.workspace }}
            </span>
            <span class="rounded-full bg-accent-soft px-3 py-1 text-xs font-semibold text-accent-ink">
              {{ account.role }}
            </span>
            <span class="rounded-full bg-surface-muted px-3 py-1 text-xs font-semibold text-ink-secondary">
              {{ account.plan }}
            </span>
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-4 md:grid-cols-3">
        <div class="rounded-row border border-subtle bg-surface-muted p-4">
          <div class="flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <ShieldCheck class="h-4 w-4 text-accent" />
            Permissions
          </div>
          <div class="mono-data mt-2 text-2xl font-bold text-ink-primary">
            {{ account.permissions?.length || 0 }}
          </div>
        </div>
        <div class="rounded-row border border-subtle bg-surface-muted p-4">
          <div class="flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <UserRound class="h-4 w-4 text-accent" />
            Licensed seats
          </div>
          <div class="mono-data mt-2 text-2xl font-bold text-ink-primary">
            {{ team.licensed_seats || 0 }}
          </div>
        </div>
        <div class="rounded-row border border-subtle bg-surface-muted p-4">
          <div class="flex items-center gap-2 text-sm font-semibold text-ink-primary">
            <Activity class="h-4 w-4 text-accent" />
            Analytics events
          </div>
          <div class="mono-data mt-2 text-2xl font-bold text-ink-primary">
            {{ usage.analytics_events || 0 }}
          </div>
        </div>
      </div>

      <div class="mt-6 grid gap-4 lg:grid-cols-2">
        <div class="rounded-row border border-subtle bg-surface-muted p-4">
          <div class="vogue-label">System Status</div>
          <div class="mt-3 space-y-2 text-sm">
            <div v-for="(value, key) in status" :key="key" class="flex justify-between gap-3">
              <span class="capitalize text-ink-muted">{{ String(key).replaceAll('_', ' ') }}</span>
              <span class="font-semibold text-ink-primary">{{ value }}</span>
            </div>
          </div>
        </div>
        <div class="rounded-row border border-subtle bg-surface-muted p-4">
          <div class="vogue-label">Product Metrics</div>
          <div class="mt-3 space-y-2 text-sm">
            <div class="flex justify-between gap-3">
              <span class="text-ink-muted">Co-pilot task acceptance</span>
              <span class="mono-data font-semibold text-ink-primary">
                {{
                  analytics.copilot_task_acceptance?.acceptance_rate == null
                    ? "N/A"
                    : `${Math.round(analytics.copilot_task_acceptance.acceptance_rate * 100)}%`
                }}
              </span>
            </div>
            <div class="flex justify-between gap-3">
              <span class="text-ink-muted">Source coverage</span>
              <span class="mono-data font-semibold text-ink-primary">
                {{
                  analytics.source_coverage?.coverage == null
                    ? "N/A"
                    : `${Math.round(analytics.source_coverage.coverage * 100)}%`
                }}
              </span>
            </div>
            <div class="flex justify-between gap-3">
              <span class="text-ink-muted">Median time to first memo</span>
              <span class="mono-data font-semibold text-ink-primary">
                {{
                  analytics.time_to_first_memo?.median_minutes == null
                    ? "N/A"
                    : `${Math.round(analytics.time_to_first_memo.median_minutes)}m`
                }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
