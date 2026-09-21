import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api.js", () => {
  const mock = { getCompanyEarningsFilings: vi.fn() };
  return { default: mock, api: mock };
});

import api from "../src/api.js";
import EarningsFilingsCard from "../src/components/research/EarningsFilingsCard.vue";

// A listed company's Overview leads with this instead of a VC deal pipeline:
// when it next reports, how recent quarters landed against the estimate,
// and what it has filed.

async function mountCard(payload) {
  api.getCompanyEarningsFilings.mockResolvedValue(payload);
  const wrapper = mount(EarningsFilingsCard, { props: { companyId: "aapl" } });
  await flushPromises();
  return wrapper;
}

describe("EarningsFilingsCard", () => {
  it("shows the next report, quarters against estimates and filings", async () => {
    const wrapper = await mountCard({
      ticker: "AAPL",
      earnings: {
        next_date: "2026-10-29",
        next_estimated: true,
        days_to_next: 38,
        history: [
          { period: "Jun 2026", reported: "2026-07-30", eps: 1.62, estimate: 1.5, surprise_pct: 8 },
          { period: "Mar 2026", reported: "2026-04-30", eps: 1.4, estimate: 1.45, surprise_pct: -3.4 },
        ],
      },
      filings: [
        { form: "10-Q", filed: "2026-08-01", description: "Quarterly report", url: "https://sec.gov/a", material: true },
        { form: "4", filed: "2026-08-10", description: "Insider", url: "https://sec.gov/b", material: false },
      ],
      error: null,
    });

    const next = wrapper.get('[data-testid="next-earnings"]').text();
    expect(next).toContain("2026-10-29");
    expect(next).toContain("in 38 days · estimated");

    const quarters = wrapper.findAll('[data-testid="earnings-quarter"]');
    expect(quarters).toHaveLength(2);
    expect(quarters[0].text()).toContain("EPS $1.62 vs $1.50");
    expect(quarters[0].text()).toContain("+8.0%");
    expect(quarters[1].text()).toContain("-3.4%");

    // newest first: the Aug 10 insider trade, then the Aug 1 10-Q
    const filings = wrapper.findAll('[data-testid="filing-row"]');
    expect(filings.map((f) => f.attributes("href"))).toEqual(["https://sec.gov/b", "https://sec.gov/a"]);
    expect(filings[1].text()).toContain("Material");
    expect(filings[0].text()).not.toContain("Material");
  });

  it("says why there are no filings when EDGAR has none", async () => {
    const wrapper = await mountCard({
      ticker: "JOYY",
      earnings: { next_date: null, history: [] },
      filings: [],
      error: "No CIK for ticker (not SEC-registered or ticker map unavailable)",
    });
    expect(wrapper.text()).toContain("No CIK for ticker");
    expect(wrapper.text()).toContain("No earnings history available");
  });

  it("offers a retry when the request fails", async () => {
    api.getCompanyEarningsFilings.mockRejectedValue(new Error("offline"));
    const wrapper = mount(EarningsFilingsCard, { props: { companyId: "aapl" } });
    await flushPromises();
    expect(wrapper.text()).toContain("couldn't be loaded");
  });

  it("names bare forms and keeps a quarterly report in view", async () => {
    const insider = (day) => ({
      form: "4",
      filed: `2026-09-${day}`,
      description: "FORM 4",
      url: `https://sec.gov/${day}`,
      material: false,
    });
    const wrapper = await mountCard({
      ticker: "AAPL",
      earnings: { next_date: null, history: [] },
      filings: [
        insider("20"), insider("18"), insider("16"), insider("14"), insider("12"), insider("10"),
        { form: "10-Q", filed: "2026-08-01", description: "", url: "https://sec.gov/q", material: true },
      ],
    });
    const rows = wrapper.findAll('[data-testid="filing-row"]');
    expect(rows).toHaveLength(5);
    expect(rows[0].text()).toContain("Insider transaction");
    expect(rows[0].text()).not.toContain("FORM 4");
    // the 10-Q is older than every insider trade but still makes the cut
    expect(rows[4].text()).toContain("Quarterly report");
  });
});
