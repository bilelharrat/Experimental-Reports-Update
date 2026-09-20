import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// The client used to decide this from the URL: localhost on a dev port
// meant "no sign-in needed", whatever the server actually did. With the
// bypass turned off that walked the SPA straight past its own sign-in
// wall into a desk whose every request 401s.
describe("anon-dev is the server's answer, not a guess from the URL", () => {
  let auth;

  beforeEach(async () => {
    vi.resetModules();
    document.head.innerHTML = "";
    auth = await import("../src/auth.js");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.head.innerHTML = "";
  });

  it("does not claim anon dev on a dev port when the server enforces auth", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 401 })));
    expect(await auth.probeAnonDev()).toBe(false);
    expect(auth.isAnonDev()).toBe(false);
    expect(auth.isAuthenticated.value).toBe(false);
  });

  it("believes the server when it says the bypass is on", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ auth: "anon_dev" }) })),
    );
    expect(await auth.probeAnonDev()).toBe(true);
    expect(auth.isAnonDev()).toBe(true);
  });

  it("takes the served meta tag without asking", async () => {
    document.head.innerHTML = '<meta name="bsh-research-anon-dev" content="1">';
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    expect(await auth.probeAnonDev()).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("fails closed when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    expect(await auth.probeAnonDev()).toBe(false);
  });

  it("asks once per boot", async () => {
    const fetchSpy = vi.fn(async () => ({ ok: false, status: 401 }));
    vi.stubGlobal("fetch", fetchSpy);
    await auth.probeAnonDev();
    await auth.probeAnonDev();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });
});
