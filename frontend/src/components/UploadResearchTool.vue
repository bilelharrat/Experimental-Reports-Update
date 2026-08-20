<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  UploadCloud,
} from "lucide-vue-next";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const t = useT();

const router = useRouter();
const emit = defineEmits(["created"]);

// v-model:expanded — HomeView drives this from ?intake= deep-links; the
// header button below still toggles it locally.
const expanded = defineModel("expanded", { type: Boolean, default: false });
const file = ref(null);
const title = ref("");
const sourceCompany = ref("");
const contactName = ref("");
const contactEmail = ref("");
const notes = ref("");
const submitting = ref(false);
const error = ref(null);
const fileInput = ref(null);
const savedItem = ref(null);

const ACCEPT = ".pdf,.pptx,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown";

function onPick(e) {
  const f = e.target.files?.[0];
  if (!f) return;
  file.value = f;
  // Don't prefill the title from the filename: the placeholder already
  // advertises "defaults to filename" and the server applies that default
  // for an empty field. A prefilled value made typing append to the
  // filename instead of replacing it (QA 2026-07-13).
}

function assignmentSummary(item) {
  const assignment = item?.intake_assignment;
  if (!assignment) return "";
  if (item.dedupe_status === "duplicate") {
    return "Duplicate intake found; using the existing research item.";
  }
  if (assignment.status === "assigned") {
    return `Filed to ${assignment.company_name} · ${assignment.category_label}`;
  }
  return `Needs assignment review · ${assignment.category_label}`;
}

async function submit() {
  if (!file.value) return;
  submitting.value = true;
  error.value = null;
  try {
    const fd = new FormData();
    fd.append("file", file.value);
    if (title.value) fd.append("title", title.value);
    if (sourceCompany.value) fd.append("source_company", sourceCompany.value);
    if (contactName.value) fd.append("contact_name", contactName.value);
    if (contactEmail.value) fd.append("contact_email", contactEmail.value);
    if (notes.value) fd.append("notes", notes.value);
    const item = await api.uploadExternalResearch(fd);
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
        <FileText class="h-4 w-4 text-ink-muted" />
        {{ t("upload_research.title") }}
        <span class="text-xs text-ink-muted font-normal">
          {{ t("upload_research.subtitle") }}
        </span>
      </span>
      <ChevronDown v-if="expanded" class="h-4 w-4 text-ink-muted" />
      <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
    </button>

    <div v-if="expanded" class="border-t border-subtle px-4 py-3 space-y-3">
      <div
        @click="fileInput?.click()"
        class="rounded-lg border-2 border-dashed border-subtle bg-surface-muted hover:border-strong px-4 py-4 text-center cursor-pointer focus-ring"
      >
        <UploadCloud class="h-5 w-5 text-ink-muted mx-auto mb-1" />
        <div class="text-sm text-ink-secondary">
          {{ file ? file.name : t("upload_research.choose_file") }}
        </div>
        <div class="text-xs text-ink-muted mt-0.5">
          {{ t("upload_research.accepted_types") }}
        </div>
        <input
          ref="fileInput"
          type="file"
          :accept="ACCEPT"
          class="hidden"
          @change="onPick"
        />
      </div>

      <div class="grid sm:grid-cols-2 gap-2">
        <input
          v-model="title"
          :placeholder="t('upload_research.placeholder_title')"
          class="field focus-ring"
        />
        <input
          v-model="sourceCompany"
          :placeholder="t('upload_research.placeholder_source')"
          class="field focus-ring"
        />
        <input
          v-model="contactName"
          :placeholder="t('upload_research.placeholder_contact_name')"
          class="field focus-ring"
        />
        <input
          v-model="contactEmail"
          type="email"
          :placeholder="t('upload_research.placeholder_contact_email')"
          class="field focus-ring"
        />
      </div>
      <textarea
        v-model="notes"
        rows="2"
        :placeholder="t('upload_research.placeholder_notes')"
        class="field resize-y focus-ring"
      ></textarea>

      <div v-if="error" class="text-sm text-danger">{{ error }}</div>

      <div
        v-if="savedItem"
        class="rounded-card bg-surface-muted p-3 text-sm"
      >
        <div class="font-semibold text-ink-primary">
          {{ assignmentSummary(savedItem) }}
        </div>
        <p class="mt-1 text-xs text-ink-muted">
          {{ savedItem.intake_assignment?.company_reason || "Assignment metadata recorded." }}
        </p>
        <button
          type="button"
          @click="router.push({ name: 'external-research', params: { id: savedItem.id } })"
          class="btn-bordered btn-sm mt-2 focus-ring"
        >
          {{ t("intake.open_analysis") }}
        </button>
      </div>

      <div class="flex justify-end">
        <button
          type="button"
          @click="submit"
          :disabled="!file || submitting"
          class="btn-filled focus-ring"
        >
          <Loader2 v-if="submitting" class="h-3.5 w-3.5 animate-spin" />
          <UploadCloud v-else class="h-3.5 w-3.5" />
          <span>{{ submitting ? t("upload_research.uploading") : t("upload_research.upload") }}</span>
        </button>
      </div>
    </div>
  </section>
</template>
