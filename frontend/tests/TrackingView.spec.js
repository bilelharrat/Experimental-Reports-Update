import { describe, expect, it, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { ref } from "vue";
import TrackingView from "../src/views/TrackingView.vue";
import { trackedCompanyIds } from "../src/state.js";

const RouterLinkStub = {
  props: ["to"],
  template: "<a><slot /></a>",
};

describe("TrackingView", () => {
  beforeEach(() => {
    trackedCompanyIds.value = new Set(["nvda"]);
  });

  it("renders denser tracked boards and a news board", () => {
    const wrapper = mount(TrackingView, {
      global: {
        stubs: { RouterLink: RouterLinkStub },
        provide: {
          workspaceCompanies: ref([
            {
              id: "nvda",
              name: "NVIDIA",
              status: "public",
              company_type: "public",
              change_pct_1d: 2.4,
            },
          ]),
          workspaceNews: ref([
            {
              id: "n1",
              title: "NVIDIA ships a new accelerator",
              captured_at: "2026-08-18T00:00:00Z",
            },
          ]),
          workspaceLoading: ref(false),
        },
      },
    });

    expect(wrapper.text()).toContain("Following");
    expect(wrapper.text()).toContain("NVIDIA");
    expect(wrapper.text()).toContain("NVIDIA ships a new accelerator");
    expect(wrapper.text()).toContain("News Board");
    expect(wrapper.text()).toContain("Up +2.4%");
  });
});
