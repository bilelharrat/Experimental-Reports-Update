import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import Sidebar from "../src/components/Sidebar.vue";

const RouterLinkStub = {
  props: ["to"],
  template: "<a><slot /></a>",
};

describe("Sidebar", () => {
  it("does not render recent-report links without a company_id", () => {
    const wrapper = mount(Sidebar, {
      props: {
        loading: false,
        reports: [
          {
            id: "routeable",
            company_id: "acme-inc",
            company_name: "Acme Inc.",
            report_type: "Investment Memo",
            audience: "IC",
            status: "complete",
          },
          {
            id: "unrouteable",
            company_id: null,
            company_name: "Hormuz Appendix",
            report_type: "Daily Appendix",
            audience: null,
            status: "complete",
          },
        ],
      },
      global: {
        stubs: {
          RouterLink: RouterLinkStub,
        },
      },
    });

    expect(wrapper.text()).toContain("Acme Inc.");
    expect(wrapper.text()).not.toContain("Hormuz Appendix");
  });
});
