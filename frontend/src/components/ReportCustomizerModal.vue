<script setup>
import { computed, inject, ref, watch } from "vue";
import { useRouter } from "vue-router";
import {
  AlertCircle,
  AlertTriangle,
  Building2,
  Check,
  ChevronDown,
  Clock3,
  Cpu,
  Database,
  FileText,
  Info,
  Loader2,
  Search,
  X,
} from "lucide-vue-next";
import { api } from "../api.js";
import { companyIdentityParts, companyNameKey } from "../companyLogo.js";
import { useT } from "../i18n.js";
import { appLanguage } from "../state.js";
import AiMark from "./AiMark.vue";
import Monogram from "./Monogram.vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  initialCompanyId: { type: String, default: null },
  // "studio_review" opens on Memo Studio review, on its own tab, with a
  // report type that supports it. Empty keeps whatever was last chosen.
  initialGenerationMode: { type: String, default: "" },
});

const emit = defineEmits(["close", "created"]);
const router = useRouter();
const t = useT();

// Available companies from App.vue
const workspaceCompanies = inject("workspaceCompanies", ref([]));

// Target Company. Every open starts from the company the opener names, or
// from none: a silent default (the last pick, or the first company in the
// workspace) is how ⌘N on one desk once launched a memo on another.
const selectedCompanyId = ref(props.initialCompanyId || "");
const companySearch = ref("");
const companyPickerOpen = ref(false);

// Active Tab
const activeTab = ref("blueprint");
const tabs = computed(() => [
  { id: "blueprint", label: t("customizer.tab_blueprint"), icon: FileText },
  { id: "engine", label: t("customizer.tab_engine"), icon: Cpu },
  { id: "evidence", label: t("customizer.tab_evidence"), icon: Database },
]);

// Submission state
const generating = ref(false);
const error = ref(null);

const currentCompany = computed(
  () => workspaceCompanies.value.find((c) => c.id === selectedCompanyId.value) || null,
);

const filteredCompanies = computed(() => {
  const q = companySearch.value.trim().toLowerCase();
  if (!q) return workspaceCompanies.value;
  return workspaceCompanies.value.filter(
    (c) =>
      String(c.name || "").toLowerCase().includes(q) ||
      String(c.legal_name || "").toLowerCase().includes(q) ||
      String(c.ticker || "").toLowerCase().includes(q) ||
      String(c.id || "").toLowerCase().includes(q),
  );
});

// Which entity the run is about, under its name: legal name, the search's
// disambiguator and its domain. A lookalike is caught here, before the
// money is spent, not in the memo's text afterwards.
function identityLineFor(company) {
  return companyIdentityParts(company).join(" · ");
}
const identityLine = computed(() => identityLineFor(currentCompany.value));

// Tab 1: Blueprint Options.
//
// `reportType` must be a literal from the server's REPORT_TYPES — the
// endpoint compares strings and 400s on anything else. `studio` marks the
// ones Memo Studio can run: memo_prep.is_memo_report_type accepts only the
// auto and late-stage memos, and the studio endpoint additionally rejects the
// Buffett memo. `available: false` marks the three types that only ever
// reached a placeholder generator: they are shown, disabled, and can never
// be chosen. `template` marks the memos the memo template (standard / the
// founder's IC template) applies to.
const archetypes = computed(() => [
  {
    id: "auto",
    reportType: "Investment Report (Auto)",
    studio: true,
    available: true,
    template: true,
    title: t("customizer.arch_auto_title"),
    badge: t("customizer.badge_recommended"),
    desc: t("customizer.arch_auto_desc"),
  },
  {
    id: "investment_memo_late_stage",
    reportType: "Investment Memo (Late-Stage)",
    studio: true,
    available: true,
    template: true,
    title: t("customizer.arch_late_title"),
    badge: t("customizer.arch_late_badge"),
    desc: t("customizer.arch_late_desc"),
  },
  {
    id: "buffett_memo",
    reportType: "Buffett Investment Memo",
    studio: false,
    available: true,
    template: false,
    title: t("customizer.arch_buffett_title"),
    badge: t("customizer.arch_buffett_badge"),
    desc: t("customizer.arch_buffett_desc"),
  },
  {
    id: "deep_dive",
    reportType: "Financial Analysis",
    studio: false,
    available: false,
    template: false,
    title: t("customizer.arch_financial_title"),
    badge: t("customizer.arch_financial_badge"),
    desc: t("customizer.arch_financial_desc"),
  },
  {
    id: "market_analysis",
    reportType: "Market Analysis",
    studio: false,
    available: false,
    template: false,
    title: t("customizer.arch_market_title"),
    badge: t("customizer.arch_market_badge"),
    desc: t("customizer.arch_market_desc"),
  },
  {
    id: "background",
    reportType: "Background",
    studio: false,
    available: false,
    template: false,
    title: t("customizer.arch_background_title"),
    badge: t("customizer.arch_background_badge"),
    desc: t("customizer.arch_background_desc"),
  },
]);
const selectedArchetype = ref("auto");

function selectArchetype(arch) {
  if (!arch?.available) return;
  selectedArchetype.value = arch.id;
}

// `audience` must be a literal from the server's AUDIENCES ("LP",
// "Assistant", "Partner", "Internal"). Each option says what the run
// produces: the LP memo for everyone, plus an internal IC decision memo for
// the three in-house audiences (one more paid call) — never for LP, because
// the IC memo carries BSH's own sizing and walk-away and is never shared
// outside the firm.
const audiences = computed(() => [
  { id: "Internal", title: t("customizer.aud_internal_title"), desc: t("customizer.aud_internal_desc") },
  { id: "Partner", title: t("customizer.aud_partner_title"), desc: t("customizer.aud_partner_desc") },
  { id: "LP", title: t("customizer.aud_lp_title"), desc: t("customizer.aud_lp_desc") },
  { id: "Assistant", title: t("customizer.aud_assistant_title"), desc: t("customizer.aud_assistant_desc") },
]);
const selectedAudience = ref("Internal");

// The memo template: the 5-section standard memo, or the founder's
// 12-section IC template (v2), which is the server's default now
// (memo_flags). The workspace choice comes from Settings
// (memo_template_effective); a pick here applies to this run only and
// travels as `memo_template` in the request. Untouched, nothing is sent and
// the server applies the workspace choice itself — so a Settings read that
// fails can never pin a run to the wrong template.
const DEFAULT_TEMPLATE = "ic_v2";
const workspaceTemplate = ref(DEFAULT_TEMPLATE);
const selectedTemplate = ref(DEFAULT_TEMPLATE);
let templateTouched = false;

const templateOptions = computed(() => [
  { id: "standard", title: t("customizer.template_standard"), desc: t("customizer.template_standard_desc") },
  { id: "ic_v2", title: t("customizer.template_ic_v2"), desc: t("customizer.template_ic_v2_desc") },
]);

function templateName(id) {
  return id === "ic_v2" ? t("customizer.template_ic_v2") : t("customizer.template_standard");
}

function chooseTemplate(id) {
  if (studioSelected.value) return;
  templateTouched = true;
  selectedTemplate.value = id === "ic_v2" ? "ic_v2" : "standard";
}

function templateFrom(raw) {
  if (raw === "ic_v2" || raw === "standard") return raw;
  return DEFAULT_TEMPLATE;
}

async function loadWorkspaceTemplate() {
  let value = DEFAULT_TEMPLATE;
  try {
    const settings = await api.workspaceSettings();
    const prefs = settings?.preferences || {};
    value = templateFrom(
      settings?.memo_template_effective ??
        prefs.memo_template_effective ??
        settings?.memo_template ??
        prefs.memo_template,
    );
  } catch {
    // Unreadable settings: show the server's default. Nothing is sent
    // unless the analyst picks, so the server still applies its own choice.
  }
  workspaceTemplate.value = value;
  if (!templateTouched) selectedTemplate.value = value;
}

// Report length applies to the IC template only: the standard memo has one
// length, so on it the control shows as the single standard option,
// disabled, with the reason — never as two cards that change nothing.
const reportModes = computed(() => [
  { id: "compact", title: t("customizer.length_compact"), desc: t("customizer.length_compact_desc") },
  { id: "full", title: t("customizer.length_full"), desc: t("customizer.length_full_desc") },
]);
const selectedReportMode = ref("compact");

// The pipeline writes an English and a Chinese .docx on every run —
// memo_prep builds both paths unconditionally — so bilingual is not a mode
// you opt into, it is what the pipeline does. The single-language options
// are disabled until the pipeline can genuinely skip one half; picking one
// today would only change which file leads, not what gets generated.
const languages = computed(() => [
  {
    id: "dual",
    label: t("customizer.language_dual"),
    desc: t("customizer.language_dual_desc"),
    disabled: false,
  },
  {
    id: "en",
    label: t("customizer.language_en"),
    desc: t("customizer.not_available"),
    disabled: true,
  },
  {
    id: "zh",
    label: t("customizer.language_zh"),
    desc: t("customizer.not_available"),
    disabled: true,
  },
]);
const selectedLanguage = ref("dual");

// Tab 2: Engine & Quality Options
const generationModes = computed(() => [
  {
    id: "one_click",
    title: t("customizer.mode_one_click"),
    badge: t("customizer.badge_recommended"),
    desc: t("customizer.mode_one_click_desc"),
  },
  {
    id: "studio_review",
    title: t("customizer.mode_studio"),
    badge: t("customizer.mode_studio_badge"),
    desc: t("customizer.mode_studio_desc"),
  },
]);
const selectedGenerationMode = ref("one_click");

// Tiers map to claude_runner._MEMO_QUALITY_TIERS. Balanced leads: it keeps
// the top model on the English the founder reads and moves research,
// checking and translation to Sonnet.
const qualities = computed(() => [
  {
    id: "balanced",
    title: t("customizer.quality_balanced"),
    badge: t("customizer.badge_recommended"),
    desc: t("customizer.quality_balanced_desc"),
  },
  {
    id: "best",
    title: t("customizer.quality_best"),
    badge: t("customizer.quality_best_badge"),
    desc: t("customizer.quality_best_desc"),
  },
  {
    id: "economy",
    title: t("customizer.quality_economy"),
    badge: t("customizer.quality_economy_badge"),
    desc: t("customizer.quality_economy_desc"),
  },
]);
const selectedQuality = ref("balanced");

// Same pipeline either way — the stage graph, prompts, schemas, validation
// and DOCX renderer are shared; only the model differs. Claude stays the
// default because it reads the research folder itself, where Gemini is
// handed the extracted text.
const engines = computed(() => [
  {
    id: "claude",
    title: "Claude",
    badge: t("customizer.engine_claude_badge"),
    desc: t("customizer.engine_claude_desc"),
  },
  {
    id: "gemini",
    title: "Gemini",
    badge: t("customizer.engine_gemini_badge"),
    desc: t("customizer.engine_gemini_desc"),
  },
]);
const selectedEngine = ref("claude");

const activeArchetypeObj = computed(() => {
  return (
    archetypes.value.find((a) => a.id === selectedArchetype.value && a.available) ||
    archetypes.value[0]
  );
});

// The Buffett memo runs at one fixed depth and quality (memo_prep drops
// both), so its controls lock with the reason rather than look live.
const isBuffett = computed(() => activeArchetypeObj.value?.id === "buffett_memo");
const templateApplies = computed(() => Boolean(activeArchetypeObj.value?.template));

// Memo Studio's investigation takes only the company and the report type
// (POST /memos/studio/investigate): template, length, engine, quality and
// audience are the workspace's, whatever this sheet says. So they lock with
// that reason while Studio is chosen.
const studioSelected = computed(() => selectedGenerationMode.value === "studio_review");

// The template this run will be written on, as shown.
const shownTemplate = computed(() =>
  studioSelected.value ? workspaceTemplate.value : selectedTemplate.value,
);
const lengthEnabled = computed(
  () => templateApplies.value && shownTemplate.value === "ic_v2" && !studioSelected.value,
);
const lengthLockReason = computed(() => {
  if (isBuffett.value) return t("customizer.buffett_locked");
  if (studioSelected.value) return t("customizer.studio_defaults");
  return t("customizer.length_locked_standard");
});

// A Buffett memo is one document for every reader: no IC memo is written,
// so there is no audience to pick (memo_prep never writes the IC memo for a
// Buffett run). A Studio run is written for the internal IC.
const audienceLocked = computed(() => isBuffett.value || studioSelected.value);
const audienceLockReason = computed(() =>
  isBuffett.value ? t("customizer.audience_locked_buffett") : t("customizer.audience_locked_studio"),
);
const sentAudience = computed(() => (audienceLocked.value ? "Internal" : selectedAudience.value));
const shownAudienceObj = computed(
  () => audiences.value.find((a) => a.id === sentAudience.value) || audiences.value[0],
);

// The Buffett skill runs the Claude CLI as an agent and has no Gemini path
// (claude_runner.claude_only_stage_error): a Gemini pick would be ignored or
// fail. Studio takes no engine at all. Both run on Claude.
const engineLocked = computed(() => isBuffett.value || studioSelected.value);
const effectiveEngine = computed(() => (engineLocked.value ? "claude" : selectedEngine.value));
const engineLockReason = computed(() =>
  isBuffett.value ? t("customizer.engine_locked_buffett") : t("customizer.studio_defaults"),
);

// The tiers above are Claude model/effort pairs, and claude_runner drops them
// on a Gemini run (claude_runner.py:4633) — Gemini picks its own model. So the
// selector is a no-op there, and saying so beats letting it look live. The
// Buffett memo and Memo Studio ignore them too.
const qualityLocked = computed(
  () => effectiveEngine.value !== "claude" || isBuffett.value || studioSelected.value,
);
const qualityLockReason = computed(() => {
  if (isBuffett.value) return t("customizer.buffett_locked");
  if (studioSelected.value) return t("customizer.studio_defaults");
  return t("customizer.quality_locked");
});
// A Studio investigation runs at the top tier (memo_prep's default), so
// that is what shows while Studio is chosen.
const shownQuality = computed(() => (studioSelected.value ? "best" : selectedQuality.value));

// Run controls. "Pause after English" stops the run once the English memo
// is accepted (status english_ready_paused) so it can be read before the
// Chinese, artifacts and IC memo are paid for; Resume continues it. The
// spend ceiling is the run's API-equivalent budget in USD: past it, the run
// stops before its next paid phase (memo_analysis, BSH_MEMO_COST_CEILING_USD,
// default 60). Blank sends null, which means the server's default.
const DEFAULT_COST_CEILING_USD = 60;
const pauseAfterEnglish = ref(false);
const costCeilingInput = ref("");
const runControlsLocked = computed(() => studioSelected.value);
const costCeilingUsd = computed(() => {
  const raw = String(costCeilingInput.value ?? "").trim();
  if (!raw) return null;
  const number = Number(raw);
  return Number.isFinite(number) && number > 0 ? number : null;
});
const costCeilingInvalid = computed(
  () => String(costCeilingInput.value ?? "").trim() !== "" && costCeilingUsd.value === null,
);

// A short word for the run's length, for the tagline and the footer: only
// on the IC template, where it is a real choice. The standard memo's one
// length is already in its name.
const lengthShortLabel = computed(() => {
  if (!lengthEnabled.value) return "";
  return selectedReportMode.value === "full"
    ? t("customizer.length_short_full")
    : t("customizer.length_short_compact");
});

const templateShortLabel = computed(() => {
  if (!templateApplies.value) return "";
  return shownTemplate.value === "ic_v2"
    ? t("reports.ic_template_tag")
    : t("customizer.template_standard");
});

const audienceShortLabel = computed(() => (isBuffett.value ? "" : shownAudienceObj.value?.title || ""));

const qualityShortLabel = computed(() => {
  if (effectiveEngine.value !== "claude") {
    return engines.value.find((e) => e.id === effectiveEngine.value)?.title || effectiveEngine.value;
  }
  if (isBuffett.value || studioSelected.value) return "";
  return qualities.value.find((q) => q.id === selectedQuality.value)?.title || "";
});

// What this run will be, in one line, built from the choices above.
const tagline = computed(() =>
  [
    activeArchetypeObj.value?.title,
    audienceShortLabel.value,
    templateShortLabel.value,
    lengthShortLabel.value,
    studioSelected.value ? t("customizer.tag_studio") : t("customizer.tag_autonomous"),
  ]
    .filter(Boolean)
    .join(" · "),
);

const launchLabel = computed(() => {
  if (generating.value) return t("customizer.initializing");
  const name = currentCompany.value?.name;
  if (studioSelected.value) {
    return name ? t("customizer.launch_studio_for", { name }) : t("customizer.launch_studio");
  }
  return name ? t("customizer.generate_memo_for", { name }) : t("customizer.generate_memo");
});

// ---- Pre-flight -----------------------------------------------------------
// GET /api/reports/readiness: zero-cost signals only (the CLI is installed,
// a recorded Claude usage limit, a Gemini key, the company is real). It is
// advisory — Generate stays live — but it says what would stop the run and
// when a limit resets, and offers Gemini instead of switching to it.
const readiness = ref(null);
let readinessSeq = 0;

async function loadReadiness() {
  const seq = ++readinessSeq;
  const companyId = currentCompany.value?.id;
  if (!props.open || !companyId) {
    readiness.value = null;
    return;
  }
  try {
    const result = await api.reportReadiness(companyId, effectiveEngine.value);
    if (seq === readinessSeq) readiness.value = result;
  } catch {
    // No answer is not a problem to report: the run itself will say.
    if (seq === readinessSeq) readiness.value = null;
  }
}

watch(
  () => [props.open, currentCompany.value?.id, effectiveEngine.value],
  () => loadReadiness(),
  { immediate: true },
);

function localized(item) {
  if (!item) return "";
  return (appLanguage.value === "zh" ? item.zh : item.en) || item.en || item.code || "";
}

function uiLocale() {
  return appLanguage.value === "zh" ? "zh-CN" : "en-US";
}

// "15:00 (in 2 hr)" — the local clock time a limit lifts, and how far off.
function formatReset(iso) {
  const date = new Date(iso);
  if (!iso || Number.isNaN(date.getTime())) return null;
  const sameDay = date.toDateString() === new Date().toDateString();
  const time = new Intl.DateTimeFormat(uiLocale(), {
    ...(sameDay ? {} : { weekday: "short" }),
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  const minutes = Math.round((date.getTime() - Date.now()) / 60000);
  const rtf = new Intl.RelativeTimeFormat(uiLocale(), { numeric: "auto", style: "short" });
  const relative =
    Math.abs(minutes) < 90 ? rtf.format(minutes, "minute") : rtf.format(Math.round(minutes / 60), "hour");
  return { time, relative };
}

function switchEngine(engine) {
  // Only ever on the analyst's click: the pre-flight never changes the
  // engine by itself.
  selectedEngine.value = engine;
}

// Sentences run together in Chinese; English puts a space between them.
function joinSentences(...parts) {
  return parts.filter(Boolean).join(appLanguage.value === "zh" ? "" : " ");
}

function blockerRow(item) {
  const reset = item.reset_at ? formatReset(item.reset_at) : null;
  const text = joinSentences(localized(item), reset ? t("customizer.preflight_resets", reset) : "");
  const row = { key: `blocker-${item.code}`, tone: "blocker", icon: AlertCircle, text };
  const engineStatus = readiness.value?.engines || {};
  const claudeBlocker = item.code === "claude_limited" || item.code === "claude_cli_missing";
  if (
    claudeBlocker &&
    readiness.value?.suggest_engine === "gemini" &&
    !engineLocked.value &&
    effectiveEngine.value === "claude"
  ) {
    row.action = {
      label: t("customizer.preflight_switch_gemini"),
      testid: "preflight-switch-gemini",
      run: () => switchEngine("gemini"),
    };
  } else if (
    item.code === "gemini_key_missing" &&
    engineStatus.claude?.available &&
    !engineStatus.claude?.limited
  ) {
    row.action = {
      label: t("customizer.preflight_switch_claude"),
      testid: "preflight-switch-claude",
      run: () => switchEngine("claude"),
    };
  }
  if (claudeBlocker && engineLocked.value) {
    // Buffett and Studio runs have no Gemini path: say so instead.
    row.text = joinSentences(
      row.text,
      isBuffett.value
        ? t("customizer.preflight_claude_only_buffett")
        : t("customizer.preflight_claude_only_studio"),
    );
  }
  return row;
}

// ---- Which entity, and is there anything to buy ---------------------------
const CORPORATE_TYPES = new Set(["subsidiary", "nonprofit"]);

// The parent's own record, when the workspace has one: matched on name,
// legal name, ticker or id, never on a substring.
const parentRecord = computed(() => {
  const company = currentCompany.value;
  const parent = String(company?.parent_company || "").trim();
  if (!company || !parent) return null;
  const key = companyNameKey(parent);
  return (
    workspaceCompanies.value.find(
      (c) =>
        c.id !== company.id &&
        (companyNameKey(c.name) === key ||
          (c.legal_name && companyNameKey(c.legal_name) === key) ||
          String(c.ticker || "").toUpperCase() === parent.toUpperCase() ||
          String(c.id || "").toLowerCase() === parent.toLowerCase()),
    ) || null
  );
});

function isListed(company) {
  const status = String(company?.status || "").toLowerCase();
  return status === "public" || company?.company_type === "public" || Boolean(company?.ticker);
}

// Soft notes, never a gate: the analyst decides.
const identityRows = computed(() => {
  const company = currentCompany.value;
  if (!company) return [];
  const rows = [];
  const status = String(company.status || "").toLowerCase();
  const parent = String(company.parent_company || "").trim();
  if (parent) {
    const record = parentRecord.value;
    rows.push({
      key: "note-parent",
      tone: "note",
      icon: Building2,
      text: record
        ? t("customizer.note_subsidiary_of", { parent })
        : t("customizer.note_subsidiary_of_missing", { parent }),
      action: record
        ? {
            label: t("customizer.note_run_on_parent", { name: record.name || parent }),
            testid: "note-run-on-parent",
            run: () => {
              selectedCompanyId.value = record.id;
            },
          }
        : null,
    });
  } else if (CORPORATE_TYPES.has(status)) {
    rows.push({
      key: `note-${status}`,
      tone: "note",
      icon: Building2,
      text: t(status === "nonprofit" ? "customizer.note_nonprofit" : "customizer.note_subsidiary"),
    });
  }
  if (parent && status === "nonprofit") {
    rows.push({ key: "note-nonprofit", tone: "note", icon: Building2, text: t("customizer.note_nonprofit") });
  }
  // A listed company going through a private-round memo (verified.md R29
  // B): the Buffett-method memo is the one built to value a public stock.
  if (isListed(company) && !isBuffett.value && !parent) {
    rows.push({
      key: "note-listed",
      tone: "note",
      icon: Info,
      text: t("customizer.note_listed"),
      action: {
        label: t("customizer.note_use_buffett"),
        testid: "note-use-buffett",
        run: () => selectArchetype(archetypes.value.find((a) => a.id === "buffett_memo")),
      },
    });
  }
  return rows;
});

const preflightRows = computed(() => {
  const rows = [];
  const result = readiness.value;
  if (result && result.company?.id === currentCompany.value?.id) {
    for (const item of result.blockers || []) rows.push(blockerRow(item));
    for (const item of result.warnings || []) {
      rows.push({ key: `warning-${item.code}`, tone: "warning", icon: AlertTriangle, text: localized(item) });
    }
  }
  return [...rows, ...identityRows.value];
});

const PREFLIGHT_TONES = {
  blocker: "bg-danger-soft text-danger-ink",
  warning: "bg-warning-soft text-warning-ink",
  note: "bg-fill-tertiary text-ink-secondary",
};

// ---- Estimate ---------------------------------------------------------------
// GET /api/reports/estimates: finished runs' time and API-equivalent cost,
// keyed the way the report record stores a run (memo_prep leaves model
// quality and length off a Buffett run, and "best" / "full" when unset).
const estimates = ref(null);

async function loadEstimates() {
  try {
    estimates.value = await api.reportEstimates();
  } catch {
    estimates.value = null;
  }
}

const estimateKey = computed(() => {
  const buffett = isBuffett.value;
  return {
    report_type: activeArchetypeObj.value?.reportType,
    model_quality: buffett ? "best" : selectedQuality.value,
    structure_mode: buffett || sentReportMode.value === "full" ? "full" : sentReportMode.value,
    engine: effectiveEngine.value,
  };
});

const estimateRow = computed(() => {
  const rows = estimates.value?.estimates;
  if (!Array.isArray(rows)) return undefined;
  const key = estimateKey.value;
  const minSamples = Number(estimates.value?.min_samples) || 3;
  const row = rows.find(
    (r) =>
      r.report_type === key.report_type &&
      r.model_quality === key.model_quality &&
      r.structure_mode === key.structure_mode &&
      r.engine === key.engine,
  );
  return row && Number(row.samples) >= minSamples ? row : null;
});

// Minutes, to the minute under a quarter hour and to five above.
function roundMinutes(ms) {
  const minutes = Number(ms) / 60000;
  if (!Number.isFinite(minutes) || minutes <= 0) return null;
  return minutes < 15 ? Math.max(1, Math.round(minutes)) : Math.round(minutes / 5) * 5;
}

function formatUsd(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: number >= 10 ? 0 : 2,
    minimumFractionDigits: 0,
  }).format(number);
}

const estimateText = computed(() => {
  if (studioSelected.value) return "";
  const row = estimateRow.value;
  if (row === undefined) return "";
  const parts = [];
  if (row === null) {
    parts.push(t("customizer.estimate_none"));
  } else {
    const low = roundMinutes(row.duration_ms?.min);
    const high = roundMinutes(row.duration_ms?.max);
    if (low && high && low !== high) parts.push(t("customizer.estimate_time_range", { low, high }));
    else if (low || high) parts.push(t("customizer.estimate_time_about", { n: low || high }));
    const median = row.cost_usd?.median;
    if (!row.unpriced && median != null) {
      parts.push(
        t(row.engine === "claude" ? "customizer.estimate_cost_claude" : "customizer.estimate_cost", {
          cost: formatUsd(median),
        }),
      );
    } else {
      parts.push(t("customizer.estimate_unpriced"));
    }
    parts.push(t("customizer.estimate_samples", { n: row.samples }));
  }
  // A ceiling below the typical cost is worth knowing before Generate.
  if (costCeilingUsd.value != null) {
    parts.push(t("customizer.estimate_ceiling", { cost: formatUsd(costCeilingUsd.value) }));
  }
  return parts.join(" · ");
});

watch(
  () => props.initialCompanyId,
  (newId) => {
    if (newId) selectedCompanyId.value = newId;
  },
);

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    selectedCompanyId.value = props.initialCompanyId || "";
    companySearch.value = "";
    companyPickerOpen.value = false;
    error.value = null;
    generating.value = false;
    templateTouched = false;
    selectedTemplate.value = workspaceTemplate.value;
    loadWorkspaceTemplate();
    loadEstimates();
    if (props.initialGenerationMode === "studio_review") {
      if (!activeArchetypeObj.value?.studio) selectedArchetype.value = "auto";
      selectedGenerationMode.value = "studio_review";
      activeTab.value = "engine";
    }
  },
  { immediate: true },
);

// Tab 4: Evidence Sources
// Tab 4: the analysed documents this company actually has. An Analyze run
// in the Files tab writes a <name>_analysis.md beside the upload, and that
// markdown is what the memo passes read — the raw source is deliberately
// hidden behind it. Everything is selected by default: dropping one is the
// exception, not the routine.
const evidenceSources = ref([]);
const evidenceLoading = ref(false);
const evidenceLoadFailed = ref(false);

async function loadEvidenceSources(companyId) {
  if (!companyId) {
    evidenceSources.value = [];
    return;
  }
  evidenceLoading.value = true;
  evidenceLoadFailed.value = false;
  try {
    const payload = await api.listCompanyDocuments(companyId);
    const rows = (payload?.groups || []).flatMap((group) => group.rows || []);
    const seen = new Set();
    evidenceSources.value = rows
      .filter((row) => row.analysis_of && row.record_id && !seen.has(row.record_id) && seen.add(row.record_id))
      .map((row) => ({
        id: row.record_id,
        label: row.title || row.filename || row.record_id,
        uploadedAt: String(row.uploaded_at || row.captured_at || "").slice(0, 10),
        checked: true,
      }));
  } catch {
    evidenceSources.value = [];
    evidenceLoadFailed.value = true;
  } finally {
    evidenceLoading.value = false;
  }
}

const allEvidenceSelected = computed(
  () => evidenceSources.value.length > 0 && evidenceSources.value.every((s) => s.checked),
);

function toggleAllEvidence() {
  const next = !allEvidenceSelected.value;
  evidenceSources.value.forEach((src) => {
    src.checked = next;
  });
}

// null = "read the whole research folder", which is what a run did before
// this tab existed. Only an actual deselection narrows it.
const selectedEvidenceIds = computed(() => {
  if (!evidenceSources.value.length) return null;
  if (allEvidenceSelected.value) return null;
  return evidenceSources.value.filter((s) => s.checked).map((s) => s.id);
});

// What the memo will be built from, in one line. Only the analysed
// documents are counted: calls and founder updates have no count the web
// can read yet, and the web research every run does is said, not counted.
const builtFromLine = computed(() => {
  if (evidenceLoading.value || evidenceLoadFailed.value) return "";
  const total = evidenceSources.value.length;
  if (!total) return t("customizer.built_from_web_only");
  const chosen = evidenceSources.value.filter((s) => s.checked).length;
  if (!chosen) return t("customizer.built_from_none_selected");
  if (chosen < total) return t("customizer.built_from_some", { n: chosen, total });
  return total === 1 ? t("customizer.built_from_one") : t("customizer.built_from_all", { n: total });
});
const builtFromWebOnly = computed(
  () =>
    !evidenceLoading.value &&
    !evidenceLoadFailed.value &&
    !evidenceSources.value.some((s) => s.checked),
);

watch(
  () => currentCompany.value?.id,
  (companyId) => loadEvidenceSources(companyId),
  { immediate: true },
);

// Memo Studio only runs the memo archetypes. Offering it for a Buffett
// memo just buys a 400 from the studio endpoint, so it locks instead — and
// if the analyst had already chosen it, the mode falls back to One-Click.
const studioAvailable = computed(() => Boolean(activeArchetypeObj.value?.studio));

watch(studioAvailable, (ok) => {
  if (!ok && selectedGenerationMode.value === "studio_review") {
    selectedGenerationMode.value = "one_click";
  }
});

// The length the request carries: the standard memo has one, the full one,
// so a locked control never files a run under a length it did not have.
const sentReportMode = computed(() => (lengthEnabled.value ? selectedReportMode.value : "full"));

async function launchReport() {
  if (!currentCompany.value?.id) {
    error.value = t("customizer.error_no_company");
    return;
  }
  if (!activeArchetypeObj.value?.available) return;

  generating.value = true;
  error.value = null;

  try {
    const companyId = currentCompany.value.id;
    const reportTypeVal = activeArchetypeObj.value.reportType;

    if (studioSelected.value) {
      // Launch studio deep investigation
      const rep = await api.studioInvestigate({
        company_id: companyId,
        report_type: reportTypeVal,
      });

      emit("created");
      emit("close");

      // Memo Studio on the company's desk; `report` reloads its run list,
      // where the investigation waits for review.
      router.push({
        name: "research",
        params: { companyId },
        query: rep?.id ? { section: "memos", report: rep.id } : { section: "memos" },
      });
    } else {
      const payload = {
        company_id: companyId,
        report_type: reportTypeVal,
        audience: sentAudience.value,
        // The API takes one language and it names the LEAD document; both
        // are written either way. "dual" therefore sends "en".
        language: selectedLanguage.value === "zh" ? "zh" : "en",
        report_mode: sentReportMode.value,
        quality: selectedQuality.value,
        engine: effectiveEngine.value,
        evidence_files: selectedEvidenceIds.value,
        // Run controls (per run; null ceiling means the server default).
        pause_after_english: Boolean(pauseAfterEnglish.value),
        cost_ceiling_usd: costCeilingUsd.value,
      };
      // A template picked here, for this run only. Otherwise the server
      // applies the workspace's own choice.
      if (templateApplies.value && templateTouched) payload.memo_template = selectedTemplate.value;
      // Launch one-click autonomous report
      const rep = await api.generateReport(payload);

      emit("created", rep);
      emit("close");

      // Memo Studio on the company's desk, where the new run shows under
      // Active Analysis Pipelines once `report` reloads the list.
      router.push({
        name: "research",
        params: { companyId },
        query: { section: "memos", report: rep.id },
      });
    }
  } catch (err) {
    error.value = err?.message || t("customizer.error_launch");
  } finally {
    generating.value = false;
  }
}
</script>

<template>
  <div v-if="open" class="mac-desk fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 md:p-8" style="background: transparent">
    <!-- Scrim backdrop -->
    <div
      class="sheet-scrim fixed inset-0 backdrop-blur-sm"
      @click="emit('close')"
    />

    <!-- Main Summit Glass Panel -->
    <div
      class="sheet-panel relative z-10 flex h-[92vh] w-[96vw] max-w-[1040px] flex-col overflow-hidden rounded-2xl bg-canvas shadow-2xl border border-hairline"
    >
      <!-- Hero Monogram Header -->
      <header class="flex shrink-0 items-center justify-between border-b border-subtle bg-surface px-5 py-3.5">
        <div class="flex items-center gap-3.5 min-w-0">
          <Monogram
            v-if="currentCompany"
            :company="currentCompany"
            :size="38"
            tinted
          />
          <div v-else class="flex h-[38px] w-[38px] items-center justify-center rounded-xl bg-accent/10 text-accent font-bold">
            <Building2 class="h-5 w-5" />
          </div>

          <div class="min-w-0">
            <!-- Company Title with Selector Dropdown -->
            <div class="flex items-center gap-2">
              <div class="relative">
                <button
                  type="button"
                  class="flex items-center gap-1.5 text-base font-semibold text-ink-primary hover:text-accent-ink transition-colors"
                  @click="companyPickerOpen = !companyPickerOpen"
                >
                  <span class="truncate max-w-[280px] sm:max-w-[400px]">
                    {{ currentCompany?.name || t("customizer.select_company") }}
                  </span>
                  <ChevronDown class="h-4 w-4 text-ink-muted" />
                </button>

                <!-- Floating Company Picker -->
                <div
                  v-if="companyPickerOpen"
                  class="absolute left-0 top-full mt-2 z-50 w-80 rounded-xl bg-surface p-2 shadow-card border border-subtle backdrop-blur-md"
                >
                  <div class="relative mb-2">
                    <Search class="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-muted" />
                    <input
                      v-model="companySearch"
                      type="text"
                      :placeholder="t('customizer.search_company')"
                      class="field field-sm w-full !pl-8"
                      @click.stop
                    />
                  </div>
                  <div class="max-h-64 overflow-y-auto space-y-0.5">
                    <button
                      v-for="c in filteredCompanies"
                      :key="c.id"
                      type="button"
                      class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-surface-muted transition-colors"
                      :class="{ 'bg-accent/10 text-accent-ink font-medium': c.id === currentCompany?.id }"
                      @click="selectedCompanyId = c.id; companyPickerOpen = false"
                    >
                      <Monogram :company="c" :size="20" tinted />
                      <span class="min-w-0 flex-1">
                        <span class="block truncate">{{ c.name }}</span>
                        <span
                          v-if="identityLineFor(c)"
                          class="block truncate text-[11px] font-normal text-ink-muted"
                        >
                          {{ identityLineFor(c) }}
                        </span>
                      </span>
                      <span v-if="c.ticker" class="text-xs text-ink-muted uppercase">{{ c.ticker }}</span>
                    </button>
                  </div>
                </div>
              </div>

              <span
                v-if="currentCompany?.ticker"
                class="rounded-md border border-subtle bg-surface-muted px-2 py-0.5 text-xs font-mono font-semibold uppercase text-ink-secondary"
              >
                {{ currentCompany.ticker }}
              </span>

              <span
                v-if="currentCompany?.sector || currentCompany?.industry"
                class="hidden sm:inline-block rounded-md border border-subtle bg-surface-muted px-2 py-0.5 text-xs text-ink-muted truncate max-w-[140px]"
              >
                {{ currentCompany.sector || currentCompany.industry }}
              </span>
            </div>

            <!-- Which entity: legal name · disambiguator · domain. -->
            <p
              v-if="identityLine"
              class="mt-0.5 truncate text-xs text-ink-secondary"
              :title="identityLine"
              data-testid="customizer-identity"
            >
              {{ identityLine }}
            </p>

            <!-- Blueprint Status Tagline: what this run will be, from the choices. -->
            <p class="text-xs text-ink-muted mt-0.5 truncate" data-testid="customizer-tagline">
              {{ tagline }}
            </p>
          </div>
        </div>

        <!-- Close Button -->
        <button
          type="button"
          class="rounded-lg p-1.5 text-ink-muted hover:bg-surface-muted hover:text-ink-primary transition-colors focus-ring"
          :aria-label="t('customizer.close')"
          @click="emit('close')"
        >
          <X class="h-5 w-5" />
        </button>
      </header>

      <!-- Glass Tab Navigation -->
      <nav class="flex shrink-0 gap-1 border-b border-subtle bg-surface/80 px-4 py-2 overflow-x-auto">
        <button
          v-for="tItem in tabs"
          :key="tItem.id"
          type="button"
          class="flex items-center gap-2 rounded-lg px-3.5 py-1.5 text-xs font-medium transition-all focus-ring whitespace-nowrap"
          :class="[
            activeTab === tItem.id
              ? 'bg-accent text-white shadow-sm'
              : 'text-ink-secondary hover:bg-surface-muted hover:text-ink-primary',
          ]"
          @click="activeTab = tItem.id"
        >
          <component :is="tItem.icon" class="h-3.5 w-3.5" />
          <span>{{ tItem.label }}</span>
        </button>
      </nav>

      <!-- Tab Content Area -->
      <div class="flex-1 min-h-0 overflow-y-auto p-5 md:p-6 space-y-6">
        <!-- ================= TAB 1: BLUEPRINT & FRAMING ================= -->
        <div v-if="activeTab === 'blueprint'" class="space-y-6">
          <!-- Archetypes Grid -->
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="vogue-label">{{ t("customizer.archetype_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.archetype_desc") }}</span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <button
                v-for="arch in archetypes"
                :key="arch.id"
                type="button"
                :disabled="!arch.available"
                :aria-pressed="arch.available ? selectedArchetype === arch.id : undefined"
                :title="arch.available ? null : t('customizer.archetype_unavailable')"
                class="flex flex-col text-left p-3.5 rounded-xl border transition-all text-sm focus-ring relative"
                :class="[
                  !arch.available
                    ? 'border-subtle bg-surface opacity-40 cursor-not-allowed'
                    : selectedArchetype === arch.id
                      ? 'border-accent bg-accent/5 ring-1 ring-accent'
                      : 'border-subtle bg-surface hover:border-strong',
                ]"
                :data-testid="`archetype-${arch.id}`"
                @click="selectArchetype(arch)"
              >
                <div class="flex items-center justify-between gap-2 w-full mb-1">
                  <span class="font-semibold text-ink-primary">{{ arch.title }}</span>
                  <span
                    class="shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      arch.available && selectedArchetype === arch.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ arch.available ? arch.badge : t("customizer.not_available") }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted line-clamp-2 mt-0.5">{{ arch.desc }}</p>
              </button>
            </div>
          </div>

          <!-- Audience & Depth Split -->
          <div class="grid grid-cols-1 gap-6 md:grid-cols-2">
            <!-- Target Audience: what the run writes. Locked, with the
                 reason, where there is nothing to choose. -->
            <div data-testid="audience-choice">
              <span class="vogue-label block mb-2.5" :class="audienceLocked ? 'opacity-50' : ''">
                {{ t("customizer.audience_title") }}
              </span>
              <!-- The reason first: four locked cards would push it out of view. -->
              <p
                v-if="audienceLocked"
                class="-mt-1 mb-2.5 text-[11px] italic text-ink-muted"
                data-testid="audience-lock-reason"
              >
                {{ audienceLockReason }}
              </p>
              <div class="space-y-2">
                <button
                  v-for="aud in audiences"
                  :key="aud.id"
                  type="button"
                  :disabled="audienceLocked"
                  :aria-pressed="audienceLocked ? undefined : selectedAudience === aud.id"
                  class="flex w-full items-start gap-3 p-3 rounded-xl border text-left text-sm transition-all focus-ring"
                  :class="[
                    audienceLocked
                      ? 'border-subtle bg-surface opacity-40 cursor-not-allowed'
                      : selectedAudience === aud.id
                        ? 'border-accent bg-accent/5 ring-1 ring-accent'
                        : 'border-subtle bg-surface hover:border-strong',
                  ]"
                  :data-testid="`audience-${aud.id}`"
                  @click="audienceLocked || (selectedAudience = aud.id)"
                >
                  <div
                    class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border"
                    :class="[
                      !audienceLocked && selectedAudience === aud.id
                        ? 'border-accent bg-accent text-white'
                        : 'border-strong bg-surface',
                    ]"
                  >
                    <Check v-if="!audienceLocked && selectedAudience === aud.id" class="h-2.5 w-2.5 stroke-[3]" />
                  </div>
                  <div class="min-w-0">
                    <div class="font-medium text-ink-primary">{{ aud.title }}</div>
                    <div class="text-xs text-ink-muted">{{ aud.desc }}</div>
                  </div>
                </button>
              </div>
            </div>

            <!-- Template, Depth and Language -->
            <div class="space-y-5">
              <!-- Memo template: this run's, the workspace default preset.
                   The Buffett memo has its own structure, so it has none. -->
              <div v-if="templateApplies" data-testid="template-choice">
                <span class="vogue-label block mb-2.5" :class="studioSelected ? 'opacity-50' : ''">
                  {{ t("customizer.template_title") }}
                </span>
                <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <button
                    v-for="option in templateOptions"
                    :key="option.id"
                    type="button"
                    :disabled="studioSelected"
                    class="flex flex-col text-left p-3 rounded-xl border transition-all focus-ring"
                    :class="[
                      shownTemplate === option.id
                        ? 'border-accent bg-accent/5 ring-1 ring-accent'
                        : 'border-subtle bg-surface',
                      studioSelected ? 'opacity-50 cursor-not-allowed' : shownTemplate === option.id ? '' : 'hover:border-strong',
                    ]"
                    :aria-pressed="shownTemplate === option.id"
                    :data-testid="`template-${option.id}`"
                    @click="chooseTemplate(option.id)"
                  >
                    <span class="font-semibold text-xs text-ink-primary">{{ option.title }}</span>
                    <span class="text-[11px] text-ink-muted mt-1">{{ option.desc }}</span>
                  </button>
                </div>
                <p class="mt-1.5 text-[11px] text-ink-muted" data-testid="template-default-hint">
                  {{
                    studioSelected
                      ? t("customizer.template_studio_hint", { name: templateName(workspaceTemplate) })
                      : t("customizer.template_default_hint", { name: templateName(workspaceTemplate) })
                  }}
                </p>
              </div>

              <!-- Report Depth: live on the IC template only. -->
              <div>
                <span class="vogue-label block mb-2.5" :class="lengthEnabled ? '' : 'opacity-50'">
                  {{ t("customizer.scope_title") }}
                </span>
                <div v-if="lengthEnabled" class="grid grid-cols-2 gap-2" data-testid="length-modes">
                  <button
                    v-for="mode in reportModes"
                    :key="mode.id"
                    type="button"
                    class="flex flex-col text-left p-3 rounded-xl border transition-all focus-ring"
                    :class="[
                      selectedReportMode === mode.id
                        ? 'border-accent bg-accent/5 ring-1 ring-accent'
                        : 'border-subtle bg-surface hover:border-strong',
                    ]"
                    :aria-pressed="selectedReportMode === mode.id"
                    :data-testid="`length-${mode.id}`"
                    @click="selectedReportMode = mode.id"
                  >
                    <span class="font-semibold text-xs text-ink-primary">{{ mode.title }}</span>
                    <span class="text-[11px] text-ink-muted mt-1">{{ mode.desc }}</span>
                  </button>
                </div>
                <button
                  v-else
                  type="button"
                  disabled
                  class="flex w-full flex-col text-left p-3 rounded-xl border border-subtle bg-surface opacity-60 cursor-not-allowed"
                  data-testid="length-locked"
                >
                  <span class="font-semibold text-xs text-ink-primary">
                    {{
                      isBuffett
                        ? t("customizer.arch_buffett_title")
                        : shownTemplate === "ic_v2"
                          ? t("customizer.length_full")
                          : t("customizer.length_standard")
                    }}
                  </span>
                  <span v-if="!isBuffett" class="text-[11px] text-ink-muted mt-1">
                    {{
                      shownTemplate === "ic_v2"
                        ? t("customizer.length_full_desc")
                        : t("customizer.length_standard_desc")
                    }}
                  </span>
                </button>
                <p v-if="!lengthEnabled" class="mt-1.5 text-[11px] italic text-ink-muted" data-testid="length-lock-reason">
                  {{ lengthLockReason }}
                </p>
              </div>

              <!-- Language Selection -->
              <div>
                <span class="vogue-label block mb-2">{{ t("customizer.language_title") }}</span>
                <div class="grid grid-cols-3 gap-2">
                  <button
                    v-for="lang in languages"
                    :key="lang.id"
                    type="button"
                    :disabled="lang.disabled"
                    :title="lang.disabled ? t('customizer.language_locked') : null"
                    class="flex flex-col items-center justify-center p-2.5 rounded-xl border text-center transition-all focus-ring"
                    :class="[
                      lang.disabled
                        ? 'border-subtle bg-surface opacity-40 cursor-not-allowed'
                        : selectedLanguage === lang.id
                          ? 'border-accent bg-accent/5 ring-1 ring-accent'
                          : 'border-subtle bg-surface hover:border-strong',
                    ]"
                    @click="lang.disabled || (selectedLanguage = lang.id)"
                  >
                    <span class="text-xs font-semibold text-ink-primary">{{ lang.label }}</span>
                    <span class="text-[10px] text-ink-muted mt-0.5">{{ lang.desc }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ================= TAB 2: ENGINE & COMPUTE QUALITY ================= -->
        <div v-if="activeTab === 'engine'" class="space-y-6">
          <!-- Generation Workflow Mode -->
          <div>
            <div class="flex items-center justify-between mb-3">
              <span class="vogue-label">{{ t("customizer.workflow_title") }}</span>
              <span class="text-xs text-ink-muted">{{ t("customizer.workflow_desc") }}</span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                v-for="mode in generationModes"
                :key="mode.id"
                type="button"
                :disabled="mode.id === 'studio_review' && !studioAvailable"
                :title="mode.id === 'studio_review' && !studioAvailable ? t('customizer.studio_unavailable') : null"
                class="flex flex-col text-left p-4 rounded-xl border transition-all focus-ring"
                :class="[
                  mode.id === 'studio_review' && !studioAvailable
                    ? 'border-subtle bg-surface opacity-40 cursor-not-allowed'
                    : selectedGenerationMode === mode.id
                      ? 'border-accent bg-accent/5 ring-1 ring-accent'
                      : 'border-subtle bg-surface hover:border-strong',
                ]"
                @click="(mode.id === 'studio_review' && !studioAvailable) || (selectedGenerationMode = mode.id)"
              >
                <div class="flex items-center justify-between mb-1.5">
                  <span class="font-semibold text-sm text-ink-primary">{{ mode.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      selectedGenerationMode === mode.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ mode.badge }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted leading-relaxed">{{ mode.desc }}</p>
              </button>
            </div>
          </div>

          <!-- Generation engine -->
          <div>
            <div class="flex items-center justify-between gap-3 mb-3">
              <span class="vogue-label" :class="engineLocked ? 'opacity-50' : ''">{{ t("customizer.engine_title") }}</span>
              <span
                class="text-xs text-right"
                :class="engineLocked ? 'text-ink-muted italic' : 'text-ink-muted'"
                data-testid="engine-lock-reason"
              >
                {{ engineLocked ? engineLockReason : t("customizer.engine_desc") }}
              </span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                v-for="e in engines"
                :key="e.id"
                type="button"
                :disabled="engineLocked"
                class="flex flex-col text-left p-3.5 rounded-xl border transition-all focus-ring"
                :class="[
                  effectiveEngine === e.id
                    ? 'border-accent bg-accent/5 ring-1 ring-accent'
                    : 'border-subtle bg-surface',
                  engineLocked ? 'opacity-40 cursor-not-allowed' : 'hover:border-strong',
                ]"
                :aria-pressed="effectiveEngine === e.id"
                :data-testid="`engine-${e.id}`"
                @click="engineLocked || (selectedEngine = e.id)"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-semibold text-xs text-ink-primary">{{ e.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      effectiveEngine === e.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ e.badge }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted leading-relaxed">{{ e.desc }}</p>
              </button>
            </div>
          </div>

          <!-- Compute Quality Tier -->
          <div>
            <div class="flex items-center justify-between gap-3 mb-3">
              <span class="vogue-label" :class="qualityLocked ? 'opacity-50' : ''">{{
                t("customizer.quality_title")
              }}</span>
              <span class="text-xs text-right" :class="qualityLocked ? 'text-ink-muted italic' : 'text-ink-muted'" data-testid="quality-lock-reason">{{
                qualityLocked ? qualityLockReason : t("customizer.quality_desc")
              }}</span>
            </div>
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <button
                v-for="q in qualities"
                :key="q.id"
                type="button"
                class="flex flex-col text-left p-3.5 rounded-xl border transition-all focus-ring"
                :class="[
                  shownQuality === q.id
                    ? 'border-accent bg-accent/5 ring-1 ring-accent'
                    : 'border-subtle bg-surface',
                  qualityLocked ? 'opacity-40 cursor-not-allowed' : 'hover:border-strong',
                ]"
                :disabled="qualityLocked"
                :aria-pressed="shownQuality === q.id"
                :data-testid="`quality-${q.id}`"
                @click="selectedQuality = q.id"
              >
                <div class="flex items-center justify-between mb-1">
                  <span class="font-semibold text-xs text-ink-primary">{{ q.title }}</span>
                  <span
                    class="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                    :class="[
                      shownQuality === q.id
                        ? 'bg-accent text-white'
                        : 'bg-surface-muted text-ink-muted border border-subtle',
                    ]"
                  >
                    {{ q.badge }}
                  </span>
                </div>
                <p class="text-xs text-ink-muted leading-relaxed">{{ q.desc }}</p>
              </button>
            </div>
          </div>

          <!-- Run controls: where the run pauses and what it may spend. Both
               are per-run choices the API takes as pause_after_english and
               cost_ceiling_usd; Studio takes neither. -->
          <div data-testid="run-controls">
            <div class="flex items-center justify-between gap-3 mb-3">
              <span class="vogue-label" :class="runControlsLocked ? 'opacity-50' : ''">{{
                t("customizer.controls_title")
              }}</span>
              <span
                class="text-xs text-right"
                :class="runControlsLocked ? 'text-ink-muted italic' : 'text-ink-muted'"
                data-testid="run-controls-lock-reason"
              >
                {{ runControlsLocked ? t("customizer.studio_defaults") : t("customizer.controls_desc") }}
              </span>
            </div>
            <div class="rounded-xl border border-subtle bg-surface divide-y divide-subtle">
              <label
                class="flex items-center justify-between gap-3 px-3.5 py-3"
                :class="runControlsLocked ? 'opacity-40 cursor-not-allowed' : ''"
              >
                <span class="min-w-0">
                  <span class="block text-sm font-semibold text-ink-primary">{{ t("customizer.pause_after_english") }}</span>
                  <span class="block text-xs text-ink-muted leading-relaxed">{{ t("customizer.pause_after_english_help") }}</span>
                </span>
                <input
                  v-model="pauseAfterEnglish"
                  type="checkbox"
                  class="switch focus-ring shrink-0"
                  :disabled="runControlsLocked"
                  data-testid="pause-after-english"
                />
              </label>
              <label
                class="flex items-center justify-between gap-3 px-3.5 py-3"
                :class="runControlsLocked ? 'opacity-40 cursor-not-allowed' : ''"
              >
                <span class="min-w-0">
                  <span class="block text-sm font-semibold text-ink-primary">{{ t("customizer.cost_ceiling") }}</span>
                  <span class="block text-xs text-ink-muted leading-relaxed">{{ t("customizer.cost_ceiling_help") }}</span>
                  <span v-if="costCeilingInvalid" class="block text-xs text-danger" data-testid="cost-ceiling-invalid">
                    {{ t("customizer.cost_ceiling_invalid") }}
                  </span>
                </span>
                <span class="flex shrink-0 items-center gap-1.5">
                  <input
                    v-model="costCeilingInput"
                    type="number"
                    inputmode="decimal"
                    min="1"
                    step="1"
                    :placeholder="String(DEFAULT_COST_CEILING_USD)"
                    class="field field-sm w-24 text-right tabular"
                    :disabled="runControlsLocked"
                    :aria-label="t('customizer.cost_ceiling')"
                    :aria-invalid="costCeilingInvalid ? 'true' : null"
                    data-testid="cost-ceiling"
                  />
                  <span class="text-xs text-ink-muted">{{ t("customizer.cost_ceiling_unit") }}</span>
                </span>
              </label>
            </div>
          </div>
        </div>

        <!-- ================= TAB 4: EVIDENCE SOURCES ================= -->
        <div v-if="activeTab === 'evidence'" class="space-y-4">
          <div class="flex items-center justify-between mb-2">
            <span class="vogue-label">{{ t("customizer.evidence_title") }}</span>
            <span class="text-xs text-ink-muted">{{ t("customizer.evidence_desc") }}</span>
          </div>

          <!-- What the memo will be built from. -->
          <p
            v-if="builtFromLine"
            class="flex items-start gap-2 rounded-lg px-3 py-2 text-xs"
            :class="builtFromWebOnly ? 'bg-warning-soft text-warning-ink' : 'bg-fill-tertiary text-ink-secondary'"
            data-testid="customizer-built-from"
          >
            <component :is="builtFromWebOnly ? AlertTriangle : Database" class="mt-px h-3.5 w-3.5 shrink-0" />
            <span class="min-w-0">{{ builtFromLine }}</span>
          </p>

          <p v-if="evidenceLoading" class="text-sm text-ink-muted">
            {{ t("customizer.evidence_loading") }}
          </p>
          <p v-else-if="evidenceLoadFailed" class="text-sm text-danger">
            {{ t("customizer.evidence_failed") }}
          </p>
          <!-- Nothing analysed: the web-only warning above already says so,
               and how to fix it. -->
          <p v-else-if="!evidenceSources.length && !builtFromLine" class="text-sm text-ink-muted">
            {{ t("customizer.evidence_empty") }}
          </p>

          <template v-else-if="evidenceSources.length">
            <button
              type="button"
              class="text-xs font-medium text-accent focus-ring rounded"
              @click="toggleAllEvidence"
            >
              {{ allEvidenceSelected ? t("customizer.evidence_clear_all") : t("customizer.evidence_select_all") }}
            </button>

            <div class="space-y-2">
              <label
                v-for="src in evidenceSources"
                :key="src.id"
                class="flex items-center justify-between p-3.5 rounded-xl border border-subtle bg-surface hover:border-strong cursor-pointer transition-colors"
              >
                <div class="flex items-center gap-3">
                  <input
                    v-model="src.checked"
                    type="checkbox"
                    class="rounded border-subtle text-accent focus:ring-accent h-4 w-4"
                  />
                  <span class="text-sm font-medium text-ink-primary">{{ src.label }}</span>
                </div>
                <span v-if="src.uploadedAt" class="text-xs text-ink-muted">{{ src.uploadedAt }}</span>
              </label>
            </div>
          </template>
        </div>
      </div>

      <!-- Error Banner -->
      <!-- A launch error is shown whole: the server's 400s say what to fix. -->
      <div
        v-if="error"
        class="flex max-h-32 items-start gap-2 overflow-y-auto border-t border-danger/20 bg-danger/10 px-5 py-2.5 text-xs text-danger"
        role="alert"
        data-testid="customizer-error"
      >
        <AlertCircle class="mt-px h-4 w-4 shrink-0" />
        <span class="min-w-0 flex-1 whitespace-pre-wrap break-words">{{ error }}</span>
      </div>

      <!-- Pre-flight: what could stop this run, and which entity it is
           about, before anything is spent. Advisory: Generate stays live. -->
      <div
        v-if="preflightRows.length"
        class="max-h-40 shrink-0 space-y-1.5 overflow-y-auto border-t border-subtle bg-surface px-5 py-2.5"
        aria-live="polite"
        data-testid="customizer-preflight"
      >
        <div
          v-for="row in preflightRows"
          :key="row.key"
          class="flex items-start gap-2 rounded-lg px-2.5 py-1.5 text-xs"
          :class="PREFLIGHT_TONES[row.tone]"
          :data-testid="`preflight-${row.key}`"
        >
          <component :is="row.icon" class="mt-px h-3.5 w-3.5 shrink-0" />
          <span class="min-w-0 flex-1 leading-snug">{{ row.text }}</span>
          <button
            v-if="row.action"
            type="button"
            class="btn-bordered btn-sm shrink-0 !py-0.5 !text-[11px]"
            :data-testid="row.action.testid"
            @click="row.action.run()"
          >
            {{ row.action.label }}
          </button>
        </div>
      </div>

      <!-- Bottom Glass Action Bar -->
      <footer class="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-subtle bg-surface px-5 py-3.5">
        <div class="flex min-w-0 flex-col gap-1">
          <!-- Live Parameter Badges -->
          <div class="hidden sm:flex flex-wrap items-center gap-1.5 text-xs">
            <span class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium">
              {{ activeArchetypeObj.title }}
            </span>
            <span
              v-if="audienceShortLabel"
              class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium"
            >
              {{ audienceShortLabel }}
            </span>
            <span
              v-if="templateShortLabel"
              class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium"
            >
              {{ templateShortLabel }}
            </span>
            <span
              v-if="lengthShortLabel"
              class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium"
            >
              {{ lengthShortLabel }}
            </span>
            <span
              v-if="qualityShortLabel"
              class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium"
            >
              {{ qualityShortLabel }}
            </span>
            <span
              v-if="pauseAfterEnglish && !runControlsLocked"
              class="rounded-full bg-surface-muted border border-subtle px-2.5 py-0.5 text-ink-muted font-medium"
              data-testid="customizer-pause-pill"
            >
              {{ t("customizer.pause_pill") }}
            </span>
          </div>
          <!-- How long and how much, from finished runs at these settings. -->
          <p
            v-if="estimateText"
            class="flex items-start gap-1.5 text-[11px] leading-snug text-ink-muted"
            :title="estimates?.cost_note || null"
            data-testid="customizer-estimate"
          >
            <Clock3 class="mt-px h-3 w-3 shrink-0" />
            <span class="min-w-0">{{ estimateText }}</span>
          </p>
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center gap-2 ml-auto">
          <button
            type="button"
            class="btn-bordered btn-sm focus-ring"
            :disabled="generating"
            @click="emit('close')"
          >
            {{ t("customizer.cancel") }}
          </button>

          <button
            type="button"
            class="btn-filled btn-sm focus-ring inline-flex min-w-0 items-center gap-2"
            :disabled="generating || !currentCompany"
            :title="launchLabel"
            data-testid="customizer-launch"
            @click="launchReport"
          >
            <Loader2 v-if="generating" class="h-4 w-4 animate-spin" />
            <AiMark v-else class="h-4 w-4 shrink-0" />
            <span class="max-w-[22rem] truncate">{{ launchLabel }}</span>
          </button>
        </div>
      </footer>
    </div>
  </div>
</template>
