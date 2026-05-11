<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  ArrowLeft,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  Send,
  Sparkles,
} from "lucide-vue-next";
import { api } from "../api.js";
import CompanyLibrary from "../components/CompanyLibrary.vue";
import CompanyDetail from "../components/CompanyDetail.vue";

const props = defineProps({ companyId: { type: String, required: true } });
const emit = defineEmits(["reports-changed"]);

const route = useRoute();
const router = useRouter();

const company = ref(null);
const companyError = ref(null);
const options = ref({ report_types: [], audiences: [], languages: [] });

const reportType = ref("Investment Report");
const audience = ref("Internal");

const activeReport = ref(null);
const generating = computed(
  () => activeReport.value && activeReport.value.status !== "complete",
);

// Memo report — language toggle for the preview pane.
const previewLanguage = ref("en");
const isMemo = computed(
  () => activeReport.value?.kind === "investment_memo_latestage",
);
const memoPreview = computed(() => {
  const r = activeReport.value;
  if (!r) return "";
  if (previewLanguage.value === "zh") return r.content_zh || r.content || "";
  return r.content_en || r.content || "";
});

const threads = ref([]);
const newQuestion = ref("");
const newAnswer = ref("");
const submittingThread = ref(false);

const libraryRefresh = ref(0);

let pollId = null;

async function loadCompany() {
  companyError.value = null;
  try {
    company.value = await api.getCompany(props.companyId);
  } catch (e) {
    companyError.value = e.message;
  }
}

async function loadOptions() {
  try {
    options.value = await api.options();
    if (!options.value.report_types.includes(reportType.value)) {
      reportType.value = options.value.report_types[0] || reportType.value;
    }
    if (!options.value.audiences.includes(audience.value)) {
      audience.value = options.value.audiences[0] || audience.value;
    }
  } catch (e) {
    // non-fatal — keep defaults.
  }
}

async function loadThreads() {
  try {
    threads.value = await api.listThreads(props.companyId);
  } catch (e) {
    threads.value = [];
  }
}

async function pollReport() {
  if (!activeReport.value) return;
  try {
    const r = await api.getReport(activeReport.value.id);
    activeReport.value = r;
    if (r.status === "complete") {
      stopPolling();
      emit("reports-changed");
      libraryRefresh.value += 1;
    }
  } catch (e) {
    stopPolling();
  }
}

async function openReportFromLibrary(r) {
  router.replace({
    name: "research",
    params: { companyId: props.companyId },
    query: { report: r.id },
  });
}

function startPolling() {
  stopPolling();
  pollId = setInterval(pollReport, 1000);
}
function stopPolling() {
  if (pollId) clearInterval(pollId);
  pollId = null;
}

async function generate() {
  try {
    const r = await api.generateReport({
      company_id: props.companyId,
      report_type: reportType.value,
      audience: audience.value,
      // Language is fixed at the server: investment-memo runs always
      // produce both EN + ZH; legacy report types default to en.
      language: "en",
    });
    activeReport.value = r;
    emit("reports-changed");
    startPolling();
  } catch (e) {
    companyError.value = e.message;
  }
}

async function submitThread() {
  if (!newQuestion.value.trim()) return;
  submittingThread.value = true;
  try {
    await api.addThread(props.companyId, {
      question: newQuestion.value.trim(),
      answer: newAnswer.value.trim(),
    });
    newQuestion.value = "";
    newAnswer.value = "";
    await loadThreads();
  } finally {
    submittingThread.value = false;
  }
}

async function loadFromQuery() {
  const reportId = route.query.report;
  if (reportId) {
    try {
      activeReport.value = await api.getReport(reportId);
      if (activeReport.value.status !== "complete") startPolling();
    } catch (e) {
      activeReport.value = null;
    }
  } else {
    activeReport.value = null;
    stopPolling();
  }
}

watch(
  () => props.companyId,
  async () => {
    activeReport.value = null;
    stopPolling();
    await Promise.all([loadCompany(), loadThreads()]);
    await loadFromQuery();
  },
);

watch(() => route.query.report, loadFromQuery);

onMounted(async () => {
  await Promise.all([loadOptions(), loadCompany(), loadThreads()]);
  await loadFromQuery();
});

onUnmounted(stopPolling);
</script>

<template>
  <div class="max-w-4xl mx-auto px-8 py-10 space-y-8">
    <div>
      <button
        @click="router.push({ name: 'home' })"
        class="text-sm text-ink-muted hover:text-ink-primary inline-flex items-center gap-1 focus-ring rounded"
      >
        <ArrowLeft class="h-4 w-4" /> Back to search
      </button>
    </div>

    <CompanyDetail
      v-if="company"
      :company="company"
      @refreshed="(c) => (company = c)"
    />

    <div
      v-else-if="companyError"
      class="rounded-card border border-subtle bg-surface p-6 text-center"
    >
      <div class="font-display text-lg text-ink-primary">Company not found</div>
      <p class="mt-1 text-sm text-ink-muted">
        No company is tracked for
        <span class="font-mono text-ink-secondary">{{ companyId }}</span>. Search
        from the home page to add it, or pick one from the sidebar.
      </p>
      <button
        @click="router.push({ name: 'home' })"
        class="mt-3 text-sm text-accent hover:text-accent-hover focus-ring rounded"
      >
        Back to search
      </button>
    </div>
    <div v-else class="text-sm text-ink-muted">Loading…</div>

    <section
      v-if="company"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <h2 class="font-display text-lg font-semibold text-ink-primary mb-4">
        Generate report
      </h2>
      <div class="grid sm:grid-cols-2 gap-4">
        <label class="block">
          <div class="text-xs font-medium text-ink-muted uppercase tracking-wide mb-1.5">
            Report type
          </div>
          <select
            v-model="reportType"
            class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary focus-ring"
          >
            <option v-for="t in options.report_types" :key="t" :value="t">
              {{ t }}
            </option>
          </select>
        </label>
        <label class="block">
          <div class="text-xs font-medium text-ink-muted uppercase tracking-wide mb-1.5">
            Audience
          </div>
          <select
            v-model="audience"
            class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary focus-ring"
          >
            <option v-for="a in options.audiences" :key="a" :value="a">
              {{ a }}
            </option>
          </select>
        </label>
      </div>
      <div class="mt-5 flex items-center gap-3">
        <button
          @click="generate"
          :disabled="generating"
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-60 disabled:cursor-not-allowed focus-ring"
        >
          <Sparkles class="h-4 w-4" />
          <span>{{ generating ? "Generating…" : "Generate report" }}</span>
        </button>
        <span v-if="generating" class="text-xs text-ink-muted">
          You can leave this page; the report continues in the background.
        </span>
      </div>
    </section>

    <section
      v-if="activeReport"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <div class="text-xs uppercase tracking-wider text-ink-muted">
            {{ activeReport.report_type }} · {{ activeReport.audience }}
            · {{ (activeReport.language || "en").toUpperCase() }}
          </div>
          <div class="font-display text-lg font-semibold text-ink-primary">
            {{ activeReport.stage || activeReport.status }}
          </div>
        </div>
        <span
          v-if="activeReport.status === 'complete'"
          class="text-xs px-2 py-1 rounded bg-success-soft text-success-ink"
          >Complete</span
        >
        <span
          v-else
          class="text-xs px-2 py-1 rounded bg-warning-soft text-warning-ink inline-flex items-center gap-1"
        >
          <Loader2 class="h-3 w-3 animate-spin" />
          {{ activeReport.progress }}%
        </span>
      </div>

      <div class="mt-4 h-2 w-full rounded-full bg-surface-muted overflow-hidden">
        <div
          class="h-full bg-accent transition-all"
          :style="{ width: (activeReport.progress || 0) + '%' }"
        ></div>
      </div>

      <ul
        v-if="activeReport.stages && activeReport.stages.length"
        class="mt-4 space-y-1 text-sm"
      >
        <li
          v-for="(s, i) in activeReport.stages"
          :key="i"
          class="flex items-center gap-2 text-ink-secondary"
        >
          <span class="h-1.5 w-1.5 rounded-full bg-accent"></span>
          <span>{{ s.label }}</span>
          <span class="text-ink-muted">— {{ s.progress }}%</span>
        </li>
      </ul>

      <!-- Memo-specific affordances: language toggle, download buttons,
           bilingual preview. Only shown for completed memo runs. -->
      <div
        v-if="isMemo && activeReport.status === 'complete'"
        class="mt-6 space-y-4"
      >
        <!-- Download row: both .docx files, always available once complete. -->
        <div class="flex flex-wrap items-center gap-3">
          <a
            v-if="activeReport.download_urls?.en"
            :href="activeReport.download_urls.en"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <FileText class="h-4 w-4" />
            <span>Download English (.docx)</span>
            <Download class="h-3.5 w-3.5 text-ink-muted" />
          </a>
          <a
            v-if="activeReport.download_urls?.zh"
            :href="activeReport.download_urls.zh"
            class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface focus-ring"
          >
            <FileText class="h-4 w-4" />
            <span>下载中文 (.docx)</span>
            <Download class="h-3.5 w-3.5 text-ink-muted" />
          </a>
          <a
            v-if="activeReport.run_dir"
            :href="`file://${activeReport.run_dir}`"
            class="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink-primary focus-ring rounded"
            :title="activeReport.run_dir"
          >
            <ExternalLink class="h-3 w-3" />
            <span>Run folder</span>
          </a>
        </div>

        <!-- Language toggle for the preview body. -->
        <div
          v-if="activeReport.content_en || activeReport.content_zh"
          class="flex items-center gap-2 text-xs"
        >
          <span class="text-ink-muted uppercase tracking-wide">Preview:</span>
          <button
            type="button"
            @click="previewLanguage = 'en'"
            :class="[
              'px-2 py-1 rounded',
              previewLanguage === 'en'
                ? 'bg-accent text-white'
                : 'bg-surface-muted text-ink-secondary hover:bg-surface',
            ]"
          >
            English
          </button>
          <button
            type="button"
            @click="previewLanguage = 'zh'"
            :class="[
              'px-2 py-1 rounded',
              previewLanguage === 'zh'
                ? 'bg-accent text-white'
                : 'bg-surface-muted text-ink-secondary hover:bg-surface',
            ]"
          >
            中文
          </button>
        </div>

        <pre
          v-if="memoPreview"
          class="whitespace-pre-wrap font-body text-sm leading-relaxed text-ink-primary bg-surface-muted rounded-lg p-4 border border-subtle"
          >{{ memoPreview }}</pre
        >
      </div>

      <!-- Non-memo reports: simple preview block (legacy). -->
      <pre
        v-else-if="activeReport.status === 'complete' && activeReport.content"
        class="mt-6 whitespace-pre-wrap font-body text-sm leading-relaxed text-ink-primary bg-surface-muted rounded-lg p-4 border border-subtle"
        >{{ activeReport.content }}</pre
      >

      <!-- Memo scope-fail: show the reason and the run folder for browsing. -->
      <div
        v-if="isMemo && activeReport.status === 'failed_scope_check' && activeReport.scope_check"
        class="mt-6 rounded-lg border border-warning bg-warning-soft p-4 text-sm text-warning-ink"
      >
        <div class="font-semibold mb-1">
          Scope check failed —
          {{ activeReport.scope_check.classification }}
        </div>
        <p>{{ activeReport.scope_check.reason }}</p>
        <p v-if="activeReport.run_dir" class="mt-2 text-xs text-ink-muted">
          Run folder preserved at
          <span class="font-mono">{{ activeReport.run_dir }}</span>
        </p>
      </div>
    </section>

    <CompanyLibrary
      v-if="company"
      :company-id="companyId"
      :refresh-key="libraryRefresh"
      @open-report="openReportFromLibrary"
    />

    <section
      v-if="company"
      class="bg-surface border border-subtle rounded-card shadow-card p-6"
    >
      <h2 class="font-display text-lg font-semibold text-ink-primary mb-1">
        Knowledge base
      </h2>
      <p class="text-sm text-ink-muted mb-4">
        Past questions and threads on this company.
      </p>

      <form @submit.prevent="submitThread" class="space-y-2 mb-5">
        <input
          v-model="newQuestion"
          placeholder="Ask a question…"
          class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring"
        />
        <textarea
          v-model="newAnswer"
          rows="2"
          placeholder="Optional notes / answer"
          class="w-full px-3 py-2 rounded-lg border border-subtle bg-surface-muted text-ink-primary placeholder:text-ink-subtle focus-ring resize-y"
        ></textarea>
        <div class="flex justify-end">
          <button
            type="submit"
            :disabled="!newQuestion.trim() || submittingThread"
            class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-60 focus-ring text-sm"
          >
            <Send class="h-3.5 w-3.5" />
            Save thread
          </button>
        </div>
      </form>

      <div v-if="threads.length === 0" class="text-sm text-ink-muted">
        No threads yet.
      </div>
      <ul class="space-y-3">
        <li
          v-for="t in threads"
          :key="t.id"
          class="border border-subtle rounded-lg p-3 bg-surface-muted"
        >
          <div class="text-sm font-medium text-ink-primary">{{ t.question }}</div>
          <div v-if="t.answer" class="mt-1 text-sm text-ink-secondary whitespace-pre-wrap">
            {{ t.answer }}
          </div>
          <div class="mt-1 text-xs text-ink-muted">{{ t.created_at }}</div>
        </li>
      </ul>
    </section>
  </div>
</template>
