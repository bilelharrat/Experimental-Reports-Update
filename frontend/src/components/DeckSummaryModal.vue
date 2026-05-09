<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  Languages,
  Loader2,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
  file: { type: Object, default: null }, // null = closed
});
const emit = defineEmits(["close", "summary-updated"]);

const isOpen = computed(() => !!props.file);
const summary = ref(null);
const loading = ref(false);
const error = ref(null);
const tab = ref("en");

function reset() {
  summary.value = null;
  loading.value = false;
  error.value = null;
  tab.value = "en";
}

async function loadOrGenerate(forceGenerate = false) {
  if (!props.file) return;
  error.value = null;
  // Try cached on the record first.
  if (!forceGenerate && props.file.summary) {
    summary.value = props.file.summary;
    return;
  }
  if (!forceGenerate) {
    try {
      summary.value = await api.getFileSummary(props.companyId, props.file.id);
      return;
    } catch (e) {
      // 404 cached miss — proceed to generate.
    }
  }
  loading.value = true;
  try {
    summary.value = await api.generateFileSummary(props.companyId, props.file.id);
    emit("summary-updated", summary.value);
  } catch (e) {
    error.value = e.message;
  } finally {
    loading.value = false;
  }
}

async function regenerate() {
  await loadOrGenerate(true);
}

function onKey(e) {
  if (e.key === "Escape" && isOpen.value) emit("close");
}

onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));

watch(
  () => props.file?.id,
  () => {
    if (typeof document !== "undefined") {
      document.body.style.overflow = props.file ? "hidden" : "";
    }
    if (props.file) {
      reset();
      loadOrGenerate();
    } else {
      reset();
    }
  },
  { immediate: true },
);

// Default to source language tab once we know it.
watch(
  () => summary.value?.language,
  (lang) => {
    if (lang === "zh") tab.value = "zh";
    else tab.value = "en";
  },
);

const exec = computed(() =>
  summary.value?.exec_summary?.[tab.value] || "",
);
const sections = computed(() => summary.value?.sections || []);

function fmtSlideRefs(refs, lang) {
  if (!refs || refs.length === 0) return "";
  // Collapse runs of consecutive numbers: 5,6,7 → 5–7
  const sorted = [...refs].sort((a, b) => a - b);
  const groups = [];
  let start = sorted[0],
    prev = sorted[0];
  for (let i = 1; i < sorted.length; i++) {
    if (sorted[i] === prev + 1) {
      prev = sorted[i];
    } else {
      groups.push(start === prev ? `${start}` : `${start}–${prev}`);
      start = sorted[i];
      prev = sorted[i];
    }
  }
  groups.push(start === prev ? `${start}` : `${start}–${prev}`);
  return lang === "zh"
    ? `第 ${groups.join("、")} 页`
    : `slide${refs.length > 1 ? "s" : ""} ${groups.join(", ")}`;
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="isOpen"
      class="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4"
      @click.self="emit('close')"
    >
      <div
        class="w-[90vw] h-[90vh] max-w-[1100px] bg-surface rounded-card shadow-card-raised border border-subtle flex flex-col overflow-hidden"
      >
        <header
          class="flex items-center gap-3 px-5 py-3 border-b border-subtle bg-surface"
        >
          <Sparkles class="h-4 w-4 text-accent shrink-0" />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-ink-primary truncate">
              Bilingual summary — {{ file?.label || file?.filename }}
            </div>
            <div v-if="summary" class="text-xs text-ink-muted truncate">
              {{ summary.slides_used || summary.slide_count }} slides
              <span v-if="summary.mode === 'vision'">· read visually</span>
              <span v-if="summary.generated_at">
                · {{ new Date(summary.generated_at).toLocaleString() }}</span
              >
            </div>
          </div>

          <div
            v-if="summary"
            class="flex items-center gap-1 mr-1"
            :title="`Source language: ${summary.language}`"
          >
            <Languages class="h-3.5 w-3.5 text-ink-muted mr-1" />
            <button
              type="button"
              @click="tab = 'en'"
              :class="[
                'text-xs px-2.5 py-1 rounded-md border focus-ring',
                tab === 'en'
                  ? 'bg-accent text-white border-accent'
                  : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong',
              ]"
            >
              English
            </button>
            <button
              type="button"
              @click="tab = 'zh'"
              :class="[
                'text-xs px-2.5 py-1 rounded-md border focus-ring',
                tab === 'zh'
                  ? 'bg-accent text-white border-accent'
                  : 'bg-surface-muted border-subtle text-ink-secondary hover:border-strong',
              ]"
            >
              中文
            </button>
          </div>

          <button
            type="button"
            @click="regenerate"
            :disabled="loading"
            class="text-xs px-2 py-1 rounded border border-subtle hover:bg-surface-muted text-ink-secondary focus-ring inline-flex items-center gap-1.5 disabled:opacity-60"
            :title="summary ? 'Regenerate summary' : 'Generate summary'"
          >
            <Loader2 v-if="loading" class="h-3 w-3 animate-spin" />
            <RefreshCw v-else class="h-3 w-3" />
            <span>{{ loading ? "Generating…" : summary ? "Regenerate" : "Generate" }}</span>
          </button>
          <button
            type="button"
            @click="emit('close')"
            class="p-1.5 rounded hover:bg-surface-muted text-ink-muted hover:text-ink-primary focus-ring"
            aria-label="Close"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <div class="flex-1 min-h-0 overflow-y-auto px-6 py-5 bg-surface">
          <div v-if="loading && !summary" class="h-full grid place-items-center">
            <div class="max-w-md text-center">
              <Loader2 class="h-8 w-8 text-accent mx-auto mb-3 animate-spin" />
              <div class="font-display text-lg text-ink-primary">
                Reading the deck…
              </div>
              <p class="mt-1 text-sm text-ink-muted">
                Extracting slides, sending to the model, building a bilingual
                summary. Usually 10–25 seconds.
              </p>
            </div>
          </div>

          <div v-else-if="error" class="max-w-2xl">
            <div
              class="text-sm text-danger-ink bg-danger-soft border border-danger/40 rounded-lg px-3 py-2"
            >
              {{ error }}
            </div>
            <button
              type="button"
              @click="regenerate"
              class="mt-3 text-sm text-accent hover:text-accent-hover focus-ring rounded"
            >
              Try again
            </button>
          </div>

          <div v-else-if="summary" class="max-w-3xl space-y-7">
            <section>
              <h2
                class="text-xs font-semibold uppercase tracking-wide text-ink-muted mb-2"
              >
                {{ tab === "zh" ? "执行摘要" : "Executive summary" }}
              </h2>
              <p
                class="text-ink-primary leading-relaxed whitespace-pre-wrap text-base"
              >
                {{ exec }}
              </p>
            </section>

            <section v-if="sections.length">
              <h2
                class="text-xs font-semibold uppercase tracking-wide text-ink-muted mb-3"
              >
                {{ tab === "zh" ? "支持细节" : "Supporting detail" }}
              </h2>
              <div class="space-y-5">
                <article
                  v-for="(s, i) in sections"
                  :key="i"
                  class="border-l-2 border-accent/40 pl-4"
                >
                  <h3 class="font-display font-semibold text-ink-primary">
                    {{ s.title?.[tab] }}
                  </h3>
                  <p
                    class="mt-1 text-ink-secondary leading-relaxed whitespace-pre-wrap"
                  >
                    {{ s.body?.[tab] }}
                  </p>
                  <div
                    v-if="s.slide_refs && s.slide_refs.length"
                    class="mt-1.5 text-xs text-ink-muted"
                  >
                    <span class="font-mono">{{ fmtSlideRefs(s.slide_refs, tab) }}</span>
                  </div>
                </article>
              </div>
            </section>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
