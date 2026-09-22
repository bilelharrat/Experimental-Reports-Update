import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import App from "../src/App.vue";
import { session } from "../src/auth.js";
import { api } from "../src/api.js";
import { setLastCompanyId, setSidebarCollapsed } from "../src/state.js";
import {
  copilotCompanyOverride,
  copilotDraftPrompt,
  copilotPendingPrompt,
  copilotSelection,
} from "../src/copilotContext.js";

vi.mock("../src/api.js", () => ({
  api: {
    listReports: vi.fn(),
    externalFeed: vi.fn(),
    listHormuz: vi.fn(),
    listCompanies: vi.fn(),
    quotesNews: vi.fn().mockResolvedValue({ items: [] }),
    uploadFile: vi.fn(),
    uploadResearchFile: vi.fn(),
    deskPrefs: vi.fn().mockResolvedValue({ updated_at: null, data: {} }),
    saveDeskPrefs: vi.fn().mockResolvedValue({ updated_at: "x", data: {} }),
    runAlertCheck: vi.fn().mockResolvedValue({ checked: 0, fired: [] }),
  },
}));

function makeRouter(initialPath) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: { template: "<div>Login route</div>" } },
      { path: "/", name: "home", component: { template: "<div>Home route</div>" } },
      { path: "/tracking", name: "tracking", component: { template: "<div>Tracking route</div>" } },
      { path: "/market-radar", name: "market-radar", component: { template: "<div>Radar route</div>" } },
      { path: "/settings", name: "settings", component: { template: "<div>Settings route</div>" } },
      {
        path: "/ask-from-page",
        name: "ask-from-page",
        component: {
          emits: ["open-copilot"],
          mounted() {
            this.$emit("open-copilot", {
              companyId: null,
              prompt: "Why is NVDA moving?",
              context: { surface: "market_desk", selection: { ticker: "NVDA" } },
            });
          },
          template: "<div>Ask from page</div>",
        },
      },
      { path: "/user", name: "user-center", component: { template: "<div>User route</div>" } },
      {
        path: "/open-citation",
        name: "open-citation",
        component: {
          inject: ["copilotNavigate"],
          template: "<button data-testid='cite' @click='open'>Cite</button>",
          methods: {
            open() {
              this.copilotNavigate({
                kind: "file",
                companyId: "zainar-inc",
                file: { id: "file-7", filename: "deck.pdf" },
                page: "4",
              });
            },
          },
        },
      },
      {
        path: "/research-desk/:companyId",
        name: "research-desk-company",
        component: { template: "<div>Desk company route</div>" },
      },
      { path: "/:companyId", name: "research", component: { template: "<div>Company route</div>" } },
    ],
  });
  return router.push(initialPath).then(() => router.isReady()).then(() => router);
}

async function mountApp(initialPath) {
  const router = await makeRouter(initialPath);
  const wrapper = mount(App, {
    global: {
      plugins: [router],
      stubs: {
        Sidebar: {
          props: ["companies"],
          template: "<aside data-testid='left-rail'>Rail {{ companies.length }}</aside>",
        },
        ActiveJobsRail: { template: "<div data-testid='active-jobs' />" },
        DeckSummaryModal: { template: "<div />" },
        CompanyConsole: {
          props: ["companyId"],
          template: "<section data-testid='company-console'>Console {{ companyId }}</section>",
        },
        CopilotPanel: {
          props: ["companyId", "companyName", "contextLabel", "suggestedCompanies"],
          template:
            "<section data-testid='copilot-panel'>Copilot {{ companyId }} sees {{ contextLabel }}</section>",
        },
        Teleport: true,
      },
    },
  });
  await flushPromises();
  return { wrapper, router };
}

describe("App global shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setSidebarCollapsed(false);
    api.listReports.mockResolvedValue([]);
    api.externalFeed.mockResolvedValue([]);
    api.listHormuz.mockResolvedValue([]);
    api.listCompanies.mockResolvedValue([
      { id: "zainar-inc", name: "ZaiNar, Inc.", status: "private" },
    ]);
  });

  afterEach(() => {
    session.value = null;
    copilotCompanyOverride.value = null;
    copilotDraftPrompt.value = "";
    copilotPendingPrompt.value = "";
    copilotSelection.value = null;
    setLastCompanyId("");
  });

  it("renders login without app chrome when unauthenticated", async () => {
    session.value = null;

    const { wrapper } = await mountApp("/login");

    expect(wrapper.text()).toContain("Login route");
    expect(wrapper.find("[data-testid='left-rail']").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Ask Warren");
    expect(api.listReports).not.toHaveBeenCalled();
  });

  it("shows Ask Warren in the toolbar on Home", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };

    const { wrapper } = await mountApp("/");
    await flushPromises();

    expect(wrapper.text()).toContain("Home route");
    const askButton = wrapper.find('[aria-label="Ask Warren"]');
    expect(askButton.exists()).toBe(true);
    expect(askButton.text()).toContain("Ask Warren");
    // Warren's portrait is the mark, as on iPhone.
    expect(askButton.find(".warren-mark img").exists()).toBe(true);
    expect(wrapper.find(".copilot-drag-handle").exists()).toBe(false);
    expect(wrapper.find(".copilot-drag-lens").exists()).toBe(false);
    expect(wrapper.find('[aria-label="Add"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Settings"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Market Radar"]').exists()).toBe(false);
    // The account lives in the sidebar footer now (as on the Mac), not the toolbar.
    expect(wrapper.find('[aria-label="Account"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="App language"]').exists()).toBe(false);

    await wrapper.find('[aria-label="Add"]').trigger("click");
    expect(wrapper.text()).toContain("Link");
    expect(wrapper.text()).toContain("File");
    expect(wrapper.text()).toContain("Note");
    expect(wrapper.text()).not.toContain("Company files");
  });

  it("renders authenticated chrome and opens the company Ask Warren sheet", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };

    const { wrapper } = await mountApp("/zainar-inc?tab=memo");
    await flushPromises();

    expect(wrapper.find("[data-testid='left-rail']").text()).toContain("Rail 1");
    expect(wrapper.text()).toContain("ZaiNar, Inc.");
    expect(wrapper.find('[aria-label="Ask Warren"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Settings"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Market Radar"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Account"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="App language"]').exists()).toBe(false);
    expect(wrapper.find(`[aria-label="Jump to a company or command"]`).exists()).toBe(true);

    await wrapper.find('[aria-label="Add to ZaiNar, Inc."]').trigger("click");
    expect(wrapper.text()).not.toContain("Company files");
    expect(wrapper.text()).not.toContain("Memo inputs");
    expect(wrapper.text()).not.toContain("Link");

    const openButton = wrapper.find('[aria-label="Ask Warren"]');
    await openButton.trigger("click");

    const sheet = wrapper.find("aside.copilot-sheet");
    expect(sheet.text()).toContain("Ask Warren");
    // The header names the company Warren is reading, switchable in place.
    expect(sheet.find(".warren-about").text()).toContain("ZaiNar, Inc.");
    // Named as the desk's tab bar names it.
    expect(wrapper.find("[data-testid='copilot-panel']").text()).toContain(
      "Copilot zainar-inc sees Memo Studio",
    );
    expect(openButton.attributes("aria-pressed")).toBe("true");
  });

  it("points Warren at the last company off company pages and switches from his header", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };
    api.listCompanies.mockResolvedValue([
      { id: "zainar-inc", name: "ZaiNar, Inc.", status: "private" },
      { id: "nextnav", name: "NextNav", status: "public", ticker: "NN" },
    ]);
    setLastCompanyId("zainar-inc");

    const { wrapper } = await mountApp("/");
    await wrapper.find('[aria-label="Ask Warren"]').trigger("click");

    const panel = () => wrapper.find("[data-testid='copilot-panel']");
    expect(panel().text()).toContain("Copilot zainar-inc");
    // Off the company's own page Warren can't see a tab.
    expect(panel().text()).not.toMatch(/sees \S/);

    await wrapper.find(".warren-about").trigger("click");
    const option = wrapper
      .findAll("[role='option']")
      .find((row) => row.text().includes("NextNav"));
    await option.trigger("click");

    expect(panel().text()).toContain("Copilot nextnav");
    expect(wrapper.find(".warren-about").text()).toContain("NextNav");
    expect(wrapper.find("[role='listbox']").exists()).toBe(false);
  });

  it("leaves a company-less question in Warren's composer instead of sending it", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };
    setLastCompanyId("zainar-inc");

    const { wrapper, router } = await mountApp("/ask-from-page");
    await flushPromises();

    // Warren opens under the last company, but the ticker question waits.
    expect(wrapper.find("[data-testid='copilot-panel']").text()).toContain("Copilot zainar-inc");
    expect(copilotDraftPrompt.value).toBe("Why is NVDA moving?");
    expect(copilotPendingPrompt.value).toBe("");
    expect(copilotSelection.value).toMatchObject({ ticker: "NVDA" });

    // Leaving the page drops what it handed Warren.
    await router.push("/settings");
    await flushPromises();
    expect(copilotSelection.value).toBeNull();
  });

  it("opens a file Warren cites on the company's Files tab", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };

    const { wrapper, router } = await mountApp("/open-citation");
    await wrapper.find("[data-testid='cite']").trigger("click");
    await flushPromises();

    expect(router.currentRoute.value.name).toBe("research");
    expect(router.currentRoute.value.params.companyId).toBe("zainar-inc");
    expect(router.currentRoute.value.query).toEqual({
      section: "files",
      previewFile: "file-7",
      previewPage: "4",
    });
  });

  async function addFromToolbar(wrapper, name) {
    const input = wrapper.find('input[type="file"][multiple]');
    const file = new File(["deck"], name, { type: "application/pdf" });
    Object.defineProperty(input.element, "files", { value: [file], configurable: true });
    await input.trigger("change");
    await flushPromises();
    return file;
  }

  it.each([
    ["/zainar-inc?section=team", "/zainar-inc"],
    ["/research-desk/zainar-inc", "/research-desk/zainar-inc"],
  ])(
    "uploads straight from the toolbar's Add on %s and opens the desk's Files tab",
    async (start, path) => {
      session.value = {
        token: "test-token",
        email: "elina.sun@bshfoundation.org",
        expires_at: "2999-01-01T00:00:00Z",
      };
      api.uploadResearchFile.mockResolvedValue({ id: "new-file" });

      const { wrapper, router } = await mountApp(start);
      // A company page's Add is the upload itself, not the menu.
      await wrapper.find('[aria-label="Add to ZaiNar, Inc."]').trigger("click");
      expect(wrapper.find("[role='menu']").exists()).toBe(false);

      const file = await addFromToolbar(wrapper, "deck.pdf");

      expect(api.uploadResearchFile).toHaveBeenCalledWith("zainar-inc", file);
      // Same page, Files tab, and a stamp that has the list reload.
      expect(router.currentRoute.value.path).toBe(path);
      expect(router.currentRoute.value.query).toEqual({
        section: "files",
        files: expect.stringMatching(/^\d+$/),
      });
    },
  );
});
