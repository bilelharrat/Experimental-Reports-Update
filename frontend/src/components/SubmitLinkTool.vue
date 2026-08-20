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
import { useT } from "../i18n.js";

const t = useT();

const router = useRouter();
const emit = defineEmits(["created"]);

// v-model:expanded — HomeView drives this from ?intake= deep-links; the
// header button below still toggles it locally.
const expanded = defineModel("expanded", { type: Boolean, default: false });
const url = ref("");
const previewing = ref(false);
const preview = ref(null);
const error = ref(null);
const submitting = ref(false);
const savedItem = ref(null);

function assignmentSummary(item) {
  const assignment = item?.intake_assignment;
  if (!assignment) return "";
  if (item.dedupe_status === "duplicate") {
    return "Duplicate intake found; using the existing archived item.";
  }
  if (assignment.status === "assigned") {
    return `Filed to ${assignment.company_name} · ${assignment.category_label}`;
  }
  return `Needs assignment review · ${assignment.category_label}`;
}

// Mirrors the server's own https:// prefixing (link intake accepts bare
// hosts). Returns a localized error string, or null when the URL is usable.
function urlValidationError() {
  const raw = url.value.trim();
  if (!raw) return t("submit_link.error_url_required");
  try {
    const candidate = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const parsed = new URL(candidate);
    if (!parsed.hostname || !parsed.hostname.includes(".")) {
      return t("submit_link.error_url_invalid");
    }
  } catch {
    return t("submit_link.error_url_invalid");
  }
  return null;
}

async function runPreview() {
  error.value = null;
  preview.value = null;
  const invalid = urlValidationError();
  if (invalid) {
    error.value = invalid;
    return;
  }
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
  const invalid = urlValidationError();
  if (invalid) {
    error.value = invalid;
    return;
  }
  submitting.value = true;
  error.value = null;
  try {
    const item = await api.createNews(url.value.trim());
    emit("created");
    savedItem.value = item;
  } catch (e) {
    error.value = e.message;
  } finally {
    submitting.value = false;
  }
}

function cancel() {
  preview.value = null;
  url.value = "";
  savedItem.value = null;
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
        {{ t("submit_link.title") }}
        <span class="text-xs text-ink-muted font-normal">
          {{ t("submit_link.subtitle") }}
        </span>
      </span>
      <ChevronDown v-if="expanded" class="h-4 w-4 text-ink-muted" />
      <ChevronRight v-else class="h-4 w-4 text-ink-muted" />
    </button>

    <div v-if="expanded" class="border-t border-subtle px-4 py-3 space-y-3">
      <form @submit.prevent="runPreview" class="flex items-center gap-2">
        <!-- type=text, not type=url: native constraint validation silently
             cancels the submit event for invalid values, so the user gets no
             spinner and no error. Validation happens in runPreview instead. -->
        <input
          v-model="url"
          type="text"
          inputmode="url"
          :placeholder="t('submit_link.url_placeholder')"
          class="field flex-1 focus-ring"
        />
        <button
          type="submit"
          :disabled="previewing"
          class="btn-filled focus-ring"
        >
          <Loader2 v-if="previewing" class="h-3.5 w-3.5 animate-spin" />
          <span>{{ t("submit_link.preview") }}</span>
        </button>
      </form>

      <div v-if="error" class="text-sm text-danger">{{ error }}</div>

      <div
        v-if="preview"
        class="rounded-card bg-surface-muted p-3 flex items-start gap-3"
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
            >{{ t("submit_link.chars_captured", { n: preview.text_chars }) }}</span>
          </div>
        </div>
        <div class="shrink-0 flex flex-col gap-1.5">
          <button
            type="button"
            @click="accept"
            :disabled="submitting"
            class="btn-filled btn-sm focus-ring"
          >
            <Sparkles class="h-3 w-3" />
            <span>{{ submitting ? t("common.saving") : t("submit_link.accept") }}</span>
          </button>
          <button
            type="button"
            @click="cancel"
            class="px-3 py-1.5 rounded-lg border border-subtle text-xs text-ink-secondary hover:bg-surface focus-ring"
          >
            {{ t("common.cancel") }}
          </button>
        </div>
      </div>

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
          @click="router.push({ name: 'external-news', params: { id: savedItem.id } })"
          class="btn-bordered btn-sm mt-2 focus-ring"
        >
          <ExternalLink class="h-3 w-3" />
          {{ t("intake.open_analysis") }}
        </button>
      </div>
    </div>
  </section>
</template>
