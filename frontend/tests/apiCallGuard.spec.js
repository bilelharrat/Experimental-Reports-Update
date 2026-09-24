// Every `api.<name>(` and `api.<ns>.<name>(` call in the app must resolve to
// a function api.js actually exports.
//
// The company desk once called api.getReports, api.getFollowedCompanies,
// api.followCompany and api.unfollowCompany — none of which exist — and
// swallowed the TypeErrors, so the desk always said no reports were on file.
// CI stayed green because each spec mocked the missing functions. This scan
// reads the source instead of trusting the mocks.

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { api } from "../src/api.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.join(__dirname, "..", "src");

function sourceFiles(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...sourceFiles(full));
    else if (/\.(vue|js)$/.test(entry.name)) out.push(full);
  }
  return out;
}

// Comments name things in prose ("a literal from api.REPORT_TYPES"); only
// code counts. `://` in URLs is not a comment.
function stripComments(source) {
  return source
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1");
}

const CALL = /(?<![\w$./])api\.([A-Za-z_$][\w$]*)(?:\.([A-Za-z_$][\w$]*))?\s*\(/g;

function unresolvedCalls(source) {
  const missing = [];
  for (const match of stripComments(source).matchAll(CALL)) {
    const [, first, second] = match;
    let value = api[first];
    if (second !== undefined) value = value?.[second];
    if (typeof value !== "function") missing.push(second ? `api.${first}.${second}` : `api.${first}`);
  }
  return missing;
}

describe("api call guard", () => {
  it("finds a missing export and ignores prose in comments", () => {
    expect(
      unresolvedCalls(`
        // api.notInComments(1)
        /* api.norInBlocks() */
        const rows = await api.listReports();
        const run = await api.memoAnalysis.cancelTask("co", "task");
        const gone = await api.getReports({ company_id: "x" });
        const alsoGone = api.memoAnalysis.nope();
        const url = "https://example.com/api.fake(";
      `),
    ).toEqual(["api.getReports", "api.memoAnalysis.nope"]);
  });

  it("every api.<name>( call in src resolves to a function api.js exports", () => {
    const missing = [];
    for (const file of sourceFiles(SRC_ROOT)) {
      const rel = path.relative(SRC_ROOT, file).split(path.sep).join("/");
      if (rel === "api.js") continue;
      for (const call of unresolvedCalls(fs.readFileSync(file, "utf8"))) {
        missing.push(`${rel}: ${call}`);
      }
    }
    expect(missing).toEqual([]);
  });
});
