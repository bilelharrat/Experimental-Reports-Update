import { createRouter, createWebHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import ResearchView from "./views/ResearchView.vue";
import ExternalNewsView from "./views/ExternalNewsView.vue";
import ExternalResearchView from "./views/ExternalResearchView.vue";
import HormuzResearchView from "./views/HormuzResearchView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
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
      path: "/hormuz/:id",
      name: "hormuz-research",
      component: HormuzResearchView,
      props: true,
    },
  ],
});
