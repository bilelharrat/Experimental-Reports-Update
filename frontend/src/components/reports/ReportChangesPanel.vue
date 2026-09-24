<script setup>
// "Changes since <date>": this memo beside the previous finished memo of
// the same company and kind (GET /api/reports/{id}/diff — deterministic,
// no model call). Rows are shown side by side with how they were paired;
// a row without a counterpart is "no counterpart", never "added" or
// "removed", because labels drift between runs and the pairing is fuzzy.
import { computed, ref, watch } from "vue";
import { ArrowRight, History, Loader2, TriangleAlert, X } from "lucide-vue-next";
import { api } from "../../api.js";
import { useT } from "../../i18n.js";
import { decisionWord, spanLabel } from "../../reportStatus.js";

const props = defineProps({
  report: { type: Object, required: true },
  // The previous version's summary, when the list has it (for its date).
  previous: { type: Object, default: null },
  lang: { type: String, default: "en" },
});

const emit = defineEmits(["close"]);
const t = useT();

// One comparison per pair of versions for the life of the page: the
// documents behind a finished memo do not change without a new updated_at.
const cache = new Map();

const diff = ref(null);
const loading = ref(false);
const error = ref("");
const openUnchanged = ref(new Set());
const openSources = ref(false);
let token = 0;

const cacheKey = computed(
  () => `${props.report?.id}|${props.report?.previous_version_id || ""}|${props.report?.updated_at || ""}`,
);

async function load() {
  const id = props.report?.id;
  if (!id) return;
  const key = cacheKey.value;
  if (cache.has(key)) {
    diff.value = cache.get(key);
    error.value = "";
    return;
  }
  const mine = ++token;
  loading.value = true;
  error.value = "";
  diff.value = null;
  try {
    const payload = await api.getReportDiff(id, props.report?.previous_version_id || undefined);
    if (mine !== token) return;
    cache.set(key, payload);
    diff.value = payload;
  } catch {
    if (mine !== token) return;
    error.value = t("viewer.diff.failed");
  } finally {
    if (mine === token) loading.value = false;
  }
}

watch(cacheKey, () => {
  openUnchanged.value = new Set();
  openSources.value = false;
  load();
}, { immediate: true });

// ---- Text of a cell ----------------------------------------------------------------

function cellText(cell) {
  if (cell == null) return "";
  if (typeof cell === "string" || typeof cell === "number") return String(cell);
  if (typeof cell === "object" && ("en" in cell || "zh" in cell)) {
    const own = props.lang === "zh" ? cell.zh : cell.en;
    const other = props.lang === "zh" ? cell.en : cell.zh;
    return String((own && String(own).trim()) || other || "");
  }
  return "";
}

function cellsText(cells) {
  if (!Array.isArray(cells)) return "";
  return cells.map(cellText).filter(Boolean).join(" · ");
}

function valueText(value) {
  if (value == null || value === "") return "";
  if (typeof value === "number") return value.toLocaleString(props.lang === "zh" ? "zh-CN" : "en-US");
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return t("viewer.diff.items", { count: value.length });
  if (typeof value === "object") {
    if ("en" in value || "zh" in value) return cellText(value);
    if ("low" in value || "high" in value) {
      return [cellText(value.low) || value.low, cellText(value.high) || value.high]
        .filter((part) => part != null && part !== "")
        .join("–");
    }
    const text = JSON.stringify(value);
    return text.length > 140 ? `${text.slice(0, 138)}…` : text;
  }
  return String(value);
}

function day(value) {
  const parsed = Date.parse(value || "");
  if (Number.isNaN(parsed)) return "";
  return new Date(parsed).toLocaleDateString(props.lang === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function matchLabel(match) {
  const key = String(match || "none");
  return ["exact", "scenario", "fuzzy", "none", "url", "title"].includes(key)
    ? t(`viewer.diff.match.${key}`)
    : key;
}

// ---- The comparison, arranged for reading -------------------------------------------

const previousDate = computed(() => day(diff.value?.previous?.created_at || props.previous?.created_at));
const currentDate = computed(() => day(diff.value?.current?.created_at || props.report?.created_at));
const apart = computed(() => spanLabel(diff.value?.days_apart, t));

const verdict = computed(() => {
  const v = diff.value?.verdict;
  if (!v || (!v.current && !v.previous)) return null;
  return {
    previous: v.previous ? decisionWord(v.previous, props.report, t) : t("viewer.diff.no_call"),
    current: v.current ? decisionWord(v.current, props.report, t) : t("viewer.diff.no_call"),
    changed: Boolean(v.changed),
    unstable: Boolean(v.unstable),
  };
});

const headlines = computed(() => {
  const previous = cellText(diff.value?.previous?.headline);
  const current = cellText(diff.value?.current?.headline);
  return previous || current ? { previous, current } : null;
});

const BUFFETT_FIELD_KEYS = new Set([
  "buy_price",
  "pass_kind",
  "price",
  "price_date",
  "currency",
  "value_low",
  "value_central",
  "value_high",
  "buy_price_value",
  "mos_pct",
]);

function buffettValue(field, value) {
  if (field === "pass_kind") {
    const kind = String(value || "");
    return kind === "price" || kind === "business" ? t(`viewer.diff.pass_kind.${kind}`) : kind;
  }
  if (field === "mos_pct" && typeof value === "number") return `${value}%`;
  return valueText(value);
}

const buffettRows = computed(() =>
  (diff.value?.buffett?.fields || [])
    .filter((row) => row && BUFFETT_FIELD_KEYS.has(row.field))
    .map((row) => ({
      key: row.field,
      label: t(`viewer.diff.field.${row.field}`),
      previous: buffettValue(row.field, row.previous),
      current: buffettValue(row.field, row.current),
      changed: Boolean(row.changed),
    })),
);

const SCENARIO_KEYS = new Set(["bear", "base", "bull"]);

function tableRows(table) {
  const component = table?.component;
  return (table?.rows || []).map((row, index) => {
    if (component === "risk_register") {
      const risk = row.risk_type || {};
      const label = cellText(risk.current) || cellText(risk.previous);
      const earlierLabel = cellText(risk.previous);
      const side = (value) =>
        value
          ? [value.rating, value.likelihood, value.impact].map(cellText).filter(Boolean).join(" · ")
          : "";
      return {
        id: `${component}-${index}`,
        label,
        earlierLabel: earlierLabel && earlierLabel !== label ? earlierLabel : "",
        match: row.match,
        previous: side(row.previous),
        current: side(row.current),
        changed: row.rating_changed,
      };
    }
    if (component === "scenario_analysis") {
      const current = Array.isArray(row.current) ? row.current : null;
      const previous = Array.isArray(row.previous) ? row.previous : null;
      const label = SCENARIO_KEYS.has(row.key)
        ? t(`viewer.diff.scenario.${row.key}`)
        : cellText(current?.[0]) || cellText(previous?.[0]);
      return {
        id: `${component}-${index}`,
        label,
        earlierLabel: "",
        match: row.match,
        previous: previous ? cellsText(previous) : "",
        current: current ? cellsText(current) : "",
        changed: row.changed,
      };
    }
    const labels = row.label || {};
    const label = cellText(labels.current) || cellText(labels.previous);
    const earlierLabel = cellText(labels.previous);
    return {
      id: `${component}-${index}`,
      label,
      earlierLabel: earlierLabel && earlierLabel !== label ? earlierLabel : "",
      match: row.match,
      previous: cellsText(row.previous),
      current: cellsText(row.current),
      changed: row.changed,
    };
  });
}

const tables = computed(() =>
  (diff.value?.tables || []).map((table) => {
    const rows = tableRows(table);
    return {
      component: table.component,
      title: ["scenario_analysis", "risk_register", "key_metrics_snapshot", "deal_terms"].includes(table.component)
        ? t(`viewer.diff.table.${table.component}`)
        : String(table.component || ""),
      // Changed rows and rows without a counterpart first; identical rows fold.
      shown: rows.filter((row) => row.changed !== false),
      unchanged: rows.filter((row) => row.changed === false),
    };
  }),
);

function toggleUnchanged(component) {
  const next = new Set(openUnchanged.value);
  if (next.has(component)) next.delete(component);
  else next.add(component);
  openUnchanged.value = next;
}

const sources = computed(() => {
  const s = diff.value?.sources;
  if (!s) return null;
  const rows = Array.isArray(s.rows) ? s.rows : [];
  const title = (side) => cellText(side?.title) || side?.url || side?.id || "";
  return {
    matched: Number(s.matched) || 0,
    current: Number(s.current_total) || 0,
    previous: Number(s.previous_total) || 0,
    onlyCurrent: rows.filter((row) => row.match === "none" && row.current).map((row) => title(row.current)),
    onlyPrevious: rows.filter((row) => row.match === "none" && row.previous).map((row) => title(row.previous)),
  };
});

const spineRows = computed(() =>
  (diff.value?.spine?.fields || []).map((row) => ({
    key: row.field,
    label: [
      "recommendation_sentence",
      "verdict",
      "fair_value_range",
      "entry",
      "key_metrics",
      "scenarios",
      "risks",
    ].includes(row.field)
      ? t(`viewer.diff.spine.${row.field}`)
      : String(row.field || ""),
    previous: valueText(row.previous),
    current: valueText(row.current),
    changed: Boolean(row.changed),
  })),
);

const notes = computed(() =>
  (diff.value?.notes || []).map((note) => {
    const text = String(note || "");
    if (/^Some rows were paired by similar labels/i.test(text)) return t("viewer.diff.note_fuzzy");
    if (/no memo package on disk/i.test(text)) return t("viewer.diff.note_no_package");
    return text;
  }),
);

const nothingToShow = computed(
  () =>
    diff.value &&
    !verdict.value &&
    !headlines.value &&
    !buffettRows.value.length &&
    !tables.value.length &&
    !sources.value &&
    !spineRows.value.length,
);
</script>

<template>
  <div class="flex h-full min-h-0 flex-col" data-testid="changes-panel">
    <div class="flex shrink-0 items-center gap-2 border-b border-subtle px-3 py-2">
      <History class="h-3.5 w-3.5 text-accent" />
      <div class="min-w-0 flex-1">
        <div class="truncate text-footnote font-semibold text-ink-primary">
          {{ t("viewer.changes_since", { date: previousDate }) }}
        </div>
        <div v-if="apart" class="text-caption1 text-ink-muted">{{ t("viewer.diff.apart", { span: apart }) }}</div>
      </div>
      <button
        type="button"
        class="rounded-full p-1 text-ink-muted transition-colors hover:bg-ink-primary/[0.06] hover:text-ink-primary focus-ring"
        :title="t('comments.close')"
        :aria-label="t('comments.close')"
        data-testid="changes-close"
        @click="emit('close')"
      >
        <X class="h-3.5 w-3.5" />
      </button>
    </div>

    <div class="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-2.5 text-footnote">
      <div v-if="loading" class="flex items-center gap-2 text-ink-muted">
        <Loader2 class="h-3.5 w-3.5 animate-spin" />
        {{ t("viewer.diff.loading") }}
      </div>
      <p v-else-if="error" class="text-danger" role="alert">{{ error }}</p>
      <p v-else-if="nothingToShow" class="text-ink-muted">{{ t("viewer.diff.nothing") }}</p>

      <template v-if="diff && !loading">
        <!-- The call -->
        <section v-if="verdict" data-testid="changes-verdict">
          <div class="text-caption1 font-semibold text-ink-muted">{{ t("viewer.diff.call") }}</div>
          <div class="mt-0.5 flex flex-wrap items-center gap-1.5 text-callout font-semibold text-ink-primary">
            <template v-if="verdict.changed">
              <span class="text-ink-secondary line-through decoration-ink-muted/60">{{ verdict.previous }}</span>
              <ArrowRight class="h-3.5 w-3.5 text-ink-muted" />
              <span>{{ verdict.current }}</span>
            </template>
            <span v-else>{{ t("viewer.diff.call_same", { verdict: verdict.current }) }}</span>
          </div>
          <p
            v-if="verdict.unstable"
            class="mt-1.5 flex items-start gap-1.5 rounded-[8px] bg-warning-soft px-2 py-1.5 text-warning-ink"
            data-testid="changes-unstable"
          >
            <TriangleAlert class="mt-px h-3.5 w-3.5 shrink-0" />
            <span>{{ t("reports.version.unstable_hint", { span: apart }) }}</span>
          </p>
        </section>

        <!-- The opening line of each -->
        <section v-if="headlines" data-testid="changes-headlines">
          <div class="text-caption1 font-semibold text-ink-muted">{{ t("viewer.diff.headline") }}</div>
          <div class="mt-1 grid grid-cols-2 gap-2">
            <div class="rounded-[8px] bg-ink-primary/[0.04] p-2">
              <div class="text-caption2 font-semibold text-ink-muted">{{ t("viewer.diff.earlier", { date: previousDate }) }}</div>
              <p class="mt-0.5 text-ink-secondary">{{ headlines.previous || "—" }}</p>
            </div>
            <div class="rounded-[8px] bg-accent/[0.06] p-2">
              <div class="text-caption2 font-semibold text-accent-ink">{{ t("viewer.diff.this", { date: currentDate }) }}</div>
              <p class="mt-0.5 text-ink-primary">{{ headlines.current || "—" }}</p>
            </div>
          </div>
        </section>

        <!-- Buffett-method: the price and value fields -->
        <section v-if="buffettRows.length" data-testid="changes-buffett">
          <div class="grid grid-cols-[minmax(0,0.8fr)_minmax(0,1fr)_minmax(0,1fr)] gap-x-2 gap-y-1">
            <span></span>
            <span class="text-caption2 font-semibold text-ink-muted">{{ t("viewer.diff.earlier", { date: previousDate }) }}</span>
            <span class="text-caption2 font-semibold text-accent-ink">{{ t("viewer.diff.this", { date: currentDate }) }}</span>
            <template v-for="row in buffettRows" :key="row.key">
              <span class="text-caption1 font-medium text-ink-muted">{{ row.label }}</span>
              <span class="text-ink-secondary">{{ row.previous || "—" }}</span>
              <span :class="row.changed ? 'font-medium text-ink-primary' : 'text-ink-secondary'">{{ row.current || "—" }}</span>
            </template>
          </div>
        </section>

        <!-- Late-stage tables, side by side -->
        <section v-for="table in tables" :key="table.component" :data-testid="`changes-table-${table.component}`">
          <div class="text-caption1 font-semibold text-ink-muted">{{ table.title }}</div>
          <div class="mt-1 space-y-1.5">
            <div
              v-for="row in table.shown"
              :key="row.id"
              class="rounded-[8px] border border-subtle p-2"
              data-testid="changes-row"
              :data-match="row.match"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <div class="font-medium text-ink-primary">{{ row.label || "—" }}</div>
                  <div v-if="row.earlierLabel" class="text-caption1 text-ink-muted">
                    {{ t("viewer.diff.earlier_label", { label: row.earlierLabel }) }}
                  </div>
                </div>
                <span
                  class="shrink-0 rounded-[5px] px-1.5 py-px text-caption2 font-semibold"
                  :class="row.match === 'none' ? 'bg-ink-primary/[0.06] text-ink-muted' : row.match === 'fuzzy' ? 'bg-notice-soft text-notice-ink' : 'bg-success-soft text-success-ink'"
                  data-testid="changes-match"
                >
                  {{ matchLabel(row.match) }}
                </span>
              </div>
              <div class="mt-1 grid grid-cols-2 gap-2">
                <p class="text-ink-secondary">{{ row.previous || "—" }}</p>
                <p :class="row.changed ? 'text-ink-primary' : 'text-ink-secondary'">{{ row.current || "—" }}</p>
              </div>
            </div>
            <button
              v-if="table.unchanged.length"
              type="button"
              class="rounded-full px-2 py-0.5 text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.08] focus-ring"
              :data-testid="`changes-unchanged-${table.component}`"
              @click="toggleUnchanged(table.component)"
            >
              {{
                openUnchanged.has(table.component)
                  ? t("viewer.diff.hide_unchanged")
                  : t("viewer.diff.unchanged_rows", { count: table.unchanged.length })
              }}
            </button>
            <template v-if="openUnchanged.has(table.component)">
              <div
                v-for="row in table.unchanged"
                :key="row.id"
                class="rounded-[8px] border border-subtle p-2 opacity-80"
              >
                <div class="font-medium text-ink-secondary">{{ row.label || "—" }}</div>
                <p class="mt-0.5 text-ink-secondary">{{ row.current || row.previous || "—" }}</p>
              </div>
            </template>
          </div>
        </section>

        <!-- v2 spine -->
        <section v-if="spineRows.length" data-testid="changes-spine">
          <div class="text-caption1 font-semibold text-ink-muted">{{ t("viewer.diff.spine_title") }}</div>
          <div class="mt-1 space-y-1.5">
            <div v-for="row in spineRows" :key="row.key" class="rounded-[8px] border border-subtle p-2">
              <div class="flex items-center justify-between gap-2">
                <span class="font-medium text-ink-primary">{{ row.label }}</span>
                <span class="text-caption2 font-semibold" :class="row.changed ? 'text-warning-ink' : 'text-ink-muted'">
                  {{ row.changed ? t("viewer.diff.changed") : t("viewer.diff.same") }}
                </span>
              </div>
              <div class="mt-1 grid grid-cols-2 gap-2">
                <p class="text-ink-secondary">{{ row.previous || "—" }}</p>
                <p class="text-ink-primary">{{ row.current || "—" }}</p>
              </div>
            </div>
          </div>
        </section>

        <!-- Sources -->
        <section v-if="sources" data-testid="changes-sources">
          <div class="text-caption1 font-semibold text-ink-muted">{{ t("viewer.diff.sources") }}</div>
          <p class="mt-0.5 text-ink-secondary">
            {{ t("viewer.diff.sources_summary", { matched: sources.matched, current: sources.current, previous: sources.previous }) }}
          </p>
          <button
            v-if="sources.onlyCurrent.length || sources.onlyPrevious.length"
            type="button"
            class="mt-1 rounded-full px-2 py-0.5 text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.08] focus-ring"
            data-testid="changes-sources-toggle"
            @click="openSources = !openSources"
          >
            {{ openSources ? t("viewer.diff.hide_sources") : t("viewer.diff.show_sources") }}
          </button>
          <div v-if="openSources" class="mt-1 space-y-2">
            <div v-if="sources.onlyCurrent.length">
              <div class="text-caption2 font-semibold text-ink-muted">
                {{ t("viewer.diff.sources_unmatched_this", { count: sources.onlyCurrent.length }) }}
              </div>
              <ul class="mt-0.5 list-disc space-y-0.5 pl-4 text-ink-secondary">
                <li v-for="(title, index) in sources.onlyCurrent" :key="`c-${index}`">{{ title }}</li>
              </ul>
            </div>
            <div v-if="sources.onlyPrevious.length">
              <div class="text-caption2 font-semibold text-ink-muted">
                {{ t("viewer.diff.sources_unmatched_earlier", { count: sources.onlyPrevious.length }) }}
              </div>
              <ul class="mt-0.5 list-disc space-y-0.5 pl-4 text-ink-secondary">
                <li v-for="(title, index) in sources.onlyPrevious" :key="`p-${index}`">{{ title }}</li>
              </ul>
            </div>
          </div>
        </section>

        <p v-for="(note, index) in notes" :key="`note-${index}`" class="text-caption1 text-ink-muted" data-testid="changes-note">
          {{ note }}
        </p>
      </template>
    </div>
  </div>
</template>
