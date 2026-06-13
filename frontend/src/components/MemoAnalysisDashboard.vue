<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  FileText,
  Gauge,
  Loader2,
  Play,
  Save,
  ShieldAlert,
  Sparkles,
} from "lucide-vue-next";
import { api } from "../api.js";

const props = defineProps({
  companyId: { type: String, required: true },
});

const emit = defineEmits(["generate-memo"]);

const session = ref(null);
const loading = ref(false);
const error = ref(null);
const runningTool = ref(null);
const runningTask = ref(null);
const runningBatch = ref(false);
const cancellingTask = ref(null);
const approving = ref(false);
const savingArtifact = ref(null);
const savingTask = ref(null);
const batchStatus = ref(null);
const evidenceMatrix = ref(null);
const evidenceMatrixError = ref(null);
const evidenceStatusFilter = ref("all");
const thesisDraft = ref(null);
const chartSpecsDraft = ref([]);
const benchmarkDraft = ref(null);
const narrativeDraft = ref(null);
const riskPriorityDraft = ref([]);
const readinessReviewDraft = ref({});
let taskPollId = null;
let taskPolling = false;

const artifacts = computed(() => session.value?.artifacts || {});
const sourceFiles = computed(() => artifacts.value.input_manifest?.research_files || []);
const risks = computed(() => artifacts.value.strategic_risks?.risks || []);
const riskPriorities = computed(() => {
  const priorities = artifacts.value.risk_priorities?.priorities;
  return Array.isArray(priorities) ? priorities : [];
});
const tasks = computed(() => artifacts.value.research_tasks?.tasks || []);
const hasRunningTasks = computed(() =>
  tasks.value.some((task) => task?.status === "running"),
);
const hasRunningTools = computed(() =>
  (session.value?.tools || []).some((tool) => tool?.status === "running"),
);
const hasRunningWork = computed(() => hasRunningTasks.value || hasRunningTools.value);
const thesis = computed(() => artifacts.value.thesis_spine || null);
const sourceBrief = computed(() => artifacts.value.infographic_source_brief || null);
const chartSpecs = computed(() => artifacts.value.chart_specs?.specs || []);
const narrativeHooks = computed(() => artifacts.value.narrative_hooks || null);
const benchmark = computed(() => artifacts.value.benchmark_dashboard || null);
const benchmarkView = computed(() => benchmarkDraft.value || benchmark.value);
const memoGrader = computed(() => artifacts.value.memo_grader || null);
const completedMemoRuns = computed(() => session.value?.completed_memo_runs || []);
const readiness = computed(() => session.value?.readiness || { score: 0, total: 0, pct: 0, gates: [] });
const readinessBlockers = computed(() => readiness.value.approval_blockers || []);
const readyForApproval = computed(() => Boolean(readiness.value.ready_for_approval));
const additionalAreas = computed(() => session.value?.additional_areas || []);
const approved = computed(() => Boolean(session.value?.approved_for_memo));
const thesisApproved = computed(() => Boolean(thesis.value?.approved));
const canGenerateMemo = computed(() =>
  approved.value &&
  thesisApproved.value &&
  Boolean(readiness.value.ready_for_memo) &&
  readinessBlockers.value.length === 0,
);
const readinessPct = computed(() => Math.round((readiness.value.pct || 0) * 100));
const memoWorkProducts = computed(() => {
  const rows = [];
  const currentSession = session.value || {};
  const sessionId = currentSession.id || "current";
  rows.push(workProductRow({
    id: `analysis_session:${sessionId}`,
    type: "analysis session",
    title: "Memo Studio session",
    status: approved.value ? "approved" : "draft",
    summary: currentSession.status || "draft",
    sourceCount: sourceFiles.value.length,
    value: currentSession,
  }));
  if (risks.value.length) {
    rows.push(workProductRow({
      id: "strategic_risks",
      type: "risk map",
      title: "Strategic risk map",
      status: "needs_review",
      summary: `${risks.value.length} risks`,
      value: artifacts.value.strategic_risks,
    }));
  }
  if (thesis.value) {
    rows.push(workProductRow({
      id: "thesis_spine",
      type: "thesis spine",
      title: "Investment highlights and risks",
      status: thesisApproved.value ? "approved" : "draft",
      summary: firstText(
        listItems(thesis.value.investment_highlights)[0]?.claim,
        listItems(thesis.value.top_gating_questions)[0]?.question,
      ),
      value: thesis.value,
    }));
  }
  for (const task of tasks.value) {
    rows.push(workProductRow({
      id: `research_task:${task.id || task.title || rows.length}`,
      type: "research task",
      title: task.title || task.id || "Research task",
      status: workStatus(task, "draft"),
      summary: firstText(task.answer, task.result_summary, task.prompt),
      confidence: task.confidence,
      value: task,
    }));
  }
  if (evidenceMatrix.value?.claim_count || listItems(evidenceMatrix.value?.claims).length) {
    rows.push(workProductRow({
      id: "evidence_matrix",
      type: "evidence matrix",
      title: "Evidence matrix",
      status: "needs_review",
      summary: `${evidenceMatrix.value?.claim_count || listItems(evidenceMatrix.value?.claims).length} claims`,
      sourceCount: evidenceMatrixTraceCount(evidenceMatrix.value),
      value: evidenceMatrix.value,
    }));
  }
  if (benchmark.value) {
    rows.push(workProductRow({
      id: "benchmark_dashboard",
      type: "benchmark dashboard",
      title: "Private benchmark dashboard",
      status: workStatus(benchmark.value, "needs_review"),
      summary: benchmark.value.summary,
      confidence: benchmark.value.confidence,
      value: benchmark.value,
    }));
  }
  if (sourceBrief.value) {
    rows.push(workProductRow({
      id: "infographic_source_brief",
      type: "source brief",
      title: "Infographic source brief",
      status: workStatus(sourceBrief.value, "needs_review"),
      summary: sourceBrief.value.summary,
      confidence: sourceBrief.value.confidence,
      value: sourceBrief.value,
    }));
  }
  if (chartSpecs.value.length) {
    rows.push(workProductRow({
      id: "chart_specs",
      type: "chart plans",
      title: "Chart and infographic plans",
      status: chartSpecs.value.some((spec) => spec.include_in_final_memo)
        ? "used_in_memo"
        : "needs_review",
      summary: `${chartSpecs.value.length} plans`,
      sourceCount: chartSpecs.value.reduce((total, spec) => total + sourceTraceCount(spec), 0),
      value: artifacts.value.chart_specs,
    }));
  }
  if (narrativeHooks.value) {
    rows.push(workProductRow({
      id: "narrative_hooks",
      type: "narrative hooks",
      title: "Narrative hooks",
      status: workStatus(narrativeHooks.value, "needs_review"),
      summary: narrativeHooks.value.summary,
      confidence: narrativeHooks.value.confidence,
      value: narrativeHooks.value,
    }));
  }
  if (typeof artifacts.value.memo_packet === "string" && artifacts.value.memo_packet.trim()) {
    rows.push(workProductRow({
      id: "memo_packet",
      type: "memo packet",
      title: "Memo packet",
      status: canGenerateMemo.value ? "used_in_memo" : "needs_review",
      summary: "Analysis packet for final memo generation",
      sourceCount: sourceFiles.value.length,
      value: artifacts.value.memo_packet,
    }));
  }
  for (const run of completedMemoRuns.value) {
    rows.push(workProductRow({
      id: `generated_memo:${run.id || run.run_id || rows.length}`,
      type: "generated memo",
      title: run.run_id || run.id || "Generated memo",
      status: "used_in_memo",
      summary: run.title || run.status || "",
      value: run,
    }));
  }
  if (memoGrader.value) {
    rows.push(workProductRow({
      id: "memo_grader",
      type: "memo grader",
      title: "Memo grader output",
      status: memoGrader.value.status === "waiting_for_completed_memo" ? "draft" : "needs_review",
      summary: firstText(
        memoGrader.value.next_step,
        listItems(memoGrader.value.weakest_sections)[0],
        listItems(memoGrader.value.rewrite_guidance)[0],
      ),
      confidence: memoGrader.value.confidence,
      sourceCount: listItems(memoGrader.value.source_files_reviewed).length,
      value: memoGrader.value,
    }));
    if (memoGrader.value.lessons_path || listItems(memoGrader.value.lessons_for_future_memo_runs).length) {
      rows.push(workProductRow({
        id: "memo_lessons",
        type: "lessons file",
        title: "Reusable memo lessons",
        status: "needs_review",
        summary: firstText(
          listItems(memoGrader.value.lessons_for_future_memo_runs)[0],
          memoGrader.value.lessons_path,
        ),
        sourceCount: listItems(memoGrader.value.lessons_for_future_memo_runs).length,
        value: memoGrader.value,
      }));
    }
  }
  return rows;
});
const memoReviewItems = computed(() => {
  const rows = [];
  if (approved.value && readinessBlockers.value.length) {
    rows.push(reviewItemRow({
      id: "stale-approved-state",
      type: "stale approved state",
      title: "Approved analysis has reopened blockers",
      detail: readinessBlockers.value[0]?.label,
      severity: "high",
    }));
  }
  for (const blocker of readinessBlockers.value) {
    rows.push(reviewItemRow({
      id: `readiness:${blocker.id || blocker.label}`,
      type: "readiness blocker",
      title: blocker.label || blocker.id || "Readiness blocker",
      detail: blocker.reason,
      severity: blocker.severity || "medium",
    }));
  }
  for (const area of additionalAreas.value) {
    if ((area.status || "open") !== "open") continue;
    rows.push(reviewItemRow({
      id: `gap:${area.id || area.area}`,
      type: "unwaived gap",
      title: area.area || area.id || "Open readiness gap",
      detail: area.why_it_matters,
      severity: area.severity || "medium",
    }));
  }
  for (const task of tasks.value) {
    const taskId = task.id || task.title || "task";
    if (["error", "failed"].includes(task.status)) {
      rows.push(reviewItemRow({
        id: `task-failed:${taskId}`,
        type: "failed job",
        title: task.title || taskId,
        detail: task.error || "Research task failed.",
        severity: "high",
      }));
    }
    if (task.confidence === "low") {
      rows.push(reviewItemRow({
        id: `task-confidence:${taskId}`,
        type: "low confidence",
        title: task.title || taskId,
        detail: firstText(task.answer, task.result_summary, task.prompt),
        severity: "medium",
      }));
    }
    if (
      task.status === "done" &&
      listItems(task.supporting_evidence).length === 0 &&
      listItems(task.contradicting_evidence).length === 0
    ) {
      rows.push(reviewItemRow({
        id: `task-evidence:${taskId}`,
        type: "missing evidence",
        title: task.title || taskId,
        detail: "Completed result has no supporting or contradicting source trace.",
        severity: "medium",
      }));
    }
    for (const [index, question] of listItems(task.open_questions).entries()) {
      rows.push(reviewItemRow({
        id: `task-open-question:${taskId}:${index}`,
        type: "missing evidence",
        title: task.title || taskId,
        detail: question,
        severity: "high",
      }));
    }
    for (const [index, item] of listItems(task.contradicting_evidence).entries()) {
      rows.push(reviewItemRow({
        id: `task-contradiction:${taskId}:${index}`,
        type: "contradiction",
        title: task.title || taskId,
        detail: item.excerpt || evidenceLabel(item),
        severity: "high",
      }));
    }
  }
  for (const [index, item] of listItems(sourceBrief.value?.missing_evidence).entries()) {
    rows.push(reviewItemRow({
      id: `source-brief-missing:${index}`,
      type: "missing evidence",
      title: "Infographic source brief",
      detail: item,
      severity: "medium",
    }));
  }
  for (const [index, item] of listItems(sourceBrief.value?.no_go_claims).entries()) {
    rows.push(reviewItemRow({
      id: `source-brief-no-go:${index}`,
      type: "no-go claim",
      title: "Infographic source brief",
      detail: item,
      severity: "high",
    }));
  }
  for (const prompt of listItems(sourceBrief.value?.reviewer_prompts)) {
    if (!isUnresolvedPrompt(prompt)) continue;
    rows.push(reviewItemRow({
      id: `source-brief-prompt:${prompt.id || prompt.prompt}`,
      type: "ambiguous choice",
      title: "Source brief reviewer choice",
      detail: prompt.prompt,
      severity: prompt.required ? "high" : "medium",
    }));
  }
  for (const claim of listItems(sourceBrief.value?.compact_claims)) {
    if (!["contradicted", "mixed", "missing"].includes(claim.evidence_status)) continue;
    rows.push(reviewItemRow({
      id: `source-brief-claim:${claim.id || claim.claim}`,
      type: claim.evidence_status === "missing" ? "missing evidence" : "contradiction",
      title: claim.claim || "Source brief claim",
      detail: claim.evidence_status,
      severity: claim.evidence_status === "missing" ? "medium" : "high",
    }));
  }
  for (const spec of chartSpecs.value) {
    for (const [index, gap] of listItems(spec.information_gaps).entries()) {
      rows.push(reviewItemRow({
        id: `chart-gap:${spec.id || spec.title}:${index}`,
        type: "missing evidence",
        title: spec.title || "Chart plan",
        detail: gap,
        severity: "medium",
      }));
    }
    for (const metric of listItems(spec.required_metrics)) {
      if (metric.source_available !== false) continue;
      rows.push(reviewItemRow({
        id: `chart-metric:${spec.id || spec.title}:${metric.id || metric.label}`,
        type: "missing evidence",
        title: spec.title || "Chart plan",
        detail: metric.label,
        severity: "medium",
      }));
    }
    for (const prompt of listItems(spec.reviewer_prompts)) {
      if (!isUnresolvedPrompt(prompt)) continue;
      rows.push(reviewItemRow({
        id: `chart-prompt:${spec.id || spec.title}:${prompt.id || prompt.prompt}`,
        type: "ambiguous choice",
        title: spec.title || "Chart plan",
        detail: prompt.prompt,
        severity: prompt.required ? "high" : "medium",
      }));
    }
  }
  for (const prompt of listItems(narrativeHooks.value?.reviewer_prompts)) {
    if (!isUnresolvedPrompt(prompt)) continue;
    rows.push(reviewItemRow({
      id: `narrative-prompt:${prompt.id || prompt.prompt}`,
      type: "ambiguous choice",
      title: "Narrative hooks",
      detail: prompt.prompt,
      severity: prompt.required ? "high" : "medium",
    }));
  }
  for (const [index, item] of listItems(memoGrader.value?.missing_diligence).entries()) {
    rows.push(reviewItemRow({
      id: `grader-missing:${index}`,
      type: "memo grader finding",
      title: "Missing diligence",
      detail: item,
      severity: "high",
    }));
  }
  for (const [index, item] of listItems(memoGrader.value?.rewrite_guidance).entries()) {
    rows.push(reviewItemRow({
      id: `grader-rewrite:${index}`,
      type: "memo grader finding",
      title: "Rewrite guidance",
      detail: item,
      severity: "medium",
    }));
  }
  for (const [index, item] of listItems(memoGrader.value?.lessons_for_future_memo_runs).entries()) {
    rows.push(reviewItemRow({
      id: `grader-lesson:${index}`,
      type: "proposed lesson",
      title: "Memo lesson",
      detail: item,
      severity: "low",
    }));
  }
  return rows;
});
const memoSourceBoundaryRows = computed(() => [
  {
    scope: "Research sources",
    location: `data/research/${props.companyId}/`,
    status: "included",
    count: sourceFiles.value.length,
    detail: "input_manifest.research_files",
  },
  {
    scope: "Memo Studio session",
    location: `data/serena_analysis/${props.companyId}/${session.value?.id || "session"}/`,
    status: "included",
    count: memoWorkProducts.value.length,
    detail: "analysis artifacts and memo_packet.md",
  },
  {
    scope: "Upload library",
    location: `data/uploads/${props.companyId}/`,
    status: "excluded",
    count: 0,
    detail: "not part of memo analysis intake",
  },
  {
    scope: "Stock Research",
    location: "data/stock_research/",
    status: "excluded",
    count: 0,
    detail: "requires an explicit future import path",
  },
]);
const memoSourceTraceRows = computed(() => {
  const rows = [];
  for (const product of memoWorkProducts.value) {
    if (!product.value || product.id.startsWith("analysis_session")) continue;
    rows.push(
      ...sourceTraceRowsFromValue(product.value, product.title, product.id, 6),
    );
    if (rows.length >= 18) break;
  }
  return rows.slice(0, 18);
});
const memoToolboxSummary = computed(() => {
  const activeJobs =
    (session.value?.tools || []).filter((tool) => tool?.status === "running").length +
    tasks.value.filter((task) => task?.status === "running").length;
  return {
    readiness: `${readiness.value.score || 0} / ${readiness.value.total || 0}`,
    blockers: readinessBlockers.value.length,
    waivers: additionalAreas.value.filter((area) =>
      ["reviewed", "waived"].includes(area?.status),
    ).length,
    approved: approved.value ? "approved" : "not approved",
    thesis: thesisApproved.value ? "approved" : "draft",
    activeJobs,
    recentOutputs: memoWorkProducts.value.length,
    generatedMemos: completedMemoRuns.value.length,
    reviewItems: memoReviewItems.value.length,
    nextAction: nextMemoAction(),
  };
});
const evidenceRows = computed(() => {
  const rows = evidenceMatrix.value?.claims;
  const list = Array.isArray(rows) ? rows : [];
  if (evidenceStatusFilter.value === "all") return list;
  return list.filter((row) => row?.status === evidenceStatusFilter.value);
});
const riskPriorityMap = computed(() => {
  const map = new Map();
  for (const row of riskPriorityDraft.value || []) {
    if (row?.risk_id) map.set(row.risk_id, row);
  }
  return map;
});
const prioritizedRisks = computed(() => {
  const sourceIndex = new Map(risks.value.map((risk, index) => [risk.id, index]));
  return [...risks.value].sort((a, b) => {
    const aRow = riskPriorityMap.value.get(a.id);
    const bRow = riskPriorityMap.value.get(b.id);
    const aRank = aRow?.rank ?? (sourceIndex.get(a.id) ?? 0) + 1;
    const bRank = bRow?.rank ?? (sourceIndex.get(b.id) ?? 0) + 1;
    return aRank - bRank || (sourceIndex.get(a.id) ?? 0) - (sourceIndex.get(b.id) ?? 0);
  });
});

function clone(value) {
  return value == null ? null : JSON.parse(JSON.stringify(value));
}

function firstText(...values) {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
    if (value !== null && value !== undefined && value !== "") return String(value);
  }
  return "";
}

function artifactUpdatedAt(value) {
  if (!value || typeof value !== "object") return "";
  return (
    value.updated_at ||
    value.completed_at ||
    value.last_run_at ||
    value.generated_at ||
    value.created_at ||
    ""
  );
}

function sourceTraceCount(value) {
  if (!value || typeof value !== "object") return 0;
  let count = 0;
  for (const key of [
    "source_traces",
    "supporting_evidence",
    "contradicting_evidence",
    "sources_checked",
    "source_files_reviewed",
  ]) {
    count += listItems(value[key]).length;
  }
  for (const claim of listItems(value.compact_claims)) {
    count += listItems(claim.source_traces).length;
  }
  for (const metric of listItems(value.required_metrics)) {
    count += listItems(metric.source_traces).length;
  }
  for (const comp of listItems(value.public_comps)) {
    count += listItems(comp.source_traces).length;
  }
  return count;
}

function sourceTraceRowsFromValue(value, artifactTitle, artifactId, limit = 8) {
  const rows = [];
  const seen = new Set();
  const pushTrace = (trace, kind) => {
    if (!trace || typeof trace !== "object" || rows.length >= limit) return;
    const locator = trace.locator || trace.page || "";
    const name = trace.filename || trace.title || trace.url || trace.file_id || "";
    const excerpt = trace.excerpt || trace.quote || "";
    const key = `${kind}:${name}:${locator}:${String(excerpt).slice(0, 120)}`;
    if (!name && !locator && !excerpt) return;
    if (seen.has(key)) return;
    seen.add(key);
    rows.push({
      id: `${artifactId}:${rows.length}:${key}`,
      artifact: artifactTitle,
      kind,
      source: name || "Source trace",
      locator,
      excerpt,
      confidence: trace.confidence || "",
    });
  };
  const visit = (node) => {
    if (!node || rows.length >= limit) return;
    if (Array.isArray(node)) {
      for (const item of node) {
        visit(item);
        if (rows.length >= limit) return;
      }
      return;
    }
    if (typeof node !== "object") return;
    for (const key of ["source_traces", "supporting_evidence", "contradicting_evidence"]) {
      for (const trace of listItems(node[key])) pushTrace(trace, key);
      if (rows.length >= limit) return;
    }
    for (const child of Object.values(node)) {
      visit(child);
      if (rows.length >= limit) return;
    }
  };
  visit(value);
  return rows;
}

function evidenceMatrixTraceCount(value) {
  return listItems(value?.claims).reduce(
    (total, row) => total + sourceTraceCount(row),
    0,
  );
}

function workStatus(value, fallback = "draft") {
  const raw = String(value?.status || "").toLowerCase();
  if (["error", "failed"].includes(raw)) return "failed";
  if (["archived", "superseded"].includes(raw)) return raw;
  if (value?.approved || raw === "approved") return "approved";
  if (value?.manually_edited) return "manually_edited";
  if (value?.include_in_final_memo || value?.final_memo_inclusion_state === "include") {
    return "used_in_memo";
  }
  if (["done", "graded", "complete", "completed"].includes(raw)) return "needs_review";
  return fallback;
}

function workProductRow(row) {
  return {
    id: row.id,
    type: row.type,
    title: row.title,
    status: row.status || "draft",
    summary: firstText(row.summary),
    confidence: row.confidence || "",
    sourceCount: row.sourceCount ?? sourceTraceCount(row.value),
    updatedAt: row.updatedAt || artifactUpdatedAt(row.value),
    value: row.value,
  };
}

function isUnresolvedPrompt(prompt) {
  if (!prompt || prompt.resolved_choice) return false;
  return prompt.required || ["needs_review", "open", "unresolved"].includes(prompt.status);
}

function reviewItemRow(row) {
  return {
    id: row.id,
    type: row.type,
    title: row.title,
    detail: firstText(row.detail),
    severity: row.severity || "medium",
    status: row.status || "open",
  };
}

function nextMemoAction() {
  if (readinessBlockers.value.length) {
    return readinessBlockers.value[0]?.label || "Resolve readiness blockers";
  }
  if (!thesisApproved.value) return "Approve thesis spine";
  if (!approved.value) return "Approve analysis";
  if (canGenerateMemo.value && completedMemoRuns.value.length === 0) return "Generate memo";
  if (memoReviewItems.value.length) return memoReviewItems.value[0]?.title || "Review open item";
  return "Ready for memo generation";
}

function toRank(value, fallback) {
  const rank = Number.parseInt(value, 10);
  return Number.isFinite(rank) && rank > 0 ? rank : fallback;
}

function normalizedRiskRows(rows) {
  return rows.map((row, index) => ({
    risk_id: row.risk_id,
    rank: index + 1,
    selected: Boolean(row.selected),
    rationale: row.rationale || "",
  }));
}

function buildRiskPriorityDraft() {
  const riskById = new Map(risks.value.map((risk) => [risk.id, risk]));
  const provided = [];
  const seen = new Set();
  for (const [index, row] of riskPriorities.value.entries()) {
    const riskId = row?.risk_id;
    if (!riskId || !riskById.has(riskId) || seen.has(riskId)) continue;
    seen.add(riskId);
    provided.push({
      risk_id: riskId,
      rank: toRank(row.rank, index + 1),
      selected: Boolean(row.selected),
      rationale: row.rationale || "",
      sourceIndex: index,
    });
  }
  provided.sort((a, b) => a.rank - b.rank || a.sourceIndex - b.sourceIndex);
  const missing = risks.value
    .filter((risk) => !seen.has(risk.id))
    .map((risk) => ({
      risk_id: risk.id,
      selected: false,
      rationale: "",
    }));
  return normalizedRiskRows([...provided, ...missing]);
}

function setRiskSelected(riskId, selected) {
  const row = riskPriorityMap.value.get(riskId);
  if (row) row.selected = selected;
}

function riskMoveIndex(riskId) {
  return riskPriorityDraft.value.findIndex((row) => row.risk_id === riskId);
}

function canMoveRisk(riskId, direction) {
  const index = riskMoveIndex(riskId);
  const nextIndex = index + direction;
  return index >= 0 && nextIndex >= 0 && nextIndex < riskPriorityDraft.value.length;
}

function moveRiskPriority(riskId, direction) {
  if (!canMoveRisk(riskId, direction)) return;
  const rows = [...riskPriorityDraft.value].sort((a, b) => a.rank - b.rank);
  const index = rows.findIndex((row) => row.risk_id === riskId);
  const nextIndex = index + direction;
  [rows[index], rows[nextIndex]] = [rows[nextIndex], rows[index]];
  riskPriorityDraft.value = normalizedRiskRows(rows);
}

async function load() {
  loading.value = true;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.get(props.companyId);
    await loadEvidenceMatrix();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    loading.value = false;
  }
}

async function loadEvidenceMatrix() {
  evidenceMatrixError.value = null;
  try {
    evidenceMatrix.value = await api.memoAnalysis.getEvidenceMatrix(props.companyId);
  } catch (e) {
    evidenceMatrix.value = null;
    evidenceMatrixError.value = e.message || String(e);
  }
}

function clearTaskPolling() {
  if (taskPollId) {
    clearInterval(taskPollId);
    taskPollId = null;
  }
}

async function refreshRunningTasks() {
  if (taskPolling) return;
  if (!hasRunningWork.value) {
    clearTaskPolling();
    return;
  }
  taskPolling = true;
  try {
    session.value = await api.memoAnalysis.get(props.companyId);
    await loadEvidenceMatrix();
  } catch {
    // Keep the current session visible; the AI Tasks rail still shows logs.
  } finally {
    taskPolling = false;
    if (!hasRunningWork.value) clearTaskPolling();
  }
}

function ensureTaskPolling() {
  if (taskPollId) return;
  taskPollId = setInterval(refreshRunningTasks, 4000);
}

async function runTool(toolName) {
  if (runningTool.value) return;
  runningTool.value = toolName;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.runTool(props.companyId, toolName);
    if (hasRunningWork.value) ensureTaskPolling();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    runningTool.value = null;
  }
}

async function runResearchTask(taskId) {
  if (runningTask.value) return;
  runningTask.value = taskId;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.runTask(props.companyId, taskId);
    batchStatus.value = null;
    if (hasRunningWork.value) ensureTaskPolling();
    await loadEvidenceMatrix();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    runningTask.value = null;
  }
}

async function runSelectedTasks() {
  if (runningBatch.value) return;
  runningBatch.value = true;
  error.value = null;
  try {
    const updated = await api.memoAnalysis.runSelectedTasks(props.companyId, true);
    batchStatus.value = updated?.batch || null;
    session.value = updated;
    if (hasRunningWork.value) ensureTaskPolling();
    await loadEvidenceMatrix();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    runningBatch.value = false;
  }
}

async function cancelResearchTask(taskId) {
  if (cancellingTask.value) return;
  cancellingTask.value = taskId;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.cancelTask(props.companyId, taskId);
    await loadEvidenceMatrix();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    cancellingTask.value = null;
  }
}

async function patchArtifact(artifactName, patch) {
  if (savingArtifact.value) return;
  savingArtifact.value = artifactName;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.patchArtifact(
      props.companyId,
      artifactName,
      patch,
    );
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    savingArtifact.value = null;
  }
}

async function patchTask(taskId, patch) {
  if (savingTask.value) return;
  savingTask.value = taskId;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.patchTask(
      props.companyId,
      taskId,
      patch,
    );
    await loadEvidenceMatrix();
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    savingTask.value = null;
  }
}

function taskSourceIds(task) {
  return Array.isArray(task?.selected_source_ids) ? task.selected_source_ids : [];
}

function isSourceSelected(task, sourceId) {
  return taskSourceIds(task).includes(sourceId);
}

async function toggleTaskSource(task, sourceId, checked) {
  const ids = new Set(taskSourceIds(task));
  if (checked) ids.add(sourceId);
  else ids.delete(sourceId);
  await patchTask(task.id, { selected_source_ids: [...ids] });
}

async function saveThesisDraft() {
  if (!thesisDraft.value) return;
  await patchArtifact("thesis_spine", {
    ...thesisDraft.value,
    updated_at: new Date().toISOString(),
  });
}

async function saveChartSpecsDraft() {
  await patchArtifact("chart_specs", {
    ...(artifacts.value.chart_specs || {}),
    specs: chartSpecsDraft.value || [],
    updated_at: new Date().toISOString(),
  });
}

async function saveBenchmarkDraft() {
  if (!benchmarkDraft.value) return;
  await patchArtifact("benchmark_dashboard", {
    ...benchmarkDraft.value,
    updated_at: new Date().toISOString(),
  });
}

async function saveNarrativeDraft() {
  if (!narrativeDraft.value) return;
  await patchArtifact("narrative_hooks", {
    ...narrativeDraft.value,
    updated_at: new Date().toISOString(),
  });
}

async function saveRiskPrioritiesDraft() {
  if (!riskPriorityDraft.value.length) return;
  await patchArtifact("risk_priorities", {
    priorities: riskPriorityDraft.value,
    updated_at: new Date().toISOString(),
  });
}

async function selectMemoForGrading(reportId) {
  await patchArtifact("memo_grader", {
    ...(memoGrader.value || {}),
    selected_report_id: reportId || null,
    updated_at: new Date().toISOString(),
  });
}

async function approve() {
  approving.value = true;
  error.value = null;
  try {
    session.value = await api.memoAnalysis.approve(props.companyId);
  } catch (e) {
    error.value = e.message || String(e);
  } finally {
    approving.value = false;
  }
}

async function saveReadinessReview(area, status) {
  const rationale = (readinessReviewDraft.value[area.id] || "").trim();
  if (status !== "open" && !rationale) {
    error.value = "Add a rationale before reviewing or waiving a readiness area.";
    return;
  }
  await patchArtifact("readiness_reviews", {
    items: [
      {
        id: area.id,
        status,
        rationale: status === "open" ? "" : rationale,
      },
    ],
  });
}

function generateFromAnalysis() {
  if (!session.value?.id || !canGenerateMemo.value) return;
  emit("generate-memo", session.value.id);
}

function statusClass(status) {
  if (status === "done" || status === "supported") return "bg-success-soft text-success-ink";
  if (status === "error" || status === "contradicted") return "bg-danger/10 text-danger";
  if (status === "mixed" || status === "partial") return "bg-warning-soft text-warning-ink";
  if (status === "missing" || status === "not_started") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function toolboxStatusClass(status) {
  if (["approved", "used_in_memo"].includes(status)) {
    return "bg-success-soft text-success-ink";
  }
  if (status === "failed") return "bg-danger/10 text-danger";
  if (["archived", "superseded"].includes(status)) {
    return "bg-surface-muted text-ink-muted";
  }
  return "bg-warning-soft text-warning-ink";
}

function reviewSeverityClass(severity) {
  if (severity === "high") return "bg-danger/10 text-danger";
  if (severity === "low") return "bg-surface-muted text-ink-muted";
  return "bg-warning-soft text-warning-ink";
}

function statusLabel(status) {
  return (status || "not_started").replaceAll("_", " ");
}

function severityClass(severity) {
  if (severity === "high") return "bg-danger/10 text-danger border-danger/30";
  return "bg-warning-soft text-warning-ink border-warning/40";
}

function approvalTitle() {
  if (readyForApproval.value) return approved.value ? "Analysis approved" : "Approve analysis";
  const first = readinessBlockers.value[0]?.label || "Resolve readiness blockers";
  return `Resolve before approval: ${first}`;
}

function sourceLabel(source) {
  if (typeof source === "string") return source;
  return source?.filename || source?.id || "Source";
}

function evidenceLabel(item) {
  const locator = item?.locator || item?.filename || item?.file_id;
  return locator || "Source trace";
}

function listItems(value) {
  return Array.isArray(value) ? value : [];
}

function sourceCheckedText(task) {
  return listItems(task?.sources_checked).map(sourceLabel).join(", ");
}

function coverageCount(row, key) {
  return row?.source_coverage?.[key] ?? 0;
}

function topEvidence(row) {
  return listItems(row?.supporting_evidence)[0] || listItems(row?.contradicting_evidence)[0] || null;
}

function sourceTraceLabel(trace) {
  return trace?.locator || trace?.title || trace?.url || "Source trace";
}

function promptStatus(prompt) {
  if (prompt?.resolved_choice) return prompt.resolved_choice;
  return prompt?.status || (prompt?.required ? "needs review" : "optional");
}

function fmtMetric(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return `${num.toFixed(1)}${suffix}`;
}

function toolIcon(name) {
  if (name.includes("risk")) return ShieldAlert;
  if (name.includes("chart") || name.includes("benchmark")) return BarChart3;
  if (name.includes("readiness")) return Gauge;
  if (name.includes("grader")) return ClipboardCheck;
  return Sparkles;
}

function fmtDate(value) {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString();
}

onMounted(load);
onBeforeUnmount(clearTaskPolling);
watch(() => props.companyId, () => {
  clearTaskPolling();
  load();
});
watch(hasRunningWork, (running) => {
  if (running) ensureTaskPolling();
  else clearTaskPolling();
});
watch(thesis, (value) => {
  thesisDraft.value = clone(value);
}, { immediate: true });
watch(chartSpecs, (value) => {
  chartSpecsDraft.value = clone(value) || [];
}, { immediate: true });
watch(benchmark, (value) => {
  benchmarkDraft.value = clone(value);
}, { immediate: true });
watch(narrativeHooks, (value) => {
  narrativeDraft.value = clone(value);
}, { immediate: true });
watch([risks, riskPriorities], () => {
  riskPriorityDraft.value = buildRiskPriorityDraft();
}, { immediate: true });
watch(additionalAreas, (areas) => {
  const next = { ...readinessReviewDraft.value };
  for (const area of areas || []) {
    if (!area?.id) continue;
    if (next[area.id] === undefined) next[area.id] = area.rationale || "";
  }
  readinessReviewDraft.value = next;
}, { immediate: true });
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h2 class="font-display text-xl font-semibold text-ink-primary">
          Memo Studio
        </h2>
        <div v-if="session" class="mt-1 text-xs text-ink-muted font-mono">
          {{ session.id }} · {{ session.status }}
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          @click="approve"
          :disabled="approving || loading || approved || !readyForApproval"
          :title="approvalTitle()"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-sm"
        >
          <Loader2 v-if="approving" class="h-4 w-4 animate-spin" />
          <CheckCircle2 v-else class="h-4 w-4" />
          <span>{{ approved ? "Approved" : "Approve analysis" }}</span>
        </button>
        <button
          type="button"
          @click="generateFromAnalysis"
          :disabled="!canGenerateMemo"
          :title="canGenerateMemo ? 'Generate memo' : 'Resolve blockers, approve analysis, and approve the thesis spine first'"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-accent text-white hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed focus-ring text-sm"
        >
          <FileText class="h-4 w-4" />
          <span>Generate memo</span>
        </button>
      </div>
    </div>

    <div
      v-if="error"
      class="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger flex items-start gap-2"
    >
      <AlertTriangle class="h-4 w-4 mt-0.5 shrink-0" />
      <span>{{ error }}</span>
    </div>

    <div
      v-if="loading"
      class="text-sm text-ink-muted inline-flex items-center gap-2"
    >
      <Loader2 class="h-4 w-4 animate-spin" />
      Loading memo analysis
    </div>

    <template v-if="session && !loading">
      <section class="border border-subtle bg-surface rounded-card p-5">
        <div class="flex items-center justify-between gap-4 flex-wrap">
          <div>
            <div class="text-xs uppercase tracking-wide text-ink-muted">
              Readiness
            </div>
            <div class="mt-1 text-2xl font-semibold text-ink-primary">
              {{ readiness.score }} / {{ readiness.total }}
            </div>
          </div>
          <div class="w-full sm:w-64">
            <div class="h-2 rounded-full bg-surface-muted overflow-hidden">
              <div
                class="h-full bg-accent transition-all"
                :style="{ width: readinessPct + '%' }"
              ></div>
            </div>
            <div class="mt-1 text-xs text-ink-muted text-right">
              {{ readinessPct }}%
            </div>
          </div>
        </div>
        <div class="mt-4 grid md:grid-cols-3 gap-2">
          <div
            v-for="gate in readiness.gates"
            :key="gate.id"
            class="flex items-center gap-2 rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-sm"
          >
            <CheckCircle2
              v-if="gate.status === 'done'"
              class="h-4 w-4 text-success shrink-0"
            />
            <AlertTriangle
              v-else
              class="h-4 w-4 text-warning-ink shrink-0"
            />
            <span class="text-ink-primary">{{ gate.label }}</span>
          </div>
        </div>
        <div
          v-if="readinessBlockers.length"
          class="mt-4 rounded-lg border border-warning/40 bg-warning-soft/60 p-3"
        >
          <div class="text-xs uppercase tracking-wide text-warning-ink">
            Approval blockers
          </div>
          <ul class="mt-2 space-y-1 text-sm text-warning-ink">
            <li v-for="blocker in readinessBlockers" :key="`${blocker.kind}-${blocker.id}`">
              {{ blocker.label }}
            </li>
          </ul>
        </div>
      </section>

      <section class="border border-subtle bg-surface rounded-card p-5">
        <div class="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Memo Tools Toolbox
            </h3>
            <div class="mt-1 text-sm text-ink-secondary">
              {{ memoToolboxSummary.nextAction }}
            </div>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
            <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
              <div class="uppercase tracking-wide text-ink-muted">Readiness</div>
              <div class="mt-1 font-semibold text-ink-primary">
                {{ memoToolboxSummary.readiness }}
              </div>
            </div>
            <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
              <div class="uppercase tracking-wide text-ink-muted">Active Jobs</div>
              <div class="mt-1 font-semibold text-ink-primary">
                {{ memoToolboxSummary.activeJobs }}
              </div>
            </div>
            <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
              <div class="uppercase tracking-wide text-ink-muted">Review Items</div>
              <div class="mt-1 font-semibold text-ink-primary">
                {{ memoToolboxSummary.reviewItems }}
              </div>
            </div>
            <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
              <div class="uppercase tracking-wide text-ink-muted">Generated Memos</div>
              <div class="mt-1 font-semibold text-ink-primary">
                {{ memoToolboxSummary.generatedMemos }}
              </div>
            </div>
          </div>
        </div>

        <div class="mt-4 grid md:grid-cols-5 gap-2 text-xs text-ink-secondary">
          <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
            <div class="uppercase tracking-wide text-ink-muted">Approval</div>
            <div class="mt-1 text-ink-primary">{{ memoToolboxSummary.approved }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
            <div class="uppercase tracking-wide text-ink-muted">Thesis</div>
            <div class="mt-1 text-ink-primary">{{ memoToolboxSummary.thesis }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
            <div class="uppercase tracking-wide text-ink-muted">Blockers</div>
            <div class="mt-1 text-ink-primary">{{ memoToolboxSummary.blockers }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
            <div class="uppercase tracking-wide text-ink-muted">Waivers</div>
            <div class="mt-1 text-ink-primary">{{ memoToolboxSummary.waivers }}</div>
          </div>
          <div class="rounded-lg border border-subtle bg-surface-muted px-3 py-2">
            <div class="uppercase tracking-wide text-ink-muted">Recent Outputs</div>
            <div class="mt-1 text-ink-primary">{{ memoToolboxSummary.recentOutputs }}</div>
          </div>
        </div>

        <div class="mt-5 grid xl:grid-cols-2 gap-4">
          <div>
            <div class="mb-2 flex items-center justify-between gap-3">
              <h4 class="text-sm font-semibold text-ink-primary">
                Work Products
              </h4>
              <span class="text-xs text-ink-muted">
                {{ memoWorkProducts.length }}
              </span>
            </div>
            <div class="overflow-x-auto rounded-lg border border-subtle">
              <table class="min-w-full text-sm">
                <thead class="bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                  <tr>
                    <th class="text-left py-2 px-3">Artifact</th>
                    <th class="text-left py-2 px-3">Type</th>
                    <th class="text-left py-2 px-3">Status</th>
                    <th class="text-left py-2 px-3">Sources</th>
                    <th class="text-left py-2 px-3">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="product in memoWorkProducts.slice(0, 12)"
                    :key="product.id"
                    class="border-t border-subtle/70 align-top"
                  >
                    <td class="py-2 px-3 max-w-sm">
                      <div class="font-medium text-ink-primary">{{ product.title }}</div>
                      <div class="text-[11px] font-mono text-ink-muted">
                        {{ product.id }}
                      </div>
                      <div v-if="product.summary" class="mt-1 text-xs text-ink-secondary">
                        {{ product.summary }}
                      </div>
                    </td>
                    <td class="py-2 px-3 text-ink-secondary">
                      {{ product.type }}
                    </td>
                    <td class="py-2 px-3">
                      <span
                        :class="[
                          'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                          toolboxStatusClass(product.status),
                        ]"
                      >
                        {{ statusLabel(product.status) }}
                      </span>
                      <div v-if="product.confidence" class="mt-1 text-[11px] text-ink-muted">
                        {{ product.confidence }}
                      </div>
                    </td>
                    <td class="py-2 px-3 text-ink-secondary font-mono">
                      {{ product.sourceCount }}
                    </td>
                    <td class="py-2 px-3 text-xs text-ink-muted">
                      {{ fmtDate(product.updatedAt) || "—" }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div>
            <div class="mb-2 flex items-center justify-between gap-3">
              <h4 class="text-sm font-semibold text-ink-primary">
                Review Queue
              </h4>
              <span class="text-xs text-ink-muted">
                {{ memoReviewItems.length }}
              </span>
            </div>
            <div
              v-if="memoReviewItems.length === 0"
              class="rounded-lg border border-subtle bg-surface-muted px-3 py-3 text-sm text-ink-muted"
            >
              No open review items.
            </div>
            <div v-else class="space-y-2">
              <div
                v-for="item in memoReviewItems.slice(0, 16)"
                :key="item.id"
                class="rounded-lg border border-subtle bg-surface-muted px-3 py-2"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <div class="text-sm font-medium text-ink-primary">
                      {{ item.title }}
                    </div>
                    <div class="mt-1 text-xs text-ink-secondary">
                      {{ item.detail }}
                    </div>
                    <div class="mt-1 text-[11px] font-mono text-ink-muted">
                      {{ item.id }}
                    </div>
                  </div>
                  <div class="shrink-0 text-right">
                    <span
                      :class="[
                        'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                        reviewSeverityClass(item.severity),
                      ]"
                    >
                      {{ item.severity }}
                    </span>
                    <div class="mt-1 text-[11px] text-ink-muted">
                      {{ item.type }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="mt-5">
          <div class="mb-2 flex items-center justify-between gap-3">
            <h4 class="text-sm font-semibold text-ink-primary">
              Source Trace Drawer
            </h4>
            <span class="text-xs text-ink-muted">
              {{ memoSourceTraceRows.length }}
            </span>
          </div>
          <div
            v-if="memoSourceTraceRows.length === 0"
            class="rounded-lg border border-subtle bg-surface-muted px-3 py-3 text-sm text-ink-muted"
          >
            No source traces captured.
          </div>
          <div v-else class="overflow-x-auto rounded-lg border border-subtle">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="text-left py-2 px-3">Artifact</th>
                  <th class="text-left py-2 px-3">Source</th>
                  <th class="text-left py-2 px-3">Locator</th>
                  <th class="text-left py-2 px-3">Confidence</th>
                  <th class="text-left py-2 px-3">Excerpt</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="trace in memoSourceTraceRows"
                  :key="trace.id"
                  class="border-t border-subtle/70 align-top"
                >
                  <td class="py-2 px-3 text-ink-primary">
                    {{ trace.artifact }}
                    <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                      {{ trace.kind.replace("_", " ") }}
                    </div>
                  </td>
                  <td class="py-2 px-3 text-ink-secondary">
                    {{ trace.source }}
                  </td>
                  <td class="py-2 px-3 font-mono text-xs text-ink-muted">
                    {{ trace.locator || "—" }}
                  </td>
                  <td class="py-2 px-3 text-ink-secondary">
                    {{ trace.confidence || "—" }}
                  </td>
                  <td class="py-2 px-3 text-xs text-ink-muted max-w-md">
                    {{ trace.excerpt || "—" }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="mt-5">
          <h4 class="text-sm font-semibold text-ink-primary">
            Source And Evidence Boundaries
          </h4>
          <div class="mt-2 overflow-x-auto rounded-lg border border-subtle">
            <table class="min-w-full text-sm">
              <thead class="bg-surface-muted text-xs uppercase tracking-wide text-ink-muted">
                <tr>
                  <th class="text-left py-2 px-3">Scope</th>
                  <th class="text-left py-2 px-3">Location</th>
                  <th class="text-left py-2 px-3">Status</th>
                  <th class="text-left py-2 px-3">Count</th>
                  <th class="text-left py-2 px-3">Detail</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="row in memoSourceBoundaryRows"
                  :key="row.scope"
                  class="border-t border-subtle/70"
                >
                  <td class="py-2 px-3 font-medium text-ink-primary">
                    {{ row.scope }}
                  </td>
                  <td class="py-2 px-3 font-mono text-xs text-ink-secondary">
                    {{ row.location }}
                  </td>
                  <td class="py-2 px-3">
                    <span
                      :class="[
                        'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                        row.status === 'included'
                          ? 'bg-success-soft text-success-ink'
                          : 'bg-surface-muted text-ink-muted',
                      ]"
                    >
                      {{ row.status }}
                    </span>
                  </td>
                  <td class="py-2 px-3 font-mono text-ink-secondary">
                    {{ row.count }}
                  </td>
                  <td class="py-2 px-3 text-xs text-ink-muted">
                    {{ row.detail }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="font-display text-lg font-semibold text-ink-primary">
            Tools
          </h3>
        </div>
        <div class="grid lg:grid-cols-2 gap-3">
          <div
            v-for="tool in session.tools"
            :key="tool.name"
            class="rounded-card border border-subtle bg-surface p-4"
          >
            <div class="flex items-start gap-3">
              <component
                :is="toolIcon(tool.name)"
                class="h-5 w-5 text-accent mt-0.5 shrink-0"
              />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 flex-wrap">
                  <div class="font-medium text-ink-primary">{{ tool.label }}</div>
                  <span
                    :class="[
                      'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                      statusClass(tool.status),
                    ]"
                  >
                    {{ tool.status.replace('_', ' ') }}
                  </span>
                </div>
                <p class="mt-1 text-sm text-ink-secondary">
                  {{ tool.description }}
                </p>
                <div v-if="tool.summary" class="mt-2 text-xs text-ink-muted">
                  {{ tool.summary }}
                </div>
                <div v-if="tool.name === 'memo_grader'" class="mt-3 space-y-2">
                  <select
                    :value="memoGrader?.selected_report_id || memoGrader?.completed_report_id || ''"
                    @change="selectMemoForGrading($event.target.value)"
                    :disabled="Boolean(savingArtifact) || completedMemoRuns.length === 0"
                    class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-ink-primary focus-ring"
                  >
                    <option value="">
                      {{ completedMemoRuns.length ? "Select completed memo" : "No completed memos" }}
                    </option>
                    <option
                      v-for="run in completedMemoRuns"
                      :key="run.id"
                      :value="run.id"
                    >
                      {{ run.run_id || run.id }}
                    </option>
                  </select>
                  <div
                    v-if="memoGrader?.status === 'graded'"
                    class="rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-xs text-ink-secondary"
                  >
                    <div class="font-medium text-ink-primary">
                      Graded {{ memoGrader.completed_report_id }}
                    </div>
                    <div v-if="memoGrader.confidence" class="mt-1 text-ink-muted">
                      Confidence: {{ memoGrader.confidence }}
                    </div>
                    <ul v-if="memoGrader.lessons_for_future_memo_runs?.length" class="mt-2 space-y-1">
                      <li
                        v-for="lesson in memoGrader.lessons_for_future_memo_runs.slice(0, 3)"
                        :key="lesson"
                      >
                        {{ lesson }}
                      </li>
                    </ul>
                  </div>
                </div>
                <div v-if="tool.last_run_at" class="mt-1 text-[11px] text-ink-subtle">
                  {{ fmtDate(tool.last_run_at) }}
                </div>
              </div>
              <button
                type="button"
                @click="runTool(tool.name)"
                :disabled="Boolean(runningTool) || tool.status === 'running'"
                class="h-9 w-9 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring"
                :title="`Run ${tool.label}`"
              >
                <Loader2
                  v-if="runningTool === tool.name || tool.status === 'running'"
                  class="h-4 w-4 animate-spin"
                />
                <Play v-else class="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <section
        v-if="additionalAreas.length"
        class="border border-subtle bg-surface rounded-card p-5"
      >
        <h3 class="font-display text-lg font-semibold text-ink-primary">
          Additional Areas Needed
        </h3>
        <div class="mt-3 grid md:grid-cols-2 gap-3">
          <div
            v-for="area in additionalAreas"
            :key="area.id"
            :class="[
              'rounded-lg border px-3 py-2',
              severityClass(area.severity),
            ]"
          >
            <div class="text-sm font-medium">{{ area.area }}</div>
            <div class="mt-1 text-xs opacity-80">{{ area.why_it_matters }}</div>
            <div class="mt-2 flex items-center gap-2 flex-wrap">
              <span class="text-[10px] uppercase tracking-wide opacity-75">
                {{ area.status || "open" }}
              </span>
              <span v-if="area.reviewed_at" class="text-[10px] opacity-70">
                {{ fmtDate(area.reviewed_at) }}
              </span>
            </div>
            <textarea
              v-model="readinessReviewDraft[area.id]"
              rows="2"
              class="mt-2 w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-ink-primary focus-ring resize-y"
              placeholder="Rationale"
            ></textarea>
            <div class="mt-2 flex items-center gap-2 flex-wrap">
              <button
                type="button"
                @click="saveReadinessReview(area, 'waived')"
                :disabled="Boolean(savingArtifact)"
                class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-xs"
              >
                <Save class="h-3.5 w-3.5" />
                <span>Waive</span>
              </button>
              <button
                type="button"
                @click="saveReadinessReview(area, 'reviewed')"
                :disabled="Boolean(savingArtifact)"
                class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-xs"
              >
                <CheckCircle2 class="h-3.5 w-3.5" />
                <span>Reviewed</span>
              </button>
              <button
                type="button"
                @click="saveReadinessReview(area, 'open')"
                :disabled="Boolean(savingArtifact)"
                class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring text-xs"
              >
                <AlertTriangle class="h-3.5 w-3.5" />
                <span>Reopen</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Strategic Risk Board
            </h3>
            <button
              v-if="riskPriorityDraft.length"
              type="button"
              @click="saveRiskPrioritiesDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'risk_priorities'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save priorities</span>
            </button>
          </div>
          <div v-if="risks.length === 0" class="mt-3 text-sm text-ink-muted">
            No risks generated yet.
          </div>
          <div v-else class="mt-3 space-y-3">
            <div
              v-for="risk in prioritizedRisks"
              :key="risk.id"
              class="rounded-lg border border-subtle bg-surface-muted p-3"
            >
              <div class="flex items-start gap-3">
                <div class="flex w-8 shrink-0 flex-col items-center gap-1">
                  <button
                    type="button"
                    @click="moveRiskPriority(risk.id, -1)"
                    :disabled="!canMoveRisk(risk.id, -1) || Boolean(savingArtifact)"
                    class="h-7 w-7 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-muted hover:text-ink-primary hover:bg-surface-muted disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
                    title="Move risk up"
                  >
                    <ArrowUp class="h-3.5 w-3.5" />
                  </button>
                  <div class="text-[11px] font-mono text-ink-muted">
                    #{{ riskPriorityMap.get(risk.id)?.rank || "—" }}
                  </div>
                  <button
                    type="button"
                    @click="moveRiskPriority(risk.id, 1)"
                    :disabled="!canMoveRisk(risk.id, 1) || Boolean(savingArtifact)"
                    class="h-7 w-7 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-muted hover:text-ink-primary hover:bg-surface-muted disabled:opacity-35 disabled:cursor-not-allowed focus-ring"
                    title="Move risk down"
                  >
                    <ArrowDown class="h-3.5 w-3.5" />
                  </button>
                </div>
                <div class="min-w-0 flex-1">
                  <div class="flex items-start justify-between gap-3">
                    <div class="font-medium text-ink-primary">{{ risk.title }}</div>
                    <span class="text-[10px] uppercase tracking-wide text-ink-muted">
                      {{ risk.status }}
                    </span>
                  </div>
                  <div class="mt-1 text-sm text-ink-secondary">
                    {{ risk.decision_question }}
                  </div>
                  <div class="mt-2 text-xs text-ink-muted">
                    {{ risk.why_it_matters }}
                  </div>
                </div>
                <label class="shrink-0 inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
                  <input
                    type="checkbox"
                    :checked="Boolean(riskPriorityMap.get(risk.id)?.selected)"
                    @change="setRiskSelected(risk.id, $event.target.checked)"
                    :disabled="Boolean(savingArtifact)"
                    class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
                  />
                  <span>Research</span>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Investment Highlights & Risks
            </h3>
            <button
              v-if="thesisDraft"
              type="button"
              @click="saveThesisDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'thesis_spine'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save thesis</span>
            </button>
          </div>
          <div v-if="!thesisDraft" class="mt-3 text-sm text-ink-muted">
            No thesis spine drafted yet.
          </div>
          <template v-else>
            <div class="mt-3 text-xs uppercase tracking-wide text-ink-muted">
              Highlights
            </div>
            <div class="mt-2 space-y-3">
              <div
                v-for="(item, index) in thesisDraft.investment_highlights"
                :key="item.id || index"
                class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2"
              >
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`highlight-claim-${item.id || index}`"
                >
                  Claim {{ index + 1 }}
                </label>
                <input
                  :id="`highlight-claim-${item.id || index}`"
                  v-model="item.claim"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring"
                />
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`highlight-detail-${item.id || index}`"
                >
                  Detail
                </label>
                <textarea
                  :id="`highlight-detail-${item.id || index}`"
                  v-model="item.detail"
                  rows="3"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
              </div>
            </div>
            <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
              Risks
            </div>
            <div class="mt-2 space-y-3">
              <div
                v-for="(item, index) in thesisDraft.investment_risks"
                :key="item.id || index"
                class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2"
              >
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`risk-claim-${item.id || index}`"
                >
                  Claim {{ index + 1 }}
                </label>
                <input
                  :id="`risk-claim-${item.id || index}`"
                  v-model="item.claim"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring"
                />
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`risk-detail-${item.id || index}`"
                >
                  Detail
                </label>
                <textarea
                  :id="`risk-detail-${item.id || index}`"
                  v-model="item.detail"
                  rows="3"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
              </div>
            </div>
            <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
              Top Gating Questions
            </div>
            <div class="mt-2 space-y-3">
              <div
                v-for="(gate, index) in thesisDraft.top_gating_questions"
                :key="gate.id || index"
                class="rounded-lg border border-subtle bg-surface-muted p-3 space-y-2"
              >
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`gate-question-${gate.id || index}`"
                >
                  Question {{ index + 1 }}
                </label>
                <textarea
                  :id="`gate-question-${gate.id || index}`"
                  v-model="gate.question"
                  rows="2"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
                <label
                  class="block text-[11px] font-medium uppercase tracking-wide text-ink-muted"
                  :for="`gate-why-${gate.id || index}`"
                >
                  Why It Matters
                </label>
                <textarea
                  :id="`gate-why-${gate.id || index}`"
                  v-model="gate.why_it_matters"
                  rows="2"
                  class="w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-primary focus-ring resize-y"
                ></textarea>
              </div>
            </div>
          </template>
        </div>
      </section>

      <section class="border border-subtle bg-surface rounded-card p-5">
        <div class="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Evidence Matrix
            </h3>
            <div v-if="evidenceMatrix" class="mt-1 text-xs text-ink-muted">
              {{ evidenceMatrix.claim_count || 0 }} claims
            </div>
          </div>
          <div class="flex items-center gap-1 rounded-lg border border-subtle bg-surface-muted p-1">
            <button
              v-for="status in ['all', 'mixed', 'contradicted', 'missing']"
              :key="status"
              type="button"
              @click="evidenceStatusFilter = status"
              :class="[
                'px-2 py-1 rounded-md text-xs focus-ring',
                evidenceStatusFilter === status
                  ? 'bg-surface text-ink-primary shadow-sm'
                  : 'text-ink-muted hover:text-ink-primary',
              ]"
            >
              {{ status }}
            </button>
          </div>
        </div>
        <div v-if="evidenceMatrixError" class="mt-3 text-sm text-danger">
          {{ evidenceMatrixError }}
        </div>
        <div v-else-if="!evidenceMatrix || evidenceRows.length === 0" class="mt-3 text-sm text-ink-muted">
          No evidence matrix claims yet.
        </div>
        <div v-else class="mt-4 overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead class="text-xs uppercase tracking-wide text-ink-muted">
              <tr class="border-b border-subtle">
                <th class="text-left py-2 pr-3">Claim</th>
                <th class="text-left py-2 pr-3">Status</th>
                <th class="text-left py-2 pr-3">Counts</th>
                <th class="text-left py-2 pr-3">Confidence</th>
                <th class="text-left py-2 pr-3">Top Source</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in evidenceRows"
                :key="row.claim"
                class="border-b border-subtle/70 align-top"
              >
                <td class="py-2 pr-3 text-ink-primary max-w-sm">
                  {{ row.claim }}
                </td>
                <td class="py-2 pr-3">
                  <span
                    :class="[
                      'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                      statusClass(row.status),
                    ]"
                  >
                    {{ row.status }}
                  </span>
                </td>
                <td class="py-2 pr-3 text-ink-secondary font-mono">
                  +{{ coverageCount(row, 'supporting_count') }}
                  / -{{ coverageCount(row, 'contradicting_count') }}
                  / ?{{ coverageCount(row, 'missing_count') }}
                </td>
                <td class="py-2 pr-3 text-ink-secondary">
                  {{ row.confidence }}
                </td>
                <td class="py-2 pr-3 text-ink-secondary max-w-md">
                  <template v-if="topEvidence(row)">
                    <div class="text-[11px] text-ink-muted">
                      {{ evidenceLabel(topEvidence(row)) }}
                      <a
                        v-if="topEvidence(row).task_id"
                        :href="`#memo-task-${topEvidence(row).task_id}`"
                        class="ml-2 text-accent hover:underline"
                      >
                        {{ topEvidence(row).task_title || topEvidence(row).task_id }}
                      </a>
                    </div>
                    <div>{{ topEvidence(row).excerpt }}</div>
                  </template>
                  <span v-else>—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Research Task Queue
            </h3>
            <button
              v-if="tasks.length"
              type="button"
              @click="runSelectedTasks"
              :disabled="runningBatch || hasRunningTasks"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2 v-if="runningBatch" class="h-3.5 w-3.5 animate-spin" />
              <Play v-else class="h-3.5 w-3.5" />
              <span>Run selected</span>
            </button>
          </div>
          <div
            v-if="batchStatus"
            class="mt-3 rounded-lg border border-subtle bg-surface-muted px-3 py-2 text-xs text-ink-secondary"
          >
            <div>
              Launched {{ batchStatus.launched_task_ids?.length || 0 }} tasks · concurrency {{ batchStatus.concurrency }}
            </div>
            <div class="mt-1 text-ink-muted">
              <span
                v-for="(status, taskId) in batchStatus.statuses"
                :key="taskId"
                class="mr-2"
              >
                {{ taskId }}: {{ status.replaceAll('_', ' ') }}
              </span>
            </div>
          </div>
          <div v-if="tasks.length === 0" class="mt-3 text-sm text-ink-muted">
            No research tasks yet.
          </div>
          <div v-else class="mt-3 space-y-2">
            <div
              v-for="task in tasks"
              :key="task.id"
              :id="`memo-task-${task.id}`"
              class="rounded-lg border border-subtle bg-surface-muted p-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex items-center gap-2 flex-wrap">
                    <div class="text-sm font-medium text-ink-primary">{{ task.title }}</div>
                    <span class="text-[10px] rounded bg-surface px-1.5 py-0.5 text-ink-muted uppercase">
                      {{ task.priority }}
                    </span>
                    <span
                      :class="[
                        'text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wide',
                        statusClass(task.status),
                      ]"
                    >
                      {{ statusLabel(task.status) }}
                    </span>
                  </div>
                  <div class="mt-1 text-xs text-ink-muted">{{ task.source_type }}</div>
                  <div class="mt-2 text-xs text-ink-secondary">{{ task.prompt }}</div>
                </div>
                <div class="flex items-center gap-2 shrink-0">
                  <button
                    type="button"
                    @click="runResearchTask(task.id)"
                    :disabled="Boolean(runningTask) || task.status === 'running'"
                    class="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-subtle bg-surface text-ink-primary hover:bg-surface-muted disabled:opacity-60 focus-ring"
                    :title="task.status === 'running' ? 'Task running' : task.status === 'done' ? 'Run task again' : 'Run task'"
                  >
                    <Loader2
                      v-if="runningTask === task.id || task.status === 'running'"
                      class="h-4 w-4 animate-spin"
                    />
                    <Play v-else class="h-4 w-4" />
                  </button>
                  <button
                    v-if="task.status === 'running'"
                    type="button"
                    @click="cancelResearchTask(task.id)"
                    :disabled="cancellingTask === task.id"
                    class="h-8 w-8 inline-flex items-center justify-center rounded-lg border border-danger/30 bg-danger/10 text-danger hover:bg-danger/15 disabled:opacity-60 focus-ring"
                    title="Cancel task"
                  >
                    <Loader2
                      v-if="cancellingTask === task.id"
                      class="h-4 w-4 animate-spin"
                    />
                    <AlertTriangle v-else class="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div
                v-if="sourceFiles.length"
                class="mt-3 rounded-lg border border-subtle bg-surface px-3 py-2"
              >
                <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                  Sources
                </div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <label
                    v-for="source in sourceFiles"
                    :key="source.id"
                    class="inline-flex items-center gap-1.5 rounded border border-subtle bg-surface-muted px-2 py-1 text-xs text-ink-secondary"
                  >
                    <input
                      type="checkbox"
                      :checked="isSourceSelected(task, source.id)"
                      :disabled="savingTask === task.id || task.status === 'running'"
                      @change="toggleTaskSource(task, source.id, $event.target.checked)"
                      class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
                    />
                    <span>{{ sourceLabel(source) }}</span>
                  </label>
                </div>
                <div
                  v-if="taskSourceIds(task).length === 0"
                  class="mt-2 text-[11px] text-ink-muted"
                >
                  All research-folder sources will be available.
                </div>
              </div>
              <div
                v-if="task.result_summary || task.answer"
                class="mt-3 rounded-lg border border-subtle bg-surface px-3 py-2 text-xs text-ink-secondary"
              >
                <div class="font-medium text-ink-primary">
                  {{ task.answer || task.result_summary }}
                </div>
                <div
                  v-if="task.confidence || task.sources_checked?.length"
                  class="mt-1 text-[11px] text-ink-muted"
                >
                  <span v-if="task.confidence">Confidence: {{ task.confidence }}</span>
                  <span v-if="task.sources_checked?.length">
                    · Sources checked: {{ sourceCheckedText(task) }}
                  </span>
                </div>
                <div
                  v-if="listItems(task.supporting_evidence).length"
                  class="mt-3"
                >
                  <div class="text-[11px] uppercase tracking-wide text-success-ink">
                    Supporting evidence
                  </div>
                  <div
                    v-for="(item, index) in listItems(task.supporting_evidence)"
                    :key="`support-${task.id}-${index}`"
                    class="mt-1 rounded border border-subtle bg-surface-muted px-2 py-1"
                  >
                    <div class="text-[11px] text-ink-muted">{{ evidenceLabel(item) }}</div>
                    <div>{{ item.excerpt }}</div>
                  </div>
                </div>
                <div
                  v-if="listItems(task.contradicting_evidence).length"
                  class="mt-3"
                >
                  <div class="text-[11px] uppercase tracking-wide text-danger">
                    Contradicting evidence
                  </div>
                  <div
                    v-for="(item, index) in listItems(task.contradicting_evidence)"
                    :key="`contradict-${task.id}-${index}`"
                    class="mt-1 rounded border border-subtle bg-surface-muted px-2 py-1"
                  >
                    <div class="text-[11px] text-ink-muted">{{ evidenceLabel(item) }}</div>
                    <div>{{ item.excerpt }}</div>
                  </div>
                </div>
                <div
                  v-if="listItems(task.open_questions).length"
                  class="mt-3"
                >
                  <div class="text-[11px] uppercase tracking-wide text-warning-ink">
                    Open questions
                  </div>
                  <ul class="mt-1 space-y-1">
                    <li
                      v-for="(question, index) in listItems(task.open_questions)"
                      :key="`question-${task.id}-${index}`"
                    >
                      {{ question }}
                    </li>
                  </ul>
                </div>
                <div
                  v-if="task.completed_at || task.last_run_at"
                  class="mt-1 text-[11px] text-ink-subtle"
                >
                  {{ fmtDate(task.completed_at || task.last_run_at) }}
                  <span v-if="task.result_generated_by">
                    · {{ task.result_generated_by.replaceAll('_', ' ') }}
                  </span>
                </div>
              </div>
              <div v-if="task.error" class="mt-2 text-xs text-danger">
                {{ task.error }}
              </div>
            </div>
          </div>
        </div>

        <div class="xl:col-span-2 border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="font-display text-lg font-semibold text-ink-primary">
                Infographic Source Brief
              </h3>
              <div v-if="sourceBrief?.confidence" class="mt-1 text-xs text-ink-muted">
                Confidence: {{ sourceBrief.confidence }}
              </div>
            </div>
            <span
              v-if="sourceBrief?.generated_by"
              class="rounded bg-surface-muted px-2 py-1 text-[10px] uppercase tracking-wide text-ink-muted"
            >
              {{ sourceBrief.generated_by.replaceAll('_', ' ') }}
            </span>
          </div>
          <div v-if="!sourceBrief" class="mt-3 text-sm text-ink-muted">
            No infographic source brief yet.
          </div>
          <template v-else>
            <p v-if="sourceBrief.summary" class="mt-3 text-sm text-ink-secondary">
              {{ sourceBrief.summary }}
            </p>
            <div class="mt-4 grid xl:grid-cols-3 gap-3">
              <div class="rounded-lg border border-subtle bg-surface-muted p-3">
                <div class="text-xs uppercase tracking-wide text-ink-muted">
                  Claims
                </div>
                <div
                  v-for="claim in listItems(sourceBrief.compact_claims).slice(0, 6)"
                  :key="claim.id || claim.claim"
                  class="mt-2 rounded border border-subtle bg-surface px-2 py-1.5 text-xs"
                >
                  <div class="font-medium text-ink-primary">{{ claim.claim }}</div>
                  <div class="mt-1 text-[11px] text-ink-muted">
                    {{ claim.evidence_status || "needs review" }} · {{ claim.confidence || "medium" }}
                    <span v-if="claim.prohibited_for_visuals"> · no visual fact claim</span>
                  </div>
                  <div
                    v-for="trace in listItems(claim.source_traces).slice(0, 2)"
                    :key="`${claim.id}-${sourceTraceLabel(trace)}`"
                    class="mt-1 text-[11px] text-ink-secondary"
                  >
                    <span class="text-ink-muted">{{ sourceTraceLabel(trace) }}:</span>
                    {{ trace.excerpt }}
                  </div>
                </div>
              </div>
              <div class="rounded-lg border border-subtle bg-surface-muted p-3">
                <div class="text-xs uppercase tracking-wide text-ink-muted">
                  Metrics & Warnings
                </div>
                <div
                  v-for="metric in listItems(sourceBrief.numeric_metrics).slice(0, 6)"
                  :key="metric.id || metric.label"
                  class="mt-2 text-xs text-ink-secondary"
                >
                  <span class="font-medium text-ink-primary">{{ metric.label }}</span>
                  <span>
                    · {{ metric.value ?? "missing" }}{{ metric.unit || "" }}
                  </span>
                  <span v-if="metric.period"> · {{ metric.period }}</span>
                </div>
                <div v-if="listItems(sourceBrief.missing_evidence).length" class="mt-3">
                  <div class="text-[11px] uppercase tracking-wide text-warning-ink">
                    Missing evidence
                  </div>
                  <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
                    <li
                      v-for="item in listItems(sourceBrief.missing_evidence).slice(0, 5)"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
                <div v-if="listItems(sourceBrief.no_go_claims).length" class="mt-3">
                  <div class="text-[11px] uppercase tracking-wide text-danger">
                    No-go claims
                  </div>
                  <ul class="mt-1 space-y-1 text-xs text-ink-secondary">
                    <li
                      v-for="item in listItems(sourceBrief.no_go_claims).slice(0, 5)"
                      :key="item"
                    >
                      {{ item }}
                    </li>
                  </ul>
                </div>
              </div>
              <div class="rounded-lg border border-subtle bg-surface-muted p-3">
                <div class="text-xs uppercase tracking-wide text-ink-muted">
                  Opportunities & Prompts
                </div>
                <div
                  v-for="item in listItems(sourceBrief.visual_opportunities).slice(0, 4)"
                  :key="item.id || item.title"
                  class="mt-2 text-xs text-ink-secondary"
                >
                  <div class="font-medium text-ink-primary">{{ item.title }}</div>
                  <div>{{ item.rationale }}</div>
                </div>
                <div
                  v-for="prompt in listItems(sourceBrief.reviewer_prompts).slice(0, 4)"
                  :key="prompt.id || prompt.prompt"
                  class="mt-2 rounded border border-subtle bg-surface px-2 py-1 text-xs text-ink-secondary"
                >
                  <div class="font-medium text-ink-primary">{{ prompt.prompt }}</div>
                  <div class="mt-1 text-[11px] text-ink-muted">
                    {{ promptStatus(prompt) }}
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Chart & Table Plan
            </h3>
            <button
              v-if="chartSpecsDraft.length"
              type="button"
              @click="saveChartSpecsDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'chart_specs'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save charts</span>
            </button>
          </div>
          <div v-if="chartSpecsDraft.length === 0" class="mt-3 text-sm text-ink-muted">
            No chart specs yet.
          </div>
          <div v-else class="mt-3 space-y-2">
            <div
              v-for="spec in chartSpecsDraft"
              :key="spec.id"
              class="rounded-lg border border-subtle bg-surface-muted p-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="text-sm font-medium text-ink-primary">{{ spec.title }}</div>
                <div class="flex items-center gap-2 shrink-0">
                  <label class="inline-flex items-center gap-1.5 text-[11px] text-ink-muted">
                    <input
                      v-model="spec.include_in_final_memo"
                      type="checkbox"
                      class="h-3.5 w-3.5 rounded border-subtle text-accent focus-ring"
                    />
                    <span>Final memo</span>
                  </label>
                  <span
                    :class="[
                      'text-[10px] rounded px-1.5 py-0.5 uppercase',
                      (spec.source_availability || spec.data_availability) === 'missing'
                        ? 'bg-warning-soft text-warning-ink'
                        : 'bg-success-soft text-success-ink',
                    ]"
                  >
                    {{ spec.source_availability || spec.data_availability }}
                  </span>
                </div>
              </div>
              <div class="mt-1 text-xs text-ink-secondary">
                {{ spec.purpose || spec.takeaway }}
              </div>
              <div class="mt-2 flex flex-wrap gap-2 text-[11px] text-ink-muted">
                <span class="rounded border border-subtle bg-surface px-2 py-0.5">
                  {{ spec.recommended_visual_format || "infographic" }}
                </span>
                <span class="rounded border border-subtle bg-surface px-2 py-0.5">
                  {{ (spec.image_generation_mode || "no_text_overlay").replaceAll('_', ' ') }}
                </span>
                <span
                  v-if="spec.status"
                  class="rounded border border-subtle bg-surface px-2 py-0.5"
                >
                  {{ spec.status.replaceAll('_', ' ') }}
                </span>
                <span
                  v-if="spec.final_memo_inclusion_state"
                  class="rounded border border-subtle bg-surface px-2 py-0.5"
                >
                  {{ spec.final_memo_inclusion_state.replaceAll('_', ' ') }}
                </span>
              </div>
              <div
                v-if="spec.text_overlay_plan"
                class="mt-3 rounded border border-subtle bg-surface px-2 py-1.5 text-xs text-ink-secondary"
              >
                <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                  Overlay copy
                </div>
                <div class="mt-1 font-medium text-ink-primary">
                  {{ spec.text_overlay_plan.headline }}
                </div>
                <div
                  v-if="listItems(spec.text_overlay_plan.callouts).length"
                  class="mt-1"
                >
                  <span
                    v-for="callout in listItems(spec.text_overlay_plan.callouts).slice(0, 4)"
                    :key="callout"
                    class="mr-2"
                  >
                    {{ callout }}
                  </span>
                </div>
                <div
                  v-if="spec.text_overlay_plan.safe_copy_length"
                  class="mt-1 text-[11px] text-ink-muted"
                >
                  {{ spec.text_overlay_plan.safe_copy_length }}
                </div>
              </div>
              <div
                v-if="listItems(spec.required_metrics).length"
                class="mt-3 text-xs text-ink-secondary"
              >
                <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                  Required metrics
                </div>
                <div class="mt-1 grid sm:grid-cols-2 gap-1.5">
                  <div
                    v-for="metric in listItems(spec.required_metrics).slice(0, 6)"
                    :key="metric.id || metric.label"
                    class="rounded border border-subtle bg-surface px-2 py-1"
                  >
                    <div class="font-medium text-ink-primary">{{ metric.label }}</div>
                    <div class="text-[11px] text-ink-muted">
                      {{ metric.value ?? "missing" }}{{ metric.unit || "" }}
                      <span v-if="metric.period"> · {{ metric.period }}</span>
                      <span> · {{ metric.source_available ? "sourced" : "source needed" }}</span>
                    </div>
                  </div>
                </div>
              </div>
              <div
                v-if="listItems(spec.information_gaps).length"
                class="mt-3 text-xs text-warning-ink"
              >
                <div class="text-[11px] uppercase tracking-wide">
                  Information gaps
                </div>
                <ul class="mt-1 space-y-1">
                  <li
                    v-for="gap in listItems(spec.information_gaps).slice(0, 5)"
                    :key="gap"
                  >
                    {{ gap }}
                  </li>
                </ul>
              </div>
              <div
                v-if="listItems(spec.reviewer_prompts).length"
                class="mt-3 text-xs text-ink-secondary"
              >
                <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                  Reviewer prompts
                </div>
                <div
                  v-for="prompt in listItems(spec.reviewer_prompts).slice(0, 4)"
                  :key="prompt.id || prompt.prompt"
                  class="mt-1 rounded border border-subtle bg-surface px-2 py-1"
                >
                  <div class="font-medium text-ink-primary">{{ prompt.prompt }}</div>
                  <div class="text-[11px] text-ink-muted">
                    {{ promptStatus(prompt) }}
                  </div>
                </div>
              </div>
              <div
                v-if="listItems(spec.source_traces).length"
                class="mt-3 text-xs text-ink-secondary"
              >
                <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                  Source traces
                </div>
                <div
                  v-for="trace in listItems(spec.source_traces).slice(0, 3)"
                  :key="sourceTraceLabel(trace)"
                  class="mt-1 rounded border border-subtle bg-surface px-2 py-1"
                >
                  <div class="text-[11px] text-ink-muted">
                    {{ sourceTraceLabel(trace) }}
                    <span v-if="trace.confidence">· {{ trace.confidence }}</span>
                  </div>
                  <div>{{ trace.excerpt }}</div>
                </div>
              </div>
              <div
                v-if="spec.design_prompt?.composition"
                class="mt-3 text-xs text-ink-secondary"
              >
                <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                  Image prompt
                </div>
                <div class="mt-1 rounded border border-subtle bg-surface px-2 py-1">
                  {{ spec.design_prompt.composition }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Narrative Hooks
            </h3>
            <button
              v-if="narrativeDraft"
              type="button"
              @click="saveNarrativeDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'narrative_hooks'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save hooks</span>
            </button>
          </div>
          <div v-if="!narrativeDraft" class="mt-3 text-sm text-ink-muted">
            No openings or endings yet.
          </div>
          <template v-else>
            <div class="mt-3 text-xs uppercase tracking-wide text-ink-muted">
              Openings
            </div>
            <div class="mt-2 space-y-2">
              <label
                v-for="opening in narrativeDraft.openings"
                :key="opening.id"
                :class="[
                  'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
                  narrativeDraft.selected_opening_id === opening.id
                    ? 'border-accent bg-accent-soft/40 text-accent-ink'
                    : 'border-subtle bg-surface-muted text-ink-primary',
                ]"
              >
                <input
                  v-model="narrativeDraft.selected_opening_id"
                  type="radio"
                  :name="`opening-${session.id}`"
                  :value="opening.id"
                  class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
                />
                <span class="min-w-0">
                  <span class="block">{{ opening.text }}</span>
                  <span class="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-muted">
                    <span>{{ opening.tone }}</span>
                    <span v-if="opening.confidence">· {{ opening.confidence }}</span>
                    <span v-if="opening.status">· {{ opening.status.replaceAll('_', ' ') }}</span>
                  </span>
                  <span
                    v-if="opening.overclaiming_risk"
                    class="mt-1 block text-[11px] text-warning-ink"
                  >
                    {{ opening.overclaiming_risk }}
                  </span>
                  <span
                    v-if="listItems(opening.paired_infographic_ids).length"
                    class="mt-1 block text-[11px] text-ink-muted"
                  >
                    Paired visuals: {{ listItems(opening.paired_infographic_ids).join(", ") }}
                  </span>
                </span>
              </label>
            </div>
            <div
              v-if="listItems(narrativeDraft.transitions).length"
              class="mt-4 text-xs uppercase tracking-wide text-ink-muted"
            >
              Transitions
            </div>
            <div
              v-if="listItems(narrativeDraft.transitions).length"
              class="mt-2 space-y-2"
            >
              <label
                v-for="transition in narrativeDraft.transitions"
                :key="transition.id"
                :class="[
                  'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
                  narrativeDraft.selected_transition_id === transition.id
                    ? 'border-accent bg-accent-soft/40 text-accent-ink'
                    : 'border-subtle bg-surface-muted text-ink-primary',
                ]"
              >
                <input
                  v-model="narrativeDraft.selected_transition_id"
                  type="radio"
                  :name="`transition-${session.id}`"
                  :value="transition.id"
                  class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
                />
                <span class="min-w-0">
                  <span class="block">{{ transition.text }}</span>
                  <span class="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-muted">
                    <span>{{ transition.tone }}</span>
                    <span v-if="transition.confidence">· {{ transition.confidence }}</span>
                    <span v-if="transition.status">· {{ transition.status.replaceAll('_', ' ') }}</span>
                  </span>
                  <span
                    v-if="transition.overclaiming_risk"
                    class="mt-1 block text-[11px] text-warning-ink"
                  >
                    {{ transition.overclaiming_risk }}
                  </span>
                </span>
              </label>
            </div>
            <div class="mt-4 text-xs uppercase tracking-wide text-ink-muted">
              Endings
            </div>
            <div class="mt-2 space-y-2">
              <label
                v-for="ending in narrativeDraft.endings"
                :key="ending.id"
                :class="[
                  'flex items-start gap-3 rounded-lg border p-3 text-sm cursor-pointer',
                  narrativeDraft.selected_ending_id === ending.id
                    ? 'border-accent bg-accent-soft/40 text-accent-ink'
                    : 'border-subtle bg-surface-muted text-ink-primary',
                ]"
              >
                <input
                  v-model="narrativeDraft.selected_ending_id"
                  type="radio"
                  :name="`ending-${session.id}`"
                  :value="ending.id"
                  class="mt-0.5 h-4 w-4 border-subtle text-accent focus-ring"
                />
                <span class="min-w-0">
                  <span class="block">{{ ending.text }}</span>
                  <span class="mt-1 flex flex-wrap gap-2 text-[11px] text-ink-muted">
                    <span>{{ ending.tone }}</span>
                    <span v-if="ending.confidence">· {{ ending.confidence }}</span>
                    <span v-if="ending.status">· {{ ending.status.replaceAll('_', ' ') }}</span>
                  </span>
                  <span
                    v-if="ending.overclaiming_risk"
                    class="mt-1 block text-[11px] text-warning-ink"
                  >
                    {{ ending.overclaiming_risk }}
                  </span>
                </span>
              </label>
            </div>
            <div
              v-if="listItems(narrativeDraft.reviewer_prompts).length"
              class="mt-4 rounded-lg border border-subtle bg-surface-muted p-3 text-xs text-ink-secondary"
            >
              <div class="text-[11px] uppercase tracking-wide text-ink-muted">
                Reviewer prompts
              </div>
              <div
                v-for="prompt in listItems(narrativeDraft.reviewer_prompts)"
                :key="prompt.id || prompt.prompt"
                class="mt-2 rounded border border-subtle bg-surface px-2 py-1"
              >
                <div class="font-medium text-ink-primary">{{ prompt.prompt }}</div>
                <div class="mt-1 text-[11px] text-ink-muted">
                  {{ promptStatus(prompt) }}
                </div>
              </div>
            </div>
          </template>
        </div>

        <div class="border border-subtle bg-surface rounded-card p-5">
          <div class="flex items-center justify-between gap-3">
            <h3 class="font-display text-lg font-semibold text-ink-primary">
              Benchmark Dashboard
            </h3>
            <button
              v-if="benchmarkDraft"
              type="button"
              @click="saveBenchmarkDraft"
              :disabled="Boolean(savingArtifact)"
              class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-subtle bg-surface-muted text-ink-primary hover:bg-surface disabled:opacity-60 focus-ring text-xs"
            >
              <Loader2
                v-if="savingArtifact === 'benchmark_dashboard'"
                class="h-3.5 w-3.5 animate-spin"
              />
              <Save v-else class="h-3.5 w-3.5" />
              <span>Save benchmark</span>
            </button>
          </div>
          <div v-if="!benchmark" class="mt-3 text-sm text-ink-muted">
            No benchmark dashboard yet.
          </div>
          <template v-else>
            <textarea
              v-if="benchmarkDraft"
              v-model="benchmarkDraft.summary"
              rows="2"
              class="mt-2 w-full rounded-lg border border-subtle bg-surface px-3 py-2 text-sm text-ink-secondary focus-ring resize-y"
            ></textarea>
            <div class="mt-3 overflow-x-auto">
              <table class="min-w-full text-sm">
                <thead class="text-xs uppercase tracking-wide text-ink-muted">
                  <tr class="border-b border-subtle">
                    <th class="text-left py-2 pr-3">Company</th>
                    <th class="text-left py-2 pr-3">Ticker</th>
                    <th class="text-left py-2 pr-3">Growth</th>
                    <th class="text-left py-2 pr-3">GM</th>
                    <th class="text-left py-2 pr-3">EV/Rev</th>
                    <th class="text-left py-2 pr-3">FCF</th>
                    <th class="text-left py-2 pr-3">Theme</th>
                    <th class="text-left py-2 pr-3">Confidence</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="comp in benchmarkDraft?.public_comps || []"
                    :key="comp.id"
                    class="border-b border-subtle/70"
                  >
                    <td class="py-2 pr-3">
                      <input
                        v-model="comp.company"
                        class="w-32 rounded border border-subtle bg-surface px-2 py-1 text-ink-primary focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3">
                      <input
                        v-model="comp.ticker"
                        class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary font-mono focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3">
                      <input
                        v-model.number="comp.revenue_growth_pct"
                        type="number"
                        step="0.1"
                        class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3">
                      <input
                        v-model.number="comp.gross_margin_pct"
                        type="number"
                        step="0.1"
                        class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3">
                      <input
                        v-model.number="comp.ev_revenue"
                        type="number"
                        step="0.1"
                        class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3">
                      <input
                        v-model.number="comp.fcf_margin_pct"
                        type="number"
                        step="0.1"
                        class="w-20 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3">
                      <input
                        v-model="comp.sell_side_theme"
                        class="w-48 rounded border border-subtle bg-surface px-2 py-1 text-ink-secondary focus-ring"
                      />
                    </td>
                    <td class="py-2 pr-3 text-ink-secondary">{{ comp.confidence }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-if="benchmarkView?.benchmark_gaps?.length || benchmarkView?.must_prove?.length"
              class="mt-4 grid md:grid-cols-2 gap-3 text-xs text-ink-secondary"
            >
              <div v-if="benchmarkView?.benchmark_gaps?.length">
                <div class="uppercase tracking-wide text-ink-muted">Benchmark gaps</div>
                <ul class="mt-1 space-y-1">
                  <li v-for="gap in benchmarkView?.benchmark_gaps || []" :key="gap">
                    {{ gap }}
                  </li>
                </ul>
              </div>
              <div v-if="benchmarkView?.must_prove?.length">
                <div class="uppercase tracking-wide text-ink-muted">Must prove</div>
                <ul class="mt-1 space-y-1">
                  <li v-for="claim in benchmarkView?.must_prove || []" :key="claim">
                    {{ claim }}
                  </li>
                </ul>
              </div>
            </div>
            <div
              v-if="benchmarkView?.source_traces?.length"
              class="mt-4 text-xs text-ink-secondary"
            >
              <div class="uppercase tracking-wide text-ink-muted">Source traces</div>
              <div
                v-for="(trace, index) in benchmarkView.source_traces.slice(0, 4)"
                :key="`${trace.locator || trace.title || trace.url}-${index}`"
                class="mt-1 rounded border border-subtle bg-surface-muted px-2 py-1"
              >
                <div class="text-[11px] text-ink-muted">
                  {{ trace.locator || trace.title || trace.url || "Source" }}
                  <span v-if="trace.confidence">· {{ trace.confidence }}</span>
                </div>
                <div>{{ trace.excerpt }}</div>
              </div>
            </div>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>
