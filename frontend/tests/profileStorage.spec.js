import { describe, it, expect, beforeEach } from "vitest";
import { ensureProfileFor, currentProfileOwner, DEVICE_KEYS } from "../src/profileStorage.js";

// A second account on the same browser inherited the first one's recently
// opened companies, favourites, market desk and the fact the welcome tour
// had been seen. Each account gets its own state now.
describe("per-account browser state", () => {
  beforeEach(() => localStorage.clear());

  it("gives a second account a clean store and keeps the first one's aside", () => {
    localStorage.setItem("bsh.profile.owner", "one@example.com");
    localStorage.setItem("bsh.welcomeTourSeen", "2");
    localStorage.setItem("bsh.lastCompanyId", "zainar-inc");
    localStorage.setItem("bsh.companyViews", '{"zainar-inc":3}');

    expect(ensureProfileFor("two@example.com")).toBe(true);

    expect(localStorage.getItem("bsh.welcomeTourSeen")).toBeNull();
    expect(localStorage.getItem("bsh.lastCompanyId")).toBeNull();
    expect(localStorage.getItem("bsh.companyViews")).toBeNull();
    expect(currentProfileOwner()).toBe("two@example.com");
    const stashed = JSON.parse(localStorage.getItem("bsh.profile.stash.one@example.com"));
    expect(stashed["bsh.welcomeTourSeen"]).toBe("2");
    expect(stashed["bsh.lastCompanyId"]).toBe("zainar-inc");
  });

  it("brings an account's own state back when it returns", () => {
    localStorage.setItem("bsh.profile.owner", "one@example.com");
    localStorage.setItem("bsh.lastCompanyId", "apple-inc");
    ensureProfileFor("two@example.com");
    localStorage.setItem("bsh.lastCompanyId", "koch-inc");

    expect(ensureProfileFor("one@example.com")).toBe(true);
    expect(localStorage.getItem("bsh.lastCompanyId")).toBe("apple-inc");
    // Two's state went aside in turn, and its stash is spent on restore.
    expect(JSON.parse(localStorage.getItem("bsh.profile.stash.two@example.com"))["bsh.lastCompanyId"]).toBe("koch-inc");
    expect(localStorage.getItem("bsh.profile.stash.one@example.com")).toBeNull();
  });

  it("is a no-op for the account already held", () => {
    localStorage.setItem("bsh.profile.owner", "one@example.com");
    localStorage.setItem("bsh.lastCompanyId", "apple-inc");
    expect(ensureProfileFor("One@Example.com")).toBe(false);
    expect(localStorage.getItem("bsh.lastCompanyId")).toBe("apple-inc");
  });

  it("never hands ownerless state to whoever signs in first", () => {
    // State from before profiles existed: it has no owner, and the very
    // report that prompted this was a new account seeing it.
    localStorage.setItem("bsh.welcomeTourSeen", "2");
    localStorage.setItem("bsh.companyViews", '{"zainar-inc":3}');
    expect(ensureProfileFor("new@example.com")).toBe(true);
    expect(localStorage.getItem("bsh.welcomeTourSeen")).toBeNull();
    expect(localStorage.getItem("bsh.companyViews")).toBeNull();
    expect(JSON.parse(localStorage.getItem("bsh.profile.stash.__legacy__"))["bsh.welcomeTourSeen"]).toBe("2");
  });

  it("leaves the device's own keys alone", () => {
    localStorage.setItem("bsh.profile.owner", "one@example.com");
    localStorage.setItem("bsh.research.session", '{"token":"t"}');
    localStorage.setItem("bsh.research.appearance", "dark");
    localStorage.setItem("bsh.appLanguage", "zh");
    localStorage.setItem("bsh.sidebarCollapsed", "1");
    localStorage.setItem("not-ours", "x");
    ensureProfileFor("two@example.com");
    for (const key of DEVICE_KEYS) expect(localStorage.getItem(key)).not.toBeNull();
    expect(localStorage.getItem("not-ours")).toBe("x");
  });

  it("does nothing without an email", () => {
    localStorage.setItem("bsh.lastCompanyId", "apple-inc");
    expect(ensureProfileFor("")).toBe(false);
    expect(localStorage.getItem("bsh.lastCompanyId")).toBe("apple-inc");
  });
});
