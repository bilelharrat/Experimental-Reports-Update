<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  AlertTriangle,
  Loader2,
  Save,
} from "lucide-vue-next";
import { api } from "../api.js";
import RunLedgerTable from "./RunLedgerTable.vue";
import MemoBenchmarkPanel from "./memo/MemoBenchmarkPanel.vue";
import MemoChartPlansPanel from "./memo/MemoChartPlansPanel.vue";
import MemoEvidenceMatrixPanel from "./memo/MemoEvidenceMatrixPanel.vue";
import MemoGeneratedMemoControlsPanel from "./memo/MemoGeneratedMemoControlsPanel.vue";
import MemoNarrativeHooksPanel from "./memo/MemoNarrativeHooksPanel.vue";
import MemoReadinessPanel from "./memo/MemoReadinessPanel.vue";
import MemoResearchTasksPanel from "./memo/MemoResearchTasksPanel.vue";
import MemoRiskPriorityPanel from "./memo/MemoRiskPriorityPanel.vue";
import MemoSourceBriefPanel from "./memo/MemoSourceBriefPanel.vue";
import MemoToolLauncherPanel from "./memo/MemoToolLauncherPanel.vue";
import MemoToolboxPanel from "./memo/MemoToolboxPanel.vue";

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
const memoRunLedger = ref([]);
const memoRunLedgerError = ref(null);
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
const canGenerateMemo = computed(() => Boolean(session.value?.id));
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
  if (canGenerateMemo.value && completedMemoRuns.value.length === 0) return "Generate memo";
  if (readinessBlockers.value.length) {
    return readinessBlockers.value[0]?.label || "Resolve readiness blockers";
  }
  if (!thesisApproved.value) return "Approve thesis spine";
  if (!approved.value) return "Approve analysis";
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
    await loadRunLedger();
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

async function loadRunLedger() {
  memoRunLedgerError.value = null;
  try {
    memoRunLedger.value = await api.memoAnalysis.runLedger(props.companyId);
  } catch (e) {
    memoRunLedger.value = [];
    memoRunLedgerError.value = e.message || String(e);
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
    await loadRunLedger();
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
    await loadRunLedger();
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
    await loadRunLedger();
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
    await loadRunLedger();
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
    await loadRunLedger();
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

function updateReadinessReviewDraft(areaId, value) {
  readinessReviewDraft.value = {
    ...readinessReviewDraft.value,
    [areaId]: value,
  };
}

function generateFromAnalysis() {
  if (!session.value?.id || !canGenerateMemo.value) return;
  emit("generate-memo", session.value.id);
}

function evidenceLabel(item) {
  const locator = item?.locator || item?.filename || item?.file_id;
  return locator || "Source trace";
}

function listItems(value) {
  return Array.isArray(value) ? value : [];
}

function approvalTitle() {
  if (readyForApproval.value) return approved.value ? "Analysis approved" : "Approve analysis";
  const first = readinessBlockers.value[0]?.label || "Resolve readiness blockers";
  return `Resolve before approval: ${first}`;
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
    <MemoGeneratedMemoControlsPanel
      :session="session"
      :approved="approved"
      :approving="approving"
      :loading="loading"
      :ready-for-approval="readyForApproval"
      :can-generate-memo="canGenerateMemo"
      :approval-title="approvalTitle()"
      @approve="approve"
      @generate-memo="generateFromAnalysis"
    />

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
      <MemoReadinessPanel
        :readiness="readiness"
        :readiness-pct="readinessPct"
        :readiness-blockers="readinessBlockers"
        :additional-areas="additionalAreas"
        :readiness-review-draft="readinessReviewDraft"
        :saving-artifact="savingArtifact"
        @update-readiness-review-draft="updateReadinessReviewDraft"
        @save-readiness-review="saveReadinessReview"
      />

      <MemoToolboxPanel
        :summary="memoToolboxSummary"
        :work-products="memoWorkProducts"
        :review-items="memoReviewItems"
        :source-trace-rows="memoSourceTraceRows"
        :source-boundary-rows="memoSourceBoundaryRows"
      />

      <RunLedgerTable
        :rows="memoRunLedger"
        title="Memo Run Ledger"
        description="Normalized rows for analysis tools, research tasks, and final memo generation."
        empty-text="No Memo Tools run ledger rows yet."
      />

      <div
        v-if="memoRunLedgerError"
        class="rounded-lg border border-warning/40 bg-warning-soft px-3 py-2 text-sm text-warning-ink"
      >
        {{ memoRunLedgerError }}
      </div>

      <MemoToolLauncherPanel
        :tools="session.tools"
        :running-tool="runningTool"
        :saving-artifact="savingArtifact"
        :memo-grader="memoGrader"
        :completed-memo-runs="completedMemoRuns"
        @run-tool="runTool"
        @select-memo-for-grading="selectMemoForGrading"
      />

      <section class="grid xl:grid-cols-2 gap-4">
        <MemoRiskPriorityPanel
          :risks="risks"
          :prioritized-risks="prioritizedRisks"
          :risk-priority-map="riskPriorityMap"
          :risk-priority-draft="riskPriorityDraft"
          :saving-artifact="savingArtifact"
          :can-move-risk="canMoveRisk"
          @save-risk-priorities="saveRiskPrioritiesDraft"
          @move-risk-priority="moveRiskPriority"
          @set-risk-selected="setRiskSelected"
        />

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

      <MemoEvidenceMatrixPanel
        :evidence-matrix="evidenceMatrix"
        :evidence-matrix-error="evidenceMatrixError"
        :evidence-rows="evidenceRows"
        :evidence-status-filter="evidenceStatusFilter"
        @update:evidence-status-filter="evidenceStatusFilter = $event"
      />

      <section class="grid xl:grid-cols-2 gap-4">
        <MemoResearchTasksPanel
          :tasks="tasks"
          :source-files="sourceFiles"
          :batch-status="batchStatus"
          :running-batch="runningBatch"
          :has-running-tasks="hasRunningTasks"
          :running-task="runningTask"
          :cancelling-task="cancellingTask"
          :saving-task="savingTask"
          @run-selected-tasks="runSelectedTasks"
          @run-research-task="runResearchTask"
          @cancel-research-task="cancelResearchTask"
          @toggle-task-source="toggleTaskSource"
        />

        <MemoSourceBriefPanel
          :source-brief="sourceBrief"
        />

        <MemoChartPlansPanel
          :chart-specs-draft="chartSpecsDraft"
          :saving-artifact="savingArtifact"
          @save-chart-specs="saveChartSpecsDraft"
        />
      </section>

      <section class="grid xl:grid-cols-2 gap-4">
        <MemoNarrativeHooksPanel
          :narrative-draft="narrativeDraft"
          :session-id="session.id"
          :saving-artifact="savingArtifact"
          @save-narrative="saveNarrativeDraft"
        />

        <MemoBenchmarkPanel
          :benchmark="benchmark"
          :benchmark-draft="benchmarkDraft"
          :benchmark-view="benchmarkView"
          :saving-artifact="savingArtifact"
          @save-benchmark="saveBenchmarkDraft"
        />
      </section>
    </template>
  </div>
</template>
