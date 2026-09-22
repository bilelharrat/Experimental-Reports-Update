// Which tab of the Research Desk dossier a company URL opens.
//
// `?section=` is the desk's own word for its tab (the web twin of the Mac's
// bsh.launchDossierSection launch arg), and the desk writes it back as the
// tab changes. The company page before the desk used `?tab=`, and that
// vocabulary is still out there: the Mac's "Open memo on Web" sends
// `?tab=memo&report=<id>`, and old links and bookmarks carry the rest. Each
// old tab opens the section that now holds what it used to show.

export const DOSSIER_SECTIONS = [
  "overview",
  "memos",
  "files",
  "decisions",
  "team",
  "pipeline",
  "capTable",
  "comps",
  "ratios",
  "all",
];

export const SECTION_LABEL_KEYS = {
  overview: "research_desk.section_overview",
  memos: "research_desk.section_memo_studio",
  files: "research_desk.section_files",
  decisions: "research_desk.section_decisions",
  team: "research_desk.section_team",
  pipeline: "research_desk.section_pipeline",
  capTable: "research_desk.section_cap_table",
  comps: "research_desk.section_comps",
  ratios: "research_desk.section_ratios",
  all: "research_desk.section_all",
};

const LEGACY_TABS = {
  overview: "overview",
  memo: "memos",
  documents: "files",
  evidence: "files",
  decisions: "decisions",
  // Memo Studio's analysis tools and risk research run and report in IC
  // prep, which sits under Decisions here as it does on the Mac.
  analysis: "decisions",
};

// Asks the desk acts on once and then drops from the URL, so a reload or
// the same link followed again does not replay a stale one:
//   files         the toolbar's Add finished an upload: reload Files
//   report        a memo run just launched: reload the memo list
//   previewFile   Warren cited a file (at previewPage): open it
//   file          a deck summary job finished: open that summary
//   memoSection   Warren edited a point (memoBullet) or named a section
// memoStage and evidence named sub-views the desk does not have.
const ONE_SHOT_KEYS = [
  "files",
  "report",
  "previewFile",
  "previewPage",
  "file",
  "memoSection",
  "memoBullet",
  "memoStage",
  "evidence",
];

export function queryText(value) {
  const first = Array.isArray(value) ? value[0] : value;
  return first == null ? "" : String(first);
}

/** The section a company URL's query names, or "" when it names none. */
export function sectionFromQuery(query) {
  const q = query || {};
  const section = queryText(q.section);
  if (DOSSIER_SECTIONS.includes(section)) return section;
  const legacy = LEGACY_TABS[queryText(q.tab)];
  if (legacy) return legacy;
  // Nothing names a tab, so the thing asked for decides.
  if (q.previewFile || q.file || q.files) return "files";
  if (q.memoSection || q.memoBullet || q.report) return "memos";
  return "";
}

/** The query once the desk has acted on it: its own keys out, `section` in. */
export function canonicalDossierQuery(query, section) {
  const next = {};
  for (const [key, value] of Object.entries(query || {})) {
    if (key === "section" || ONE_SHOT_KEYS.includes(key)) continue;
    if (key === "tab" && LEGACY_TABS[queryText(value)]) continue;
    next[key] = value;
  }
  if (section && section !== "overview") next.section = section;
  return next;
}

export function sameQuery(a, b) {
  const left = a || {};
  const right = b || {};
  const keys = Object.keys(left);
  if (keys.length !== Object.keys(right).length) return false;
  return keys.every(
    (key) =>
      Object.prototype.hasOwnProperty.call(right, key) &&
      String(left[key]) === String(right[key]),
  );
}

/**
 * The tab Warren's context names. His prompts and the Mac call the memo and
 * files tabs `memo` and `documents`; a tab the desk doesn't own (`console`)
 * passes through as it always did.
 */
export function copilotTabFromQuery(query) {
  const section = sectionFromQuery(query);
  if (section === "memos") return "memo";
  if (section === "files") return "documents";
  return section || queryText(query?.tab) || "overview";
}
