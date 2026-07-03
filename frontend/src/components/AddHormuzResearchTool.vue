<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  ChevronDown,
  ChevronRight,
  Loader2,
  ScrollText,
  Plus,
  UploadCloud,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const t = useT();

const router = useRouter();
const emit = defineEmits(["created"]);

const expanded = ref(false);
const title = ref("");
const body = ref("");
const file = ref(null);
const dragOver = ref(false);
const submitting = ref(false);
const error = ref(null);
const fileInput = ref(null);
const savedItem = ref(null);

const ACCEPT =
  ".pdf,.docx,.doc,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword,text/plain";

function setFile(f) {
  if (!f) return;
  file.value = f;
  if (!title.value) title.value = f.name.replace(/\.[^.]+$/, "");
}

function onPick(e) {
  setFile(e.target.files?.[0]);
}

function onDrop(e) {
  e.preventDefault();
  dragOver.value = false;
  setFile(e.dataTransfer?.files?.[0]);
}

function onDragOver(e) {
  e.preventDefault();
  dragOver.value = true;
}

function onDragLeave() {
  dragOver.value = false;
}

function clearFile(e) {
  e.stopPropagation();
  file.value = null;
  if (fileInput.value) fileInput.value.value = "";
}

function assignmentSummary(item) {
  const assignment = item?.intake_assignment;
  if (!assignment) return "";
  if (item.dedupe_status === "duplicate") {
    return "Duplicate intake found; using the existing internal note.";
  }
  if (assignment.status === "assigned") {
    return `Filed to ${assignment.company_name} · ${assignment.category_label}`;
  }
  return `Needs assignment review · ${assignment.category_label}`;
}

async function submit() {
  if (!title.value.trim()) return;
  submitting.value = true;
  error.value = null;
  try {
    const item = await api.createHormuz({
      title: title.value.trim(),
      body: body.value,
      file: file.value,
    });
    emit("created");
    savedItem.value = item;
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
        {{ t("hormuz.title") }}
        <span class="text-xs text-ink-muted font-normal">
          {{ t("hormuz.subtitle") }}
        </span>
      </span>
      <ChevronDown v-if="expanded" class="h-4 w-4 text-ink-muted" />
      <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
    </button>

    <div v-if="expanded" class="border-t border-subtle px-4 py-3 space-y-3">
      <input
        v-model="title"
        :placeholder="t('hormuz.placeholder_title')"
        class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm"
      />

      <div
        @click="fileInput?.click()"
        @drop="onDrop"
        @dragover="onDragOver"
        @dragleave="onDragLeave"
        :class="[
          'rounded-lg border-2 border-dashed px-4 py-4 text-center cursor-pointer focus-ring transition-colors',
          dragOver
            ? 'border-accent bg-accent-soft'
            : 'border-subtle bg-surface-muted hover:border-strong',
        ]"
      >
        <UploadCloud class="h-5 w-5 text-ink-muted mx-auto mb-1" />
        <div v-if="file" class="text-sm text-ink-secondary inline-flex items-center gap-2">
          <span>{{ file.name }}</span>
          <button
            type="button"
            @click="clearFile"
            class="p-0.5 rounded hover:bg-surface text-ink-muted hover:text-ink-primary"
            :title="t('hormuz.remove_file')"
          >
            <X class="h-3.5 w-3.5" />
          </button>
        </div>
        <div v-else class="text-sm text-ink-secondary">
          {{ t("hormuz.dropzone") }}
        </div>
        <div class="text-xs text-ink-muted mt-0.5">
          {{ t("hormuz.accepted_types") }}
        </div>
        <input
          ref="fileInput"
          type="file"
          :accept="ACCEPT"
          class="hidden"
          @change="onPick"
        />
      </div>

      <textarea
        v-model="body"
        rows="5"
        :placeholder="t('hormuz.placeholder_body')"
        class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm resize-y"
      ></textarea>

      <div v-if="error" class="text-sm text-danger">{{ error }}</div>

      <div
        v-if="savedItem"
        class="rounded-card border border-subtle bg-surface-muted p-3 text-sm"
      >
        <div class="font-semibold text-ink-primary">
          {{ assignmentSummary(savedItem) }}
        </div>
        <p class="mt-1 text-xs text-ink-muted">
          {{ savedItem.intake_assignment?.company_reason || "Assignment metadata recorded for Innovation Lab." }}
        </p>
        <button
          type="button"
          @click="router.push({ name: 'hormuz-research', params: { id: savedItem.id } })"
          class="mt-2 inline-flex items-center gap-1 rounded-lg border border-subtle bg-surface px-3 py-1.5 text-xs text-ink-secondary hover:bg-surface-muted focus-ring"
        >
          Open note
        </button>
      </div>

      <div class="flex justify-end">
        <button
          type="button"
          @click="submit"
          :disabled="!title.trim() || submitting"
          class="px-3 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-60 focus-ring inline-flex items-center gap-1.5"
        >
          <Loader2 v-if="submitting" class="h-3.5 w-3.5 animate-spin" />
          <Plus v-else class="h-3.5 w-3.5" />
          <span>{{ submitting ? t("common.saving") : t("hormuz.save_note") }}</span>
        </button>
      </div>
    </div>
  </section>
</template>
