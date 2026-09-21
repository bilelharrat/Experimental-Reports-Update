import { describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

vi.mock("../src/api.js", () => {
  const mock = { getCompanyProfile: vi.fn() };
  return { default: mock, api: mock };
});

import api from "../src/api.js";
import UnifiedProfileCard from "../src/components/research/UnifiedProfileCard.vue";

// ZaiNar's profile said "ARR —" while the memo panel on the same page quoted
// "~$24M as of 2026-06-13". Both now read the company record's figures.

async function mountCard(profile, company = { id: "zainar-inc", name: "ZaiNar" }) {
  api.getCompanyProfile.mockResolvedValue(profile);
  const wrapper = mount(UnifiedProfileCard, { props: { companyId: company.id, company } });
  await flushPromises();
  return wrapper;
}

describe("UnifiedProfileCard reported figures", () => {
  it("shows the recorded ARR with its date and source", async () => {
    const wrapper = await mountCard({
      found: true,
      is_public: false,
      private: null,
      reported: {
        arr: { label: "ARR", value: "~$24M", as_of: "2026-06-13", source_class: "BSH diligence" },
      },
    });
    const arr = wrapper.get('[data-testid="profile-arr"]');
    expect(arr.text()).toBe("~$24M");
    expect(arr.attributes("title")).toBe("ARR · as of 2026-06-13 · BSH diligence");
    expect(wrapper.text()).toContain("2026-06");
  });

  it("prefers the portfolio KPI when there is one", async () => {
    const wrapper = await mountCard({
      found: true,
      is_public: false,
      private: { position: {}, latest_kpi: { arr_usd: 30000000 } },
      reported: { arr: { label: "ARR", value: "~$24M", as_of: "2026-06-13" } },
    });
    expect(wrapper.get('[data-testid="profile-arr"]').text()).toBe("$30.0M");
  });

  it("still says so when nothing is recorded", async () => {
    const wrapper = await mountCard({
      found: true,
      is_public: false,
      private: null,
      reported: {},
    }, { id: "zainar-inc", name: "ZaiNar", metrics: [] });
    expect(wrapper.get('[data-testid="profile-arr"]').text()).toBe("—");
  });

  it("shows how the market values a listed company instead of VC fields", async () => {
    const wrapper = await mountCard(
      {
        found: true,
        is_public: true,
        private: null,
        public: {
          ticker: "AAPL",
          last_price: 338.17,
          change_pct_1d: 0.61,
          market_cap: 4.9e12,
          pe_ratio: 41.23,
          eps: 8.2,
          fifty_two_week_low: 201.5,
          fifty_two_week_high: 350,
          dividend_yield: 0.0031,
        },
        thesis_fit: { score: 0 },
        pipeline: { stage: "Sourced" },
        reported: {},
      },
      { id: "aapl", name: "Apple Inc.", ticker: "AAPL", status: "public" },
    );
    const market = wrapper.get('[data-testid="profile-market"]').text();
    expect(market).toContain("41.2");
    expect(market).toContain("$8.20");
    expect(market).toContain("$201.50 – $350.00");
    expect(market).toContain("0.31%");
    expect(wrapper.find('[data-testid="profile-arr"]').exists()).toBe(false);
    // no VC stage or thesis fit for a listed name
    expect(wrapper.text()).not.toContain("Thesis fit");
  });

  it("keeps the position rows when the firm holds a listed company", async () => {
    const wrapper = await mountCard(
      {
        found: true,
        is_public: true,
        private: { position: { round: "Public", invested_usd: 5000000 } },
        public: { ticker: "AAPL", last_price: 338 },
        reported: {},
      },
      { id: "aapl", name: "Apple Inc.", ticker: "AAPL", status: "public" },
    );
    expect(wrapper.find('[data-testid="profile-market"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="profile-arr"]').exists()).toBe(true);
  });
});
