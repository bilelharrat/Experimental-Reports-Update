import { watch } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import { isAuthenticated, isAnonDev, session, validateSession } from "./auth.js";
import { postAuthPath } from "./state.js";

const HomeView = () => import("./views/HomeView.vue");
const LoginView = () => import("./views/LoginView.vue");
const ResearchView = () => import("./views/ResearchView.vue");
const ExternalNewsView = () => import("./views/ExternalNewsView.vue");
const ExternalResearchView = () => import("./views/ExternalResearchView.vue");
const HormuzResearchView = () => import("./views/HormuzResearchView.vue");
const HormuzLibraryView = () => import("./views/HormuzLibraryView.vue");
const WeeklySummaryView = () => import("./views/WeeklySummaryView.vue");
const TraderStatsView = () => import("./views/TraderStatsView.vue");
const StockResearchView = () => import("./views/StockResearchView.vue");
const MarketPulseView = () => import("./views/MarketPulseView.vue");
const EvidenceMatrixView = () => import("./views/EvidenceMatrixView.vue");
const HypothesisLabView = () => import("./views/HypothesisLabView.vue");
const InnovationLabView = () => import("./views/InnovationLabView.vue");
const SettingsView = () => import("./views/SettingsView.vue");
const SourceLibraryView = () => import("./views/SourceLibraryView.vue");
const TrackingView = () => import("./views/TrackingView.vue");
const NewsDeskView = () => import("./views/NewsDeskView.vue");
const MarketRadarView = () => import("./views/MarketRadarView.vue");
const CompetitorDetailView = () => import("./views/CompetitorDetailView.vue");
const ReportsView = () => import("./views/ReportsView.vue");
const ResearchDeskView = () => import("./views/ResearchDeskView.vue");

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
    { path: "/research-desk", name: "research-desk", component: ResearchDeskView, props: true },
    { path: "/research-desk/:companyId", name: "research-desk-company", component: ResearchDeskView, props: true },
    { path: "/news-desk", name: "news-desk", component: NewsDeskView },
    { path: "/reports", name: "reports", component: ReportsView },
    { path: "/tracking", name: "tracking", component: TrackingView },
    { path: "/market-radar", name: "market-radar", component: MarketRadarView },
    {
      path: "/weekly-summary",
      name: "weekly-summary",
      component: WeeklySummaryView,
    },
    {
      path: "/trader-stats",
      name: "trader-stats",
      component: TraderStatsView,
    },
    {
      path: "/stock-research",
      name: "stock-research",
      component: StockResearchView,
    },
    {
      path: "/source-library",
      name: "source-library",
      component: SourceLibraryView,
    },
    {
      path: "/settings",
      name: "settings",
      component: SettingsView,
    },
    {
      path: "/user",
      name: "user-center",
      redirect: { name: "settings" },
      alias: "/profile",
    },
    {
      path: "/innovation-lab",
      name: "innovation-lab",
      component: InnovationLabView,
    },
    {
      path: "/innovation-lab/market-pulse",
      name: "research-page-market-pulse",
      component: MarketPulseView,
      alias: "/research-pages/market-pulse",
    },
    {
      path: "/innovation-lab/evidence-matrix",
      name: "research-page-evidence-matrix",
      component: EvidenceMatrixView,
      alias: "/research-pages/evidence-matrix",
    },
    {
      path: "/innovation-lab/hypothesis-lab",
      name: "research-page-hypothesis-lab",
      component: HypothesisLabView,
      alias: "/research-pages/hypothesis-lab",
    },
    {
      path: "/companies/:companyId/competitors/:competitorId",
      name: "competitor-detail",
      component: CompetitorDetailView,
      props: true,
    },
    {
      path: "/:companyId",
      name: "research",
      component: ResearchDeskView,
      alias: "/research/:companyId",
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
      path: "/innovation-lab/hormuz",
      name: "hormuz-library",
      component: HormuzLibraryView,
      alias: "/hormuz",
    },
    {
      path: "/innovation-lab/hormuz/:id",
      name: "hormuz-research",
      component: HormuzResearchView,
      props: true,
      alias: "/hormuz/:id",
    },
  ],
});

router.beforeEach((to) => {
  // Already signed in or in anon dev mode and trying to reach /login → bounce home.
  if (to.name === "login" && (session.value !== null || isAnonDev()) && !to.query.switch) {
    return postAuthPath(typeof to.query.next === "string" ? to.query.next : "/");
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
