<script setup>
defineProps({
  summary: { type: Object, default: () => ({}) },
  workProducts: { type: Array, default: () => [] },
  reviewItems: { type: Array, default: () => [] },
  sourceTraceRows: { type: Array, default: () => [] },
  sourceBoundaryRows: { type: Array, default: () => [] },
});

function fmtDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function statusLabel(status) {
  return String(status || "draft").replaceAll("_", " ");
}

function toolboxStatusClass(status) {
  if (["approved", "graded", "used_in_memo"].includes(status)) {
    return "bg-success-soft text-success-ink";
  }
  if (["needs_review", "failed", "stale"].includes(status)) {
    return "bg-warning-soft text-warning-ink";
  }
  return "bg-surface-muted text-ink-muted";
}

function reviewSeverityClass(severity) {
  if (severity === "high") return "bg-danger-soft text-danger";
  if (severity === "medium") return "bg-warning-soft text-warning-ink";
  return "bg-surface-muted text-ink-muted";
}
</script>

<template>
  <section class="border border-subtle bg-surface rounded-card p-5">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h3 class="font-display text-title3 text-ink-primary">
          Memo Tools Toolbox
        </h3>
        <div class="mt-1 text-sm text-ink-secondary">
          {{ summary.nextAction }}
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
          <div class="text-footnote font-semibold text-ink-muted">Readiness</div>
          <div class="mt-1 font-semibold text-ink-primary">
            {{ summary.readiness }}
          </div>
        </div>
        <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
          <div class="text-footnote font-semibold text-ink-muted">Active Jobs</div>
          <div class="mt-1 font-semibold text-ink-primary">
            {{ summary.activeJobs }}
          </div>
        </div>
        <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
          <div class="text-footnote font-semibold text-ink-muted">Review Items</div>
          <div class="mt-1 font-semibold text-ink-primary">
            {{ summary.reviewItems }}
          </div>
        </div>
        <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
          <div class="text-footnote font-semibold text-ink-muted">Generated Memos</div>
          <div class="mt-1 font-semibold text-ink-primary">
            {{ summary.generatedMemos }}
          </div>
        </div>
      </div>
    </div>

    <div class="mt-4 grid md:grid-cols-5 gap-2 text-xs text-ink-secondary">
      <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
        <div class="text-footnote font-semibold text-ink-muted">Approval</div>
        <div class="mt-1 text-ink-primary">{{ summary.approved }}</div>
      </div>
      <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
        <div class="text-footnote font-semibold text-ink-muted">Thesis</div>
        <div class="mt-1 text-ink-primary">{{ summary.thesis }}</div>
      </div>
      <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
        <div class="text-footnote font-semibold text-ink-muted">Blockers</div>
        <div class="mt-1 text-ink-primary">{{ summary.blockers }}</div>
      </div>
      <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
        <div class="text-footnote font-semibold text-ink-muted">Evidence Exceptions</div>
        <div class="mt-1 text-ink-primary">{{ summary.waivers }}</div>
      </div>
      <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
        <div class="text-footnote font-semibold text-ink-muted">Recent Outputs</div>
        <div class="mt-1 text-ink-primary">{{ summary.recentOutputs }}</div>
      </div>
    </div>

    <div class="mt-5 grid xl:grid-cols-2 gap-4">
      <div>
        <div class="mb-2 flex items-center justify-between gap-3">
          <h4 class="text-sm font-semibold text-ink-primary">Deliverables</h4>
          <span class="text-xs text-ink-muted">{{ workProducts.length }}</span>
        </div>
        <div class="overflow-x-auto overflow-hidden rounded-card shadow-card">
          <table class="min-w-full text-sm">
            <thead>
              <tr>
                <th class="text-left py-2 px-3">Artifact</th>
                <th class="text-left py-2 px-3">Type</th>
                <th class="text-left py-2 px-3">Status</th>
                <th class="text-left py-2 px-3">Sources</th>
                <th class="text-left py-2 px-3">Updated</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="product in workProducts.slice(0, 12)"
                :key="product.id"
                class="border-t border-subtle/70 align-top"
              >
                <td class="py-2 px-3 max-w-sm">
                  <div class="font-medium text-ink-primary">{{ product.title }}</div>
                  <div class="text-[11px] font-mono text-ink-muted">{{ product.id }}</div>
                  <div v-if="product.summary" class="mt-1 text-xs text-ink-secondary">
                    {{ product.summary }}
                  </div>
                </td>
                <td class="py-2 px-3 text-ink-secondary">{{ product.type }}</td>
                <td class="py-2 px-3">
                  <span
                    :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', toolboxStatusClass(product.status), ]"
                  >
                    {{ statusLabel(product.status) }}
                  </span>
                  <div v-if="product.confidence" class="mt-1 text-[11px] text-ink-muted">
                    {{ product.confidence }}
                  </div>
                </td>
                <td class="py-2 px-3 text-ink-secondary font-mono">{{ product.sourceCount }}</td>
                <td class="py-2 px-3 text-xs text-ink-muted">
                  {{ fmtDate(product.updatedAt) || "--" }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <div class="mb-2 flex items-center justify-between gap-3">
          <h4 class="text-sm font-semibold text-ink-primary">Review Queue</h4>
          <span class="text-xs text-ink-muted">{{ reviewItems.length }}</span>
        </div>
        <div
          v-if="reviewItems.length === 0"
          class="rounded-subbox bg-fill-tertiary px-3 py-3 text-sm text-ink-muted"
        >
          No open review items.
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="item in reviewItems.slice(0, 16)"
            :key="item.id"
            class="rounded-subbox bg-fill-tertiary px-3 py-2"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="text-sm font-medium text-ink-primary">{{ item.title }}</div>
                <div class="mt-1 text-xs text-ink-secondary">{{ item.detail }}</div>
                <div class="mt-1 text-[11px] font-mono text-ink-muted">{{ item.id }}</div>
              </div>
              <div class="shrink-0 text-right">
                <span
                  :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', reviewSeverityClass(item.severity), ]"
                >
                  {{ item.severity }}
                </span>
                <div class="mt-1 text-[11px] text-ink-muted">{{ item.type }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-5">
      <div class="mb-2 flex items-center justify-between gap-3">
        <h4 class="text-sm font-semibold text-ink-primary">Source Evidence Drawer</h4>
        <span class="text-xs text-ink-muted">{{ sourceTraceRows.length }}</span>
      </div>
      <div
        v-if="sourceTraceRows.length === 0"
        class="rounded-subbox bg-fill-tertiary px-3 py-3 text-sm text-ink-muted"
      >
        No source evidence captured.
      </div>
      <div v-else class="overflow-x-auto overflow-hidden rounded-card shadow-card">
        <table class="min-w-full text-sm">
          <thead>
            <tr>
              <th class="text-left py-2 px-3">Artifact</th>
              <th class="text-left py-2 px-3">Source</th>
              <th class="text-left py-2 px-3">Locator</th>
              <th class="text-left py-2 px-3">Confidence</th>
              <th class="text-left py-2 px-3">Excerpt</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="trace in sourceTraceRows"
              :key="trace.id"
              class="border-t border-subtle/70 align-top"
            >
              <td class="py-2 px-3 text-ink-primary">
                {{ trace.artifact }}
                <div class="text-[11px] text-footnote font-semibold text-ink-muted">
                  {{ String(trace.kind || "source").replace("_", " ") }}
                </div>
              </td>
              <td class="py-2 px-3 text-ink-secondary">{{ trace.source }}</td>
              <td class="py-2 px-3 font-mono text-xs text-ink-muted">
                {{ trace.locator || "--" }}
              </td>
              <td class="py-2 px-3 text-ink-secondary">{{ trace.confidence || "--" }}</td>
              <td class="py-2 px-3 text-xs text-ink-muted max-w-md">
                {{ trace.excerpt || "--" }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="mt-5">
      <h4 class="text-sm font-semibold text-ink-primary">Source And Evidence Boundaries</h4>
      <div class="mt-2 overflow-x-auto overflow-hidden rounded-card shadow-card">
        <table class="min-w-full text-sm">
          <thead>
            <tr>
              <th class="text-left py-2 px-3">Scope</th>
              <th class="text-left py-2 px-3">Location</th>
              <th class="text-left py-2 px-3">Status</th>
              <th class="text-left py-2 px-3">Count</th>
              <th class="text-left py-2 px-3">Detail</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in sourceBoundaryRows"
              :key="row.scope"
              class="border-t border-subtle/70"
            >
              <td class="py-2 px-3 font-medium text-ink-primary">{{ row.scope }}</td>
              <td class="py-2 px-3 font-mono text-xs text-ink-secondary">
                {{ row.location }}
              </td>
              <td class="py-2 px-3">
                <span
                  :class="[ 'text-[10px] px-1.5 py-0.5 rounded ', row.status === 'included' ? 'bg-success-soft text-success-ink' : 'bg-surface-muted text-ink-muted', ]"
                >
                  {{ row.status }}
                </span>
              </td>
              <td class="py-2 px-3 font-mono text-ink-secondary">{{ row.count }}</td>
              <td class="py-2 px-3 text-xs text-ink-muted">{{ row.detail }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>
</template>
