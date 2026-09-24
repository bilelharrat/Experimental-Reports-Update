import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";

const apiMock = vi.hoisted(() => ({ getMemoNumberLint: vi.fn() }));

vi.mock("../src/api.js", () => ({
  api: apiMock,
  default: apiMock,
  withApiToken: (u) => u,
}));

import NumberLintCard from "../src/components/research/NumberLintCard.vue";
import { setAppLanguage } from "../src/state.js";

// GET /api/companies/zainar-inc/memo-number-lint as the server answers it
// today: a thin corpus, 64 figures matching only the registry.
const ZAINAR_THIN = {
  company_id: "zainar-inc",
  memo_package: "data/memos/zainar-inc/…/logs/memo_package.json",
  checked: 254,
  supported: 136,
  unsupported: 118,
  coverage_pct: 54,
  status: "warn",
  thin_corpus: true,
  findings: [
    {
      section: "Executive Summary",
      number: "42x",
      excerpt: "…which places the February mark at about 42x current revenue…",
      code: "unsupported_figure",
    },
  ],
  sources: ["company record"],
  summary: {
    checked: 254,
    verified: 0,
    found_elsewhere: 0,
    in_context: 0,
    derived: 0,
    company_reported: 0,
    registry_only: 64,
    not_traced: 190,
    unsupported: 118,
    coverage_pct: null,
    thin_corpus: true,
    p0_count: 0,
    status: "not_checkable",
    basis: "tiered",
  },
  note: "A figure counts as supported when a source on file carries the same value in any spelling…",
};

let wrapper;

function mountCard(payload) {
  apiMock.getMemoNumberLint.mockResolvedValue(payload);
  wrapper = mount(NumberLintCard, { props: { companyId: "zainar-inc" } });
  return wrapper;
}

describe("NumberLintCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setAppLanguage("en");
  });

  afterEach(() => {
    wrapper?.unmount();
    wrapper = null;
    setAppLanguage("en");
  });

  it("calls a thin corpus not checkable instead of printing a percentage", async () => {
    mountCard(ZAINAR_THIN);
    await flushPromises();
    const headline = wrapper.get('[data-testid="number-lint-headline"]');
    expect(headline.text()).toBe("Not checkable: no sources on file");
    expect(headline.attributes("data-state")).toBe("not_checkable");
    expect(wrapper.text()).not.toMatch(/\d+%/);
    expect(wrapper.find('[data-testid="number-lint-bar"]').exists()).toBe(false);
    // The registry-only figures are named for what they are.
    expect(wrapper.get('[data-testid="number-lint-thin"]').text()).toContain(
      "64 match the registry, not evidence",
    );
  });

  it("shows verified, found elsewhere, derived and not traced figures separately", async () => {
    mountCard({
      ...ZAINAR_THIN,
      thin_corpus: false,
      unsupported: 3,
      summary: {
        ...ZAINAR_THIN.summary,
        checked: 40,
        verified: 12,
        found_elsewhere: 20,
        derived: 3,
        company_reported: 0,
        registry_only: 2,
        not_traced: 3,
        thin_corpus: false,
        status: "warn",
        coverage_pct: 88,
      },
    });
    await flushPromises();
    expect(wrapper.get('[data-testid="number-lint-headline"]').text()).toBe(
      "35 of 40 figures found in sources on file",
    );
    const tiers = wrapper.findAll('[data-testid="number-lint-tiers"] [data-tier]');
    expect(tiers.map((tier) => tier.text())).toEqual([
      "12 verified",
      "20 found elsewhere",
      "3 derived",
      "2 match the registry, not evidence",
      "3 not traced",
    ]);
    expect(wrapper.findAll('[data-testid="number-lint-bar"] > div')).toHaveLength(5);
    expect(wrapper.text()).not.toContain("traced to a source");
  });

  it("reads an older payload in honest words", async () => {
    mountCard({
      memo_package: "x",
      checked: 20,
      supported: 18,
      unsupported: 2,
      coverage_pct: 90,
      findings: [],
      sources: [],
    });
    await flushPromises();
    expect(wrapper.get('[data-testid="number-lint-headline"]').text()).toBe(
      "18 of 20 figures found in sources on file",
    );
  });

  it("says when there is no memo, and speaks Chinese", async () => {
    mountCard({ memo_package: null, checked: 0, supported: 0, unsupported: 0, findings: [], note: "No memo package on record" });
    await flushPromises();
    expect(wrapper.text()).toContain("No memo yet");
    wrapper.unmount();

    setAppLanguage("zh");
    mountCard(ZAINAR_THIN);
    await flushPromises();
    expect(wrapper.get('[data-testid="number-lint-headline"]').text()).toBe("无法核查：没有在库来源");
  });
});
