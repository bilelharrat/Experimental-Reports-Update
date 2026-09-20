import { describe, expect, it, vi, beforeEach } from "vitest";
import { flushPromises, mount } from "@vue/test-utils";
import FactLedgerCard from "../src/components/research/FactLedgerCard.vue";
import { api } from "../src/api.js";

vi.mock("../src/api.js", () => {
  const mock = {
    getFactLedger: vi.fn(),
    putFactLedger: vi.fn(),
  };
  return { default: mock, api: mock };
});

const ledger = (text, extra = {}) => ({
  company_id: "zainar-inc",
  exists: Boolean(text),
  text,
  path: "data/research/zainar-inc/fact_ledger.md",
  updated_at: text ? "2026-09-20T10:00:00+00:00" : null,
  max_chars: 6000,
  enabled: true,
  ...extra,
});

describe("FactLedgerCard", () => {
  beforeEach(() => {
    api.getFactLedger.mockReset();
    api.putFactLedger.mockReset();
  });

  it("loads the ledger and shows the empty-state hint when there is none", async () => {
    api.getFactLedger.mockResolvedValue(ledger(""));
    const wrapper = mount(FactLedgerCard, { props: { companyId: "zainar-inc" } });
    await flushPromises();
    expect(api.getFactLedger).toHaveBeenCalledWith("zainar-inc");
    expect(wrapper.text()).toContain("No ledger yet");
    expect(wrapper.find('[data-testid="ledger-save"]').attributes("disabled")).toBeDefined();
    expect(wrapper.find('[data-testid="ledger-count"]').text()).toBe("0 / 6000");
  });

  it("saves an edited ledger and reflects the server's copy", async () => {
    api.getFactLedger.mockResolvedValue(ledger("- 2026-06-13: $500M+ book."));
    api.putFactLedger.mockImplementation(async (_id, text) => ledger(text.trim()));
    const wrapper = mount(FactLedgerCard, { props: { companyId: "zainar-inc" } });
    await flushPromises();
    expect(wrapper.text()).toContain("Updated 2026-09-20");
    const textarea = wrapper.find('[data-testid="ledger-text"]');
    expect(textarea.element.value).toBe("- 2026-06-13: $500M+ book.");
    await textarea.setValue("- 2026-06-13: $500M+ book.\n- 2026-04-20: Tokyo GX.");
    const save = wrapper.find('[data-testid="ledger-save"]');
    expect(save.attributes("disabled")).toBeUndefined();
    await save.trigger("click");
    await flushPromises();
    expect(api.putFactLedger).toHaveBeenCalledWith(
      "zainar-inc",
      "- 2026-06-13: $500M+ book.\n- 2026-04-20: Tokyo GX.",
    );
    expect(wrapper.find('[data-testid="ledger-saved"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="ledger-save"]').attributes("disabled")).toBeDefined();
  });

  it("refuses to save past the loader's limit and shows the count in red", async () => {
    api.getFactLedger.mockResolvedValue(ledger("", { max_chars: 20 }));
    const wrapper = mount(FactLedgerCard, { props: { companyId: "zainar-inc" } });
    await flushPromises();
    await wrapper.find('[data-testid="ledger-text"]').setValue("x".repeat(25));
    expect(wrapper.find('[data-testid="ledger-count"]').text()).toBe("25 / 20");
    expect(wrapper.find('[data-testid="ledger-save"]').attributes("disabled")).toBeDefined();
    await wrapper.find('[data-testid="ledger-save"]').trigger("click");
    expect(api.putFactLedger).not.toHaveBeenCalled();
  });

  it("reports a failed save without losing the draft", async () => {
    api.getFactLedger.mockResolvedValue(ledger(""));
    api.putFactLedger.mockRejectedValue(new Error("500"));
    const wrapper = mount(FactLedgerCard, { props: { companyId: "zainar-inc" } });
    await flushPromises();
    await wrapper.find('[data-testid="ledger-text"]').setValue("- a fact");
    await wrapper.find('[data-testid="ledger-save"]').trigger("click");
    await flushPromises();
    expect(wrapper.text()).toContain("Could not save the ledger");
    expect(wrapper.find('[data-testid="ledger-text"]').element.value).toBe("- a fact");
  });

  it("reloads when the company changes", async () => {
    api.getFactLedger.mockResolvedValue(ledger("- one"));
    const wrapper = mount(FactLedgerCard, { props: { companyId: "zainar-inc" } });
    await flushPromises();
    api.getFactLedger.mockResolvedValue(ledger("- two"));
    await wrapper.setProps({ companyId: "nvda" });
    await flushPromises();
    expect(api.getFactLedger).toHaveBeenLastCalledWith("nvda");
    expect(wrapper.find('[data-testid="ledger-text"]').element.value).toBe("- two");
  });
});
