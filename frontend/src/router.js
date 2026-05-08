import { createRouter, createWebHistory } from "vue-router";
import HomeView from "./views/HomeView.vue";
import ResearchView from "./views/ResearchView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/research/:companyId", name: "research", component: ResearchView, props: true },
  ],
});
