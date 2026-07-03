import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import App from "../src/App.vue";
import { session } from "../src/auth.js";
import { api } from "../src/api.js";

vi.mock("../src/api.js", () => ({
  api: {
    listReports: vi.fn(),
    externalFeed: vi.fn(),
    listHormuz: vi.fn(),
    listCompanies: vi.fn(),
  },
}));

function makeRouter(initialPath) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/login", name: "login", component: { template: "<div>Login route</div>" } },
      { path: "/", name: "home", component: { template: "<div>Home route</div>" } },
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
  return wrapper;
}

describe("App global shell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

    const wrapper = await mountApp("/login");

    expect(wrapper.text()).toContain("Login route");
    expect(wrapper.find("[data-testid='left-rail']").exists()).toBe(false);
    expect(wrapper.text()).not.toContain("Ask Co-Pilot");
    expect(api.listReports).not.toHaveBeenCalled();
  });

  it("renders authenticated chrome and opens the company co-pilot drawer", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };

    const wrapper = await mountApp("/zainar-inc?tab=memo");
    await flushPromises();

    expect(wrapper.find("[data-testid='left-rail']").text()).toContain("Rail 1");
    expect(wrapper.text()).toContain("Research Center");
    expect(wrapper.text()).toContain("ZaiNar, Inc.");
    expect(wrapper.text()).toContain("Memo Studio");
    expect(wrapper.text()).toContain("Ask Co-Pilot");

    const openButton = wrapper
      .findAll("button")
      .find((button) => button.text().includes("Ask Co-Pilot"));
    await openButton.trigger("click");

    expect(wrapper.text()).toContain("AI Co-Pilot");
    expect(wrapper.find("[data-testid='company-console']").text()).toContain(
      "Console zainar-inc",
    );
    expect(wrapper.text()).not.toContain("Ask Co-Pilot");
  });
});
