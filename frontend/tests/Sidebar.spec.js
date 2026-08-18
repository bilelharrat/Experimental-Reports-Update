import { describe, expect, it, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import Sidebar from "../src/components/Sidebar.vue";
import { setSidebarCollapsed } from "../src/state.js";

const RouterLinkStub = {
  props: ["to"],
  template: "<a><slot /></a>",
};

function mountSidebar() {
  return mount(Sidebar, {
    props: {
      loading: false,
      companies: [
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
      ],
    },
    global: {
      stubs: {
        RouterLink: RouterLinkStub,
      },
    },
  });
}

describe("Sidebar", () => {
  beforeEach(() => {
    setSidebarCollapsed(false);
  });

  it("renders company buckets and destinations without duplicate add or radar", () => {
    const wrapper = mountSidebar();

    expect(wrapper.text()).toContain("Portfolio");
    expect(wrapper.text()).toContain("Top Players");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("Weekly Summary");
    expect(wrapper.text()).toContain("Stock");
    expect(wrapper.text()).toContain("Stats");
    expect(wrapper.text()).toContain("Innovation Lab");
    expect(wrapper.text()).not.toContain("Pipeline");
    expect(wrapper.text()).not.toContain("Quick Intake");
    expect(wrapper.text()).not.toContain("Market Radar");
    expect(wrapper.text()).not.toContain("Settings");
    expect(wrapper.text()).not.toContain("Profile");
    expect(wrapper.text()).not.toContain("Sign out");
    expect(wrapper.text()).not.toContain("Hormuz Research");
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
    expect(wrapper.text()).toContain("Weekly Summary");
  });
});
