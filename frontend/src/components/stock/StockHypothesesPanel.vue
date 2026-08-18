<script setup>
import { computed, ref, watch } from "vue";
import { BadgeCheck, FlaskConical, Play, RefreshCw } from "lucide-vue-next";

const props = defineProps({
  hypotheses: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
  defaultVintageDate: { type: String, default: "" },
});

const emit = defineEmits([
  "create-live",
  "create-debug-backfill",
  "evaluate-vintage",
  "calibrate",
]);

const liveVintageDate = ref(props.defaultVintageDate);
const debugVintageDate = ref("2026-06-07");

watch(
  () => props.defaultVintageDate,
  (value) => {
    if (!liveVintageDate.value) liveVintageDate.value = value;
  },
);

const vintages = computed(() => props.hypotheses?.vintages || []);
const rows = computed(() => props.hypotheses?.rows || []);
const calibration = computed(() => props.hypotheses?.calibration || []);
const selectedVintageDate = computed(
  () => vintages.value[0]?.vintage_date || rows.value[0]?.vintage_date || "",
);
const selectedVintageKind = computed(
  () => vintages.value[0]?.vintage_kind || rows.value[0]?.vintage_kind || "",
);
const selectedRows = computed(() =>
  selectedVintageDate.value
    ? rows.value.filter((row) => row.vintage_date === selectedVintageDate.value)
      .filter((row) => !selectedVintageKind.value || row.vintage_kind === selectedVintageKind.value)
    : rows.value,
);

function badgeClass(kind) {
  if (kind === "debug_backfill") {
    return "border-warning/40 bg-warning-soft text-warning-ink";
  }
  return "border-success/40 bg-success-soft text-success-ink";
}
</script>

<template>
  <section class="space-y-5">
    <div class="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h2 class="font-display text-xl font-semibold">Hypotheses</h2>
        <div class="mt-1 text-sm text-ink-muted">
          {{ hypotheses?.summary?.hypothesis_count || 0 }} claims ·
          {{ hypotheses?.summary?.pending_count || 0 }} pending ·
          {{ hypotheses?.summary?.training_eligible_count || 0 }} training eligible
        </div>
      </div>
      <div class="flex flex-wrap items-end gap-2">
        <label class="text-xs font-medium text-ink-muted">
          Live vintage
          <input
            v-model="liveVintageDate"
            type="date"
            class="mt-1 block rounded-md border border-subtle bg-surface px-2 py-1 text-sm text-ink-primary focus-ring"
          />
        </label>
        <button
          type="button"
          class="btn-filled focus-ring"
          :disabled="busy || !liveVintageDate"
          @click="emit('create-live', liveVintageDate)"
        >
          <Play class="h-4 w-4" />
          Create Live
        </button>
        <label class="text-xs font-medium text-ink-muted">
          Debug vintage
          <input
            v-model="debugVintageDate"
            type="date"
            class="mt-1 block rounded-md border border-subtle bg-surface px-2 py-1 text-sm text-ink-primary focus-ring"
          />
        </label>
        <button
          type="button"
          class="btn-bordered focus-ring"
          :disabled="busy || !debugVintageDate"
          @click="emit('create-debug-backfill', debugVintageDate)"
        >
          <FlaskConical class="h-4 w-4" />
          Debug Backfill
        </button>
        <button
          type="button"
          class="btn-bordered focus-ring"
          :disabled="busy"
          @click="emit('calibrate')"
        >
          <BadgeCheck class="h-4 w-4" />
          Calibrate
        </button>
      </div>
    </div>

    <div v-if="vintages.length" class="overflow-hidden rounded-card bg-surface shadow-card">
      <table class="min-w-full text-sm">
        <thead class="bg-surface-muted text-left text-footnote font-semibold text-ink-muted">
          <tr>
            <th class="px-3 py-2">Vintage</th>
            <th class="px-3 py-2">Kind</th>
            <th class="px-3 py-2 text-right">Claims</th>
            <th class="px-3 py-2 text-right">Pending</th>
            <th class="px-3 py-2 text-right">Eligible</th>
            <th class="px-3 py-2 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="vintage in vintages"
            :key="`${vintage.vintage_date}-${vintage.vintage_kind}`"
            class="border-b border-subtle last:border-0"
          >
            <td class="px-3 py-2 font-medium">{{ vintage.vintage_date }}</td>
            <td class="px-3 py-2">
              <span class="rounded-full border px-2 py-0.5 text-xs font-medium" :class="badgeClass(vintage.vintage_kind)">
                {{ vintage.vintage_kind }}
              </span>
            </td>
            <td class="px-3 py-2 text-right">{{ vintage.hypothesis_count }}</td>
            <td class="px-3 py-2 text-right">{{ vintage.pending_count }}</td>
            <td class="px-3 py-2 text-right">{{ vintage.training_eligible_count }}</td>
            <td class="px-3 py-2 text-right">
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-md border border-subtle px-2 py-1 text-xs font-medium text-ink-secondary hover:bg-surface-muted focus-ring disabled:opacity-50"
                :disabled="busy"
                title="Evaluate vintage"
                @click="emit('evaluate-vintage', vintage.vintage_date)"
              >
                <RefreshCw class="h-3.5 w-3.5" />
                Evaluate
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="rounded-lg border border-dashed border-subtle bg-surface p-6 text-sm text-ink-muted">
      No hypothesis vintages yet.
    </div>

    <div v-if="selectedRows.length" class="overflow-hidden rounded-card bg-surface shadow-card">
      <table class="min-w-full text-sm">
        <thead class="bg-surface-muted text-left text-footnote font-semibold text-ink-muted">
          <tr>
            <th class="px-3 py-2">Claim</th>
            <th class="px-3 py-2">Ticker</th>
            <th class="px-3 py-2">Direction</th>
            <th class="px-3 py-2">Outcome</th>
            <th class="px-3 py-2">Training</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in selectedRows" :key="row.hypothesis_id" class="border-b border-subtle last:border-0">
            <td class="px-3 py-2">
              <div class="font-medium">{{ row.claim }}</div>
              <div class="mt-1 text-xs text-ink-muted">{{ row.hypothesis_id }}</div>
            </td>
            <td class="px-3 py-2">{{ row.ticker || "n/a" }}</td>
            <td class="px-3 py-2">{{ row.direction }}</td>
            <td class="px-3 py-2">
              <span v-if="row.outcome">{{ row.outcome.directional_result }}</span>
              <span v-else class="text-ink-muted">pending</span>
              <span v-if="row.outcome?.relative_return_pct != null" class="ml-2 text-xs text-ink-muted">
                {{ row.outcome.relative_return_pct }}%
              </span>
            </td>
            <td class="px-3 py-2">
              <span
                class="rounded-full border px-2 py-0.5 text-xs font-medium"
                :class="row.outcome?.eligible_for_training ? 'border-success/40 bg-success-soft text-success-ink' : 'border-subtle bg-surface-muted text-ink-muted'"
              >
                {{ row.outcome?.eligible_for_training ? "eligible" : "not eligible" }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="calibration.length" class="rounded-card bg-surface shadow-card p-4 text-sm">
      <div class="font-medium">Latest Calibration</div>
      <div class="mt-2 text-ink-muted">
        {{ calibration[0].eligible_outcome_count || 0 }} eligible outcomes
      </div>
    </div>
  </section>
</template>
