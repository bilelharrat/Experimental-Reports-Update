import { watch } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import LoginView from "./views/LoginView.vue";
import ResearchView from "./views/ResearchView.vue";
import ExternalNewsView from "./views/ExternalNewsView.vue";
import ExternalResearchView from "./views/ExternalResearchView.vue";
import HormuzResearchView from "./views/HormuzResearchView.vue";
import HormuzLibraryView from "./views/HormuzLibraryView.vue";
import WeeklySummaryView from "./views/WeeklySummaryView.vue";
import { isAuthenticated, validateSession } from "./auth.js";

function routerHistoryBase() {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return "/";
  }
  const metaBase =
    document
      .querySelector('meta[name="bsh-research-api-base"]')
      ?.content?.trim() || "";
  const viteBase = import.meta.env.BASE_URL || "/";
  const raw = metaBase || viteBase;
  const normalized = raw
    ? ("/" + raw.replace(/^\/+|\/+$/g, "")).replace(/^\/$/, "")
    : "";
  if (!normalized) return "/";

  const path = window.location.pathname;
  if (path === normalized || path.startsWith(`${normalized}/`)) {
    return normalized;
  }
  return "/";
}

export const router = createRouter({
  history: createWebHistory(routerHistoryBase()),
  routes: [
    {
      path: "/login",
      name: "login",
      component: LoginView,
      meta: { public: true },
    },
    { path: "/", name: "home", component: HomeView },
    {
      path: "/weekly-summary",
      name: "weekly-summary",
      component: WeeklySummaryView,
    },
    {
      path: "/research/:companyId",
      name: "research",
      component: ResearchView,
      props: true,
    },
    {
      path: "/news/:id",
      name: "external-news",
      component: ExternalNewsView,
      props: true,
    },
    {
      path: "/external-research/:id",
      name: "external-research",
      component: ExternalResearchView,
      props: true,
    },
    {
      path: "/hormuz",
      name: "hormuz-library",
      component: HormuzLibraryView,
    },
    {
      path: "/hormuz/:id",
      name: "hormuz-research",
      component: HormuzResearchView,
      props: true,
    },
  ],
});

router.beforeEach((to) => {
  // Already signed in and trying to reach /login → bounce home.
  if (to.name === "login" && isAuthenticated.value) {
    return { path: "/" };
  }
  // Any non-public route requires a session.
  if (!to.meta?.public && !isAuthenticated.value) {
    return { name: "login", query: { next: to.fullPath } };
  }
  return true;
});

// auth.js flips isAuthenticated to false when a 401 arrives mid-session
// (token expired, revoked from another browser, etc.). The route guard
// only fires on navigation, so without this watcher the user would be
// stuck on a now-broken page. Catch the transition and redirect.
watch(isAuthenticated, (signedIn) => {
  if (!signedIn && router.currentRoute.value.name !== "login") {
    router.replace({
      name: "login",
      query: { next: router.currentRoute.value.fullPath },
    });
  }
});

// On boot, if we have a stored session, ping /me to confirm it's still
// valid server-side. If 401, auth.js clears it and the watcher above
// redirects. Fire-and-forget; the optimistic state lets the UI render
// immediately.
validateSession();
