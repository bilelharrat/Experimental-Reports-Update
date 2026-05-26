<script setup>
import { onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { ArrowLeft, FileText, ScrollText, Trash2 } from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const props = defineProps({ id: { type: String, required: true } });
const router = useRouter();
const t = useT();

const item = ref(null);
const error = ref(null);

async function load() {
  error.value = null;
  try {
    item.value = await api.getHormuz(props.id);
  } catch (e) {
    error.value = e.message;
  }
}

onMounted(load);
watch(() => props.id, load);

async function remove() {
  if (!confirm(t("hormuz.delete_confirm"))) return;
  await api.deleteHormuz(props.id);
  router.push({ name: "home" });
}
</script>

<template>
  <div class="max-w-3xl mx-auto px-8 py-10 space-y-6">
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
      <header class="flex items-start gap-3 border-b border-subtle pb-5">
        <ScrollText class="h-5 w-5 text-ink-muted mt-1 shrink-0" />
        <div class="flex-1 min-w-0">
          <div class="text-xs uppercase tracking-wider text-ink-muted">
            {{ t("hormuz.research_label") }}
          </div>
          <h1
            class="font-display text-2xl font-semibold text-ink-primary mt-0.5"
          >
            {{ item.title }}
          </h1>
          <div
            v-if="item.captured_at"
            class="mt-1 text-xs text-ink-muted"
          >
            {{ new Date(item.captured_at).toLocaleString() }}
          </div>
        </div>
        <button
          @click="remove"
          class="p-1.5 rounded hover:bg-danger-soft text-ink-muted hover:text-danger-ink focus-ring"
          :title="t('common.delete')"
        >
          <Trash2 class="h-4 w-4" />
        </button>
      </header>

      <a
        v-if="item.stored_name"
        :href="api.hormuzFileUrl(item.id)"
        target="_blank"
        rel="noopener"
        class="flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted hover:bg-surface text-sm text-ink-primary focus-ring"
      >
        <FileText class="h-4 w-4 text-ink-muted shrink-0" />
        <span class="truncate flex-1">{{ item.filename || item.stored_name }}</span>
        <span v-if="item.size_bytes" class="text-xs text-ink-muted">
          {{ Math.round(item.size_bytes / 1024) }} KB
        </span>
      </a>

      <pre
        v-if="item.body"
        class="whitespace-pre-wrap font-body text-sm leading-relaxed text-ink-primary bg-surface-muted rounded-lg p-4 border border-subtle"
        >{{ item.body }}</pre
      >
      <p v-else-if="!item.stored_name" class="text-sm text-ink-muted italic">
        {{ t("hormuz.no_comments") }}
      </p>
    </template>
  </div>
</template>
