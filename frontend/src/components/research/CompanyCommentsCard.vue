<script setup>
import { computed, ref, watch } from "vue";
import api from "../../api.js";
import { t } from "../../i18n.js";

const props = defineProps({
  companyId: {
    type: String,
    required: true,
  },
});

const comments = ref([]);
const loading = ref(false);
const draft = ref("");
const posting = ref(false);
const showResolved = ref(false);
const replyTo = ref(null);

const roots = computed(() => {
  return comments.value.filter(
    (c) => !c.parent_id && !c.parentId && (showResolved.value || !c.is_resolved && !c.isResolved)
  );
});

const openCount = computed(() => {
  return comments.value.filter((c) => !c.is_resolved && !c.isResolved).length;
});

function repliesFor(parentId) {
  return comments.value.filter((c) => (c.parent_id || c.parentId) === parentId);
}

async function loadComments() {
  if (!props.companyId) return;
  loading.value = true;
  try {
    const res = await api.getCompanyComments(props.companyId);
    comments.value = res?.items ?? res ?? [];
  } catch (err) {
    console.error("Failed to load comments", err);
  } finally {
    loading.value = false;
  }
}

async function postComment() {
  if (!draft.value.trim() || posting.value) return;
  posting.value = true;
  try {
    await api.addCompanyComment(props.companyId, {
      body: draft.value.trim(),
      parent_id: replyTo.value?.id,
    });
    draft.value = "";
    replyTo.value = null;
    await loadComments();
  } catch (err) {
    console.error("Failed to post comment", err);
  } finally {
    posting.value = false;
  }
}

watch(
  () => props.companyId,
  () => {
    loadComments();
  },
  { immediate: true },
);
</script>

<template>
  <div class="rounded-xl border border-border/40 bg-surface/90 dark:bg-[#1c1c1e]/90 p-4 shadow-sm backdrop-blur-md">
    <!-- Header -->
    <div class="flex items-center justify-between pb-3 border-b border-border/30">
      <div class="flex items-center gap-2">
        <svg class="h-4 w-4 text-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
        <span class="font-semibold text-foreground text-xs">
          {{ t("research_desk.comments_title") }}
        </span>
        <span v-if="openCount > 0" class="rounded px-1.5 py-0.2 text-[10px] font-mono text-amber-500 bg-amber-500/10">
          {{ t("research_desk.open_comments_count", { count: openCount }) }}
        </span>
      </div>

      <label class="flex items-center gap-1.5 text-[11px] text-muted-foreground cursor-pointer select-none">
        <input v-model="showResolved" type="checkbox" class="rounded border-border/40 text-accent focus:ring-accent" />
        <span>{{ t("research_desk.resolved") }}</span>
      </label>
    </div>

    <!-- Comments List -->
    <div class="py-3 space-y-3 text-xs max-h-64 overflow-y-auto">
      <div v-if="roots.length" class="space-y-3">
        <div v-for="c in roots" :key="c.id" class="space-y-2">
          <!-- Root comment -->
          <div class="rounded-lg bg-muted/15 p-2.5 space-y-1">
            <div class="flex items-center justify-between">
              <span class="font-semibold text-foreground text-xs">{{ c.author_handle || c.author || "User" }}</span>
              <span class="text-[10px] text-muted-foreground">{{ c.created_at ? new Date(c.created_at).toLocaleDateString() : "" }}</span>
            </div>
            <p class="text-foreground text-xs">{{ c.body }}</p>
            <div class="flex items-center gap-2 pt-1">
              <button
                type="button"
                class="text-[10px] text-accent hover:underline font-medium"
                @click="replyTo = c"
              >
                {{ t("research_desk.reply") }}
              </button>
            </div>
          </div>

          <!-- Replies -->
          <div v-for="reply in repliesFor(c.id)" :key="reply.id" class="ml-4 rounded-lg bg-muted/20 p-2 space-y-1">
            <div class="flex items-center justify-between">
              <span class="font-medium text-foreground text-[11px]">{{ reply.author_handle || reply.author || "User" }}</span>
              <span class="text-[10px] text-muted-foreground">{{ reply.created_at ? new Date(reply.created_at).toLocaleDateString() : "" }}</span>
            </div>
            <p class="text-foreground text-xs">{{ reply.body }}</p>
          </div>
        </div>
      </div>

      <div v-else class="py-4 text-center text-muted-foreground text-xs">
        {{ t("research_desk.no_comments_yet") }}
      </div>
    </div>

    <!-- Input bar -->
    <div class="pt-2 border-t border-border/30 space-y-2">
      <div v-if="replyTo" class="flex items-center justify-between text-[11px] text-muted-foreground bg-muted/20 px-2 py-1 rounded">
        <span>{{ t("research_desk.replying_to", { author: replyTo.author_handle || replyTo.author }) }}</span>
        <button type="button" class="text-foreground hover:text-rose-500" @click="replyTo = null">×</button>
      </div>

      <div class="flex items-center gap-2">
        <input
          v-model="draft"
          type="text"
          :placeholder="t('research_desk.comment_ph')"
          class="flex-1 rounded-lg border border-border/40 bg-surface dark:bg-muted/30 px-3 py-1.5 text-xs text-foreground placeholder-muted-foreground/60 focus:outline-none focus:ring-1 focus:ring-accent"
          @keydown.enter.prevent="postComment"
        />
        <button
          type="button"
          class="btn-filled rounded-lg px-3 py-1.5 text-xs text-white transition-opacity disabled:opacity-50"
          :disabled="!draft.trim() || posting"
          @click="postComment"
        >
          {{ t("research_desk.send") }}
        </button>
      </div>
    </div>
  </div>
</template>
