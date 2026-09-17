import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { confirmTokenSpend } from "../src/confirmTokens.js";
import { appLanguage } from "../src/state.js";

describe("confirmTokenSpend", () => {
  let confirmSpy;

  beforeEach(() => {
    confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    confirmSpy.mockRestore();
    appLanguage.value = "en";
  });

  it("warns that the action costs tokens", () => {
    expect(confirmTokenSpend()).toBe(true);
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(confirmSpy.mock.calls[0][0]).toContain("cost tokens");
  });

  it("warns in Chinese when the app is in Chinese", () => {
    appLanguage.value = "zh";
    confirmTokenSpend();
    expect(confirmSpy.mock.calls[0][0]).toContain("Token");
    expect(confirmSpy.mock.calls[0][0]).toContain("消耗");
  });

  it("appends the caller's detail line under the warning", () => {
    confirmTokenSpend("Rewrites 16 headlines.");
    const shown = confirmSpy.mock.calls[0][0];
    expect(shown).toContain("cost tokens");
    expect(shown).toContain("Rewrites 16 headlines.");
  });

  it("returns false when the user cancels, so the caller stops", () => {
    confirmSpy.mockReturnValue(false);
    expect(confirmTokenSpend()).toBe(false);
  });
});
