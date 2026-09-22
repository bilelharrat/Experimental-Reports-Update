import { describe, expect, it, beforeEach, afterEach, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    api: {
      ...actual.api,
      listReports: vi.fn(),
      quotesNews: vi.fn(),
    },
  };
});

import { api } from "../src/api.js";
import Sidebar from "../src/components/Sidebar.vue";
import { setSidebarCollapsed } from "../src/state.js";

// Clicking a company in the sidebar opens it in place, like a folder: its
// Reports, News, Research Desk and, when listed, Market, one row each, with
// how many reports and headlines the first two hold.

const now = new Date().toISOString();

const companies = [
  { id: "intc", name: "Intel Corp", ticker: "INTC", status: "public" },
  { id: "zeta", name: "Zeta Labs", status: "private" },
];

const reports = [
  { id: "r1", company_id: "intc", status: "complete", created_at: "2026-08-01T00:00:00Z" },
  { id: "r2", company_id: "intc", status: "running", created_at: "2026-09-01T00:00:00Z" },
  { id: "r3", company_id: "someone-else", status: "complete", created_at: "2026-09-02T00:00:00Z" },
];

const view = { template: "<div />" };
const NAMES = [
  "reports",
  "research-desk",
  "news-desk",
  "weekly-summary",
  "market-radar",
  "tracking",
  "settings",
  "login",
];

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: view },
      ...NAMES.map((name) => ({ path: `/${name}`, name, component: view })),
      { path: "/:companyId", name: "research", component: view },
    ],
  });
}

let wrapper;

async function mountSidebar(start = "/") {
  const router = makeRouter();
  await router.push(start);
  await router.isReady();
  wrapper = mount(Sidebar, {
    props: { loading: false, companies },
    global: {
      plugins: [router],
      provide: {
        workspaceNews: ref([
          {
            id: "n1",
            kind: "news",
            title: "Intel wins a foundry customer",
            source: "Reuters",
            captured_at: now,
          },
        ]),
        workspaceResearch: ref([]),
        workspaceLiveNews: ref([]),
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { router };
}

function companyRow(id) {
  return wrapper.findAll("a.company-source-row").find((a) => a.attributes("href") === `/${id}`);
}

const pages = () => wrapper.find('[data-testid="company-pages"]');
const page = (kind) => wrapper.find(`[data-testid="company-page-${kind}"]`);
const count = (kind) => page(kind).find('[data-testid="company-page-count"]');

async function toggle(id) {
  await companyRow(id).trigger("click", { button: 0 });
  await flushPromises();
}

describe("Sidebar company pages", () => {
  beforeEach(() => {
    setSidebarCollapsed(false);
    api.listReports.mockResolvedValue(reports);
    api.quotesNews.mockResolvedValue({
      items: [
        {
          id: "live-1",
          kind: "live_news",
          ticker: "INTC",
          title: "Intel shares jump on AI demand",
          source: "Yahoo Finance",
          published_at: now,
        },
      ],
    });
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    vi.clearAllMocks();
    document.body.innerHTML = "";
  });

  it("opens a company in place, like a folder, instead of navigating", async () => {
    const { router } = await mountSidebar();
    expect(pages().exists()).toBe(false);
    expect(companyRow("intc").attributes("aria-expanded")).toBe("false");

    await toggle("intc");

    expect(router.currentRoute.value.name).toBe("home");
    expect(companyRow("intc").attributes("aria-expanded")).toBe("true");
    expect(companyRow("intc").attributes("aria-controls")).toBe(pages().attributes("id"));
    const rows = pages().findAll("a.company-page-row");
    expect(rows.map((row) => row.text().replace(/\d+/g, "").trim())).toEqual([
      "Reports",
      "News",
      "Research Desk",
      "Market",
    ]);
    expect(rows.map((row) => row.attributes("href"))).toEqual([
      "/reports?company=intc",
      "/news-desk?company=intc",
      "/intc",
      "/market-radar?ticker=INTC",
    ]);
  });

  it("a company with no listing has no Market row", async () => {
    await mountSidebar();
    await toggle("zeta");

    const kinds = pages().findAll("a.company-page-row").map((row) => row.attributes("data-kind"));
    expect(kinds).toEqual(["reports", "news", "desk"]);
  });

  it("the Market desk on a company's stock marks its Market row", async () => {
    const { router } = await mountSidebar();
    await router.push({ name: "market-radar", query: { ticker: "intc" } });
    await flushPromises();

    expect(pages().attributes("id")).toBe("company-pages-intc");
    expect(page("market").attributes("aria-current")).toBe("page");
    const deskRow = wrapper.get('[data-tour="nav-market"]');
    expect(deskRow.classes()).not.toContain("router-link-exact-active");

    // A symbol that isn't a workspace company: the Market desk row holds it,
    // and the open company stays open.
    await router.push({ name: "market-radar", query: { ticker: "SPY" } });
    await flushPromises();
    expect(deskRow.classes()).toContain("router-link-exact-active");
    expect(page("market").attributes("aria-current")).toBeUndefined();
    expect(pages().attributes("id")).toBe("company-pages-intc");
  });

  it("counts the company's reports and its headlines, its own ticker's included", async () => {
    await mountSidebar();
    await toggle("intc");

    expect(api.listReports).toHaveBeenCalled();
    expect(api.quotesNews).toHaveBeenCalledWith({ tickers: ["INTC"], limit: 30 });
    expect(count("reports").text()).toBe("2");
    expect(count("news").text()).toBe("2");
    expect(count("desk").exists()).toBe(false);
    expect(count("market").exists()).toBe(false);
  });

  it("holds a count back until its numbers are in, rather than showing 0", async () => {
    api.listReports.mockReturnValue(new Promise(() => {}));
    api.quotesNews.mockReturnValue(new Promise(() => {}));
    await mountSidebar();
    await toggle("intc");

    expect(page("reports").exists()).toBe(true);
    expect(count("reports").exists()).toBe(false);
    expect(count("news").exists()).toBe(false);
  });

  it("counts a private company's headlines from the feed, without asking the wire", async () => {
    await mountSidebar();
    await toggle("zeta");

    expect(api.quotesNews).not.toHaveBeenCalled();
    expect(count("reports").text()).toBe("0");
    expect(count("news").text()).toBe("0");
  });

  it("marks the open company, row and pages together, for the welcome tour", async () => {
    await mountSidebar();
    expect(wrapper.find('[data-tour="company-folder"]').exists()).toBe(false);

    await toggle("intc");
    const folder = wrapper.findAll('[data-tour="company-folder"]');
    expect(folder).toHaveLength(1);
    expect(folder[0].find('a.company-source-row[href="/intc"]').exists()).toBe(true);
    expect(folder[0].find('[data-testid="company-pages"]').exists()).toBe(true);
  });

  it("closes on a second click, and one company is open at a time", async () => {
    await mountSidebar();
    await toggle("intc");
    await toggle("zeta");

    expect(wrapper.findAll('[data-testid="company-pages"]')).toHaveLength(1);
    expect(pages().attributes("id")).toBe("company-pages-zeta");
    expect(companyRow("intc").attributes("aria-expanded")).toBe("false");

    await toggle("zeta");
    expect(pages().exists()).toBe(false);
  });

  it("a page row goes there and holds the one selection", async () => {
    const { router } = await mountSidebar();
    await toggle("intc");
    await page("reports").trigger("click", { button: 0 });
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("reports");
    expect(router.currentRoute.value.query).toEqual({ company: "intc" });
    expect(page("reports").attributes("aria-current")).toBe("page");
    expect(page("reports").classes()).toContain("router-link-active");
    // The Reports desk row above doesn't hold a second selection.
    const deskRow = wrapper.get('[data-tour="nav-reports"]');
    expect(deskRow.classes()).not.toContain("router-link-exact-active");

    // All reports again: the desk row holds it.
    await router.push({ name: "reports" });
    await flushPromises();
    expect(deskRow.classes()).toContain("router-link-exact-active");
    expect(page("reports").attributes("aria-current")).toBeUndefined();
  });

  it("a company's page reached from anywhere opens it here, with that page marked", async () => {
    const { router } = await mountSidebar();
    await router.push("/intc");
    await flushPromises();

    expect(pages().attributes("id")).toBe("company-pages-intc");
    expect(page("desk").attributes("aria-current")).toBe("page");
    expect(companyRow("intc").attributes("aria-current")).toBeUndefined();
    expect(companyRow("intc").classes()).not.toContain("router-link-active");

    await router.push({ name: "news-desk", query: { company: "intc" } });
    await flushPromises();
    expect(page("news").attributes("aria-current")).toBe("page");
    expect(page("desk").attributes("aria-current")).toBeUndefined();
  });

  it("shut on its own page, the company row holds the selection", async () => {
    await mountSidebar("/intc");
    expect(pages().exists()).toBe(true);

    await toggle("intc");
    expect(pages().exists()).toBe(false);
    expect(companyRow("intc").classes()).toContain("router-link-active");
    expect(companyRow("intc").attributes("aria-current")).toBe("page");
  });

  it("the arrow keys open and shut it", async () => {
    await mountSidebar();
    await companyRow("intc").trigger("keydown", { key: "ArrowRight" });
    await flushPromises();
    expect(pages().exists()).toBe(true);

    await companyRow("intc").trigger("keydown", { key: "ArrowLeft" });
    await flushPromises();
    expect(pages().exists()).toBe(false);
  });

  it("a modified click keeps the plain link (new tab) and opens nothing", async () => {
    await mountSidebar();
    await companyRow("intc").trigger("click", { button: 0, metaKey: true });
    await flushPromises();
    expect(pages().exists()).toBe(false);
  });

  it("the icon rail stacks the pages as glyphs, named on hover", async () => {
    setSidebarCollapsed(true);
    await mountSidebar("/intc");

    const rows = pages().findAll("a.company-page-row");
    expect(rows.map((row) => row.attributes("title"))).toEqual([
      "Reports",
      "News",
      "Research Desk",
      "Market",
    ]);
    expect(rows.every((row) => row.text() === "")).toBe(true);
    // No glider in the rail: the logo keeps its ring as well.
    expect(companyRow("intc").classes()).toContain("router-link-active");
    expect(page("desk").classes()).toContain("router-link-active");
  });
});
