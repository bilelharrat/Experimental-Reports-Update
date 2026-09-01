import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import App from "../src/App.vue";
import { session } from "../src/auth.js";
import { api } from "../src/api.js";
import { setSidebarCollapsed } from "../src/state.js";

vi.mock("../src/api.js", () => ({
  api: {
    listReports: vi.fn(),
    externalFeed: vi.fn(),
    listHormuz: vi.fn(),
    listCompanies: vi.fn(),
    uploadFile: vi.fn(),
    uploadResearchFile: vi.fn(),
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
      { path: "/user", name: "user-center", component: { template: "<div>User route</div>" } },
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
  });

  it("renders login without app chrome when unauthenticated", async () => {
    session.value = null;

    const { wrapper } = await mountApp("/login");

    expect(wrapper.text()).toContain("Login route");
    expect(wrapper.find("[data-testid='left-rail']").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Ask Co-Pilot");
    expect(api.listReports).not.toHaveBeenCalled();
  });

  it("keeps Co-Pilot as a quiet toolbar inspector on Home", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };

    const { wrapper } = await mountApp("/");
    await flushPromises();

    expect(wrapper.text()).toContain("Home route");
    expect(wrapper.find('[aria-label="Ask Co-Pilot"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Add"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Settings"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Market Radar"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Account"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Account"]').text()).toContain("ES");
    expect(wrapper.find('[aria-label="App language"]').exists()).toBe(false);

    await wrapper.find('[aria-label="Add"]').trigger("click");
    expect(wrapper.text()).toContain("Link");
    expect(wrapper.text()).toContain("File");
    expect(wrapper.text()).toContain("Note");
    expect(wrapper.text()).not.toContain("Company files");
  });

  it("renders authenticated chrome and opens the company co-pilot drawer", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };

    const { wrapper } = await mountApp("/zainar-inc?tab=memo");
    await flushPromises();

    expect(wrapper.find("[data-testid='left-rail']").text()).toContain("Rail 1");
    expect(wrapper.text()).toContain("ZaiNar, Inc.");
    expect(wrapper.find('[aria-label="Ask Co-Pilot"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Add to ZaiNar, Inc."]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Settings"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Market Radar"]').exists()).toBe(false);
    expect(wrapper.find('[aria-label="Account"]').exists()).toBe(true);
    expect(wrapper.find('[aria-label="Account"]').text()).toContain("ES");
    expect(wrapper.find('[aria-label="App language"]').exists()).toBe(false);
    expect(wrapper.find(`[aria-label="Search or add a company…"]`).exists()).toBe(true);

    await wrapper.find('[aria-label="Add to ZaiNar, Inc."]').trigger("click");
    expect(wrapper.text()).not.toContain("Company files");
    expect(wrapper.text()).not.toContain("Memo inputs");
    expect(wrapper.text()).not.toContain("Link");

    const openButton = wrapper.find('[aria-label="Ask Co-Pilot"]');
    await openButton.trigger("click");

    expect(wrapper.text()).toContain("Co-Pilot");
    expect(wrapper.text()).toContain("Review the current workspace");
    expect(wrapper.find("[data-testid='company-console']").text()).toContain(
      "Console zainar-inc",
    );
    expect(openButton.attributes("aria-pressed")).toBe("true");
  });
});
