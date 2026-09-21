import { describe, it, expect, vi, afterEach } from "vitest";

// `isAuthenticated` also lets in a server's local anon-dev bypass, where
// nobody is signed in. The account UI goes by `isSignedIn` instead, so it
// never offers Sign out when there is nothing to sign out of.
describe("signed in, as opposed to let in by the anon-dev bypass", () => {
  const STORED = {
    token: "stored-token",
    email: "old.hand@bshfoundation.org",
    expires_at: "2999-01-01T00:00:00Z",
  };

  async function boot({ stored = null, anonDev = false } = {}) {
    vi.resetModules();
    localStorage.clear();
    document.head.innerHTML = anonDev ? '<meta name="bsh-research-anon-dev" content="1">' : "";
    if (stored) {
      localStorage.setItem("bsh.research.session", JSON.stringify(stored));
      // The browser already holds this account's desk state, so keeping the
      // session is not a profile switch (which would reload the page).
      localStorage.setItem("bsh.profile.owner", stored.email);
    }
    const auth = await import("../src/auth.js");
    const { api } = await import("../src/api.js");
    return { auth, api };
  }

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    document.head.innerHTML = "";
  });

  it("lets the bypass in without counting it as a sign-in", async () => {
    const { auth } = await boot({ anonDev: true });
    expect(auth.isAuthenticated.value).toBe(true);
    expect(auth.isSignedIn.value).toBe(false);
  });

  it("counts a personal session as signed in", async () => {
    const { auth } = await boot({ stored: STORED, anonDev: true });
    expect(auth.isSignedIn.value).toBe(true);
  });

  it("asks for the sign-in form only where the login route would bounce", async () => {
    let { auth } = await boot();
    expect(auth.signInRoute("/settings")).toEqual({ name: "login", query: { next: "/settings" } });

    ({ auth } = await boot({ anonDev: true }));
    expect(auth.signInRoute("/settings")).toEqual({
      name: "login",
      query: { switch: "1", next: "/settings" },
    });
    expect(auth.signInRoute()).toEqual({ name: "login", query: { switch: "1" } });
  });

  it("drops a session the anon-dev server no longer accepts", async () => {
    // Such a server answers a dead token as the local operator, not a 401.
    const { auth, api } = await boot({ stored: STORED, anonDev: true });
    vi.spyOn(api, "me").mockResolvedValue({ email: null, name: "Bilel Harrat", auth: "anon_dev" });

    expect(await auth.validateSession()).toBe(false);
    expect(auth.isSignedIn.value).toBe(false);
    expect(localStorage.getItem("bsh.research.session")).toBeNull();
    expect(auth.sessionName.value).toBe("Bilel Harrat");
  });

  it("keeps a session the server still recognises", async () => {
    const { auth, api } = await boot({ stored: STORED, anonDev: true });
    vi.spyOn(api, "me").mockResolvedValue({ email: STORED.email, name: "Old Hand", auth: "session" });

    expect(await auth.validateSession()).toBe(true);
    expect(auth.isSignedIn.value).toBe(true);
    expect(JSON.parse(localStorage.getItem("bsh.research.session")).token).toBe("stored-token");
  });
});
