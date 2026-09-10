import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  listCompanyDocuments: vi.fn(),
  updateDocumentMetadata: vi.fn(),
  setDocumentUseInReport: vi.fn(),
  uploadFile: vi.fn(),
  uploadResearchFile: vi.fn(),
  deleteFile: vi.fn(),
  deleteResearchFile: vi.fn(),
  fileUrl: vi.fn((companyId, fileId) => `/files/${companyId}/${fileId}`),
  researchFileUrl: vi.fn((companyId, fileId) => `/research/${companyId}/${fileId}`),
  generateResearchFileSummary: vi.fn(),
  analyzeResearchFile: vi.fn(),
  cancelResearchFileAnalysis: vi.fn(),
  listActiveJobs: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: m,
  withApiToken: (path) => path,
}));

vi.mock("../src/state.js", () => ({
  appLanguage: { value: "en" },
  openSummary: vi.fn(),
}));

import UnifiedDocumentsView from "../src/components/UnifiedDocumentsView.vue";

function documentsPayload() {
  const rows = [
    {
      id: "document_library:file-1",
      backend: "document_library",
      backend_label: "Document Library",
      record_id: "file-1",
      title: "Customer deck",
      filename: "customer-deck.pdf",
      kind: "pdf",
      type_badge: "PDF",
      category: "company_materials",
      category_label: "Company Materials",
      source_class: "unknown/pending",
      source_class_label: "unknown/pending",
      language: "en",
      status: "ready",
      captured_at: "2026-07-03T12:00:00Z",
      provenance: {
        title: "Customer deck",
        origin: "Document Library",
        file: "file-1__customer-deck.pdf",
        source_class: "unknown/pending",
      },
      source_refs: [{ title: "Customer deck", source_class: "unknown/pending" }],
      source_traces: [],
      source_trace_count: 0,
      editable_metadata: true,
      use_in_report: false,
      use_in_report_locked: false,
      record: { id: "file-1", filename: "customer-deck.pdf", kind: "pdf", size_bytes: 2048 },
    },
    {
      id: "background_documents:bg-1",
      backend: "background_documents",
      backend_label: "Background Documents",
      record_id: "bg-1",
      title: "ZaiNar market report",
      filename: "market-report.txt",
      kind: "text",
      type_badge: "TXT",
      category: "external_reports",
      category_label: "External Reports",
      source_class: "third-party market data",
      source_class_label: "third-party market data",
      language: "en",
      status: "summarized",
      captured_at: "2026-07-02T12:00:00Z",
      provenance: {
        title: "ZaiNar market report",
        origin: "PitchBook",
        file: "bg-1__market-report.txt",
        source_class: "third-party market data",
      },
      source_refs: [{ title: "Market model", source_class: "third-party market data" }],
      source_traces: [
        {
          locator: "Page 1",
          excerpt: "ARR reached $24M in the diligence model.",
          confidence: "medium",
        },
      ],
      source_trace_count: 1,
      editable_metadata: true,
      use_in_report: true,
      use_in_report_locked: true,
      quick_summary: { summary_en: "Market context summary." },
      record: { id: "bg-1", filename: "market-report.txt", kind: "text", size_bytes: 512 },
    },
    {
      id: "generated_report:report-1",
      backend: "generated_report",
      backend_label: "Generated Reports",
      record_id: "report-1",
      title: "Investment Memo (Late-Stage)",
      filename: "memo.memo",
      kind: "memo",
      type_badge: "MEMO",
      category: "memos",
      category_label: "Memos",
      source_class: "generated memo",
      source_class_label: "generated memo",
      language: "en",
      status: "complete",
      captured_at: "2026-07-01T12:00:00Z",
      provenance: { origin: "Generated memo", source_class: "generated memo" },
      source_refs: [{ title: "Generated memo", source_class: "generated memo" }],
      source_traces: [],
      source_trace_count: 0,
      editable_metadata: false,
      report: { id: "report-1", report_type: "Investment Memo (Late-Stage)" },
      download_urls: { en: "/api/reports/report-1/download?language=en" },
      record: { id: "report-1" },
    },
  ];
  return {
    company_id: "zainar-inc",
    rows,
    categories: [
      { id: "memos", label: "Memos" },
      { id: "company_materials", label: "Company Materials" },
      { id: "legal_corporate", label: "Legal and Corporate" },
      { id: "financial", label: "Financial" },
      { id: "external_reports", label: "External Reports" },
      { id: "internal_notes_sources", label: "Internal Notes and Sources" },
    ],
    source_classes: [
      "company material",
      "public filing",
      "third-party market data",
      "BSH primary diligence",
      "internal note",
      "generated memo",
      "unknown/pending",
    ],
    filters: {
      languages: ["en"],
      statuses: ["complete", "ready", "summarized"],
    },
    groups: [
      { id: "memos", label: "Memos", count: 1, rows: [rows[2]] },
      { id: "company_materials", label: "Company Materials", count: 1, rows: [rows[0]] },
      { id: "legal_corporate", label: "Legal and Corporate", count: 0, rows: [] },
      { id: "financial", label: "Financial", count: 0, rows: [] },
      { id: "external_reports", label: "External Reports", count: 1, rows: [rows[1]] },
      { id: "internal_notes_sources", label: "Internal Notes and Sources", count: 0, rows: [] },
    ],
    unresolved_intake_count: 1,
  };
}

describe("UnifiedDocumentsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    m.listCompanyDocuments.mockResolvedValue(documentsPayload());
    m.updateDocumentMetadata.mockResolvedValue({});
    m.listActiveJobs.mockResolvedValue([]);
    m.analyzeResearchFile.mockResolvedValue({ kind: "research_analysis" });
    vi.stubGlobal("confirm", vi.fn(() => true));
  });

  it("renders grouped documents, filters source classes, and opens source traces", async () => {
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
      global: {
        stubs: {
          Teleport: true,
        },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Generated Memos");
    expect(wrapper.text()).toContain("Uploaded Documents");
    expect(wrapper.text()).toContain("Source pending");
    expect(wrapper.text()).toContain("third-party market data");
    expect(wrapper.text()).toContain("Use in report");
    expect(wrapper.text()).toContain("Add file");
    expect(wrapper.text()).toContain("Filter");
    expect(wrapper.text()).not.toContain("Document Library upload");
    expect(wrapper.text()).not.toContain("Memo inputs");
    expect(wrapper.text()).not.toContain("1 awaiting review");

    const filterToggle = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Filter"));
    await filterToggle.trigger("click");
    expect(wrapper.text()).toContain("1 awaiting review");

    const sourceClassFilter = wrapper.findAll("select")[1];
    await sourceClassFilter.setValue("third-party market data");
    expect(wrapper.text()).toContain("ZaiNar market report");
    expect(wrapper.text()).not.toContain("Customer deck");

    const traceButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Source trace"));
    await traceButton.trigger("click");
    expect(wrapper.text()).toContain("Source trace");
    expect(wrapper.text()).toContain("PitchBook");
    expect(wrapper.text()).toContain("ARR reached $24M");
  });

  it("hides per-row metadata dropdowns and research-file summarize", async () => {
    // The category/source-class selects confused users and gate nothing
    // for report generation; Summarize is redundant next to Analyze for
    // research files (the deck-library summarize modal stays).
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
    });
    await flushPromises();

    const rowSourceSelect = wrapper
      .findAll("select")
      .find((select) => select.element.value === "unknown/pending");
    expect(rowSourceSelect).toBeUndefined();

    const summarizeButtons = wrapper
      .findAll("button")
      .filter((b) => b.text().includes("Summarize"));
    // bg-1 (background document) offers Analyze instead; the pdf library
    // row keeps its deck-summary button.
    expect(summarizeButtons.length).toBe(1);
    expect(
      wrapper.findAll("button").filter((b) => b.text() === "Analyze").length,
    ).toBe(1);
  });

  it("moves a library file into the report set", async () => {
    m.setDocumentUseInReport.mockResolvedValue({});
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
    });
    await flushPromises();

    const toggle = wrapper.find('input[aria-label="Use in report"]');
    expect(toggle.exists()).toBe(true);
    await toggle.setValue(true);
    await flushPromises();

    expect(m.setDocumentUseInReport).toHaveBeenCalledWith(
      "zainar-inc",
      "document_library",
      "file-1",
      true,
    );
  });

  it("opens the slide-in viewer for generated memos", async () => {
    m.listCompanyDocuments.mockResolvedValue(documentsPayload());
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        status: 200,
        text: async () => "",
        arrayBuffer: async () => new ArrayBuffer(8),
      })),
    );
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "generalist" },
    });
    await flushPromises();

    const viewButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "View");
    expect(viewButton).toBeTruthy();
    await viewButton.trigger("click");
    await vi.dynamicImportSettled();
    await flushPromises();

    // The drawer is open on the memo's EN docx (teleported to body).
    expect(document.querySelector("[role='dialog']")).toBeTruthy();
    expect(fetch).toHaveBeenCalledWith(
      "/api/reports/report-1/download?language=en",
    );
    wrapper.unmount();
    expect(document.querySelector("[role='dialog']")).toBeFalsy();
  });

  function bgRow(recordId, filename, extra = {}) {
    return {
      id: `background_documents:${recordId}`,
      backend: "background_documents",
      backend_label: "Background Documents",
      record_id: recordId,
      title: filename,
      filename,
      kind: "text",
      type_badge: "TXT",
      category: "external_reports",
      category_label: "External Reports",
      source_class: "unknown/pending",
      source_class_label: "unknown/pending",
      language: "en",
      status: "ready",
      captured_at: "2026-07-02T12:00:00Z",
      provenance: { title: filename, file: `${recordId}__${filename}` },
      source_refs: [],
      source_traces: [],
      source_trace_count: 0,
      editable_metadata: true,
      use_in_report: true,
      use_in_report_locked: true,
      record: { id: recordId, filename, kind: "text", size_bytes: 64 },
      folder_id: null,
      folder_name: null,
      analysis_of: null,
      analysis_file_id: null,
      ...extra,
    };
  }

  function folderPayload() {
    const rows = [
      bgRow("m1", "note1.md", { folder_id: "fld123456789", folder_name: "notes" }),
      bgRow("m2", "note2.md", { folder_id: "fld123456789", folder_name: "notes" }),
      bgRow("solo", "solo-report.md"),
      bgRow("an1", "notes_analysis.md", { analysis_of: "fld123456789" }),
    ];
    return {
      categories: [],
      source_classes: [],
      filters: { languages: [], statuses: [] },
      groups: [{ id: "external_reports", label: "External Reports", count: rows.length, rows }],
      unresolved_intake_count: 0,
    };
  }

  it("groups folder members under a folded header with fold/unfold", async () => {
    m.listCompanyDocuments.mockResolvedValue(folderPayload());
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("notes");
    expect(wrapper.text()).toContain("2 files");
    // Folded by default: members hidden, standalone row visible.
    expect(wrapper.text()).not.toContain("note1.md");
    expect(wrapper.text()).toContain("solo-report.md");
    // The folder analysis renders as a child row.
    expect(wrapper.text()).toContain("notes_analysis.md");

    const toggle = wrapper
      .findAll("button")
      .find((b) => b.text().includes("notes") && b.text().includes("2 files"));
    await toggle.trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("note1.md");
    expect(wrapper.text()).toContain("note2.md");
  });

  it("analyze posts for files, folders reanalyze, members get no buttons", async () => {
    m.listCompanyDocuments.mockResolvedValue(folderPayload());
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    // The folder already has an analysis -> Reanalyze; the standalone
    // file has none -> Analyze.
    const reanalyze = wrapper.findAll("button").filter((b) => b.text() === "Reanalyze");
    const analyze = wrapper.findAll("button").filter((b) => b.text() === "Analyze");
    expect(reanalyze.length).toBe(1);
    expect(analyze.length).toBe(1);

    await analyze.at(0).trigger("click");
    await flushPromises();
    expect(m.analyzeResearchFile).toHaveBeenCalledWith("zainar-inc", "solo");

    await reanalyze.at(0).trigger("click");
    await flushPromises();
    expect(m.analyzeResearchFile).toHaveBeenCalledWith(
      "zainar-inc",
      "fld123456789",
    );

    // Unfold: member rows carry no Analyze/Summarize buttons.
    const toggle = wrapper
      .findAll("button")
      .find((b) => b.text().includes("2 files"));
    await toggle.trigger("click");
    await flushPromises();
    const memberRowText = wrapper.text();
    expect(memberRowText).toContain("note1.md");
    // Only the original two analysis buttons exist (folder + solo).
    const buttons = wrapper
      .findAll("button")
      .filter((b) => ["Analyze", "Reanalyze"].includes(b.text()));
    expect(buttons.length).toBe(2);
  });

  it("uploads a picked folder through the folder_id handshake", async () => {
    m.listCompanyDocuments.mockResolvedValue(folderPayload());
    m.uploadResearchFile
      .mockResolvedValueOnce({ id: "n1", folder_id: "fldabcabcabc" })
      .mockResolvedValueOnce({ id: "n2", folder_id: "fldabcabcabc" });
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    const input = wrapper.find("[data-testid='folder-input']");
    expect(input.attributes("webkitdirectory")).toBeDefined();

    const fileA = new File(["a"], "a.md");
    Object.defineProperty(fileA, "webkitRelativePath", { value: "meeting/a.md" });
    const fileB = new File(["b"], "b.md");
    Object.defineProperty(fileB, "webkitRelativePath", { value: "meeting/b.md" });
    const junk = new File(["x"], ".DS_Store");

    const vm = wrapper.vm;
    await vm.uploadFolder([fileA, fileB, junk]);

    expect(m.uploadResearchFile).toHaveBeenCalledTimes(2);
    expect(m.uploadResearchFile.mock.calls[0][3]).toEqual({
      folder_name: "meeting",
    });
    expect(m.uploadResearchFile.mock.calls[1][3]).toEqual({
      folder_id: "fldabcabcabc",
      folder_name: "meeting",
    });
  });

  it("flags analysis failure only after the rail has seen the job leave", async () => {
    m.listCompanyDocuments.mockResolvedValue(folderPayload());
    const { activeJobs } = await import("../src/activeJobs.js");
    activeJobs.value = [];
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
      global: { stubs: { Teleport: true } },
    });
    await flushPromises();

    const analyze = wrapper.findAll("button").find((b) => b.text() === "Analyze");
    await analyze.trigger("click");
    await flushPromises();

    // Rail tick WITHOUT the job (3s poll on a 3s cache lags the launch):
    // this must NOT read as "finished and failed".
    activeJobs.value = [];
    await flushPromises();
    expect(wrapper.text()).not.toContain("did not finish");
    // The button stays busy while the launch is pending.
    expect(analyze.attributes("disabled")).toBeDefined();

    // The rail shows the job...
    activeJobs.value = [
      { kind: "research_analysis", company_id: "zainar-inc", file_id: "solo" },
    ];
    await flushPromises();

    // ...then it leaves with no analysis row -> genuine failure banner.
    activeJobs.value = [];
    await flushPromises();
    await flushPromises();
    expect(wrapper.text()).toContain("did not finish");
    activeJobs.value = [];
  });
});
