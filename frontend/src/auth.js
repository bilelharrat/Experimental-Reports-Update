// Web login / session-token state.
//
// The SPA gates every non-/login route behind `isAuthenticated`. A
// successful POST /api/auth/token stashes the response in localStorage
// under SESSION_KEY (same key `getApiToken()` in api.js reads), and the
// route guard in router.js sends you to /login when there's no live
// session. A 401 from any /api/* call dispatches `bsh:unauthorized` —
// we listen for it here and tear the session down so the router bounces
// the user to /login on the next navigation.
//
// Local exception: when the server injects
// `<meta name="bsh-research-anon-dev" content="1">` (`BSH_ALLOW_ANON_DEV=1`),
// the SPA treats the operator as signed in with no stored session.

import { computed, ref } from "vue";
import { api, withBase } from "./api.js";
import { accountInitials, displayNameFromEmail } from "./formatters.js";
import { appBasePath, ensureProfileFor } from "./profileStorage.js";

const SESSION_KEY = "bsh.research.session";

function _readStoredSession() {
  if (typeof window === "undefined" || !window.localStorage) return null;
  let raw;
  try {
    raw = window.localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  let s;
  try {
    s = JSON.parse(raw);
  } catch {
    window.localStorage.removeItem(SESSION_KEY);
    return null;
  }
  if (!s || !s.token) return null;
  if (s.expires_at) {
    const t = Date.parse(s.expires_at);
    if (Number.isFinite(t) && t <= Date.now()) {
      window.localStorage.removeItem(SESSION_KEY);
      return null;
    }
  }
  return s;
}

function _writeStoredSession(s) {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(s));
  } catch {
    // localStorage quota / private mode — session lives in memory only.
  }
}

function _clearStoredSession() {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.removeItem(SESSION_KEY);
  } catch {
    // ignore
  }
}

export const session = ref(_readStoredSession());
export const sessionName = ref(null);

// Whether the server is running with BSH_ALLOW_ANON_DEV=1, which makes
// every request admin with no sign-in.
//
// The server states this by injecting a meta tag into the HTML it serves.
// Under `vite dev` the HTML comes from Vite instead, so the tag is never
// there — and this used to fall back to guessing from the URL: localhost
// on a dev port meant anon dev, whatever the server actually did. With
// the bypass turned off that guess let the SPA past its own sign-in wall
// and render a desk whose every request 401s. The client does not guess
// any more; when there is no tag it asks (`probeAnonDev`) and, until the
// answer arrives, assumes it is NOT bypassed, which fails closed.
const _anonDevProbe = ref(null);

export function isAnonDev() {
  if (typeof document === "undefined") return false;
  const el = document.querySelector('meta[name="bsh-research-anon-dev"]');
  if (el?.content?.trim() === "1") return true;
  return _anonDevProbe.value === true;
}

/** Ask the server whether it is in anon-dev mode. Resolves to a boolean and
 *  is cheap: one unauthenticated GET, once per boot. */
export async function probeAnonDev() {
  if (typeof document !== "undefined") {
    const el = document.querySelector('meta[name="bsh-research-anon-dev"]');
    if (el?.content?.trim() === "1") {
      _anonDevProbe.value = true;
      return true;
    }
  }
  if (_anonDevProbe.value !== null) return _anonDevProbe.value;
  try {
    const res = await fetch(withBase("/api/auth/me"), {
      headers: { "X-BSH-Client": "web" },
      credentials: "same-origin",
    });
    const body = res.ok ? await res.json() : null;
    _anonDevProbe.value = body?.auth === "anon_dev";
  } catch {
    // Unreachable server: assume no bypass, which sends the person to the
    // sign-in page rather than into a desk that cannot load anything.
    _anonDevProbe.value = false;
  }
  return _anonDevProbe.value;
}

export const isAuthenticated = computed(
  () => session.value !== null || isAnonDev(),
);
export const sessionEmail = computed(() => session.value?.email ?? null);
// True while the server holds this session to a password change and
// nothing else. Set by the login response, kept fresh by /auth/me on every
// boot, and cleared by the fresh session a successful change returns.
export const mustResetPassword = computed(() => Boolean(session.value?.must_reset));
export const sessionInitials = computed(() =>
  accountInitials(sessionName.value || session.value?.email, "?"),
);

function _applyIdentity(me) {
  if (!me || typeof me !== "object") return;
  const email = me.email || null;
  if (session.value) {
    const mustReset = Boolean(me.must_reset);
    const emailChanged = Boolean(email) && session.value.email !== email;
    if (emailChanged || Boolean(session.value.must_reset) !== mustReset) {
      const next = { ...session.value, must_reset: mustReset };
      if (emailChanged) next.email = email;
      _writeStoredSession(next);
      session.value = next;
    }
  }
  sessionName.value = me.name || (email ? displayNameFromEmail(email) : null) || null;
}

export async function signIn(email, password) {
  const res = await api.login(email, password);
  // Shape: { token, email, created_at, expires_at }
  _writeStoredSession(res);
  session.value = res;
  sessionName.value = displayNameFromEmail(res.email) || null;
  if (ensureProfileFor(res.email)) {
    // A different account than this browser last held: its state is
    // stashed, this one's restored, and the page must start over so
    // every module reads the right store. The login route's guard sends
    // the reloaded page on to its destination.
    res.profileSwitched = true;
    _reload();
    return res;
  }
  try {
    _applyIdentity(await api.me());
  } catch {
    // Login succeeded; identity enrichment is best-effort.
  }
  return res;
}

function _reload(path) {
  if (typeof window === "undefined" || !window.location) return;
  if (path) {
    window.location.replace(appBasePath().replace(/\/$/, "") + path);
    return;
  }
  // Reload in place, minus the flag that lets the sign-in page show while
  // a session exists: with it kept, the reloaded page would sit on an
  // empty form instead of being sent on by the guard.
  const url = new URL(window.location.href);
  url.searchParams.delete("switch");
  window.location.replace(url.toString());
}

/** Take up a session the server minted outside the login form — today the
 *  password-reset flow, which signs the person in as it spends the link. */
export async function adoptSession(res) {
  if (!res?.token) return null;
  _writeStoredSession(res);
  session.value = res;
  sessionName.value = displayNameFromEmail(res.email) || null;
  if (ensureProfileFor(res.email)) {
    // Reached from the reset page, whose URL no longer carries a usable
    // token, so start over at the front door rather than in place.
    res.profileSwitched = true;
    _reload("/");
    return res;
  }
  try {
    _applyIdentity(await api.me());
  } catch {
    // The session is live; identity enrichment is best-effort.
  }
  return res;
}

export async function signOut() {
  const had = session.value;
  // Clear local state first so the router guard kicks the user to
  // /login immediately, even if the network call below hangs.
  _clearStoredSession();
  session.value = null;
  sessionName.value = null;
  if (had?.token) {
    // Post directly with the captured token (local state is already
    // cleared, so apiFetch would send no Authorization header). Include
    // credentials so the server can also clear the session cookie.
    try {
      await fetch(withBase("/api/auth/logout"), {
        method: "POST",
        headers: { Authorization: `Bearer ${had.token}`, "X-BSH-Client": "web" },
        credentials: "same-origin",
      });
    } catch {
      // Network blip / server already gone — local state is gone too.
    }
  }
}

// Called by router on boot: confirm a stored token still works, and always
// hydrate display name/initials (including anon-dev operator identity).
export async function validateSession() {
  if (!session.value && !isAnonDev()) return false;
  try {
    const me = await api.me();
    _applyIdentity(me);
    if (session.value && me?.email && ensureProfileFor(me.email)) {
      _reload();
    }
    return Boolean(session.value);
  } catch (e) {
    if (e && e.status === 401) {
      _clearStoredSession();
      session.value = null;
      sessionName.value = null;
    }
    return false;
  }
}

if (typeof window !== "undefined") {
  // api.js dispatches this on every 401 — covers expired/revoked
  // tokens mid-session without each caller having to handle it.
  window.addEventListener("bsh:unauthorized", () => {
    if (session.value !== null) {
      _clearStoredSession();
      session.value = null;
      sessionName.value = null;
    }
  });
}
