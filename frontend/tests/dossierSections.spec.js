import { describe, expect, it } from "vitest";
import {
  canonicalDossierQuery,
  copilotTabFromQuery,
  sameQuery,
  sectionFromQuery,
} from "../src/dossierSections.js";

describe("sectionFromQuery", () => {
  it("takes the desk's own ?section= first", () => {
    expect(sectionFromQuery({ section: "capTable" })).toBe("capTable");
    expect(sectionFromQuery({ section: "files", tab: "memo" })).toBe("files");
  });

  it("opens the section that now holds what each old ?tab= showed", () => {
    expect(sectionFromQuery({ tab: "overview" })).toBe("overview");
    // The Mac's "Open memo on Web" link.
    expect(sectionFromQuery({ tab: "memo", report: "rep-1" })).toBe("memos");
    expect(sectionFromQuery({ tab: "documents" })).toBe("files");
    expect(sectionFromQuery({ tab: "evidence" })).toBe("files");
    expect(sectionFromQuery({ tab: "decisions" })).toBe("decisions");
    // Memo Studio's analysis tools run and report in IC prep, as on the Mac.
    expect(sectionFromQuery({ tab: "analysis" })).toBe("decisions");
  });

  it("lets the thing asked for decide when no tab is named", () => {
    expect(sectionFromQuery({ previewFile: "f-1" })).toBe("files");
    expect(sectionFromQuery({ file: "deck-1" })).toBe("files");
    expect(sectionFromQuery({ report: "rep-1" })).toBe("memos");
    expect(sectionFromQuery({ memoSection: "risks_mitigations" })).toBe("memos");
  });

  it("names nothing for a tab the desk doesn't own", () => {
    expect(sectionFromQuery({})).toBe("");
    expect(sectionFromQuery(undefined)).toBe("");
    expect(sectionFromQuery({ tab: "console" })).toBe("");
    expect(sectionFromQuery({ section: "nope" })).toBe("");
  });
});

describe("canonicalDossierQuery", () => {
  it("drops the asks the desk has acted on and keeps the section", () => {
    expect(
      canonicalDossierQuery(
        { tab: "documents", previewFile: "f-1", previewPage: "4", files: "123" },
        "files",
      ),
    ).toEqual({ section: "files" });
    expect(
      canonicalDossierQuery(
        { tab: "memo", memoStage: "edit", memoSection: "s", memoBullet: "b", report: "r" },
        "memos",
      ),
    ).toEqual({ section: "memos" });
  });

  it("leaves keys the desk doesn't own, and Overview needs no section", () => {
    expect(canonicalDossierQuery({ tab: "console", company: "acme" }, "overview")).toEqual({
      tab: "console",
      company: "acme",
    });
    expect(canonicalDossierQuery({ section: "files" }, "overview")).toEqual({});
  });
});

describe("sameQuery", () => {
  it("compares values, not key order", () => {
    expect(sameQuery({ a: "1", b: "2" }, { b: "2", a: "1" })).toBe(true);
    expect(sameQuery({ a: "1" }, { a: "1", b: "2" })).toBe(false);
    expect(sameQuery({ a: "1" }, { b: "1" })).toBe(false);
    expect(sameQuery({}, undefined)).toBe(true);
  });
});

describe("copilotTabFromQuery", () => {
  it("names the desk's tab in the words Warren's prompts use", () => {
    expect(copilotTabFromQuery({ section: "memos" })).toBe("memo");
    expect(copilotTabFromQuery({ section: "files" })).toBe("documents");
    expect(copilotTabFromQuery({ section: "decisions" })).toBe("decisions");
    expect(copilotTabFromQuery({ tab: "memo" })).toBe("memo");
    expect(copilotTabFromQuery({ tab: "console" })).toBe("console");
    expect(copilotTabFromQuery({})).toBe("overview");
  });
});
