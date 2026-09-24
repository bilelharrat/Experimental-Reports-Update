import { createApp } from "vue";
import App from "./App.vue";
import { router } from "./router.js";
import { initAppearance } from "./appearance.js";
import { initDesign } from "./design.js";
import "@fontsource/instrument-serif/latin-400.css";
import "@fontsource/instrument-serif/latin-400-italic.css";
import "@fontsource-variable/instrument-sans/wght.css";
import "./style.css";
import "./folio.css";
import "./bureau.css";
import "./bureau-desks.css";

initAppearance();
initDesign();

createApp(App).use(router).mount("#app");
