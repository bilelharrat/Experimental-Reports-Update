// Coverage check: every `console.*` and `research.tab_*` key referenced
// by the new components must exist in BOTH the en and zh dictionaries
// (i18n.js falls back silently to English if a zh key is missing, which
// is exactly the regression this test catches).

import { describe, expect, it } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function loadDicts() {
  // The i18n module exports a `t()` function but not the raw dictionaries,
  // so we parse the source to inspect both language blocks. Cheaper than
  // running a Vue reactive runtime here.
  const src = fs.readFileSync(
    path.join(__dirname, "..", "src", "i18n.js"),
    "utf8",
  );
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

describe("i18n coverage", () => {
  const { en, zh } = loadDicts();

  it("every console.* en key has a zh counterpart", () => {
    const missing = [...en]
      .filter((k) => k.startsWith("console."))
      .filter((k) => !zh.has(k));
    expect(missing).toEqual([]);
  });

  it("every research.tab_* en key has a zh counterpart", () => {
    const missing = [...en]
      .filter((k) => k.startsWith("research.tab_"))
      .filter((k) => !zh.has(k));
    expect(missing).toEqual([]);
  });

  it("there are at least 20 console.* keys defined", () => {
    const enConsole = [...en].filter((k) => k.startsWith("console."));
    expect(enConsole.length).toBeGreaterThanOrEqual(20);
  });
});
