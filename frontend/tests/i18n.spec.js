// i18n regression guards.
//
// 1. Dictionary parity: every en key must have a zh key (and vice versa).
//    `t()` falls back zh → en silently, so a missing zh key ships English
//    to Chinese users with no error anywhere — this is the only place
//    that failure is visible.
//
// 2. Template scan: dictionary parity was already 100% when the July 2026
//    QA report found ~60 English strings in the zh UI — every one was a
//    template literal that never called t(). This scan parses each .vue
//    <template> block and flags bare ASCII text nodes and static
//    placeholder/aria-label/title/alt attributes.
//    - STRICT_FILES (the QA-audited surfaces) must have ZERO violations.
//    - Every other file is ratcheted: it may not exceed its recorded
//      baseline, so new hardcoded strings fail CI while the pre-existing
//      backlog is burned down file by file (lower the number as you fix).

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SRC_ROOT = path.join(__dirname, "..", "src");

function loadDicts() {
  // The i18n module exports a `t()` function but not the raw dictionaries,
  // so we parse the source to inspect both language blocks. Cheaper than
  // running a Vue reactive runtime here.
  const src = fs.readFileSync(path.join(SRC_ROOT, "i18n.js"), "utf8");
  const enStart = src.indexOf("en: {");
  const zhStart = src.indexOf("zh: {");
  if (enStart < 0 || zhStart < 0) throw new Error("i18n blocks not found");
  function keysIn(block) {
    return Array.from(block.matchAll(/"([a-z_][\w.]*)":/g)).map((m) => m[1]);
  }
  const en = new Set(keysIn(src.slice(enStart, zhStart)));
  const zh = new Set(keysIn(src.slice(zhStart)));
  return { en, zh };
}

describe("i18n dictionary parity", () => {
  const { en, zh } = loadDicts();

  it("every en key has a zh counterpart", () => {
    const missing = [...en].filter((k) => !zh.has(k));
    expect(missing).toEqual([]);
  });

  it("every zh key has an en counterpart", () => {
    const missing = [...zh].filter((k) => !en.has(k));
    expect(missing).toEqual([]);
  });

  it("there are at least 20 console.* keys defined", () => {
    const enConsole = [...en].filter((k) => k.startsWith("console."));
    expect(enConsole.length).toBeGreaterThanOrEqual(20);
  });
});

// ---------------------------------------------------------------------------
// Template scan
// ---------------------------------------------------------------------------

// Brand names, product nouns, and strings that are intentionally identical
// in both languages. Matched against whole trimmed segments AND individual
// words. Keep this list short — it exists for brands, not for skipping work.
const ALLOW = new Set([
  "Berkeley Summit House",
  "Research Center",
  "BSH",
  "Hormuz",
  "Co-Pilot",
  "AI",
  "EN",
]);

// QA-audited surfaces (2026-07-13 report): zero hardcoded UI strings.
const STRICT_FILES = new Set([
  "App.vue",
  "components/Sidebar.vue",
  "components/CompanyCard.vue",
  "components/SubmitLinkTool.vue",
  "components/UploadResearchTool.vue",
  "components/AddHormuzResearchTool.vue",
  "components/ActiveJobsRail.vue",
  "views/HomeView.vue",
  "views/NewsDeskView.vue",
  "views/ResearchView.vue",
  "components/HomeNewsDesk.vue",
  "components/HomeMarketPanel.vue",
  "views/MarketRadarView.vue",
  "components/QuoteChart.vue",
  "components/QuoteWorkspace.vue",
  "components/MarketCommandPalette.vue",
]);

// Ratchet baseline for the pre-existing backlog (counted 2026-07-14).
// Fixing a file? Lower (or delete) its entry. Never raise a number.
const BASELINE = {
  "components/CompanyDetail.vue": 16,
  "components/DeckSummaryModal.vue": 23,
  "components/FilePreviewModal.vue": 13,
  "components/HormuzConsole.vue": 16,
  "components/MemoAnalysisDashboard.vue": 16,
  "components/MemoStudioEditor.vue": 41,
  "components/ResearchUploads.vue": 3,
  "components/RunLedgerTable.vue": 12,
  "components/TraderView.vue": 1,
  "components/UnifiedDocumentsView.vue": 38,
  "components/memo/MemoBenchmarkPanel.vue": 12,
  "components/memo/MemoChartPlansPanel.vue": 10,
  "components/memo/MemoEvidenceMatrixPanel.vue": 8,
  "components/memo/MemoGeneratedMemoControlsPanel.vue": 2,
  "components/memo/MemoGraderPanel.vue": 0,
  "components/memo/MemoNarrativeHooksPanel.vue": 8,
  "components/memo/MemoReadinessPanel.vue": 7,
  "components/memo/MemoResearchTasksPanel.vue": 12,
  "components/memo/MemoRiskPriorityPanel.vue": 0,
  "components/memo/MemoSourceBriefPanel.vue": 9,
  "components/memo/MemoStudioBulletTree.vue": 5,
  "components/memo/MemoToolLauncherPanel.vue": 3,
  "components/memo/MemoToolboxPanel.vue": 31,
  "components/research-pages/ResearchPagesNav.vue": 1,
  "components/research/VCRatiosCard.vue": 28,
  "components/stock/StockAggregatePanel.vue": 34,
  "components/stock/StockEvaluationPanel.vue": 35,
  "components/stock/StockHypothesesPanel.vue": 26,
  "components/stock/StockResearchHomePanel.vue": 24,
  "components/stock/StockReviewQueuePanel.vue": 19,
  "components/stock/StockRunsPanel.vue": 27,
  "components/stock/StockSourceIntakePanel.vue": 17,
  "components/stock/StockStrategyMapPanel.vue": 24,
  "components/stock/StockTrackerRegistryPanel.vue": 15,
  "components/stock/StockWorkProductsPanel.vue": 25,
  "views/CompetitorDetailView.vue": 7,
  "views/EvidenceMatrixView.vue": 38,
  "views/HormuzLibraryView.vue": 10,
  "views/HypothesisLabView.vue": 48,
  "views/InnovationLabView.vue": 0,
  "views/MarketPulseView.vue": 40,
  "views/SettingsView.vue": 0,
  "views/SourceLibraryView.vue": 14,
  "views/StockResearchView.vue": 6,
  "views/TraderStatsView.vue": 1,
  "views/UserCenterView.vue": 11,
  "views/WeeklySummaryView.vue": 0,
};

function vueFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...vueFiles(p));
    else if (entry.name.endsWith(".vue")) out.push(p);
  }
  return out;
}

function templateBlock(src) {
  const start = src.indexOf("<template>");
  const end = src.lastIndexOf("</template>");
  if (start < 0 || end < 0) return "";
  return src.slice(start + "<template>".length, end);
}

function isAllowedSegment(seg) {
  if (ALLOW.has(seg)) return true;
  const words = seg.match(/[A-Za-z]{3,}/g) || [];
  // All-caps short tokens are tickers / file formats (AMD, PDF, DOCX…).
  const bad = words.filter((w) => !ALLOW.has(w) && !/^[A-Z0-9]{2,6}$/.test(w));
  return bad.length === 0;
}

// Walks the template character by character (a regex over `<[^>]*>` breaks
// on `>` inside quoted attribute values, e.g. arrow-function handlers).
// Collects violations from text nodes (with {{ }} interpolations removed)
// and from static placeholder/aria-label/title/alt attribute literals.
function scanTemplate(template) {
  const violations = [];
  let i = 0;
  let text = "";
  const flushText = () => {
    const cleaned = text.replace(/\{\{[\s\S]*?\}\}/g, " ");
    for (const raw of cleaned.split(/\n/)) {
      const seg = raw.trim();
      if (seg && !isAllowedSegment(seg)) {
        violations.push(`text: ${JSON.stringify(seg.slice(0, 80))}`);
      }
    }
    text = "";
  };
  while (i < template.length) {
    if (template[i] === "<") {
      flushText();
      if (template.startsWith("<!--", i)) {
        const end = template.indexOf("-->", i);
        i = end < 0 ? template.length : end + 3;
        continue;
      }
      let j = i + 1;
      let quote = null;
      let tag = "<";
      while (j < template.length) {
        const c = template[j];
        tag += c;
        if (quote) {
          if (c === quote) quote = null;
        } else if (c === '"' || c === "'") {
          quote = c;
        } else if (c === ">") {
          break;
        }
        j++;
      }
      for (const m of tag.matchAll(
        /(?<![:\w@-])(placeholder|aria-label|title|alt)="([^"]*)"/g,
      )) {
        const val = m[2].trim();
        if (val && !isAllowedSegment(val)) {
          violations.push(`${m[1]}=${JSON.stringify(val.slice(0, 60))}`);
        }
      }
      i = j + 1;
      continue;
    }
    text += template[i];
    i++;
  }
  flushText();
  return violations;
}

describe("no hardcoded UI strings in templates", () => {
  const results = new Map();
  for (const file of vueFiles(SRC_ROOT)) {
    const rel = path.relative(SRC_ROOT, file).split(path.sep).join("/");
    results.set(rel, scanTemplate(templateBlock(fs.readFileSync(file, "utf8"))));
  }

  it("QA-audited surfaces have zero bare strings", () => {
    const report = {};
    for (const rel of STRICT_FILES) {
      const v = results.get(rel) || [];
      if (v.length) report[rel] = v;
    }
    expect(report).toEqual({});
  });

  it("no file exceeds its i18n-backlog baseline (ratchet)", () => {
    const over = {};
    for (const [rel, v] of results) {
      if (STRICT_FILES.has(rel)) continue;
      const budget = BASELINE[rel] ?? 0;
      if (v.length > budget) {
        over[rel] = { budget, actual: v.length, violations: v };
      }
    }
    expect(over).toEqual({});
  });
});
