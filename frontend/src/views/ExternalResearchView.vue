<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  AlertCircle,
  ArrowLeft,
  Brain,
  Building2,
  CheckCircle2,
  Download,
  FileText,
  Languages,
  Loader2,
  Mail,
  RefreshCw,
  Trash2,
  User,
} from "lucide-vue-next";
import { api } from "../api.js";
import ExternalItemBody from "../components/ExternalItemBody.vue";
import { appLanguage } from "../state.js";
import { useT } from "../i18n.js";

const t = useT();

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();

const item = ref(null);
const error = ref(null);
let pollId = null;

async function load() {
  error.value = null;
  try {
    item.value = await api.getExternalResearch(props.id);
  } catch (e) {
    error.value = e.message;
  }
}
function startPolling() {
  stopPolling();
  pollId = setInterval(async () => {
    try {
      const fresh = await api.getExternalResearch(props.id);
      item.value = fresh;
      if (fresh.status === "ready" || fresh.status === "failed") stopPolling();
    } catch {
      stopPolling();
    }
  }, 1500);
}
function stopPolling() {
  if (pollId) clearInterval(pollId);
  pollId = null;
}

onMounted(async () => {
  await load();
  if (item.value && item.value.status !== "ready" && item.value.status !== "failed")
    startPolling();
});
watch(
  () => props.id,
  async () => {
    stopPolling();
    closeTranslateStream();
    item.value = null;
    translateProgressEvents.value = [];
    translateStage.value = null;
    translating.value = false;
    translateError.value = null;
    showFullViewer.value = false;
    await load();
    if (
      item.value &&
      item.value.status !== "ready" &&
      item.value.status !== "failed"
    )
      startPolling();
  },
);
onUnmounted(stopPolling);

async function remove() {
  if (!confirm(t("external.delete_confirm"))) return;
  await api.deleteExternalResearch(props.id);
  router.push({ name: "home" });
}

const retrying = ref(false);
async function retry() {
  retrying.value = true;
  try {
    item.value = await api.retryExternalResearch(props.id);
    startPolling();
  } catch (e) {
    error.value = e.message;
  } finally {
    retrying.value = false;
  }
}

// ---- PDF translation ----

const isPdf = computed(() => {
  if (!item.value) return false;
  const ct = (item.value.content_type || "").toLowerCase();
  if (ct === "application/pdf") return true;
  return (item.value.filename || "").toLowerCase().endsWith(".pdf");
});

// Download link for the toolbar — default attachment disposition.
const fileUrl = computed(() =>
  item.value ? api.externalResearchFileUrl(item.value.id) : null,
);
// Inline-disposition variant for the <iframe> preview, otherwise the
// browser respects `Content-Disposition: attachment` and downloads
// instead of rendering inside the frame.
const inlineFileUrl = computed(() =>
  item.value ? api.externalResearchFileUrl(item.value.id, { inline: true }) : null,
);

const translation = computed(() => item.value?.pdf_translation || null);
const translating = ref(false);
const translateProgressEvents = ref([]);
const translateStage = ref(null);
const translateError = ref(null);
const translateProgressFeedRef = ref(null);
let activeTranslateStream = null;

const detectedLang = computed(
  () => translation.value?.detected_language || item.value?.language || null,
);

// Warn if the user's app language differs from what we detected as the source.
const showLangMismatch = computed(() => {
  if (!detectedLang.value) return false;
  if (detectedLang.value === "other") return false;
  return detectedLang.value !== appLanguage.value;
});

const targetLangForTranslate = computed(() => appLanguage.value);

function langLabel(code) {
  if (code === "en") return "English";
  if (code === "zh") return "中文";
  return code || "?";
}

function closeTranslateStream() {
  if (activeTranslateStream) {
    activeTranslateStream.close();
    activeTranslateStream = null;
  }
}

function handleTranslateEvent(entry) {
  if (entry.type === "stage") {
    translateStage.value = {
      stage: entry.stage,
      message: entry.message || entry.stage,
      page_no: entry.page_no,
      page_count: entry.page_count,
    };
    translateProgressEvents.value.push(entry);
  } else if (entry.type === "claude_action") {
    translateProgressEvents.value.push(entry);
  } else if (entry.type === "done") {
    translating.value = false;
    closeTranslateStream();
    // Reload the item to pick up the persisted pdf_translation block.
    load();
  } else if (entry.type === "error") {
    translateError.value = entry.error || t("external.translation_failed_short");
    translating.value = false;
    closeTranslateStream();
  }
  nextTick(() => {
    const el = translateProgressFeedRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

async function startTranslation() {
  if (!isPdf.value || translating.value) return;
  translating.value = true;
  translateError.value = null;
  translateProgressEvents.value = [];
  translateStage.value = null;

  try {
    const start = await api.startResearchTranslation(
      props.id,
      targetLangForTranslate.value,
    );
    if (start.cached) {
      // Already cached; just reload the item.
      translating.value = false;
      await load();
      return;
    }

    const es = new EventSource(api.researchTranslationStreamUrl(props.id));
    activeTranslateStream = es;
    es.onmessage = (msg) => {
      try {
        const entry = JSON.parse(msg.data);
        handleTranslateEvent(entry);
      } catch {
        // ignore
      }
    };
    es.onerror = () => {
      if (!translating.value) closeTranslateStream();
    };
  } catch (e) {
    translateError.value = e.message;
    translating.value = false;
  }
}

onBeforeUnmount(closeTranslateStream);

// Display helpers for the progress feed (mirrors HomeView search feed).
function actionLabel(entry) {
  if (entry.type === "stage") return entry.message || entry.stage;
  if (entry.action === "init")
    return `${t("jobs.action.claude_initialized")} (${entry.model || "claude"})`;
  if (entry.action === "thinking") return entry.text || t("jobs.action.thinking");
  if (entry.action === "tool_use") return `${entry.tool}: ${entry.preview || ""}`;
  if (entry.action === "tool_result") {
    const status = entry.is_error
      ? t("jobs.action.tool_error")
      : t("jobs.action.tool_ok");
    return `${entry.tool} → ${status}`;
  }
  if (entry.action === "result") {
    const cost = entry.cost_usd
      ? ` ($${Number(entry.cost_usd).toFixed(4)})`
      : "";
    const dur = entry.duration_ms
      ? ` · ${(entry.duration_ms / 1000).toFixed(1)}s`
      : "";
    return `${t("home.progress_done")}${cost}${dur}`;
  }
  return entry.type;
}
function actionIcon(entry) {
  if (entry.action === "thinking") return Brain;
  if (entry.action === "result") return CheckCircle2;
  return null;
}

const showFullViewer = ref(false);
</script>

<template>
  <div class="max-w-7xl mx-auto px-6 py-8 space-y-5">
    <button
      @click="router.push({ name: 'home' })"
      class="text-sm text-ink-muted hover:text-ink-primary inline-flex items-center gap-1 focus-ring rounded"
    >
      <ArrowLeft class="h-4 w-4" /> {{ t("external.back") }}
    </button>

    <div v-if="error" class="text-sm text-danger">{{ error }}</div>
    <div v-if="!item && !error" class="text-sm text-ink-muted">
      {{ t("external.loading") }}
    </div>

    <template v-if="item">
      <header class="flex items-start gap-4 border-b border-subtle pb-4">
        <div
          class="h-12 w-12 rounded-card bg-surface-muted border border-subtle grid place-items-center shrink-0"
        >
          <FileText class="h-5 w-5 text-ink-muted" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-xs uppercase tracking-wider text-ink-muted">
            {{ t("external.type") }}
          </div>
          <h1
            class="font-display text-2xl font-semibold text-ink-primary mt-0.5"
          >
            {{ item.title || item.filename }}
          </h1>
          <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
            <span v-if="item.source_company" class="inline-flex items-center gap-1">
              <Building2 class="h-3 w-3" />
              <span class="text-ink-secondary">{{ item.source_company }}</span>
            </span>
            <span v-if="item.contact_name" class="inline-flex items-center gap-1">
              <User class="h-3 w-3" />
              {{ item.contact_name }}
            </span>
            <a
              v-if="item.contact_email"
              :href="`mailto:${item.contact_email}`"
              class="inline-flex items-center gap-1 hover:text-ink-primary focus-ring rounded"
            >
              <Mail class="h-3 w-3" />
              {{ item.contact_email }}
            </a>
            <span v-if="item.captured_at"
              >{{
                t("news.captured", {
                  time: new Date(item.captured_at).toLocaleString(),
                })
              }}</span
            >
            <span
              v-if="detectedLang"
              class="px-1.5 py-0.5 rounded bg-surface-muted text-ink-secondary font-mono uppercase"
              :title="t('external.detected_source_language', { lang: langLabel(detectedLang) })"
              >{{ detectedLang }}</span
            >
            <span
              v-if="item.status === 'ready'"
              class="px-1.5 py-0.5 rounded bg-success-soft text-success-ink"
              >{{ t("news.ready") }}</span
            >
            <span
              v-else-if="item.status === 'failed'"
              class="px-1.5 py-0.5 rounded bg-danger-soft text-danger-ink"
              >{{ t("news.failed") }}</span
            >
            <span
              v-else
              class="px-1.5 py-0.5 rounded bg-warning-soft text-warning-ink inline-flex items-center gap-1"
            >
              <Loader2 class="h-3 w-3 animate-spin" /> {{ item.status }}
            </span>
          </div>
          <p
            v-if="item.notes"
            class="mt-2 text-sm text-ink-secondary whitespace-pre-wrap"
          >
            {{ item.notes }}
          </p>
        </div>
        <a
          v-if="item.stored_name"
          :href="fileUrl"
          :download="item.filename"
          class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring"
          :title="t('external.download_tooltip', { file: item.filename })"
        >
          <Download class="h-4 w-4" />
        </a>
        <button
          @click="remove"
          class="p-1.5 rounded hover:bg-danger-soft text-ink-muted hover:text-danger-ink focus-ring"
          :title="t('external.delete')"
        >
          <Trash2 class="h-4 w-4" />
        </button>
      </header>

      <!-- Language-mismatch warning -->
      <div
        v-if="isPdf && showLangMismatch && !translation && !translating"
        class="rounded-lg border border-warning/40 bg-warning-soft/60 px-3 py-2 text-sm text-warning-ink flex items-start gap-2"
      >
        <AlertCircle class="h-4 w-4 mt-0.5 shrink-0" />
        <div class="flex-1">
          {{ t("external.source_detected_as") }}
          <strong>{{ langLabel(detectedLang) }}</strong>
          {{ t("external.but_app_language_is") }}
          <strong>{{ langLabel(appLanguage) }}</strong>.
          {{ t("external.generate_translation_question", { lang: langLabel(appLanguage) }) }}
        </div>
        <button
          type="button"
          @click="startTranslation"
          class="text-xs px-2 py-1 rounded border border-warning/40 hover:bg-warning/10 text-warning-ink focus-ring inline-flex items-center gap-1.5 shrink-0"
        >
          <Languages class="h-3 w-3" />
          {{ t("external.translate") }}
        </button>
      </div>

      <div
        v-if="item.analysis_error"
        class="text-sm text-warning-ink bg-warning-soft border border-warning/40 rounded-lg px-3 py-2 flex items-center justify-between gap-3"
      >
        <span>{{ t("external.analysis_incomplete", { error: item.analysis_error }) }}</span>
        <button
          type="button"
          @click="retry"
          :disabled="retrying"
          class="text-xs px-2 py-1 rounded border border-warning/40 hover:bg-warning/10 text-warning-ink focus-ring inline-flex items-center gap-1.5 disabled:opacity-60 shrink-0"
        >
          <Loader2 v-if="retrying" class="h-3 w-3 animate-spin" />
          <RefreshCw v-else class="h-3 w-3" />
          <span>{{ t("external.retry") }}</span>
        </button>
      </div>
      <div
        v-if="item.error && item.status === 'failed'"
        class="text-sm text-danger-ink bg-danger-soft border border-danger/40 rounded-lg px-3 py-2"
      >
        {{ item.error }}
      </div>

      <!-- Bilingual brief summary — always render so PDF items show
           their EN/中文 toggle for summary/key_points. (Non-PDF items
           render this further below via the standalone branch.) -->
      <ExternalItemBody v-if="isPdf && (item.summary || item.translation?.summary)" :item="item" />

      <!-- Side-by-side viewer + translation -->
      <div v-if="isPdf" class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <!-- Source PDF iframe -->
        <section
          class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
        >
          <header
            class="px-3 py-2 border-b border-subtle bg-surface-muted flex items-center justify-between text-sm"
          >
            <span class="font-medium text-ink-primary">
              {{ t("external.source_panel") }} · {{ langLabel(detectedLang) }}
            </span>
            <div class="flex items-center gap-2">
              <button
                type="button"
                @click="showFullViewer = !showFullViewer"
                class="text-xs px-2 py-0.5 rounded border border-subtle hover:bg-surface focus-ring text-ink-secondary"
              >
                {{
                  showFullViewer
                    ? t("external.side_by_side")
                    : t("external.full_width")
                }}
              </button>
              <a
                :href="fileUrl"
                :download="item.filename"
                class="text-xs text-accent hover:text-accent-hover inline-flex items-center gap-1 focus-ring rounded"
              >
                <Download class="h-3 w-3" />
                {{ t("external.download") }}
              </a>
            </div>
          </header>
          <iframe
            :src="inlineFileUrl"
            class="w-full h-[80vh] border-0"
            :title="item.filename"
          ></iframe>
        </section>

        <!-- Translation panel -->
        <section
          v-if="!showFullViewer"
          class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden flex flex-col"
        >
          <header
            class="px-3 py-2 border-b border-subtle bg-surface-muted flex items-center justify-between text-sm"
          >
            <span class="font-medium text-ink-primary inline-flex items-center gap-1.5">
              <Languages class="h-3.5 w-3.5 text-ink-muted" />
              {{ t("external.translation_panel") }}
              <span v-if="translation?.target_language" class="text-ink-muted">
                · {{ langLabel(translation.target_language) }}
              </span>
            </span>
            <button
              v-if="translation && !translating"
              type="button"
              @click="startTranslation"
              class="text-xs px-2 py-0.5 rounded border border-subtle hover:bg-surface focus-ring text-ink-secondary inline-flex items-center gap-1"
              :title="t('external.retranslate_title', { lang: langLabel(appLanguage) })"
            >
              <RefreshCw class="h-3 w-3" />
              {{ t("external.retranslate") }}
            </button>
          </header>

          <!-- Empty state: prompt to translate -->
          <div
            v-if="!translation && !translating && !translateError"
            class="flex-1 flex flex-col items-center justify-center gap-3 px-6 py-10 text-center"
          >
            <Languages class="h-8 w-8 text-ink-muted" />
            <div class="text-sm text-ink-secondary">
              {{
                t("external.empty_translate_prompt", {
                  lang: langLabel(appLanguage),
                })
              }}
            </div>
            <button
              type="button"
              @click="startTranslation"
              :disabled="!isPdf"
              class="px-3 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-60 focus-ring inline-flex items-center gap-1.5"
            >
              <Languages class="h-3.5 w-3.5" />
              {{ t("external.translate_to", { lang: langLabel(appLanguage) }) }}
            </button>
          </div>

          <!-- Live progress -->
          <div
            v-else-if="translating"
            class="flex-1 flex flex-col overflow-hidden"
          >
            <div
              class="px-3 py-2 border-b border-subtle bg-canvas/40 flex items-center gap-2 text-sm"
            >
              <Loader2 class="h-4 w-4 animate-spin text-accent shrink-0" />
              <span class="text-ink-primary font-medium">
                {{ translateStage?.message || t("external.starting_translation") }}
              </span>
              <span
                v-if="translateStage?.stage"
                class="ml-auto text-[10px] uppercase tracking-wide text-ink-muted font-mono"
              >
                {{ translateStage.stage }}
              </span>
            </div>
            <div
              ref="translateProgressFeedRef"
              class="flex-1 overflow-y-auto px-3 py-2 space-y-1 font-mono text-[12px] leading-snug bg-canvas"
            >
              <div
                v-for="(entry, i) in translateProgressEvents"
                :key="i"
                class="flex items-start gap-2 px-2 py-1 rounded"
                :class="{
                  'bg-accent-soft/30': entry.type === 'stage',
                  'text-danger': entry.is_error,
                }"
              >
                <component
                  v-if="actionIcon(entry)"
                  :is="actionIcon(entry)"
                  class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted"
                />
                <span
                  v-else
                  class="h-3.5 w-3.5 mt-0.5 shrink-0 text-ink-muted text-center"
                  >·</span
                >
                <div class="min-w-0 flex-1 break-words text-ink-secondary">
                  {{ actionLabel(entry) }}
                </div>
              </div>
            </div>
          </div>

          <!-- Error state -->
          <div
            v-else-if="translateError"
            class="flex-1 px-4 py-6 text-sm text-danger-ink bg-danger-soft/40"
          >
            <div class="flex items-start gap-2">
              <AlertCircle class="h-4 w-4 mt-0.5 shrink-0" />
              <div class="flex-1">
                {{ t("external.translation_failed", { error: translateError }) }}
              </div>
            </div>
            <button
              type="button"
              @click="startTranslation"
              class="mt-3 text-xs px-2 py-1 rounded border border-danger/40 hover:bg-danger/10 text-danger-ink focus-ring inline-flex items-center gap-1.5"
            >
              <RefreshCw class="h-3 w-3" />
              {{ t("external.retry") }}
            </button>
          </div>

          <!-- Rendered translation -->
          <div
            v-else
            class="flex-1 overflow-y-auto px-5 py-4 space-y-4 text-ink-primary"
            :class="{
              'font-zh':
                translation.target_language === 'zh',
            }"
          >
            <div
              v-for="(page, pi) in translation.pages"
              :key="pi"
              class="space-y-3"
            >
              <div
                class="text-[10px] uppercase tracking-wider text-ink-muted border-t border-subtle pt-2"
                v-if="pi > 0"
              >
                {{ t("external.page", { page: page.page }) }}
              </div>
              <template v-for="(b, bi) in page.blocks" :key="bi">
                <h1
                  v-if="b.type === 'heading' && (b.level || 1) === 1"
                  class="text-xl font-display font-semibold text-ink-primary"
                >
                  {{ b.text }}
                </h1>
                <h2
                  v-else-if="b.type === 'heading' && (b.level || 2) === 2"
                  class="text-lg font-display font-semibold text-ink-primary"
                >
                  {{ b.text }}
                </h2>
                <h3
                  v-else-if="b.type === 'heading'"
                  class="text-base font-display font-semibold text-ink-primary"
                >
                  {{ b.text }}
                </h3>
                <ul
                  v-else-if="b.type === 'list_item'"
                  class="list-disc pl-6 text-ink-secondary"
                >
                  <li>{{ b.text }}</li>
                </ul>
                <blockquote
                  v-else-if="b.type === 'quote'"
                  class="border-l-2 border-accent pl-3 text-ink-secondary italic"
                >
                  {{ b.text }}
                </blockquote>
                <div
                  v-else-if="b.type === 'caption'"
                  class="text-xs text-ink-muted italic text-center"
                >
                  {{ b.text }}
                </div>
                <div
                  v-else-if="b.type === 'table_row'"
                  class="grid gap-2 text-sm border-b border-subtle py-1"
                  :style="{
                    gridTemplateColumns: `repeat(${(b.cells || []).length || 1}, minmax(0, 1fr))`,
                  }"
                >
                  <span
                    v-for="(cell, ci) in b.cells || []"
                    :key="ci"
                    class="text-ink-secondary"
                  >
                    {{ cell }}
                  </span>
                </div>
                <p
                  v-else
                  class="text-ink-secondary leading-relaxed"
                >
                  {{ b.text }}
                </p>
              </template>
            </div>

            <div
              v-if="translation.claude_cost_usd"
              class="text-[10px] text-ink-subtle border-t border-subtle pt-2"
            >
              {{ t("external.translated_by") }} · ${{ Number(translation.claude_cost_usd).toFixed(4) }}
              <span v-if="translation.claude_duration_ms">
                · {{ (translation.claude_duration_ms / 1000).toFixed(1) }}s
              </span>
            </div>
          </div>
        </section>
      </div>

      <!-- Non-PDF: keep the existing summary view -->
      <ExternalItemBody v-else :item="item" />
    </template>
  </div>
</template>
