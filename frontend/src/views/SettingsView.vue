<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Activity, BarChart3, Bell, Check, Database, Download, FileText, FlaskConical, Languages, Loader2, Moon, RefreshCw, Scale, SlidersHorizontal, Sun, SunMoon, Upload } from "lucide-vue-next";
import { api } from "../api.js";
import { confirmTokenSpend } from "../confirmTokens.js";
import AiMark from "../components/AiMark.vue";
import { APPEARANCES, appearance, setAppearance } from "../appearance.js";
import { isSignedIn, signInRoute } from "../auth.js";
import {
  applyDeskState,
  DESK_KEYS,
  scheduleDeskSync,
  snapshotDeskState,
} from "../deskSync.js";
import { accountInitials, formatIsoDate, formatModelName } from "../formatters.js";
import { useT } from "../i18n.js";
import Monogram from "../components/Monogram.vue";
import PageHeader from "../components/PageHeader.vue";
import { appLanguage, setAppLanguage } from "../state.js";
import { openWelcomeTour } from "../welcomeTour.js";

const t = useT();
const route = useRoute();

const signingOutElsewhere = ref(false);
const sessionsNotice = ref("");
async function signOutElsewhere() {
  if (signingOutElsewhere.value) return;
  signingOutElsewhere.value = true;
  sessionsNotice.value = "";
  try {
    const res = await api.revokeSessions();
    sessionsNotice.value = t("accounts.signed_out_others", { count: res?.revoked ?? 0 });
  } catch (e) {
    sessionsNotice.value = e?.detail || e?.message || "";
  } finally {
    signingOutElsewhere.value = false;
  }
}

const settings = ref(null);
const profile = ref(null);
const loading = ref(true);
const error = ref("");
const saving = ref("");
const regeneratingAll = ref(false);
const refreshingStockViews = ref(false);
const operationsMessage = ref("");
const operationsError = ref("");
const deskMessage = ref("");
const deskError = ref("");
const deskBusy = ref(false);
const fileInput = ref(null);

const prefs = computed(() => settings.value?.preferences || {});
// Parallel memo-run cap options (News/Updates auto-runs keep their own
// 2 reserved slots server-side, outside this cap).
const MEMO_PARALLEL_OPTIONS = [1, 2, 3, 4];
// Which engine answers the web-grounded research surfaces — the founder
// dossier, the daily desk note and the company news sweep. Desk-wide, not
// per-user: it decides where the workspace spends. Memos are NOT affected;
// their engine is picked per run in the report customizer.
// Claude first: it is the default until someone chooses Gemini here.
const RESEARCH_ENGINE_OPTIONS = ["claude", "gemini", "gemini-only"];
// Unset means nothing has been chosen here yet, so the server is still
// falling back to BSH_AI_ENGINE and then its own default, which is Claude.
const researchEngine = computed(
  () => prefs.value.research_engine || "claude",
);
// Which engine Warren asks first; the other stands in when it cannot answer
// (server/warren_engine.py). The server reports the Gemini model it runs and
// whether a key is set, so the labels say what will actually happen.
const WARREN_ENGINE_OPTIONS = ["claude", "gemini"];
const warren = computed(() => settings.value?.warren || {});
const warrenEngine = computed(
  () => warren.value.engine || prefs.value.warren_engine || "claude",
);
const geminiModelLabel = computed(
  () => formatModelName(warren.value.gemini_model) || t("copilot.engine_gemini"),
);
// The memo template late-stage and Auto memos are written on: the standard
// 5-section memo or the founder's IC template (v2). The server reports the
// one in force as `memo_template_effective`; absent means the server's own
// default, which is the IC template since v2 was turned on (memo_flags).
const MEMO_TEMPLATE_OPTIONS = ["standard", "ic_v2"];
const memoTemplate = computed(() => {
  const s = settings.value || {};
  const raw =
    s.memo_template_effective ??
    prefs.value.memo_template_effective ??
    s.memo_template ??
    prefs.value.memo_template;
  return raw === "standard" ? "standard" : "ic_v2";
});
const memoTemplateNotSaved = ref(false);

async function chooseMemoTemplate(option) {
  if (option === memoTemplate.value || saving.value === "memo_template") return;
  memoTemplateNotSaved.value = false;
  await patchPreference("memo_template", option);
  // A server without the field accepts the PATCH and ignores it; say so
  // rather than leave the choice looking saved.
  if (!error.value && memoTemplate.value !== option) memoTemplateNotSaved.value = true;
}
const account = computed(() => profile.value?.account || settings.value?.account || {});
// With nobody signed in the server fills the email with a placeholder
// ("shared-token session"); say what this browser is using instead.
const accountEmail = computed(() =>
  isSignedIn.value ? account.value.email : t("sidebar.local_dev"),
);
const team = computed(() => profile.value?.team || {});
const usage = computed(() => profile.value?.usage || {});
const status = computed(() => profile.value?.status || {});

async function load() {
  loading.value = true;
  error.value = "";
  try {
    const [workspace, user] = await Promise.allSettled([
      api.workspaceSettings(),
      api.userCenter(),
    ]);
    if (workspace.status === "fulfilled") settings.value = workspace.value;
    if (user.status === "fulfilled") profile.value = user.value;
    if (workspace.status === "rejected" && user.status === "rejected") {
      error.value = workspace.reason?.message || String(workspace.reason);
    }
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    loading.value = false;
  }
}

async function patchPreference(key, value) {
  saving.value = key;
  error.value = "";
  try {
    settings.value = await api.updateWorkspaceSettings({ [key]: value });
    if (key === "language" && value) setAppLanguage(value);
  } catch (e) {
    error.value = e?.message || String(e);
  } finally {
    saving.value = "";
  }
}

onMounted(load);

// ---- Fund return policy ---------------------------------------------------
// The bar each stage's memos answer to (server/fund_policy.py): per stage a
// target MOIC and IRR, the longest hold the target assumes, the largest
// position as a share of the fund, and whether the bar is gross or net of
// SPV fees and carry. It starts unset, and nothing reaches a memo until a
// stage has a MOIC or IRR target. Admins and partners (settings:update)
// change it; everyone else reads it.
const POLICY_STAGES = ["early", "growth", "late"];
// Ranges match the server's validation.
const POLICY_FIELDS = [
  { key: "target_moic", min: 1, max: 50, step: 0.1, value: "settings.fundPolicy.value_moic" },
  { key: "target_irr_pct", min: 0, max: 500, step: 1, value: "settings.fundPolicy.value_pct" },
  { key: "max_hold_years", min: 0.5, max: 30, step: 0.5, value: "settings.fundPolicy.value_years" },
  { key: "max_position_pct", min: 0, max: 100, step: 0.5, value: "settings.fundPolicy.value_position" },
];
const POLICY_BASES = ["gross", "net"];

const policy = ref(null);
const policyLoading = ref(true);
const policyLoadFailed = ref(false);
const policySaving = ref(false);
const policyError = ref("");
const policySaved = ref(false);
// /api/auth/me's permissions: the same role resolution the save checks.
const mePermissions = ref(null);

function blankStage() {
  return { target_moic: "", target_irr_pct: "", max_hold_years: "", max_position_pct: "", basis: "gross" };
}

function draftFrom(saved) {
  const draft = {};
  for (const stage of POLICY_STAGES) {
    const entry = saved?.stages?.[stage] || {};
    draft[stage] = blankStage();
    for (const field of POLICY_FIELDS) {
      const value = entry[field.key];
      draft[stage][field.key] = value === null || value === undefined ? "" : String(value);
    }
    draft[stage].basis = entry.basis === "net" ? "net" : "gross";
  }
  return draft;
}

const policyDraft = ref(draftFrom(null));

const canEditPolicy = computed(() => {
  const permissions =
    mePermissions.value ??
    account.value.permissions ??
    settings.value?.account?.permissions ??
    [];
  return permissions.includes("settings:update");
});

function numberOrNull(raw) {
  const text = String(raw ?? "").trim();
  if (!text) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : NaN;
}

// A stage's request body, or null when it has no numbers (which clears it).
function stageBody(draftStage) {
  const entry = {};
  for (const field of POLICY_FIELDS) {
    const value = numberOrNull(draftStage[field.key]);
    if (value !== null) entry[field.key] = value;
  }
  return Object.keys(entry).length ? { ...entry, basis: draftStage.basis } : null;
}

function stagePayload(stage) {
  return stageBody(policyDraft.value[stage]);
}

function fieldInvalid(stage, field) {
  const value = numberOrNull(policyDraft.value[stage][field.key]);
  if (value === null) return false;
  return Number.isNaN(value) || value < field.min || value > field.max;
}

// Out-of-range and non-numeric entries, named, per stage.
const policyErrors = computed(() => {
  const errors = {};
  for (const stage of POLICY_STAGES) {
    const messages = [];
    for (const field of POLICY_FIELDS) {
      if (fieldInvalid(stage, field)) {
        messages.push(
          t("settings.fundPolicy.invalid", {
            field: t(`settings.fundPolicy.field_${field.key}`),
            min: field.min,
            max: field.max,
          }),
        );
      }
    }
    if (messages.length) errors[stage] = messages.join(" ");
  }
  return errors;
});
const policyInvalid = computed(() => Object.keys(policyErrors.value).length > 0);

const policyDirty = computed(() => {
  const saved = draftFrom(policy.value);
  return POLICY_STAGES.some(
    (stage) => JSON.stringify(stagePayload(stage)) !== JSON.stringify(stageBody(saved[stage])),
  );
});

// Set means the server will hand the stage to memos: a MOIC or IRR target.
function stageIsSet(stage) {
  const entry = policy.value?.stages?.[stage];
  return Boolean(entry && (entry.target_moic != null || entry.target_irr_pct != null));
}

function policyValue(stage, field) {
  const value = policy.value?.stages?.[stage]?.[field.key];
  if (value === null || value === undefined) return t("settings.fundPolicy.not_set");
  return t(field.value, { n: value });
}

function policyBasis(stage) {
  const entry = policy.value?.stages?.[stage];
  if (!entry) return t("settings.fundPolicy.not_set");
  return t(`settings.fundPolicy.basis_${entry.basis === "net" ? "net" : "gross"}`);
}

function musd(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number <= 0) return "";
  return `$${number >= 1000 ? `${Number((number / 1000).toFixed(2))}B` : `${Number(number.toFixed(2))}M`}`;
}

// Fund size and check size, read-only, from the files that own them.
const policyContext = computed(() => {
  const context = policy.value?.context || {};
  const parts = [];
  const fund = musd(context.fund_size_musd);
  if (fund) parts.push(t("settings.fundPolicy.context_fund", { value: fund }));
  const low = musd(context.check_size_min_musd);
  const high = musd(context.check_size_max_musd);
  if (low && high) parts.push(t("settings.fundPolicy.context_check", { min: low, max: high }));
  return parts.length ? `${t("settings.fundPolicy.context_intro")} ${parts.join(t("settings.fundPolicy.context_join"))}` : "";
});

const policyUpdatedLine = computed(() => {
  const at = policy.value?.updated_at;
  if (!at) return "";
  const date = formatIsoDate(at, "");
  const who = policy.value?.updated_by;
  return who
    ? t("settings.fundPolicy.updated_by", { date, who })
    : t("settings.fundPolicy.updated", { date });
});

async function loadPolicy() {
  policyLoading.value = true;
  policyLoadFailed.value = false;
  try {
    const [saved, me] = await Promise.allSettled([api.getFundPolicy(), api.me()]);
    if (me.status === "fulfilled" && Array.isArray(me.value?.permissions)) {
      mePermissions.value = me.value.permissions;
    }
    if (saved.status === "fulfilled" && saved.value && typeof saved.value === "object") {
      policy.value = saved.value;
      policyDraft.value = draftFrom(saved.value);
    } else {
      policyLoadFailed.value = true;
    }
  } catch {
    policyLoadFailed.value = true;
  } finally {
    policyLoading.value = false;
  }
}

function discardPolicyDraft() {
  policyDraft.value = draftFrom(policy.value);
  policyError.value = "";
}

async function savePolicy() {
  if (!canEditPolicy.value || policySaving.value || !policyDirty.value || policyInvalid.value) return;
  policySaving.value = true;
  policyError.value = "";
  policySaved.value = false;
  try {
    const stages = {};
    for (const stage of POLICY_STAGES) stages[stage] = stagePayload(stage);
    const saved = await api.updateFundPolicy({ stages });
    policy.value = saved;
    policyDraft.value = draftFrom(saved);
    policySaved.value = true;
  } catch (e) {
    const detail = e?.detail?.detail || e?.message || String(e);
    policyError.value = t("settings.fundPolicy.save_failed", { detail });
  } finally {
    policySaving.value = false;
  }
}

onMounted(loadPolicy);

async function regenAllCompanies() {
  if (regeneratingAll.value) return;
  if (!confirmTokenSpend()) return;
  regeneratingAll.value = true;
  operationsMessage.value = "";
  operationsError.value = "";
  try {
    const result = await api.regenAllCompanies();
    const total = result.total_count ?? 0;
    if (!total) operationsMessage.value = t("home.regen_all_none");
    else if (result.status === "already_running") {
      operationsMessage.value = t("home.regen_all_running", { total });
    } else {
      operationsMessage.value = t("home.regen_all_started", {
        total,
        public: result.public_trader_count ?? 0,
      });
    }
  } catch {
    operationsError.value = t("home.regen_all_failed");
  } finally {
    regeneratingAll.value = false;
  }
}

async function refreshAllStockViews() {
  if (refreshingStockViews.value) return;
  if (!confirmTokenSpend()) return;
  refreshingStockViews.value = true;
  operationsMessage.value = "";
  operationsError.value = "";
  try {
    const result = await api.trader.refreshAll();
    const total = result.total_count ?? 0;
    if (!total) operationsMessage.value = t("home.refresh_stock_views_none");
    else if (result.status === "already_running") {
      operationsMessage.value = t("home.refresh_stock_views_running", { total });
    } else {
      operationsMessage.value = t("home.refresh_stock_views_started", {
        queued: result.queued_count ?? 0,
        total,
      });
    }
  } catch {
    operationsError.value = t("home.refresh_stock_views_failed");
  } finally {
    refreshingStockViews.value = false;
  }
}

function appearanceLabel(value) {
  if (value === "light") return t("settings.appearance_light");
  if (value === "dark") return t("settings.appearance_dark");
  return t("settings.appearance_auto");
}

function appearanceIcon(value) {
  if (value === "light") return Sun;
  if (value === "dark") return Moon;
  return SunMoon;
}

async function exportDeskState() {
  deskBusy.value = true;
  deskError.value = "";
  deskMessage.value = "";
  try {
    let data = snapshotDeskState();
    try {
      const remote = await api.deskPrefs();
      if (remote?.data && typeof remote.data === "object") {
        data = { ...remote.data, ...data };
      }
    } catch {
      // Local snapshot is enough when the server is offline.
    }
    const blob = new Blob(
      [JSON.stringify({ schema: "bsh.marketDesk.v1", exported_at: new Date().toISOString(), data }, null, 2)],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `bsh-desk-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    deskMessage.value = t("settings.desk_export_done", { n: Object.keys(data).length });
  } catch (e) {
    deskError.value = e?.message || t("settings.desk_export_failed");
  } finally {
    deskBusy.value = false;
  }
}

function triggerDeskImport() {
  fileInput.value?.click();
}

async function importDeskState(event) {
  const file = event?.target?.files?.[0];
  if (!file) return;
  deskBusy.value = true;
  deskError.value = "";
  deskMessage.value = "";
  try {
    const text = await file.text();
    const payload = JSON.parse(text);
    const data =
      payload?.data && typeof payload.data === "object"
        ? payload.data
        : payload && typeof payload === "object"
          ? payload
          : null;
    if (!data) throw new Error(t("settings.desk_import_invalid"));
    const known = Object.keys(data).filter((key) => DESK_KEYS.includes(key));
    if (!known.length) throw new Error(t("settings.desk_import_empty"));
    applyDeskState(data, { overwrite: true });
    scheduleDeskSync();
    try {
      await api.saveDeskPrefs(snapshotDeskState());
    } catch {
      // Local write succeeded; sync will retry later.
    }
    deskMessage.value = t("settings.desk_import_done", { n: known.length });
  } catch (e) {
    deskError.value = e?.message || t("settings.desk_import_failed");
  } finally {
    deskBusy.value = false;
    if (event?.target) event.target.value = "";
  }
}
</script>

<template>
  <div class="mx-auto w-full max-w-5xl px-5 pb-12 pt-4 md:px-8">
    <PageHeader :title="t('settings.title')" />

    <div v-if="loading" class="rounded-card bg-surface p-5 text-callout text-ink-muted">
      {{ t("settings.loading") }}
    </div>
    <div v-else-if="error" class="rounded-card bg-danger-soft p-5 text-callout text-danger-ink">
      {{ error }}
    </div>

    <div v-else class="space-y-4">
      <section class="group-card p-5">
        <div class="flex items-start gap-4">
          <Monogram
            :name="account.name || account.email || ''"
            :initials="accountInitials(account.name || account.email)"
            :size="52"
            tinted
            round
          />
          <div class="min-w-0 flex-1">
            <h2 class="font-display text-title3 text-ink-primary">
              {{ t("settings.profile") }}
            </h2>
            <div class="mt-0.5 text-callout text-ink-primary">{{ account.name || account.email }}</div>
            <div class="text-footnote text-ink-muted">{{ accountEmail }}</div>
            <div class="mt-2 flex flex-wrap gap-2 text-caption1 text-ink-muted">
              <span v-if="account.workspace">{{ account.workspace }}</span>
              <span v-if="account.role">{{ account.role }}</span>
              <span v-if="account.plan">{{ account.plan }}</span>
            </div>
          </div>
        </div>
        <dl class="mt-4 grid gap-2 text-callout sm:grid-cols-3">
          <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
            <dt class="text-caption1 text-ink-muted">{{ t("settings.permissions") }}</dt>
            <dd class="mt-0.5 font-medium text-ink-primary">
              {{ t("settings.permission_grants", { n: account.permissions?.length || 0 }) }}
            </dd>
          </div>
          <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
            <dt class="text-caption1 text-ink-muted">{{ t("settings.seats") }}</dt>
            <dd class="mt-0.5 font-medium text-ink-primary">
              {{ t("settings.licensed_seats", { n: team.licensed_seats || 0 }) }}
            </dd>
          </div>
          <div class="rounded-subbox bg-fill-tertiary px-3 py-2">
            <dt class="text-caption1 text-ink-muted">{{ t("settings.usage") }}</dt>
            <dd class="mt-0.5 font-medium text-ink-primary">
              {{ t("settings.usage_events", { n: usage.analytics_events || 0 }) }}
            </dd>
          </div>
        </dl>
      </section>

      <div class="grid gap-4 lg:grid-cols-2">
      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Languages class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.preferences") }}
          </h2>
        </div>
        <div class="mt-4">
          <div class="vogue-label mb-2">{{ t("settings.language") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.language_group')"
          >
            <button
              type="button"
              @click="patchPreference('language', 'en')"
              class="segmented-item focus-ring"
              :data-selected="(prefs.language || appLanguage) === 'en'"
            >
              EN
            </button>
            <button
              type="button"
              @click="patchPreference('language', 'zh')"
              class="segmented-item focus-ring"
              :data-selected="(prefs.language || appLanguage) === 'zh'"
            >
              中文
            </button>
          </div>
        </div>
        <div class="mt-5">
          <div class="vogue-label mb-2">{{ t("settings.appearance") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.appearance')"
          >
            <button
              v-for="option in APPEARANCES"
              :key="option"
              type="button"
              @click="setAppearance(option)"
              class="segmented-item focus-ring inline-flex items-center gap-1"
              :data-selected="appearance === option"
            >
              <component :is="appearanceIcon(option)" class="h-3.5 w-3.5" />
              {{ appearanceLabel(option) }}
            </button>
          </div>
        </div>
        <div class="mt-5 flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
          <div class="min-w-0">
            <div class="text-callout text-ink-secondary">{{ t("settings.welcome_tour") }}</div>
            <div class="text-footnote text-ink-muted">{{ t("settings.welcome_tour_help") }}</div>
          </div>
          <button
            type="button"
            class="btn-bordered btn-sm shrink-0"
            data-testid="settings-replay-tour"
            @click="openWelcomeTour"
          >
            {{ t("settings.welcome_tour_replay") }}
          </button>
        </div>
        <label class="mt-5 flex items-center justify-between gap-3 rounded-subbox px-1 py-2 text-callout text-ink-secondary">
          <span>{{ t("settings.compact_density") }}</span>
          <input
            type="checkbox"
            :checked="prefs.compact_density"
            :disabled="saving === 'compact_density'"
            class="switch focus-ring"
            @change="patchPreference('compact_density', $event.target.checked)"
          />
        </label>
        <div class="mt-5">
          <div class="vogue-label mb-2">{{ t("settings.memo_parallel_runs") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.memo_parallel_runs')"
          >
            <button
              v-for="option in MEMO_PARALLEL_OPTIONS"
              :key="option"
              type="button"
              @click="patchPreference('memo_parallel_runs', option)"
              class="segmented-item focus-ring"
              :disabled="saving === 'memo_parallel_runs'"
              :data-selected="(prefs.memo_parallel_runs || 2) === option"
            >
              {{ option }}
            </button>
          </div>
          <p class="mt-2 text-caption1 text-ink-muted">
            {{ t("settings.memo_parallel_runs_hint") }}
          </p>
        </div>
        <div class="mt-5">
          <div class="vogue-label mb-2">{{ t("settings.research_engine") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.research_engine')"
          >
            <button
              v-for="option in RESEARCH_ENGINE_OPTIONS"
              :key="option"
              type="button"
              @click="patchPreference('research_engine', option)"
              class="segmented-item focus-ring"
              :disabled="saving === 'research_engine'"
              :data-selected="researchEngine === option"
              :data-testid="`research-engine-${option}`"
            >
              {{ t(`settings.research_engine_${option.replace("-", "_")}`) }}
            </button>
          </div>
          <p class="mt-2 text-caption1 text-ink-muted">
            {{ t("settings.research_engine_hint") }}
          </p>
        </div>
        <div class="mt-5">
          <div class="vogue-label mb-2">{{ t("settings.warren_engine") }}</div>
          <div
            class="segmented"
            role="group"
            :aria-label="t('settings.warren_engine')"
          >
            <button
              v-for="option in WARREN_ENGINE_OPTIONS"
              :key="option"
              type="button"
              @click="patchPreference('warren_engine', option)"
              class="segmented-item focus-ring"
              :disabled="saving === 'warren_engine'"
              :data-selected="warrenEngine === option"
              :data-testid="`warren-engine-${option}`"
            >
              {{ option === "gemini" ? geminiModelLabel : t("settings.warren_engine_claude") }}
            </button>
          </div>
          <p class="mt-2 text-caption1 text-ink-muted">
            {{
              t(
                warrenEngine === "gemini"
                  ? "settings.warren_engine_hint_gemini"
                  : "settings.warren_engine_hint_claude",
                { model: geminiModelLabel },
              )
            }}
          </p>
          <p
            v-if="warren.gemini_available === false"
            class="mt-1 text-caption1 text-warning"
            data-testid="warren-no-gemini-key"
          >
            {{ t("settings.warren_no_gemini_key") }}
          </p>
          <p
            v-else-if="warren.claude_resting"
            class="mt-1 text-caption1 text-ink-muted"
            data-testid="warren-claude-resting"
          >
            {{ t("settings.warren_claude_resting", { reason: warren.claude_resting, model: geminiModelLabel }) }}
          </p>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Bell class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.notifications") }}
          </h2>
        </div>
        <div class="mt-4 space-y-1 text-callout text-ink-secondary">
          <label class="flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
            <span>{{ t("settings.weekly_summary") }}</span>
            <input
              type="checkbox"
              :checked="prefs.weekly_summary"
              :disabled="saving === 'weekly_summary'"
              class="switch focus-ring"
              @change="patchPreference('weekly_summary', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
            <span>{{ t("settings.stock_auto_refresh") }}</span>
            <input
              type="checkbox"
              :checked="prefs.stock_auto_refresh"
              :disabled="saving === 'stock_auto_refresh'"
              class="switch focus-ring"
              @change="patchPreference('stock_auto_refresh', $event.target.checked)"
            />
          </label>
          <label class="flex items-center justify-between gap-3 rounded-subbox px-1 py-2">
            <span>{{ t("settings.agent_alerts") }}</span>
            <input
              type="checkbox"
              :checked="prefs.agent_alerts"
              :disabled="saving === 'agent_alerts'"
              class="switch focus-ring"
              @change="patchPreference('agent_alerts', $event.target.checked)"
            />
          </label>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card" data-testid="settings-reports">
        <div class="flex items-center gap-2">
          <FileText class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.reports") }}
          </h2>
        </div>
        <div class="mt-4">
          <div class="vogue-label mb-2">{{ t("settings.memo_template") }}</div>
          <div class="space-y-2" role="radiogroup" :aria-label="t('settings.memo_template')">
            <button
              v-for="option in MEMO_TEMPLATE_OPTIONS"
              :key="option"
              type="button"
              role="radio"
              :aria-checked="memoTemplate === option"
              :disabled="saving === 'memo_template'"
              class="flex w-full items-start gap-3 rounded-subbox border px-3 py-2.5 text-left transition-colors focus-ring"
              :class="memoTemplate === option ? 'border-accent bg-accent/5' : 'border-subtle hover:border-strong'"
              :data-testid="`memo-template-${option}`"
              @click="chooseMemoTemplate(option)"
            >
              <span
                class="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border"
                :class="memoTemplate === option ? 'border-accent bg-accent text-white' : 'border-strong'"
              >
                <Check v-if="memoTemplate === option" class="h-2.5 w-2.5" />
              </span>
              <span class="min-w-0">
                <span class="block text-callout font-medium text-ink-primary">
                  {{ t(`settings.memo_template_${option}`) }}
                </span>
                <span class="mt-0.5 block text-footnote text-ink-muted">
                  {{ t(`settings.memo_template_${option}_desc`) }}
                </span>
              </span>
            </button>
          </div>
          <p class="mt-2 text-caption1 text-ink-muted">{{ t("settings.memo_template_scope") }}</p>
          <p
            v-if="memoTemplateNotSaved"
            class="mt-1 text-caption1 text-warning"
            data-testid="memo-template-not-saved"
          >
            {{ t("settings.memo_template_not_saved") }}
          </p>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <Database class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.system") }}
          </h2>
        </div>
        <div class="mt-4 grid gap-1.5 text-callout">
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="text-ink-secondary">{{ t("settings.workspace_role") }}</span>
            <span class="min-w-0 truncate font-semibold text-accent-ink">{{ account.role || t("settings.role_adapter") }}</span>
          </div>
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="shrink-0 text-ink-secondary">{{ t("settings.account") }}</span>
            <span class="min-w-0 truncate font-semibold text-ink-primary">{{ accountEmail }}</span>
          </div>
        </div>
        <!-- The account's own controls. Signing out elsewhere is what
             someone does about a session they do not recognise, and the
             password change is the stronger form of the same act. With
             nobody signed in (the local anon-dev bypass) there is no
             account to act on, so the control is Sign in. -->
        <div v-if="account.email" class="mt-3 flex flex-wrap items-center gap-2">
          <template v-if="isSignedIn">
            <RouterLink :to="{ name: 'change-password' }" class="btn-bordered btn-sm">
              {{ t("user.change_password") }}
            </RouterLink>
            <button
              type="button"
              class="btn-bordered btn-sm"
              :disabled="signingOutElsewhere"
              data-testid="sign-out-elsewhere"
              @click="signOutElsewhere"
            >
              {{ t("accounts.sign_out_others") }}
            </button>
          </template>
          <RouterLink
            v-else
            :to="signInRoute(route.fullPath)"
            class="btn-bordered btn-sm"
            data-testid="sign-in"
          >
            {{ t("auth.sign_in") }}
          </RouterLink>
          <RouterLink
            v-if="(account.permissions || []).includes('users:manage')"
            :to="{ name: 'accounts' }"
            class="btn-bordered btn-sm"
            data-testid="manage-accounts"
          >
            {{ t("settings.manage_accounts") }}
          </RouterLink>
          <span v-if="sessionsNotice" class="text-footnote text-ink-muted">{{ sessionsNotice }}</span>
        </div>
        <details class="mt-3">
          <summary class="cursor-pointer text-footnote text-ink-muted focus-ring rounded-subbox px-1 py-1">
            {{ t("settings.system_details") }}
          </summary>
          <div class="mt-2 space-y-1 text-footnote text-ink-muted">
            <div v-if="settings?.adapter_scope" class="rounded-row bg-fill-tertiary px-3 py-2">
              {{ settings.adapter_scope }}
            </div>
            <div v-for="(value, key) in status" :key="key" class="flex justify-between gap-3 px-1 py-1">
              <span>{{ String(key).replaceAll("_", " ") }}</span>
              <span class="text-ink-primary">{{ value }}</span>
            </div>
          </div>
        </details>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card">
        <div class="flex items-center gap-2">
          <SlidersHorizontal class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.usage") }}
          </h2>
        </div>
        <div class="mt-4 grid gap-1.5 text-callout">
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="text-ink-secondary">{{ t("settings.plan") }}</span>
            <span class="min-w-0 truncate font-semibold text-ink-primary">{{ account.plan }}</span>
          </div>
          <div class="flex justify-between gap-3 rounded-row bg-fill-tertiary px-3 py-2">
            <span class="text-ink-secondary">{{ t("settings.permissions") }}</span>
            <span class="mono-data font-semibold text-ink-primary">
              {{ t("settings.permission_grants", { n: account.permissions?.length || 0 }) }}
            </span>
          </div>
        </div>
      </section>

      <!-- Fund return policy: the bar each stage's memos answer to. Unset
           until someone with settings:update saves a target. -->
      <section class="rounded-card bg-surface p-5 shadow-card lg:col-span-2" data-testid="settings-fund-policy">
        <div class="flex flex-wrap items-center gap-2">
          <Scale class="h-4 w-4 text-accent" />
          <h2 class="font-display text-title3 text-ink-primary">
            {{ t("settings.fundPolicy.title") }}
          </h2>
          <span
            v-if="policy"
            class="chip"
            :class="policy.set ? 'bg-success-soft text-success-ink' : 'bg-fill-secondary text-ink-secondary'"
            data-testid="fund-policy-state"
          >
            {{ policy.set ? t("settings.fundPolicy.state_set") : t("settings.fundPolicy.state_unset") }}
          </span>
        </div>
        <p class="mt-1 max-w-3xl text-footnote text-ink-muted">{{ t("settings.fundPolicy.explain") }}</p>

        <p v-if="policyLoading" class="mt-4 text-callout text-ink-muted">
          {{ t("settings.fundPolicy.loading") }}
        </p>
        <p v-else-if="policyLoadFailed" class="mt-4 text-callout text-danger-ink" data-testid="fund-policy-load-failed">
          {{ t("settings.fundPolicy.load_failed") }}
        </p>
        <template v-else>
          <div class="mt-4 grid gap-3 md:grid-cols-3">
            <fieldset
              v-for="stage in POLICY_STAGES"
              :key="stage"
              class="min-w-0 rounded-subbox bg-fill-tertiary p-3"
              :disabled="!canEditPolicy || policySaving"
              :data-testid="`fund-policy-${stage}`"
            >
              <legend class="sr-only">{{ t(`settings.fundPolicy.stage_${stage}`) }}</legend>
              <div class="flex items-center justify-between gap-2">
                <span class="text-callout font-semibold text-ink-primary">
                  {{ t(`settings.fundPolicy.stage_${stage}`) }}
                </span>
                <span
                  class="text-caption1"
                  :class="stageIsSet(stage) ? 'text-success-ink' : 'text-ink-muted'"
                  :data-testid="`fund-policy-${stage}-state`"
                >
                  {{ stageIsSet(stage) ? t("settings.fundPolicy.stage_set") : t("settings.fundPolicy.not_set") }}
                </span>
              </div>

              <div v-if="canEditPolicy" class="mt-2.5 space-y-2">
                <label
                  v-for="field in POLICY_FIELDS"
                  :key="field.key"
                  class="flex items-center justify-between gap-2 text-footnote text-ink-secondary"
                >
                  <span class="min-w-0">{{ t(`settings.fundPolicy.field_${field.key}`) }}</span>
                  <span class="flex shrink-0 items-center gap-1.5">
                    <input
                      v-model="policyDraft[stage][field.key]"
                      type="number"
                      inputmode="decimal"
                      :min="field.min"
                      :max="field.max"
                      :step="field.step"
                      class="field field-sm w-20 text-right tabular"
                      :placeholder="t('settings.fundPolicy.placeholder')"
                      :class="fieldInvalid(stage, field) ? '!ring-1 !ring-danger' : ''"
                      :aria-invalid="fieldInvalid(stage, field)"
                      :data-testid="`fund-policy-${stage}-${field.key}`"
                    />
                    <span class="w-16 whitespace-nowrap text-caption1 text-ink-muted">{{ t(`settings.fundPolicy.unit_${field.key}`) }}</span>
                  </span>
                </label>
                <div class="flex items-center justify-between gap-2 text-footnote text-ink-secondary">
                  <span>{{ t("settings.fundPolicy.field_basis") }}</span>
                  <div class="segmented" role="group" :aria-label="t('settings.fundPolicy.field_basis')">
                    <button
                      v-for="basis in POLICY_BASES"
                      :key="basis"
                      type="button"
                      class="segmented-item focus-ring"
                      :data-selected="policyDraft[stage].basis === basis"
                      :data-testid="`fund-policy-${stage}-basis-${basis}`"
                      @click="policyDraft[stage].basis = basis"
                    >
                      {{ t(`settings.fundPolicy.basis_${basis}`) }}
                    </button>
                  </div>
                </div>
                <p
                  v-if="policyErrors[stage]"
                  class="text-caption1 text-danger-ink"
                  :data-testid="`fund-policy-${stage}-error`"
                >
                  {{ policyErrors[stage] }}
                </p>
              </div>

              <dl v-else class="mt-2.5 space-y-1 text-footnote">
                <div v-for="field in POLICY_FIELDS" :key="field.key" class="flex justify-between gap-2">
                  <dt class="text-ink-secondary">{{ t(`settings.fundPolicy.field_${field.key}`) }}</dt>
                  <dd class="tabular text-ink-primary">{{ policyValue(stage, field) }}</dd>
                </div>
                <div class="flex justify-between gap-2">
                  <dt class="text-ink-secondary">{{ t("settings.fundPolicy.field_basis") }}</dt>
                  <dd class="text-ink-primary">{{ policyBasis(stage) }}</dd>
                </div>
              </dl>
            </fieldset>
          </div>

          <p class="mt-2 text-caption1 text-ink-muted">{{ t("settings.fundPolicy.basis_hint") }}</p>
          <p v-if="policyContext" class="mt-1 text-caption1 text-ink-muted" data-testid="fund-policy-context">
            {{ policyContext }}
          </p>

          <div v-if="canEditPolicy" class="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="btn-filled btn-sm focus-ring"
              :disabled="!policyDirty || policyInvalid || policySaving"
              data-testid="fund-policy-save"
              @click="savePolicy"
            >
              <Loader2 v-if="policySaving" class="h-3.5 w-3.5 animate-spin" />
              {{ policySaving ? t("settings.fundPolicy.saving") : t("settings.fundPolicy.save") }}
            </button>
            <button
              type="button"
              class="btn-bordered btn-sm focus-ring"
              :disabled="!policyDirty || policySaving"
              data-testid="fund-policy-discard"
              @click="discardPolicyDraft"
            >
              {{ t("settings.fundPolicy.discard") }}
            </button>
            <span v-if="policySaved && !policyDirty" class="text-footnote text-success-ink" data-testid="fund-policy-saved">
              {{ t("settings.fundPolicy.saved") }}
            </span>
            <span v-if="policyError" class="text-footnote text-danger-ink" role="alert" data-testid="fund-policy-error">
              {{ policyError }}
            </span>
          </div>
          <p v-else class="mt-3 text-caption1 text-ink-muted" data-testid="fund-policy-read-only">
            {{ t("settings.fundPolicy.read_only") }}
          </p>
          <p v-if="policyUpdatedLine" class="mt-1 text-caption1 text-ink-muted" data-testid="fund-policy-updated">
            {{ policyUpdatedLine }}
          </p>
        </template>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card lg:col-span-2">
        <h2 class="font-display text-title3 text-ink-primary">
          {{ t("settings.advanced_tools") }}
        </h2>
        <p class="mt-1 text-footnote text-ink-muted">{{ t("settings.advanced_tools_help") }}</p>
        <div class="mt-4 grid gap-2 sm:grid-cols-3">
          <RouterLink
            :to="{ name: 'stock-research' }"
            class="flex items-center gap-3 rounded-row bg-fill-tertiary px-3 py-3 text-callout font-medium text-ink-primary hover:bg-fill-secondary focus-ring"
          >
            <Activity class="h-4 w-4 shrink-0 text-accent" />
            {{ t("sidebar.markets_workbench") }}
          </RouterLink>
          <RouterLink
            :to="{ name: 'trader-stats' }"
            class="flex items-center gap-3 rounded-row bg-fill-tertiary px-3 py-3 text-callout font-medium text-ink-primary hover:bg-fill-secondary focus-ring"
          >
            <BarChart3 class="h-4 w-4 shrink-0 text-accent" />
            {{ t("sidebar.markets_stats") }}
          </RouterLink>
          <RouterLink
            :to="{ name: 'innovation-lab' }"
            class="flex items-center gap-3 rounded-row bg-fill-tertiary px-3 py-3 text-callout font-medium text-ink-primary hover:bg-fill-secondary focus-ring"
          >
            <FlaskConical class="h-4 w-4 shrink-0 text-accent" />
            {{ t("sidebar.markets_labs") }}
          </RouterLink>
        </div>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card lg:col-span-2">
        <h2 class="font-display text-title3 text-ink-primary">
          {{ t("settings.desk_backup") }}
        </h2>
        <p class="mt-1 text-footnote text-ink-muted">{{ t("settings.desk_backup_help") }}</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            class="btn-bordered focus-ring"
            :disabled="deskBusy"
            @click="exportDeskState"
          >
            <Loader2 v-if="deskBusy" class="h-4 w-4 animate-spin" />
            <Download v-else class="h-4 w-4" />
            {{ t("settings.desk_export") }}
          </button>
          <button
            type="button"
            class="btn-bordered focus-ring"
            :disabled="deskBusy"
            @click="triggerDeskImport"
          >
            <Upload class="h-4 w-4" />
            {{ t("settings.desk_import") }}
          </button>
          <input
            ref="fileInput"
            type="file"
            accept="application/json,.json"
            class="hidden"
            @change="importDeskState"
          />
        </div>
        <p v-if="deskMessage" class="mt-2 text-footnote text-ink-muted">{{ deskMessage }}</p>
        <p v-if="deskError" class="mt-2 text-footnote text-danger">{{ deskError }}</p>
      </section>

      <section class="rounded-card bg-surface p-5 shadow-card lg:col-span-2">
        <h2 class="font-display text-title3 text-ink-primary">
          {{ t("settings.operations") }}
        </h2>
        <p class="mt-1 text-footnote text-ink-muted">{{ t("home.operations_help") }}</p>
        <div class="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            :disabled="regeneratingAll"
            class="btn-bordered focus-ring"
            @click="regenAllCompanies"
          >
            <Loader2 v-if="regeneratingAll" class="h-4 w-4 animate-spin" />
            <AiMark v-else class="h-4 w-4" />
            {{ regeneratingAll ? t("home.regenerating_all") : t("home.regen_all") }}
          </button>
          <button
            type="button"
            :disabled="refreshingStockViews"
            class="btn-bordered focus-ring"
            @click="refreshAllStockViews"
          >
            <Loader2 v-if="refreshingStockViews" class="h-4 w-4 animate-spin" />
            <RefreshCw v-else class="h-4 w-4" />
            {{ refreshingStockViews ? t("home.refreshing_stock_views") : t("home.refresh_stock_views") }}
          </button>
        </div>
        <p v-if="operationsMessage" class="mt-2 text-footnote text-ink-muted">{{ operationsMessage }}</p>
        <p v-if="operationsError" class="mt-2 text-footnote text-danger">{{ operationsError }}</p>
      </section>
    </div>
    </div>
  </div>
</template>
