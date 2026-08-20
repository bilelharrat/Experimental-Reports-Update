import { describe, expect, it } from "vitest";
import { companyBucket, sortCompanies } from "../src/companyLists.js";

describe("companyLists", () => {
  it("puts public tickers in Top Players and private names in Portfolio", () => {
    const apple = { id: "aapl", name: "Apple", company_type: "public", ticker: "AAPL" };
    const acme = { id: "acme", name: "Acme", company_type: "private" };
    expect(companyBucket(apple)).toBe("watchlist");
    expect(companyBucket(acme)).toBe("portfolio");
    expect(sortCompanies([apple, acme], { sort: "az" }).map((row) => row.id)).toEqual([
      "acme",
      "aapl",
    ]);
  });
});
