import { describe, expect, it } from "vitest";
import { collapseRuns } from "../src/collapseRuns.js";

describe("collapseRuns", () => {
  it("folds consecutive rows with the same key", () => {
    const runs = collapseRuns(["a", "a", "b", "a"], (x) => x);
    expect(runs.map((r) => [r.key, r.count])).toEqual([
      ["a", 2],
      ["b", 1],
      ["a", 1],
    ]);
  });

  it("keeps the first and last row of each run", () => {
    const [run] = collapseRuns(
      [{ id: 3, e: "x" }, { id: 2, e: "x" }, { id: 1, e: "x" }],
      (r) => r.e,
    );
    expect(run.first.id).toBe(3);
    expect(run.last.id).toBe(1);
  });

  it("handles nothing", () => {
    expect(collapseRuns(undefined, (x) => x)).toEqual([]);
  });
});
