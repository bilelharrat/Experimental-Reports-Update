import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api.js", () => {
  const mock = { getSignalScore: vi.fn() };
  return { default: mock, api: mock };
});

import api from "../src/api.js";
import SignalScoreCard from "../src/components/research/SignalScoreCard.vue";

// ZaiNar showed a full-strength 85 built from 2 of its 6 components, with
// the coverage only in the caption. A partial score now says so beside the
// title and its ring is dimmed; a well-covered score looks as it did.

function components(available, total) {
  return Array.from({ length: total }, (_, i) => ({
    name: `c${i}`,
    available: i < available,
    points: 10,
    max: 20,
  }));
}

async function mountScore(payload) {
  api.getSignalScore.mockResolvedValue(payload);
  const wrapper = mount(SignalScoreCard, { props: { companyId: "zainar" } });
  await flushPromises();
  return wrapper;
}

describe("SignalScoreCard coverage", () => {
  it("flags a score built from under half its components", async () => {
    const wrapper = await mountScore({ score: 85, components: components(2, 6) });
    expect(wrapper.get('[data-testid="signal-partial"]').text()).toBe("Partial · 2 of 6");
    expect(wrapper.get('[data-testid="signal-ring"]').attributes("opacity")).toBe("0.4");
  });

  it("leaves a well-covered score alone", async () => {
    const wrapper = await mountScore({ score: 72, components: components(4, 6) });
    expect(wrapper.find('[data-testid="signal-partial"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="signal-ring"]').attributes("opacity")).toBe("1");
  });

  it("does not flag a score it is not showing", async () => {
    const wrapper = await mountScore({
      score: null,
      is_insufficient: true,
      components: components(1, 6),
    });
    expect(wrapper.find('[data-testid="signal-partial"]').exists()).toBe(false);
  });
});
