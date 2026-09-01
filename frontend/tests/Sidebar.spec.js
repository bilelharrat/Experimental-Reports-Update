import { describe, expect, it, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import Sidebar from "../src/components/Sidebar.vue";
import {
  companyViews,
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

function mountSidebar() {
  return mount(Sidebar, {
    props: {
      loading: false,
      companies,
    },
    global: {
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

    expect(wrapper.text()).toContain("Companies");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("Zeta Labs");
    expect(wrapper.text()).toContain("Markets");
    expect(wrapper.text()).toContain("Radar");
    expect(wrapper.text()).toContain("Pulse");
    expect(wrapper.text()).toContain("Tracking");
    expect(wrapper.text()).not.toContain("Portfolio");
    expect(wrapper.text()).not.toContain("Top Players");
    expect(wrapper.text()).not.toContain("More markets");
    expect(wrapper.text()).not.toContain("Workbench");
    expect(wrapper.text()).not.toContain("Stats");
    expect(wrapper.text()).not.toContain("Pipeline");
    expect(wrapper.text()).not.toContain("News Board");
    expect(wrapper.text()).not.toContain("Settings");
    expect(wrapper.text()).not.toContain("Sign out");
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
    expect(wrapper.get('button[aria-label="Expand sidebar"]').exists()).toBe(true);

    await wrapper.get('button[aria-label="Expand sidebar"]').trigger("click");

    expect(wrapper.find("aside").attributes("data-collapsed")).toBe("false");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).toContain("Pulse");
  });

  it("shows the full company list in the rail", async () => {
    const many = Array.from({ length: 6 }, (_, i) => ({
      id: `co-${i}`,
      name: `Company ${i}`,
      company_type: "private",
      status: "private",
      industry: "AI",
    }));
    const wrapper = mount(Sidebar, {
      props: { loading: false, companies: many },
      global: { stubs: { RouterLink: RouterLinkStub } },
    });

    expect(wrapper.text()).toContain("Company 0");
    expect(wrapper.text()).toContain("Company 2");
    expect(wrapper.text()).toContain("Company 3");
    expect(wrapper.text()).toContain("Company 5");
    expect(wrapper.text()).not.toContain("Show all");
  });
});
