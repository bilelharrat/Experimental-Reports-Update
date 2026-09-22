import { afterEach, describe, expect, it, vi } from "vitest";
import { flushPromises } from "@vue/test-utils";
import { ref } from "vue";

vi.mock("../src/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, api: { ...actual.api, quotesNews: vi.fn() } };
});

import { api } from "../src/api.js";
import { companyReports, useTickerNewsFeed } from "../src/companyPages.js";

describe("company page helpers", () => {
  afterEach(() => vi.clearAllMocks());

  it("lists one company's reports, newest first", () => {
    const rows = companyReports(
      [
        { id: "a", company_id: "acme", created_at: "2026-08-01T00:00:00Z" },
        { id: "b", company_id: "other", created_at: "2026-09-09T00:00:00Z" },
        { id: "c", company_id: "acme", created_at: "2026-09-01T00:00:00Z" },
      ],
      "acme",
    );
    expect(rows.map((r) => r.id)).toEqual(["c", "a"]);
    expect(companyReports([{ id: "a", company_id: "acme" }], "")).toEqual([]);
  });

  it("settles a ticker's headlines only once the wire answers", async () => {
    let answer;
    api.quotesNews.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    const ticker = ref("intc");
    const { items, settled } = useTickerNewsFeed(ticker);

    expect(api.quotesNews).toHaveBeenCalledWith({ tickers: ["INTC"], limit: 30 });
    expect(settled.value).toBe(false);
    answer({ items: [{ id: "n1", title: "Intel shares jump" }] });
    await flushPromises();
    expect(settled.value).toBe(true);
    expect(items.value.map((item) => item.id)).toEqual(["n1"]);

    // No ticker (a private company): nothing to ask, settled at once.
    ticker.value = "";
    await flushPromises();
    expect(settled.value).toBe(true);
    expect(items.value).toEqual([]);
  });

  it("settles on a failed call too, with nothing added", async () => {
    api.quotesNews.mockRejectedValue(new Error("offline"));
    const { items, settled } = useTickerNewsFeed(ref("AMD"));
    await flushPromises();
    expect(settled.value).toBe(true);
    expect(items.value).toEqual([]);
  });
});
