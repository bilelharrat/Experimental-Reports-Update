import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";

const docx = vi.hoisted(() => ({ renderAsync: vi.fn(() => Promise.resolve()) }));
vi.mock("docx-preview", () => docx);

const mockApi = vi.hoisted(() => ({
  listReports: vi.fn(),
}));

vi.mock("../src/api.js", () => ({
  api: mockApi,
  withApiToken: (path) => path,
}));

import ReportsView from "../src/views/ReportsView.vue";

const sampleReports = [
  {
    id: "rep-1",
    company_id: "acme",
    company_name: "Acme Inc.",
    kind: "investment_memo_late_stage",
    report_type: "investment_memo_late_stage",
    title: "Acme Inc. — Investment Memo (Late-Stage)",
    status: "complete",
    created_at: "2026-04-10T14:30:00Z",
    download_urls: {
      en: "/api/reports/rep-1/en.docx",
      zh: "/api/reports/rep-1/zh.docx",
    },
    memo_quality_lint: { overall_score: 92 },
  },
  {
    id: "rep-2",
    company_id: "zeta",
    company_name: "Zeta AI",
    kind: "buffett_memo",
    report_type: "buffett_memo",
    title: "Zeta AI — Buffett Memo",
    status: "complete",
    created_at: "2026-04-11T09:15:00Z",
    download_urls: {
      en: "/api/reports/rep-2/en.docx",
    },
    memo_quality_lint: { overall_score: 88 },
  },
  {
    id: "rep-3",
    company_id: "acme",
    company_name: "Acme Inc.",
    kind: "hormuz_appendix",
    report_type: "hormuz_appendix",
    title: "Acme Inc. — Hormuz Appendix",
    status: "running",
    created_at: "2026-04-12T11:00:00Z",
    download_urls: {},
  },
];

async function createTestRouter(initialQuery = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/reports", name: "reports", component: ReportsView },
      { path: "/:companyId", name: "research", component: { template: "<div />" } },
    ],
  });
  await router.push({ path: "/reports", query: initialQuery });
  await router.isReady();
  return router;
}

describe("ReportsView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        text: () => Promise.resolve(""),
        arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)),
      }),
    ));
    mockApi.listReports.mockResolvedValue([...sampleReports]);
  });

  it("loads and displays report cards and summary stats", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    expect(mockApi.listReports).toHaveBeenCalled();
    expect(wrapper.text()).toContain("Research Reports");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).toContain("Zeta AI");
    expect(wrapper.text()).toContain("3 reports");
  });

  it("filters reports by search query", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    const searchInput = wrapper.find('input[type="text"]');
    await searchInput.setValue("Zeta");
    await flushPromises();

    const articles = wrapper.findAll("article");
    expect(articles.length).toBe(1);
    expect(articles[0].text()).toContain("Zeta AI");
  });

  it("filters reports by company selector", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    const companySelect = wrapper.findAll("select")[0];
    await companySelect.setValue("zeta");
    await flushPromises();

    const articles = wrapper.findAll("article");
    expect(articles.length).toBe(1);
    expect(articles[0].text()).toContain("Zeta AI");
  });

  it("filters reports by status selector", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    const selects = wrapper.findAll("select");
    const statusSelect = selects[selects.length - 1];
    await statusSelect.setValue("running");
    await flushPromises();

    const articles = wrapper.findAll("article");
    expect(articles.length).toBe(1);
    expect(articles[0].text()).toContain("Acme Inc. — Hormuz Appendix");
  });

  it("selects a report and loads into document viewer window", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    // Initially selects first ready report (rep-1)
    expect(wrapper.html()).toContain("rep-1");

    // Click rep-2 article card
    const cards = wrapper.findAll("article");
    await cards[1].trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.query.id).toBe("rep-2");
    expect(wrapper.text()).toContain("Zeta AI — Buffett Memo");
  });

  it("supports deep linking via query parameter ?id=rep-2", async () => {
    const router = await createTestRouter({ id: "rep-2" });
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    expect(wrapper.text()).toContain("Zeta AI — Buffett Memo");
  });

  it("renders Monogram for each report with correct company info", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: {
        plugins: [router],
        stubs: { DocumentViewerDrawer: true },
      },
    });
    await flushPromises();

    const monograms = wrapper.findAllComponents({ name: "Monogram" });
    expect(monograms.length).toBeGreaterThanOrEqual(sampleReports.length);
    const acmeMonogram = monograms.find(
      (m) => m.props("company")?.id === "acme"
    );
    expect(acmeMonogram).toBeTruthy();
    expect(acmeMonogram.props("company").name).toBe("Acme Inc.");
  });

  it("collapses the reports list to a rail and remembers it", async () => {
    const router = await createTestRouter();
    const wrapper = mount(ReportsView, {
      global: { plugins: [router], stubs: { DocumentViewerDrawer: true } },
    });
    await flushPromises();

    const aside = wrapper.find("aside");
    expect(aside.classes()).toContain("w-80");
    expect(wrapper.findAll("article").length).toBeGreaterThan(0);

    await wrapper.find('[data-testid="reports-list-collapse"]').trigger("click");
    await flushPromises();

    // Collapsed: a 44px rail, no rows, and a control to bring them back.
    expect(wrapper.find("aside").classes()).toContain("w-[44px]");
    expect(wrapper.findAll("article").length).toBe(0);
    const rail = wrapper.find('[data-testid="reports-list-expand"]');
    expect(rail.exists()).toBe(true);
    // The rail still says how many reports are hidden behind it.
    expect(rail.text()).toContain("reports");
    expect(window.localStorage.getItem("bsh.reportsListCollapsed")).toBe("1");

    await rail.trigger("click");
    await flushPromises();
    expect(wrapper.find("aside").classes()).toContain("w-80");
    expect(wrapper.findAll("article").length).toBeGreaterThan(0);
    expect(window.localStorage.getItem("bsh.reportsListCollapsed")).toBe("0");
  });
});
