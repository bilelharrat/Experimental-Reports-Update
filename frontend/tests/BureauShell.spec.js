import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, ref } from "vue";
import { createMemoryHistory, createRouter } from "vue-router";

vi.mock("../src/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    api: {
      ...actual.api,
      listReports: vi.fn().mockResolvedValue([]),
      quotesNews: vi.fn().mockResolvedValue({ items: [] }),
    },
  };
});

import Sidebar from "../src/components/Sidebar.vue";
import { setDesign } from "../src/design.js";
import {
  companyIndexOpen,
  setCompanyIndexOpen,
  setSidebarCollapsed,
  sidebarCollapsed,
} from "../src/state.js";

// Bureau lays the page on a desk: the desks become tabs along the top edge
// of the sheet (the sidebar's own rows, carried into the masthead) and the
// company list folds to a rail of logos until it is opened.

const companies = [
  { id: "intc", name: "Intel Corp", ticker: "INTC", status: "public" },
  { id: "zeta", name: "Zeta Labs", status: "private" },
];

const view = { template: "<div />" };
const NAMES = ["reports", "research-desk", "news-desk", "weekly-summary", "market-radar", "tracking", "settings", "login"];

// The masthead slot App.vue renders, with the sidebar beside it.
const Shell = defineComponent({
  components: { Sidebar },
  props: { companies: { type: Array, default: () => [] } },
  template: `
    <div>
      <header><div id="masthead-desk-tabs" data-testid="masthead-tabs"></div></header>
      <Sidebar :companies="companies" :loading="false" />
    </div>
  `,
});

let wrapper;

async function mountShell(start = "/reports") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", name: "home", component: view },
      ...NAMES.map((name) => ({ path: `/${name}`, name, component: view })),
      { path: "/:companyId", name: "research", component: view },
    ],
  });
  await router.push(start);
  await router.isReady();
  wrapper = mount(Shell, {
    props: { companies },
    global: {
      plugins: [router],
      provide: {
        workspaceNews: ref([]),
        workspaceResearch: ref([]),
        workspaceLiveNews: ref([]),
      },
    },
    attachTo: document.body,
  });
  await flushPromises();
  return { router };
}

const tabs = () => document.querySelector('[data-testid="masthead-tabs"]');
const aside = () => wrapper.find("aside.app-sidebar");

describe("Bureau shell", () => {
  beforeEach(() => {
    window.localStorage.removeItem("bsh.companyIndexOpen");
    setCompanyIndexOpen(false);
    setSidebarCollapsed(false);
    setDesign("bureau");
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    document.body.innerHTML = "";
    setDesign("bureau");
    setCompanyIndexOpen(false);
  });

  it("carries the desks into the masthead as labelled tabs", async () => {
    await mountShell("/reports");

    const slot = tabs();
    const desks = ["Home", "Reports", "Research Desk", "News", "Pulse", "Market", "Tracking"];
    for (const desk of desks) expect(slot.textContent).toContain(desk);
    // Same links and tour anchors as the sidebar rows, now in the masthead…
    expect(slot.querySelector('[data-tour="nav-home"]')).not.toBeNull();
    expect(slot.querySelector('[data-tour="nav-tracking"]')).not.toBeNull();
    expect(slot.querySelector(".sidebar-desks").getAttribute("data-masthead")).toBe("true");
    // …and no longer in the sidebar itself.
    expect(aside().find('[data-tour="nav-home"]').exists()).toBe(false);
  });

  it("marks the desk you are on, and none while a company's page holds the selection", async () => {
    const { router } = await mountShell("/reports");
    const current = () => tabs().querySelector(".router-link-exact-active");
    expect(current().getAttribute("data-tour")).toBe("nav-reports");

    await router.push("/intc");
    await flushPromises();
    expect(current()).toBeNull();
  });

  it("folds the company list to a rail by default, whatever the list sidebar was", async () => {
    setSidebarCollapsed(false);
    await mountShell("/reports");

    expect(aside().attributes("data-collapsed")).toBe("true");
    const toggle = wrapper.get('[data-testid="sidebar-collapse-toggle"]');
    expect(toggle.attributes("title")).toBe("Open the company index");
    // The rail shows the companies as logos, not names.
    expect(aside().text()).not.toContain("Intel Corp");
  });

  it("opens the index and folds it back, keeping its own choice", async () => {
    await mountShell("/reports");
    const toggle = () => wrapper.get('[data-testid="sidebar-collapse-toggle"]');

    await toggle().trigger("click");
    expect(aside().attributes("data-collapsed")).toBe("false");
    expect(companyIndexOpen.value).toBe(true);
    expect(window.localStorage.getItem("bsh.companyIndexOpen")).toBe("1");
    expect(toggle().attributes("title")).toBe("Fold the index to a rail");
    expect(aside().text()).toContain("Intel Corp");
    // The other designs' collapsed state is left alone.
    expect(sidebarCollapsed.value).toBe(false);

    await toggle().trigger("click");
    expect(aside().attributes("data-collapsed")).toBe("true");
    expect(window.localStorage.getItem("bsh.companyIndexOpen")).toBe("0");
  });

  it("leaves the desks in the sidebar under Folio", async () => {
    setDesign("folio");
    await mountShell("/reports");

    expect(tabs().children.length).toBe(0);
    expect(aside().find('[data-tour="nav-home"]').exists()).toBe(true);
    expect(aside().attributes("data-collapsed")).toBe("false");
    expect(wrapper.get('[data-testid="sidebar-collapse-toggle"]').attributes("title")).toBe(
      "Collapse sidebar",
    );
  });
});
