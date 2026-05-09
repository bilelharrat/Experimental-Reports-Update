<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Globe,
  Loader2,
  Sparkles,
} from "lucide-vue-next";
import { api } from "../api.js";

const router = useRouter();
const emit = defineEmits(["created"]);

const expanded = ref(false);
const url = ref("");
const previewing = ref(false);
const preview = ref(null);
const error = ref(null);
const submitting = ref(false);

async function runPreview() {
  error.value = null;
  preview.value = null;
  if (!url.value.trim()) return;
  previewing.value = true;
  try {
    preview.value = await api.linkPreview(url.value.trim());
  } catch (e) {
    error.value = e.message;
  } finally {
    previewing.value = false;
  }
}

async function accept() {
  if (!url.value.trim()) return;
  submitting.value = true;
  error.value = null;
  try {
    const item = await api.createNews(url.value.trim());
    emit("created");
    // Take user straight to the detail page so they see analysis progress.
    router.push({ name: "external-news", params: { id: item.id } });
  } catch (e) {
    error.value = e.message;
  } finally {
    submitting.value = false;
  }
}

function cancel() {
  preview.value = null;
  url.value = "";
}
</script>

<template>
  <section
    class="bg-surface border border-subtle rounded-card shadow-card overflow-hidden"
  >
    <button
      type="button"
      @click="expanded = !expanded"
      class="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-muted focus-ring text-left"
    >
      <span class="flex items-center gap-2 text-sm font-medium text-ink-primary">
        <Globe class="h-4 w-4 text-ink-muted" />
        Submit a link
        <span class="text-xs text-ink-muted font-normal">
          — paste a news article or web page; we'll archive and summarize it
        </span>
      </span>
      <ChevronDown v-if="expanded" class="h-4 w-4 text-ink-muted" />
      <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
    </button>

    <div v-if="expanded" class="border-t border-subtle px-4 py-3 space-y-3">
      <form @submit.prevent="runPreview" class="flex items-center gap-2">
        <input
          v-model="url"
          type="url"
          placeholder="https://example.com/article"
          class="flex-1 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring"
        />
        <button
          type="submit"
          :disabled="!url.trim() || previewing"
          class="px-3 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-60 focus-ring inline-flex items-center gap-1.5"
        >
          <Loader2 v-if="previewing" class="h-3.5 w-3.5 animate-spin" />
          <span>Preview</span>
        </button>
      </form>

      <div v-if="error" class="text-sm text-danger">{{ error }}</div>

      <div
        v-if="preview"
        class="rounded-card border border-subtle bg-surface-muted p-3 flex items-start gap-3"
      >
        <img
          v-if="preview.image"
          :src="preview.image"
          alt=""
          class="h-16 w-16 rounded object-cover bg-surface shrink-0"
          @error="(e) => (e.target.style.display = 'none')"
        />
        <div class="flex-1 min-w-0">
          <div class="text-xs text-ink-muted truncate">
            <img
              v-if="preview.favicon"
              :src="preview.favicon"
              alt=""
              class="h-3 w-3 inline mr-1 align-text-bottom"
            />
            <span>{{ preview.site_name || preview.domain }}</span>
          </div>
          <div class="text-sm font-medium text-ink-primary mt-0.5">
            {{ preview.title || preview.final_url }}
          </div>
          <p
            v-if="preview.description"
            class="text-xs text-ink-secondary mt-1 line-clamp-3"
          >
            {{ preview.description }}
          </p>
          <div class="mt-2 flex items-center gap-2 text-xs">
            <a
              :href="preview.final_url"
              target="_blank"
              rel="noopener"
              class="text-ink-muted hover:text-ink-primary inline-flex items-center gap-1 focus-ring rounded"
            >
              <ExternalLink class="h-3 w-3" />
              {{ preview.final_url.replace(/^https?:\/\//, "").slice(0, 60) }}
            </a>
            <span
              v-if="preview.text_chars"
              class="text-ink-subtle"
            >· {{ preview.text_chars }} chars captured</span>
          </div>
        </div>
        <div class="shrink-0 flex flex-col gap-1.5">
          <button
            type="button"
            @click="accept"
            :disabled="submitting"
            class="px-3 py-1.5 rounded-lg bg-accent text-white text-xs hover:bg-accent-hover disabled:opacity-60 focus-ring inline-flex items-center gap-1"
          >
            <Sparkles class="h-3 w-3" />
            <span>{{ submitting ? "Saving…" : "Accept" }}</span>
          </button>
          <button
            type="button"
            @click="cancel"
            class="px-3 py-1.5 rounded-lg border border-subtle text-xs text-ink-secondary hover:bg-surface focus-ring"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
