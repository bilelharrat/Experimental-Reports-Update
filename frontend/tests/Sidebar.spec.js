import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Sidebar from "../src/components/Sidebar.vue";

const RouterLinkStub = {
  props: ["to"],
  template: "<a><slot /></a>",
};

describe("Sidebar", () => {
  it("renders PRD rail buckets from companies instead of report links", () => {
    const wrapper = mount(Sidebar, {
      props: {
        loading: false,
        reports: [
          {
            id: "unrouteable",
            company_id: null,
            company_name: "Hormuz Appendix",
            report_type: "Daily Appendix",
            status: "complete",
          },
        ],
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

    expect(wrapper.text()).toContain("Quick Intake");
    expect(wrapper.text()).toContain("Portfolio");
    expect(wrapper.text()).toContain("Top Players");
    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("Market Radar");
    expect(wrapper.text()).toContain("Stock");
    expect(wrapper.text()).toContain("Innovation Lab");
    expect(wrapper.text()).not.toContain("Settings");
    expect(wrapper.text()).not.toContain("Profile");
    expect(wrapper.text()).not.toContain("Hormuz Appendix");
    expect(wrapper.text()).not.toContain("Hormuz Research");
  });
});
