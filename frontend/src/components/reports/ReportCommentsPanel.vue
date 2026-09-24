<script setup>
// Comments and reader flags on one report (G2 phase 2, G7): the firm's
// shared comment store, target kind report/section. Lists them (open first,
// resolved behind a toggle), adds a comment tied to the section on screen,
// takes a flag raised on a text selection, and resolves. Posting and
// resolving need memo:edit; everyone else reads.
import { computed, ref, watch } from "vue";
import { CheckCircle2, Flag, Loader2, MessageSquare, X } from "lucide-vue-next";
import { api } from "../../api.js";
import { useT } from "../../i18n.js";
import { appLanguage } from "../../state.js";
import ReportFlagForm from "./ReportFlagForm.vue";

const props = defineProps({
  report: { type: Object, required: true },
  // The language of the document on screen (en | zh), stored with a flag.
  language: { type: String, default: "" },
  // The outline section the reader is in: { key, label } or null.
  section: { type: Object, default: null },
  // A passage the reader selected to flag: { quote, label, language } or null.
  flagDraft: { type: Object, default: null },
  canEdit: { type: Boolean, default: false },
});

const emit = defineEmits(["close", "changed", "flag-done", "go-to-section"]);
const t = useT();

const items = ref([]);
const loading = ref(false);
const loadError = ref("");
const saving = ref(false);
const saveError = ref("");
const flagError = ref("");
const text = ref("");
const onSection = ref(true);
const showResolved = ref(false);
let loadToken = 0;

async function load() {
  const id = props.report?.id;
  if (!id) return;
  const token = ++loadToken;
  loading.value = true;
  loadError.value = "";
  try {
    const payload = await api.listReportComments(id);
    if (token !== loadToken) return;
    items.value = Array.isArray(payload?.items) ? payload.items : [];
  } catch {
    if (token !== loadToken) return;
    loadError.value = t("comments.load_failed");
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

watch(
  () => props.report?.id,
  () => {
    items.value = [];
    text.value = "";
    saveError.value = "";
    showResolved.value = false;
    load();
  },
  { immediate: true },
);

// Replies hang under their comment; top-level items open first, oldest
// first (the order they were raised), resolved ones behind the toggle.
const threads = computed(() => {
  const replies = new Map();
  const top = [];
  for (const item of items.value) {
    if (!item || typeof item !== "object") continue;
    if (item.parent_id) {
      if (!replies.has(item.parent_id)) replies.set(item.parent_id, []);
      replies.get(item.parent_id).push(item);
    } else {
      top.push(item);
    }
  }
  return top.map((item) => ({ item, replies: replies.get(item.id) || [] }));
});
const openThreads = computed(() => threads.value.filter((thread) => !thread.item.resolved_at));
const resolvedThreads = computed(() => threads.value.filter((thread) => thread.item.resolved_at));

const sectionLabel = computed(() => String(props.section?.label || "").trim());

function author(item) {
  const handle = String(item?.author_handle || "").trim();
  if (handle) return `@${handle}`;
  return String(item?.author || "").trim() || t("comments.someone");
}

function when(value) {
  const parsed = Date.parse(value || "");
  if (Number.isNaN(parsed)) return "";
  return new Date(parsed).toLocaleString(appLanguage.value === "zh" ? "zh-CN" : "en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function languageTag(item) {
  const lang = String(item?.language || "").toLowerCase();
  return lang === "en" || lang === "zh" ? t(`comments.lang.${lang}`) : "";
}

async function addComment() {
  const body = text.value.trim();
  const id = props.report?.id;
  if (!body || !id || saving.value) return;
  saving.value = true;
  saveError.value = "";
  const tied = onSection.value && sectionLabel.value;
  try {
    await api.addReportComment(id, {
      text: body,
      kind: tied ? "section" : "report",
      label: tied ? sectionLabel.value : "",
      ...(props.language ? { language: props.language } : {}),
    });
    text.value = "";
    emit("changed");
    await load();
  } catch {
    saveError.value = t("comments.save_failed");
  } finally {
    saving.value = false;
  }
}

async function submitFlag({ flag, note }) {
  const id = props.report?.id;
  const draft = props.flagDraft;
  if (!id || !draft || saving.value) return;
  saving.value = true;
  flagError.value = "";
  const label = String(draft.label || "").trim();
  try {
    await api.addReportComment(id, {
      text: note || "",
      kind: label ? "section" : "report",
      label,
      flag,
      quote: String(draft.quote || "").slice(0, 300),
      ...(draft.language ? { language: draft.language } : {}),
    });
    emit("flag-done", { sent: true });
    emit("changed");
    await load();
  } catch {
    flagError.value = t("comments.save_failed");
  } finally {
    saving.value = false;
  }
}

async function resolve(item) {
  const id = props.report?.id;
  if (!id || !item?.id || saving.value) return;
  saving.value = true;
  saveError.value = "";
  try {
    await api.resolveReportComment(id, item.id);
    emit("changed");
    await load();
  } catch {
    saveError.value = t("comments.save_failed");
  } finally {
    saving.value = false;
  }
}

watch(
  () => props.flagDraft,
  () => {
    flagError.value = "";
  },
);

defineExpose({ reload: load });
</script>

<template>
  <div class="flex h-full min-h-0 flex-col" data-testid="comments-panel">
    <div class="flex shrink-0 items-center gap-2 border-b border-subtle px-3 py-2">
      <MessageSquare class="h-3.5 w-3.5 text-accent" />
      <span class="min-w-0 flex-1 truncate text-footnote font-semibold text-ink-primary">
        {{ t("comments.title") }}
      </span>
      <span v-if="openThreads.length" class="text-caption1 text-ink-muted tabular">
        {{ t("comments.open_count", { count: openThreads.length }) }}
      </span>
      <button
        type="button"
        class="rounded-full p-1 text-ink-muted transition-colors hover:bg-ink-primary/[0.06] hover:text-ink-primary focus-ring"
        :title="t('comments.close')"
        :aria-label="t('comments.close')"
        data-testid="comments-close"
        @click="emit('close')"
      >
        <X class="h-3.5 w-3.5" />
      </button>
    </div>

    <div class="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 py-2">
      <ReportFlagForm
        v-if="flagDraft && canEdit"
        :quote="flagDraft.quote"
        :section-label="flagDraft.label || ''"
        :language="flagDraft.language || ''"
        :busy="saving"
        :error="flagError"
        @submit="submitFlag"
        @cancel="emit('flag-done', { sent: false })"
      />

      <div v-if="loading && !items.length" class="flex items-center gap-2 py-3 text-footnote text-ink-muted">
        <Loader2 class="h-3.5 w-3.5 animate-spin" />
        {{ t("comments.loading") }}
      </div>
      <p v-else-if="loadError" class="py-2 text-footnote text-danger" role="alert">{{ loadError }}</p>
      <p
        v-else-if="!threads.length && !flagDraft"
        class="py-2 text-footnote text-ink-muted"
        data-testid="comments-empty"
      >
        {{ t("comments.empty") }}
      </p>

      <article
        v-for="thread in openThreads"
        :key="thread.item.id"
        class="rounded-[10px] border border-subtle bg-surface p-2.5"
        :data-comment-id="thread.item.id"
        data-testid="comment-item"
      >
        <div class="flex items-start gap-2">
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-caption1 text-ink-muted">
              <span class="font-semibold text-ink-secondary">{{ author(thread.item) }}</span>
              <span class="tabular">{{ when(thread.item.created_at) }}</span>
              <span v-if="languageTag(thread.item)">· {{ languageTag(thread.item) }}</span>
            </div>
            <div class="mt-1 flex flex-wrap items-center gap-1">
              <span
                v-if="thread.item.flag"
                class="inline-flex items-center gap-0.5 rounded-[5px] bg-warning-soft px-1.5 py-px text-caption2 font-semibold text-warning-ink"
                data-testid="comment-flag"
              >
                <Flag class="h-2.5 w-2.5" />
                {{ t(`comments.flag_type.${thread.item.flag}`) }}
              </span>
              <button
                v-if="thread.item.target?.label"
                type="button"
                class="max-w-full truncate rounded-[5px] bg-ink-primary/[0.05] px-1.5 py-px text-left text-caption2 font-medium text-ink-secondary hover:text-accent-ink focus-ring"
                :title="thread.item.target.label"
                data-testid="comment-section"
                @click="emit('go-to-section', thread.item.target.label)"
              >
                {{ thread.item.target.label }}
              </button>
            </div>
          </div>
          <button
            v-if="canEdit"
            type="button"
            class="shrink-0 rounded-full px-2 py-0.5 text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.08] disabled:opacity-50 focus-ring"
            :disabled="saving"
            data-testid="comment-resolve"
            @click="resolve(thread.item)"
          >
            {{ t("comments.resolve") }}
          </button>
        </div>
        <blockquote
          v-if="thread.item.quote"
          class="mt-1.5 line-clamp-4 border-l-2 border-subtle pl-2 text-footnote italic text-ink-secondary"
          data-testid="comment-quote"
        >
          {{ thread.item.quote }}
        </blockquote>
        <p class="mt-1 whitespace-pre-wrap break-words text-footnote text-ink-primary">{{ thread.item.text }}</p>
        <div
          v-for="reply in thread.replies"
          :key="reply.id"
          class="mt-1.5 border-l border-subtle pl-2 text-footnote"
        >
          <div class="text-caption1 text-ink-muted">
            <span class="font-semibold text-ink-secondary">{{ author(reply) }}</span>
            <span class="tabular"> · {{ when(reply.created_at) }}</span>
          </div>
          <p class="whitespace-pre-wrap break-words text-ink-primary">{{ reply.text }}</p>
        </div>
      </article>

      <button
        v-if="resolvedThreads.length"
        type="button"
        class="rounded-full px-2 py-0.5 text-caption1 font-medium text-accent-ink transition-colors hover:bg-accent/[0.08] focus-ring"
        data-testid="comments-toggle-resolved"
        @click="showResolved = !showResolved"
      >
        {{
          showResolved
            ? t("comments.hide_resolved")
            : t("comments.show_resolved", { count: resolvedThreads.length })
        }}
      </button>
      <template v-if="showResolved">
        <article
          v-for="thread in resolvedThreads"
          :key="thread.item.id"
          class="rounded-[10px] border border-subtle bg-surface-muted/40 p-2.5 opacity-80"
          :data-comment-id="thread.item.id"
          data-testid="comment-resolved"
        >
          <div class="flex flex-wrap items-center gap-x-1.5 text-caption1 text-ink-muted">
            <CheckCircle2 class="h-3 w-3 text-success" />
            <span class="font-semibold text-ink-secondary">{{ author(thread.item) }}</span>
            <span class="tabular">{{ when(thread.item.created_at) }}</span>
            <span v-if="thread.item.flag">· {{ t(`comments.flag_type.${thread.item.flag}`) }}</span>
          </div>
          <blockquote
            v-if="thread.item.quote"
            class="mt-1 line-clamp-2 border-l-2 border-subtle pl-2 text-footnote italic text-ink-muted"
          >
            {{ thread.item.quote }}
          </blockquote>
          <p class="mt-1 whitespace-pre-wrap break-words text-footnote text-ink-secondary">{{ thread.item.text }}</p>
          <p class="mt-1 text-caption1 text-ink-muted">
            {{
              thread.item.resolved_by
                ? t("comments.resolved_by", { name: thread.item.resolved_by })
                : t("comments.resolved")
            }}
          </p>
        </article>
      </template>
    </div>

    <form
      v-if="canEdit"
      class="shrink-0 space-y-1.5 border-t border-subtle px-3 py-2"
      data-testid="comment-form"
      @submit.prevent="addComment"
    >
      <label
        v-if="sectionLabel"
        class="flex min-w-0 items-center gap-1.5 text-caption1 text-ink-muted"
      >
        <input v-model="onSection" type="checkbox" class="shrink-0" data-testid="comment-on-section" />
        <span class="truncate" :title="sectionLabel">{{ t("comments.on_section", { section: sectionLabel }) }}</span>
      </label>
      <textarea
        v-model="text"
        rows="2"
        maxlength="4000"
        class="field field-sm w-full resize-y"
        :placeholder="t('comments.add_placeholder')"
        :aria-label="t('comments.add_placeholder')"
        data-testid="comment-text"
        @keydown.meta.enter.prevent="addComment"
        @keydown.ctrl.enter.prevent="addComment"
      ></textarea>
      <div class="flex items-center justify-between gap-2">
        <span v-if="!sectionLabel || !onSection" class="min-w-0 truncate text-caption1 text-ink-muted" data-testid="comment-target">
          {{ t("comments.whole_report") }}
        </span>
        <span v-else class="flex-1"></span>
        <button
          type="submit"
          class="btn-filled btn-sm shrink-0 focus-ring"
          :disabled="saving || !text.trim()"
          data-testid="comment-send"
        >
          {{ t("comments.send") }}
        </button>
      </div>
      <p v-if="saveError" class="text-caption1 text-danger" role="alert">{{ saveError }}</p>
    </form>
    <p v-else class="shrink-0 border-t border-subtle px-3 py-2 text-caption1 text-ink-muted" data-testid="comments-read-only">
      {{ t("comments.read_only") }}
    </p>
  </div>
</template>
