<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  ScrollText,
  Plus,
} from "lucide-vue-next";
import { api } from "../api.js";

const router = useRouter();
const emit = defineEmits(["created"]);

const expanded = ref(false);
const title = ref("");
const body = ref("");
const submitting = ref(false);
const error = ref(null);

async function submit() {
  if (!title.value.trim()) return;
  submitting.value = true;
  error.value = null;
  try {
    const item = await api.createHormuz({
      title: title.value.trim(),
      body: body.value,
    });
    emit("created");
    router.push({ name: "hormuz-research", params: { id: item.id } });
  } catch (e) {
    error.value = e.message;
  } finally {
    submitting.value = false;
  }
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
        <ScrollText class="h-4 w-4 text-ink-muted" />
        Add Hormuz research
        <span class="text-xs text-ink-muted font-normal">
          — internal research note
        </span>
      </span>
      <ChevronDown v-if="expanded" class="h-4 w-4 text-ink-muted" />
      <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
    </button>

    <div v-if="expanded" class="border-t border-subtle px-4 py-3 space-y-2">
      <input
        v-model="title"
        placeholder="Title"
        class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm"
      />
      <textarea
        v-model="body"
        rows="5"
        placeholder="Body — observations, analysis, references…"
        class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm resize-y"
      ></textarea>

      <div v-if="error" class="text-sm text-danger">{{ error }}</div>

      <div class="flex justify-end">
        <button
          type="button"
          @click="submit"
          :disabled="!title.trim() || submitting"
          class="px-3 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-60 focus-ring inline-flex items-center gap-1.5"
        >
          <Loader2 v-if="submitting" class="h-3.5 w-3.5 animate-spin" />
          <Plus v-else class="h-3.5 w-3.5" />
          <span>{{ submitting ? "Saving…" : "Save note" }}</span>
        </button>
      </div>
    </div>
  </section>
</template>
