<script setup>
import { Loader2, Save } from "lucide-vue-next";

defineProps({
  benchmark: { type: Object, default: null },
  benchmarkDraft: { type: Object, default: null },
  benchmarkView: { type: Object, default: null },
  savingArtifact: { type: String, default: null },
});

const emit = defineEmits(["save-benchmark"]);
</script>

<template>
  <div class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-center justify-between gap-3">
      <h3 class="font-display text-lg font-semibold text-ink-primary">
        Benchmark Dashboard
      </h3>
      <button
        v-if="benchmarkDraft"
        type="button"
        @click="emit('save-benchmark')"
        :disabled="Boolean(savingArtifact)"
        class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
      >
        <Loader2
          v-if="savingArtifact === 'benchmark_dashboard'"
          class="h-3.5 w-3.5 animate-spin"
        />
        <Save v-else class="h-3.5 w-3.5" />
        <span>Save benchmark</span>
      </button>
    </div>
    <div v-if="!benchmark" class="mt-3 text-sm text-ink-muted">
      No benchmark dashboard yet.
    </div>
    <template v-else>
      <textarea
        v-if="benchmarkDraft"
        v-model="benchmarkDraft.summary"
        rows="2"
        class="mt-2 w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-secondary focus-ring resize-y"
      ></textarea>
      <div class="mt-3 overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="text-xs uppercase tracking-wide text-ink-muted">
            <tr class="border-b border-subtle">
              <th class="text-left py-2 pr-3">Company</th>
              <th class="text-left py-2 pr-3">Ticker</th>
              <th class="text-left py-2 pr-3">Growth</th>
              <th class="text-left py-2 pr-3">GM</th>
              <th class="text-left py-2 pr-3">EV/Rev</th>
              <th class="text-left py-2 pr-3">FCF</th>
              <th class="text-left py-2 pr-3">Theme</th>
              <th class="text-left py-2 pr-3">Confidence</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="comp in benchmarkDraft?.public_comps || []"
              :key="comp.id"
              class="border-b border-subtle/70"
            >
              <td class="py-2 pr-3">
                <input
                  v-model="comp.company"
                  class="w-32 rounded border border-subtle bg-surface px-2 py-1 text-ink-primary focus-ring"
                />
              </td>
              <td class="py-2 pr-3">
                <input
                  v-model="comp.ticker"
                  class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary font-mono focus-ring"
                />
              </td>
              <td class="py-2 pr-3">
                <input
                  v-model.number="comp.revenue_growth_pct"
                  type="number"
                  step="0.1"
                  class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                />
              </td>
              <td class="py-2 pr-3">
                <input
                  v-model.number="comp.gross_margin_pct"
                  type="number"
                  step="0.1"
                  class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                />
              </td>
              <td class="py-2 pr-3">
                <input
                  v-model.number="comp.ev_revenue"
                  type="number"
                  step="0.1"
                  class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                />
              </td>
              <td class="py-2 pr-3">
                <input
                  v-model.number="comp.fcf_margin_pct"
                  type="number"
                  step="0.1"
                  class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                />
              </td>
              <td class="py-2 pr-3">
                <input
                  v-model="comp.sell_side_theme"
                  class="w-48 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                />
              </td>
              <td class="py-2 pr-3 text-ink-secondary">{{ comp.confidence }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div
        v-if="benchmarkView?.benchmark_gaps?.length || benchmarkView?.must_prove?.length"
        class="mt-4 grid md:grid-cols-2 gap-3 text-xs text-ink-secondary"
      >
        <div v-if="benchmarkView?.benchmark_gaps?.length">
          <div class="uppercase tracking-wide text-ink-muted">Benchmark Evidence Limits</div>
          <ul class="mt-1 space-y-1">
            <li v-for="gap in benchmarkView?.benchmark_gaps || []" :key="gap">
              {{ gap }}
            </li>
          </ul>
        </div>
        <div v-if="benchmarkView?.must_prove?.length">
          <div class="uppercase tracking-wide text-ink-muted">Required Valuation Support</div>
          <ul class="mt-1 space-y-1">
            <li v-for="claim in benchmarkView?.must_prove || []" :key="claim">
              {{ claim }}
            </li>
          </ul>
        </div>
      </div>
      <div
        v-if="benchmarkView?.source_traces?.length"
        class="mt-4 text-xs text-ink-secondary"
      >
        <div class="uppercase tracking-wide text-ink-muted">Source Evidence</div>
        <div
          v-for="(trace, index) in benchmarkView.source_traces.slice(0, 4)"
          :key="`${trace.locator || trace.title || trace.url}-${index}`"
          class="mt-1 rounded border border-subtle bg-surface-muted px-2 py-1"
        >
          <div class="text-[11px] text-ink-muted">
            {{ trace.locator || trace.title || trace.url || "Source" }}
            <span v-if="trace.confidence">· {{ trace.confidence }}</span>
          </div>
          <div>{{ trace.excerpt }}</div>
        </div>
      </div>
    </template>
  </div>
</template>
