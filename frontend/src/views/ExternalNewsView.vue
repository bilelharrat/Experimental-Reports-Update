<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  ArrowLeft,
  ExternalLink,
  Globe,
  Loader2,
  RefreshCw,
  Trash2,
} from "lucide-vue-next";
import { api } from "../api.js";
import ExternalItemBody from "../components/ExternalItemBody.vue";
import { useT } from "../i18n.js";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();
const t = useT();

const item = ref(null);
const error = ref(null);
let pollId = null;

async function load() {
  error.value = null;
  try {
    item.value = await api.getNews(props.id);
  } catch (e) {
    error.value = e.message;
  }
}

function startPolling() {
  stopPolling();
  pollId = setInterval(async () => {
    try {
      const fresh = await api.getNews(props.id);
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
    item.value = null;
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
  if (!confirm(t("news.delete_confirm"))) return;
  await api.deleteNews(props.id);
  router.push({ name: "home" });
}

const retrying = ref(false);
const refreshDisabled = computed(
  () =>
    retrying.value ||
    ["queued", "fetching", "analyzing"].includes(item.value?.status),
);
async function retry() {
  retrying.value = true;
  try {
    item.value = await api.retryNews(props.id);
    startPolling();
  } catch (e) {
    error.value = e.message;
  } finally {
    retrying.value = false;
  }
}
</script>

<template>
  <div class="max-w-4xl mx-auto px-8 py-10 space-y-6">
    <button
      @click="router.push({ name: 'home' })"
      class="text-sm text-ink-muted hover:text-ink-primary inline-flex items-center gap-1 focus-ring rounded"
    >
      <ArrowLeft class="h-4 w-4" /> {{ t("common.back") }}
    </button>

    <div v-if="error" class="text-sm text-danger">{{ error }}</div>

    <div v-if="!item && !error" class="text-sm text-ink-muted">
      {{ t("common.loading") }}
    </div>

    <template v-if="item">
      <header class="flex items-start gap-4 border-b border-subtle pb-5">
        <div
          class="h-12 w-12 rounded-card bg-surface-muted border border-subtle grid place-items-center shrink-0 overflow-hidden"
        >
          <Globe class="h-5 w-5 text-ink-muted" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-xs uppercase tracking-wider text-ink-muted">
            {{ t("news.type") }} · {{ item.domain || item.site_name || t("news.link") }}
          </div>
          <h1
            class="font-display text-2xl font-semibold text-ink-primary mt-0.5"
          >
            {{ item.title || item.source_url }}
          </h1>
          <div class="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-muted">
            <a
              v-if="item.source_url"
              :href="item.final_url || item.source_url"
              target="_blank"
              rel="noopener"
              class="text-accent hover:text-accent-hover inline-flex items-center gap-1 focus-ring rounded"
            >
              <ExternalLink class="h-3 w-3" />
              {{ (item.final_url || item.source_url).replace(/^https?:\/\//, "").slice(0, 80) }}
            </a>
            <span v-if="item.captured_at"
              >{{
                t("news.captured", {
                  time: new Date(item.captured_at).toLocaleString(),
                })
              }}</span
            >
            <a
              v-if="item.archive_path"
              :href="api.newsArchiveUrl(item.id)"
              target="_blank"
              rel="noopener"
              class="text-ink-muted hover:text-ink-primary underline focus-ring rounded"
              >{{ t("news.view_archive") }}</a
            >
            <span
              v-if="item.language"
              class="px-1.5 py-0.5 rounded bg-surface-muted text-ink-secondary font-mono uppercase"
              >{{ item.language }}</span
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
        </div>
        <button
          @click="retry"
          :disabled="refreshDisabled"
          class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring disabled:opacity-50"
          :title="retrying ? t('news.refreshing_archive') : t('news.refresh_archive')"
        >
          <Loader2 v-if="retrying" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
        </button>
        <button
          @click="remove"
          class="p-1.5 rounded hover:bg-danger-soft text-ink-muted hover:text-danger-ink focus-ring"
          :title="t('common.delete')"
        >
          <Trash2 class="h-4 w-4" />
        </button>
      </header>

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
          <span>{{ t("common.retry") }}</span>
        </button>
      </div>

      <div
        v-if="item.error && item.status === 'failed'"
        class="text-sm text-danger-ink bg-danger-soft border border-danger/40 rounded-lg px-3 py-2"
      >
        {{ item.error }}
      </div>

      <ExternalItemBody :item="item" />
    </template>
  </div>
</template>
