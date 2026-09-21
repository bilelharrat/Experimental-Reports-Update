import { describe, expect, it, beforeEach, vi } from "vitest";
import { nextTick } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { createMemoryHistory, createRouter } from "vue-router";
import Sidebar from "../src/components/Sidebar.vue";
import { session } from "../src/auth.js";
import {
  ALL_SECTORS,
  companyViews,
  setDeskDiffsOnly,
  setDeskSector,
  setCompanySort,
  setSidebarCollapsed,
  trackedCompanyIds,
} from "../src/state.js";

const RouterLinkStub = {
  props: ["to"],
  template: "<a><slot /></a>",
};

const companies = [
  {
    id: "acme-inc",
    name: "Acme Inc.",
    company_type: "private",
    status: "private",
    industry: "Industrial AI",
  },
  {
    id: "nvda",
    name: "NVIDIA",
    company_type: "public",
    status: "public",
    sector: "Semis / AI Infra",
  },
  {
    id: "zeta",
    name: "Zeta Labs",
    company_type: "private",
    status: "private",
    industry: "Robotics",
  },
];

function mountSidebar(list = companies) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/", component: { template: "<div />" } }, { path: "/login", name: "login", component: { template: "<div />" } }],
  });
  return mount(Sidebar, {
    props: {
      loading: false,
      companies: list,
    },
    global: {
      plugins: [router],
      stubs: {
        RouterLink: RouterLinkStub,
      },
    },
  });
}

function nameOrder(wrapper) {
  const text = wrapper.text();
  return ["Acme Inc.", "NVIDIA", "Zeta Labs"]
    .map((name) => [name, text.indexOf(name)])
    .sort((a, b) => a[1] - b[1])
    .map(([name]) => name);
}

describe("Sidebar", () => {
  beforeEach(() => {
    setSidebarCollapsed(false);
    setCompanySort("az");
    trackedCompanyIds.value = new Set();
    companyViews.value = {};
  });

  it("renders one company list and parks extra markets", () => {
    const wrapper = mountSidebar();
    const text = wrapper.text();

    expect(text).toContain("Companies");
    expect(text).toContain("Acme Inc.");
    expect(text).toContain("NVIDIA");
    expect(text).toContain("Zeta Labs");
    expect(text).toContain("Home");
    // Every desk has its own row: Research Desk, and Market, Pulse and News
    // each as a row of their own rather than one combined Markets row.
    const desks = ["Home", "Research Desk", "Market", "Pulse", "News", "Reports", "Tracking"];
    for (const desk of desks) expect(text).toContain(desk);
    for (let i = 1; i < desks.length; i += 1) {
      expect(text.indexOf(desks[i - 1])).toBeLessThan(text.indexOf(desks[i]));
    }
    expect(text).not.toContain("Markets");
    expect(text).not.toContain("Portfolio");
    expect(text).not.toContain("Top Players");
    expect(text).not.toContain("More markets");
    expect(text).not.toContain("Workbench");
    expect(text).not.toContain("Stats");
    expect(text).not.toContain("Pipeline");
    expect(text).not.toContain("News Board");
    expect(text).not.toContain("Settings");
    expect(text).not.toContain("Sign out");
  });

  it("sorts A-Z by default and by views via the sort menu", async () => {
    companyViews.value = { "acme-inc": 1, zeta: 5 };
    const wrapper = mountSidebar();

    expect(nameOrder(wrapper)).toEqual(["Acme Inc.", "NVIDIA", "Zeta Labs"]);

    await wrapper.get('button[aria-label="Sort"]').trigger("click");
    const mostViewed = wrapper
      .findAll('[role="menuitemradio"]')
      .find((option) => option.text().includes("Most viewed"));
    await mostViewed.trigger("click");

    expect(nameOrder(wrapper)).toEqual(["Zeta Labs", "Acme Inc.", "NVIDIA"]);
  });

  it("pins followed companies to the top of the list", async () => {
    const wrapper = mountSidebar();

    const followButtons = wrapper.findAll('button[aria-label="Follow"]');
    await followButtons[2].trigger("click");

    expect(trackedCompanyIds.value.has("zeta")).toBe(true);
    expect(nameOrder(wrapper)).toEqual(["Zeta Labs", "Acme Inc.", "NVIDIA"]);
  });

  it("follows a company from the list", async () => {
    const wrapper = mountSidebar();

    const followButtons = wrapper.findAll('button[aria-label="Follow"]');
    await followButtons[1].trigger("click");

    expect(trackedCompanyIds.value.has("nvda")).toBe(true);
    await wrapper.get('button[aria-label="Unfollow"]').trigger("click");
    expect(trackedCompanyIds.value.has("nvda")).toBe(false);
  });

  it("collapses to an icon rail and expands again", async () => {
    const wrapper = mountSidebar();
    const toggle = wrapper.get('button[aria-label="Collapse sidebar"]');

    await toggle.trigger("click");

    expect(wrapper.find("aside").attributes("data-collapsed")).toBe("true");
    expect(wrapper.text()).not.toContain("Acme Inc.");
    expect(wrapper.text()).toContain("AI");
    expect(wrapper.text()).toContain("NV");
    expect(wrapper.text()).toContain("ZL");
    expect(wrapper.findAll(".company-rail-mark")).toHaveLength(3);
    expect(wrapper.findAll('button[aria-label="Follow"]')).toHaveLength(0);
    expect(wrapper.get('button[aria-label="Expand sidebar"]').exists()).toBe(true);

    await wrapper.get('button[aria-label="Expand sidebar"]').trigger("click");

    expect(wrapper.find("aside").attributes("data-collapsed")).toBe("false");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).toContain("Pulse");
  });

  it("shows the account in the footer with Settings and Sign out behind it", async () => {
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };
    try {
      const wrapper = mountSidebar();
      const account = wrapper.get('button[aria-label="Account"]');

      expect(account.text()).toContain("ES");
      expect(account.text()).toContain("elina.sun@bshfoundation.org");
      expect(wrapper.text()).not.toContain("Settings");

      await account.trigger("click");

      expect(wrapper.text()).toContain("Settings");
      expect(wrapper.text()).toContain("Sign out");
    } finally {
      session.value = null;
    }
  });

  it("offers Sign in, not Sign out, when the desk is open with nobody signed in", async () => {
    // A server running the local anon-dev bypass opens the desk without a
    // sign-in, so there is nothing to sign out of.
    document.head.innerHTML = '<meta name="bsh-research-anon-dev" content="1">';
    try {
      const wrapper = mountSidebar();
      await wrapper.get('button[aria-label="Account"]').trigger("click");

      expect(wrapper.text()).not.toContain("Sign out");
      const signIn = wrapper
        .findAllComponents(RouterLinkStub)
        .find((link) => link.text() === "Sign in");
      // The login route sends an anon-dev browser straight back into the
      // app; the flag asks for the form.
      expect(signIn.props("to")).toEqual({ name: "login", query: { switch: "1", next: "/" } });
    } finally {
      document.head.innerHTML = "";
    }
  });

  it("signs out to the sign-in form, then offers Sign in", async () => {
    document.head.innerHTML = '<meta name="bsh-research-anon-dev" content="1">';
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true })));
    session.value = {
      token: "test-token",
      email: "elina.sun@bshfoundation.org",
      expires_at: "2999-01-01T00:00:00Z",
    };
    try {
      const wrapper = mountSidebar();
      const account = wrapper.get('button[aria-label="Account"]');
      await account.trigger("click");
      await wrapper
        .findAll("button")
        .find((button) => button.text() === "Sign out")
        .trigger("click");
      await flushPromises();

      expect(session.value).toBeNull();
      expect(wrapper.vm.$router.currentRoute.value).toMatchObject({
        name: "login",
        query: { switch: "1" },
      });

      await account.trigger("click");
      expect(wrapper.text()).toContain("Sign in");
      expect(wrapper.text()).not.toContain("Sign out");
    } finally {
      session.value = null;
      vi.unstubAllGlobals();
      document.head.innerHTML = "";
    }
  });

  it("filters a long company list", async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({
      id: `co-${i}`,
      name: i === 7 ? "Zeta Robotics" : `Company ${i}`,
      company_type: "private",
      status: "private",
      industry: "AI",
    }));
    const wrapper = mountSidebar(many);

    await wrapper.get('input[aria-label="Filter companies"]').setValue("zeta");

    expect(wrapper.text()).toContain("Zeta Robotics");
    expect(wrapper.text()).not.toContain("Company 3");
  });

  it("shows the full company list in the rail", async () => {
    const many = Array.from({ length: 6 }, (_, i) => ({
      id: `co-${i}`,
      name: `Company ${i}`,
      company_type: "private",
      status: "private",
      industry: "AI",
    }));
    const wrapper = mountSidebar(many);

    expect(wrapper.text()).toContain("Company 0");
    expect(wrapper.text()).toContain("Company 2");
    expect(wrapper.text()).toContain("Company 3");
    expect(wrapper.text()).toContain("Company 5");
    expect(wrapper.text()).not.toContain("Show all");
  });

  it("renders company logos via Monogram in company items", () => {
    const wrapper = mountSidebar();
    const monograms = wrapper.findAllComponents({ name: "Monogram" });
    expect(monograms.length).toBeGreaterThan(0);
    const nvdaMonogram = monograms.find(
      (m) => m.props("company")?.id === "nvda",
    );
    expect(nvdaMonogram).toBeTruthy();
    const src = nvdaMonogram.find("img").attributes("src");
    expect(src).toMatch(/nvidia\.com|NVDA/);
  });
});

// ---- the directory column, now that it is this list -------------------------
//
// The Research Desk carried its own company column — search, a sector popup,
// a Diffs toggle and a deck drop — beside this one. Two lists, one job, and
// between them they left the dossier about half the window. The column is
// gone; these are the behaviours that came across with it.

describe("Sidebar company directory", () => {
  const sectored = [
    { id: "acme", name: "Acme Corp", sector: "Industrial AI", is_modified: true },
    { id: "globex", name: "Globex Corporation", sector: "Fintech" },
    { id: "initech", name: "Initech", sector: "Fintech" },
  ];

  beforeEach(() => {
    setDeskSector(ALL_SECTORS);
    setDeskDiffsOnly(false);
  });

  it("filters the list by sector", async () => {
    const wrapper = mountSidebar(sectored);
    expect(wrapper.text()).toContain("Acme Corp");

    setDeskSector("Fintech");
    await nextTick();

    expect(wrapper.text()).toContain("Globex Corporation");
    expect(wrapper.text()).toContain("Initech");
    expect(wrapper.text()).not.toContain("Acme Corp");
  });

  it("shows only changed companies when Diffs is on", async () => {
    const wrapper = mountSidebar(sectored);
    const diffs = wrapper.find('[data-testid="sidebar-diffs-toggle"]');
    expect(diffs.exists()).toBe(true);

    await diffs.trigger("click");
    await nextTick();

    // Acme carries is_modified; the other two have been seen and changed nothing
    expect(wrapper.text()).toContain("Acme Corp");
    expect(wrapper.text()).not.toContain("Globex Corporation");
  });

  it("hides the sector popup when there is only one sector to pick", () => {
    const oneSector = [
      { id: "a", name: "Acme Corp", sector: "Fintech" },
      { id: "b", name: "Globex Corporation", sector: "Fintech" },
    ];
    expect(mountSidebar(oneSector).find("select").exists()).toBe(false);
    expect(mountSidebar(sectored).find("select").exists()).toBe(true);
  });

  it("shows the deck drop affordance only while a deck is over it", async () => {
    // A permanent drop box cost three lines of the rail to say something a
    // reader already knows how to do.
    const wrapper = mountSidebar(sectored);
    expect(wrapper.find('[data-testid="sidebar-deck-overlay"]').exists()).toBe(
      false,
    );

    await wrapper.find("section").trigger("dragover", {
      dataTransfer: { types: ["Files"] },
    });
    expect(wrapper.find('[data-testid="sidebar-deck-overlay"]').exists()).toBe(
      true,
    );

    await wrapper.find("section").trigger("dragleave");
    expect(wrapper.find('[data-testid="sidebar-deck-overlay"]').exists()).toBe(
      false,
    );
  });

  it("ignores a drag that carries no file", async () => {
    const wrapper = mountSidebar(sectored);
    await wrapper.find("section").trigger("dragover", {
      dataTransfer: { types: ["text/plain"] },
    });
    expect(wrapper.find('[data-testid="sidebar-deck-overlay"]').exists()).toBe(
      false,
    );
  });
});
