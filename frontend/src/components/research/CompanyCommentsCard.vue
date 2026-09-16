<script setup>
// Web twin of MacCommentsView (MacFirmViews.swift): threaded company
// comments with @handle mentions, open count, the Resolved toggle,
// reply/resolve/delete controls and inline @handle suggestions.
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";
import { MessageSquare, Check, Trash2, Send } from "lucide-vue-next";
import { formatRelativeTime } from "../../formatters.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
  company: {
    type: Object,
    default: () => ({}),
  },
});

const comments = ref([]);
const chatHandles = ref([]);
const draft = ref("");
const posting = ref(false);
const postError = ref(null);
const showResolved = ref(false);
const replyTo = ref(null);

// Scope: the company target (kind "company", ref companyId), plus replies.
const scoped = computed(() =>
  comments.value.filter(
    (c) =>
      (c.target?.kind === "company" && c.target?.ref === props.companyId) || c.parent_id != null,
  ),
);

function isResolved(c) {
  return Boolean(c.resolved_at || c.resolved);
}

const roots = computed(() =>
  scoped.value.filter((c) => c.parent_id == null && (showResolved.value || !isResolved(c))),
);

const openCount = computed(
  () => scoped.value.filter((c) => c.parent_id == null && !isResolved(c)).length,
);

function repliesFor(parentId) {
  return scoped.value.filter((c) => c.parent_id === parentId);
}

// @handle suggestions for the draft, like the Mac's chatHandles matcher.
const handleSuggestions = computed(() => {
  const at = draft.value.lastIndexOf("@");
  if (at === -1 || !chatHandles.value.length) return [];
  const partial = draft.value.slice(at + 1).toLowerCase();
  if (partial.includes(" ")) return [];
  return chatHandles.value.filter((h) => h.toLowerCase().startsWith(partial)).slice(0, 5);
});

function applySuggestion(handle) {
  const at = draft.value.lastIndexOf("@");
  draft.value = `${draft.value.slice(0, at)}@${handle} `;
}

// Split a comment into pieces so @mentions render in accent bold.
function mentionPieces(text) {
  return String(text || "")
    .split(/(\s+)/)
    .map((piece) => ({ text: piece, mention: piece.startsWith("@") }));
}

async function loadComments() {
  if (!props.companyId) return;
  try {
    const res = await api.getCompanyComments(props.companyId);
    comments.value = res?.items ?? res ?? [];
  } catch {
    comments.value = [];
  }
}

async function loadHandles() {
  if (chatHandles.value.length) return;
  try {
    const res = await api.getChatChannels();
    chatHandles.value = res?.handles ?? [];
  } catch {
    chatHandles.value = [];
  }
}

watch(
  () => props.companyId,
  () => {
    draft.value = "";
    replyTo.value = null;
    postError.value = null;
    loadComments();
    loadHandles();
  },
  { immediate: true },
);

async function postComment() {
  const text = draft.value.trim();
  if (!text || posting.value) return;
  posting.value = true;
  postError.value = null;
  try {
    await api.addCompanyComment(props.companyId, {
      text,
      target: { kind: "company", ref: props.companyId },
      parent_id: replyTo.value?.id || undefined,
    });
    draft.value = "";
    replyTo.value = null;
    await loadComments();
  } catch (err) {
    postError.value = err?.message || t("research_desk.comments_post_failed");
  } finally {
    posting.value = false;
  }
}

async function resolveComment(c) {
  try {
    await api.resolveCompanyComment(props.companyId, c.id, !isResolved(c));
    await loadComments();
  } catch {
    // reload shows the truth
  }
}

async function deleteComment(c) {
  try {
    await api.deleteCompanyComment(props.companyId, c.id);
    await loadComments();
  } catch {
    // reload shows the truth
  }
}
</script>

<template>
  <div class="mac-card flex flex-col gap-2 p-2.5">
    <!-- Label("Comments · {label}") · open count · Resolved toggle -->
    <div class="flex items-center gap-2">
      <MessageSquare class="mac-c-accent h-3.5 w-3.5" stroke-width="2.4" />
      <span class="mac-t-subheadline truncate" style="font-weight: 600">
        {{ t("research_desk.comments_title", { label: company?.name || companyId }) }}
      </span>
      <span class="flex-1" />
      <span v-if="openCount > 0" class="mac-t-caption10" :style="{ color: 'var(--mac-orange)' }">
        {{ t("research_desk.open_comments_count", { count: openCount }) }}
      </span>
      <label class="flex select-none items-center gap-1.5">
        <input v-model="showResolved" type="checkbox" />
        <span class="mac-t-caption10">{{ t("research_desk.resolved") }}</span>
      </label>
    </div>

    <!-- Threads -->
    <template v-for="c in roots" :key="c.id">
      <div
        class="flex flex-col gap-[3px] rounded-md p-1.5"
        :style="{ background: `color-mix(in srgb, var(--mac-secondary) ${isResolved(c) ? 3 : 6}%, transparent)` }"
      >
        <span class="flex items-center gap-1.5">
          <span class="mac-t-caption10 font-semibold">{{ c.author_handle || c.author || "—" }}</span>
          <span class="mac-t-caption10 mac-c-secondary">{{ formatRelativeTime(c.created_at) }}</span>
          <span v-if="isResolved(c)" class="mac-t-caption10 flex items-center gap-0.5" :style="{ color: 'var(--mac-green)' }">
            <Check class="h-2.5 w-2.5" />
            {{ t("research_desk.resolved") }}
          </span>
          <span class="flex-1" />
          <button type="button" class="mac-t-caption10 mac-c-accent border-none bg-transparent p-0" @click="replyTo = c">
            {{ t("research_desk.reply") }}
          </button>
          <button type="button" class="mac-t-caption10 mac-c-accent border-none bg-transparent p-0" @click="resolveComment(c)">
            {{ isResolved(c) ? t("research_desk.comments_reopen") : t("research_desk.comments_resolve") }}
          </button>
          <button type="button" class="mac-c-secondary border-none bg-transparent p-0" @click="deleteComment(c)">
            <Trash2 class="h-2.5 w-2.5" />
          </button>
        </span>
        <p class="mac-t-caption10">
          <template v-for="(piece, idx) in mentionPieces(c.text)" :key="idx">
            <span v-if="piece.mention" class="mac-c-accent font-bold">{{ piece.text }}</span>
            <template v-else>{{ piece.text }}</template>
          </template>
        </p>
      </div>

      <!-- Replies, indented 18pt -->
      <div
        v-for="reply in repliesFor(c.id)"
        :key="reply.id"
        class="ml-[18px] flex flex-col gap-[3px] rounded-md p-1.5"
        style="background: color-mix(in srgb, var(--mac-secondary) 6%, transparent)"
      >
        <span class="flex items-center gap-1.5">
          <span class="mac-t-caption10 font-semibold">{{ reply.author_handle || reply.author || "—" }}</span>
          <span class="mac-t-caption10 mac-c-secondary">{{ formatRelativeTime(reply.created_at) }}</span>
          <span class="flex-1" />
          <button type="button" class="mac-c-secondary border-none bg-transparent p-0" @click="deleteComment(reply)">
            <Trash2 class="h-2.5 w-2.5" />
          </button>
        </span>
        <p class="mac-t-caption10">
          <template v-for="(piece, idx) in mentionPieces(reply.text)" :key="idx">
            <span v-if="piece.mention" class="mac-c-accent font-bold">{{ piece.text }}</span>
            <template v-else>{{ piece.text }}</template>
          </template>
        </p>
      </div>
    </template>

    <span v-if="roots.length === 0" class="mac-t-caption10 mac-c-secondary">
      {{ t("research_desk.no_comments_yet") }}
    </span>

    <!-- Draft -->
    <div class="flex items-start gap-2">
      <div class="flex min-w-0 flex-1 flex-col gap-1">
        <span v-if="replyTo" class="mac-t-caption10 mac-c-secondary flex items-center gap-1">
          {{ t("research_desk.replying_to", { author: replyTo.author_handle || replyTo.author || "—" }) }}
          <button type="button" class="border-none bg-transparent p-0" @click="replyTo = null">×</button>
        </span>
        <textarea
          v-model="draft"
          rows="1"
          class="mac-field w-full resize-y"
          style="line-height: 1.4"
          :placeholder="t('research_desk.comment_ph')"
          @keydown.enter.exact.prevent="postComment"
        />
        <div v-if="handleSuggestions.length" class="flex flex-wrap gap-1">
          <button
            v-for="h in handleSuggestions"
            :key="h"
            type="button"
            class="mac-btn mac-btn--mini"
            @click="applySuggestion(h)"
          >
            @{{ h }}
          </button>
        </div>
      </div>
      <button
        type="button"
        class="mac-btn mac-btn--sm shrink-0"
        :disabled="posting || !draft.trim()"
        @click="postComment"
      >
        <span v-if="posting" class="mac-spinner" style="width: 12px; height: 12px" />
        <Send v-else class="h-3 w-3" />
      </button>
    </div>
    <span v-if="postError" class="mac-t-caption10" :style="{ color: 'var(--mac-red)' }">{{ postError }}</span>
  </div>
</template>
