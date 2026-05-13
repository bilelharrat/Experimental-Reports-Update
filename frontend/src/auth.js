// Web login / session-token state.
//
// The SPA gates every non-/login route behind `isAuthenticated`. A
// successful POST /api/auth/token stashes the response in localStorage
// under SESSION_KEY (same key `getApiToken()` in api.js reads), and the
// route guard in router.js sends you to /login when there's no live
// session. A 401 from any /api/* call dispatches `bsh:unauthorized` —
// we listen for it here and tear the session down so the router bounces
// the user to /login on the next navigation.

import { computed, ref } from "vue";
import { api, withBase } from "./api.js";

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
export const isAuthenticated = computed(() => session.value !== null);
export const sessionEmail = computed(() => session.value?.email ?? null);

export async function signIn(email, password) {
  const res = await api.login(email, password);
  // Shape: { token, email, created_at, expires_at }
  _writeStoredSession(res);
  session.value = res;
  return res;
}

export async function signOut() {
  const had = session.value;
  // Clear local state first so the router guard kicks the user to
  // /login immediately, even if the network call below hangs.
  _clearStoredSession();
  session.value = null;
  if (had?.token) {
    // Post directly with the captured token. We can't go through
    // api.logout() / apiFetch here because getApiToken() would now fall
    // back to the meta-tag (legacy shared token) and the server would
    // try to revoke the wrong row.
    try {
      await fetch(withBase("/api/auth/logout"), {
        method: "POST",
        headers: { Authorization: `Bearer ${had.token}` },
      });
    } catch {
      // Network blip / server already gone — local state is gone too.
    }
  }
}

// Called by router on app boot when a stored session exists; pings /me
// to confirm the token is still valid (e.g. wasn't revoked in another
// browser). Silently no-ops when no session or when the network is down.
export async function validateSession() {
  if (!session.value) return false;
  try {
    await api.me();
    return true;
  } catch (e) {
    if (e && e.status === 401) {
      _clearStoredSession();
      session.value = null;
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
    }
  });
}
