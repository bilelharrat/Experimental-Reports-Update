import { beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api.js", () => {
  const mock = { getDealPipeline: vi.fn(), updateDealPipeline: vi.fn() };
  return { default: mock, api: mock };
});

import api from "../src/api.js";
import DealPipelineCard from "../src/components/research/DealPipelineCard.vue";

// Intro path, last touchpoint and next step were display-only, so they read
// "Not recorded" on every company. They edit in place now, and a next step
// past its due date turns the tile red.

const base = {
  stage: "Sourced",
  stages: ["Sourced", "Partner Intro", "Technical Diligence", "Term Sheet / IC", "Portfolio"],
  days_in_stage: 4,
  intro_path: null,
  last_touchpoint: null,
  next_step: null,
  next_step_due: null,
  next_step_overdue: false,
};

async function mountCard(pipeline = base) {
  api.getDealPipeline.mockResolvedValue(pipeline);
  const wrapper = mount(DealPipelineCard, { props: { companyId: "zainar-inc" } });
  await flushPromises();
  return wrapper;
}

describe("DealPipelineCard inline editing", () => {
  beforeEach(() => vi.clearAllMocks());

  it("edits the intro path in place and saves it", async () => {
    api.updateDealPipeline.mockResolvedValue({ ...base, intro_path: "Via Dana at Lux" });
    const wrapper = await mountCard();
    const tile = wrapper.get('[data-testid="pipeline-intro_path"]');
    expect(tile.text()).toContain("Not recorded");

    await tile.get("button").trigger("click");
    await tile.get("textarea").setValue("Via Dana at Lux");
    await tile.get("textarea").trigger("keydown", { key: "Enter" });
    await flushPromises();

    expect(api.updateDealPipeline).toHaveBeenCalledWith("zainar-inc", { intro_path: "Via Dana at Lux" });
    expect(wrapper.get('[data-testid="pipeline-intro_path"]').text()).toContain("Via Dana at Lux");
  });

  it("saves a next step with its due date", async () => {
    api.updateDealPipeline.mockResolvedValue({
      ...base,
      next_step: "Send term sheet",
      next_step_due: "2026-09-30",
    });
    const wrapper = await mountCard();
    const tile = wrapper.get('[data-testid="pipeline-next_step"]');
    await tile.get("button").trigger("click");
    await tile.get("textarea").setValue("Send term sheet");
    await tile.get('[data-testid="pipeline-next-step-due"]').setValue("2026-09-30");
    await tile.findAll("button")[0].trigger("click");
    await flushPromises();

    expect(api.updateDealPipeline).toHaveBeenCalledWith("zainar-inc", {
      next_step: "Send term sheet",
      next_step_due: "2026-09-30",
    });
    expect(wrapper.get('[data-testid="pipeline-due"]').text()).toBe("Due 2026-09-30");
  });

  it("flags an overdue next step", async () => {
    const wrapper = await mountCard({
      ...base,
      next_step: "Call the CFO",
      next_step_due: "2026-09-01",
      next_step_overdue: true,
    });
    expect(wrapper.get('[data-testid="pipeline-due"]').text()).toBe("Overdue · was due 2026-09-01");
    expect(wrapper.get('[data-testid="pipeline-next_step"]').attributes("style")).toContain("--mac-red");
  });

  it("Escape abandons an edit without saving", async () => {
    const wrapper = await mountCard();
    const tile = wrapper.get('[data-testid="pipeline-last_touchpoint"]');
    await tile.get("button").trigger("click");
    await tile.get("textarea").setValue("draft");
    await tile.get("textarea").trigger("keydown", { key: "Escape" });
    expect(api.updateDealPipeline).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="pipeline-last_touchpoint"]').text()).toContain("Not recorded");
  });
});
