import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router.js";
import { initAppearance } from "./appearance.js";
import "./style.css";

initAppearance();

createApp(App).use(router).mount("#app");
