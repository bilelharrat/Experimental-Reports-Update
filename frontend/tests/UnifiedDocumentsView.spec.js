import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const m = vi.hoisted(() => ({
  listCompanyDocuments: vi.fn(),
  updateDocumentMetadata: vi.fn(),
  uploadFile: vi.fn(),
  uploadResearchFile: vi.fn(),
  deleteFile: vi.fn(),
  deleteResearchFile: vi.fn(),
  fileUrl: vi.fn((companyId, fileId) => `/files/${companyId}/${fileId}`),
  researchFileUrl: vi.fn((companyId, fileId) => `/research/${companyId}/${fileId}`),
  generateResearchFileSummary: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: m,
  withApiToken: (path) => path,
}));

vi.mock("../src/state.js", () => ({
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

    expect(wrapper.text()).toContain("Memos");
    expect(wrapper.text()).toContain("Company Materials");
    expect(wrapper.text()).toContain("External Reports");
    expect(wrapper.text()).toContain("unknown/pending");
    expect(wrapper.text()).toContain("third-party market data");
    expect(wrapper.text()).toContain("1 unresolved intake");

    const sourceClassFilter = wrapper.findAll("select")[1];
    await sourceClassFilter.setValue("third-party market data");
    expect(wrapper.text()).toContain("ZaiNar market report");
    expect(wrapper.text()).not.toContain("Customer deck");

    const traceButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Source trace"));
    await traceButton.trigger("click");
    expect(wrapper.text()).toContain("Source Trace");
    expect(wrapper.text()).toContain("PitchBook");
    expect(wrapper.text()).toContain("ARR reached $24M");
  });

  it("persists category/source-class edits through the document metadata API", async () => {
    const wrapper = mount(UnifiedDocumentsView, {
      props: { companyId: "zainar-inc" },
    });
    await flushPromises();

    const rowSourceSelect = wrapper
      .findAll("select")
      .find((select) => select.element.value === "unknown/pending");
    await rowSourceSelect.setValue("company material");
    await flushPromises();

    expect(m.updateDocumentMetadata).toHaveBeenCalledWith(
      "zainar-inc",
      "document_library",
      "file-1",
      { source_class: "company material" },
    );
  });
});
