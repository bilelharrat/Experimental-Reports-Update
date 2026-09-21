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
      liveQuotes: vi.fn(),
      quoteChart: vi.fn(),
      quotesNews: vi.fn(),
    },
  };
});

import { api } from "../src/api.js";
import Sidebar from "../src/components/Sidebar.vue";
import { setSidebarCollapsed } from "../src/state.js";

// Clicking a company in the sidebar opens the company launcher over the
// content column — its reports, its news, the Research Desk, each previewed —
// instead of going straight to the desk.

const now = new Date().toISOString();

const companies = [
  { id: "intc", name: "Intel Corp", ticker: "INTC", status: "public" },
  {
    id: "zeta",
    name: "Zeta Labs",
    status: "private",
    description: "Zeta builds ledgers for freight brokers.",
    hq: "Oakland, California",
    founded_year: 2019,
    key_people: [{ name: "Ada Park", role: "Co-founder & CEO" }],
  },
];

const reports = [
  {
    id: "r1",
    company_id: "intc",
    report_type: "Buffett Investment Memo",
    status: "complete",
    created_at: "2026-08-01T00:00:00Z",
    download_urls: { en: "/en.docx", zh: "/zh.docx" },
  },
  {
    id: "r2",
    company_id: "intc",
    report_type: "Investment Memo (Late-Stage)",
    status: "running",
    created_at: "2026-09-01T00:00:00Z",
  },
  {
    id: "r3",
    company_id: "someone-else",
    report_type: "Financial Analysis",
    status: "complete",
    created_at: "2026-09-02T00:00:00Z",
  },
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

async function mountSidebar() {
  const router = makeRouter();
  await router.push("/");
  await router.isReady();
  const openReportCustomizer = vi.fn();
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
        openReportCustomizer,
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { router, openReportCustomizer };
}

function companyRow(id) {
  return wrapper.findAll("a.company-source-row").find((a) => a.attributes("href") === `/${id}`);
}

const $ = (selector) => document.body.querySelector(selector);
const $$ = (selector) => Array.from(document.body.querySelectorAll(selector));
const launcher = () => $('[data-testid="company-launcher"]');

async function open(id) {
  await companyRow(id).trigger("click", { button: 0 });
  await flushPromises();
}

async function press(key, target = document.body) {
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  await flushPromises();
}

describe("Sidebar company launcher", () => {
  beforeEach(() => {
    setSidebarCollapsed(false);
    api.listReports.mockResolvedValue(reports);
    api.liveQuotes.mockResolvedValue({
      quotes: {
        INTC: {
          last_price: 121.78,
          change_pct_1d: 12.14,
          exchange: "NASDAQ",
          currency: "USD",
          market_cap: 643616000000,
          pe_ratio: -57.44,
          fifty_two_week_low: 28.73,
          fifty_two_week_high: 142.35,
        },
      },
    });
    api.quoteChart.mockResolvedValue({ points: [{ close: 100 }, { close: 110 }, { close: 121 }] });
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

  it("opens over the page instead of navigating", async () => {
    const { router } = await mountSidebar();
    await open("intc");

    expect(router.currentRoute.value.name).toBe("home");
    expect($('[data-testid="launcher-title"]').textContent).toBe("Intel Corp");
    expect($('[data-testid="launcher-reports"]')).not.toBeNull();
    expect($('[data-testid="launcher-news"]')).not.toBeNull();
    expect($('[data-testid="launcher-desk"]')).not.toBeNull();
    expect(companyRow("intc").attributes("aria-expanded")).toBe("true");
  });

  it("previews the company's reports, newest first, and opens the one picked", async () => {
    const { router } = await mountSidebar();
    await open("intc");

    const rows = $$('[data-testid="launcher-report"]');
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Investment Memo (Late-Stage)"),
      expect.stringContaining("Buffett Investment Memo"),
    ]);
    expect($('[data-testid="launcher-reports"]').textContent).toContain("2 reports");

    rows[0].click();
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("reports");
    expect(router.currentRoute.value.query).toEqual({ company: "intc", id: "r2" });
    expect(launcher()).toBeNull();
  });

  it("previews the company's headlines, its own ticker's included, and opens the story picked", async () => {
    const { router } = await mountSidebar();
    await open("intc");

    expect(api.quotesNews).toHaveBeenCalledWith({ tickers: ["INTC"], limit: 30 });
    const stories = $$('[data-testid="launcher-story"]');
    expect(stories.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Intel"),
      expect.stringContaining("Intel"),
    ]);
    const picked = stories.find((row) => row.textContent.includes("foundry customer"));
    picked.click();
    await flushPromises();
    expect(router.currentRoute.value.name).toBe("news-desk");
    expect(router.currentRoute.value.query).toEqual({ company: "intc", story: "news:n1" });
  });

  it.each([
    ["launcher-open-reports", "reports", { company: "intc" }],
    ["launcher-open-news", "news-desk", { company: "intc" }],
  ])("%s opens %s filtered to the company", async (testid, name, query) => {
    const { router } = await mountSidebar();
    await open("intc");
    $(`[data-testid="${testid}"]`).click();
    await flushPromises();

    expect(router.currentRoute.value.name).toBe(name);
    expect(router.currentRoute.value.query).toEqual(query);
    expect(launcher()).toBeNull();
  });

  it("Research Desk opens the company's dossier", async () => {
    const { router } = await mountSidebar();
    await open("intc");
    $('[data-testid="launcher-open-desk"]').click();
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("research");
    expect(router.currentRoute.value.params.companyId).toBe("intc");
  });

  it.each(["launcher-quote", "launcher-ticker"])(
    "%s opens the stock on the Market desk",
    async (testid) => {
      const { router } = await mountSidebar();
      await open("intc");
      $(`[data-testid="${testid}"]`).click();
      await flushPromises();

      expect(router.currentRoute.value.name).toBe("market-radar");
      expect(router.currentRoute.value.query).toEqual({ ticker: "INTC" });
      expect(launcher()).toBeNull();
    },
  );

  it("a click on a card's open space opens that card", async () => {
    const { router } = await mountSidebar();
    await open("intc");
    $('[data-testid="launcher-news"] .launcher-card-title').click();
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("news-desk");
    expect(router.currentRoute.value.query).toEqual({ company: "intc" });
  });

  it("shows the live price and market facts for a listed company", async () => {
    await mountSidebar();
    await open("intc");

    const quote = $('[data-testid="launcher-quote"]').textContent;
    expect(quote).toContain("$121.78");
    expect(quote).toContain("+12.14%");
    const head = $(".launcher-head").textContent;
    expect(head).toContain("NASDAQ · INTC");
    const desk = $('[data-testid="launcher-desk"]').textContent;
    expect(desk).toContain("Market cap");
    expect(desk).toContain("$644B");
    expect(desk).toContain("$28.73 – $142.35");
    // A loss-making company has no meaningful P/E.
    expect(desk).not.toContain("P/E");
  });

  it("a private company shows its profile, and no reports offers to generate one", async () => {
    const { openReportCustomizer } = await mountSidebar();
    await open("zeta");

    expect(api.liveQuotes).not.toHaveBeenCalled();
    expect(api.quotesNews).not.toHaveBeenCalled();
    // No listing, so nothing to open on the Market desk.
    expect($('[data-testid="launcher-ticker"]')).toBeNull();
    expect($('[data-testid="launcher-quote"]')).toBeNull();
    expect($(".launcher-head").textContent).toContain("Zeta builds ledgers for freight brokers.");
    const desk = $('[data-testid="launcher-desk"]').textContent;
    expect(desk).toContain("Founded");
    expect(desk).toContain("2019");
    expect(desk).toContain("Ada Park");
    expect($('[data-testid="launcher-reports"]').textContent).toContain("No reports on Zeta Labs yet");

    $('[data-testid="launcher-generate"]').click();
    await flushPromises();
    expect(openReportCustomizer).toHaveBeenCalledWith("zeta");
    expect(launcher()).toBeNull();
  });

  it("another company swaps the launcher over; the same one closes it", async () => {
    await mountSidebar();
    await open("intc");
    await open("zeta");
    expect($('[data-testid="launcher-title"]').textContent).toBe("Zeta Labs");
    await open("zeta");
    expect(launcher()).toBeNull();
  });

  it("1, 2 and 3 open the cards", async () => {
    const { router } = await mountSidebar();
    await open("intc");
    await press("3");
    expect(router.currentRoute.value.name).toBe("research");

    await open("intc");
    await press("2");
    expect(router.currentRoute.value.name).toBe("news-desk");
  });

  it("digits typed into a field are text, not shortcuts", async () => {
    const { router } = await mountSidebar();
    await open("intc");
    const field = document.createElement("input");
    document.body.appendChild(field);
    await press("1", field);

    expect(router.currentRoute.value.name).toBe("home");
    expect(launcher()).not.toBeNull();
  });

  it("Escape closes it and hands focus back to the company row", async () => {
    await mountSidebar();
    await open("intc");
    await press("Escape");

    expect(launcher()).toBeNull();
    expect(document.activeElement).toBe(companyRow("intc").element);
  });

  it("navigating anywhere closes it", async () => {
    const { router } = await mountSidebar();
    await open("intc");
    await router.push("/tracking");
    await flushPromises();
    expect(launcher()).toBeNull();
  });

  it("a modified click keeps the plain link (new tab) and opens nothing", async () => {
    await mountSidebar();
    await companyRow("intc").trigger("click", { button: 0, metaKey: true });
    await flushPromises();
    expect(launcher()).toBeNull();
  });
});
