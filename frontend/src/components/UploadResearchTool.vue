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

const expanded = ref(false);
const file = ref(null);
const title = ref("");
const sourceCompany = ref("");
const contactName = ref("");
const contactEmail = ref("");
const notes = ref("");
const submitting = ref(false);
const error = ref(null);
const fileInput = ref(null);

const ACCEPT = ".pdf,.docx,.doc,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword,text/plain";

function onPick(e) {
  const f = e.target.files?.[0];
  if (!f) return;
  file.value = f;
  if (!title.value) title.value = f.name.replace(/\.[^.]+$/, "");
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
    router.push({ name: "external-research", params: { id: item.id } });
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
          class="px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm"
        />
        <input
          v-model="sourceCompany"
          :placeholder="t('upload_research.placeholder_source')"
          class="px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm"
        />
        <input
          v-model="contactName"
          :placeholder="t('upload_research.placeholder_contact_name')"
          class="px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm"
        />
        <input
          v-model="contactEmail"
          type="email"
          :placeholder="t('upload_research.placeholder_contact_email')"
          class="px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm"
        />
      </div>
      <textarea
        v-model="notes"
        rows="2"
        :placeholder="t('upload_research.placeholder_notes')"
        class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring text-sm resize-y"
      ></textarea>

      <div v-if="error" class="text-sm text-danger">{{ error }}</div>

      <div class="flex justify-end">
        <button
          type="button"
          @click="submit"
          :disabled="!file || submitting"
          class="px-3 py-2 rounded-lg bg-accent text-white text-sm hover:bg-accent-hover disabled:opacity-60 focus-ring inline-flex items-center gap-1.5"
        >
          <Loader2 v-if="submitting" class="h-3.5 w-3.5 animate-spin" />
          <UploadCloud v-else class="h-3.5 w-3.5" />
          <span>{{ submitting ? t("upload_research.uploading") : t("upload_research.upload") }}</span>
        </button>
      </div>
    </div>
  </section>
</template>
