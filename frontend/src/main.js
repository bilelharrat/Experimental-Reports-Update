import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router.js";
import { initAppearance } from "./appearance.js";
import { initDesign } from "./design.js";
import "./style.css";
import "./folio.css";

initAppearance();
initDesign();

createApp(App).use(router).mount("#app");
