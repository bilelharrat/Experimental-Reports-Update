import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

const API_TARGET = process.env.VITE_API_TARGET || "http://127.0.0.1:8010";

// The FastAPI app is mounted at root_path="/research" so nginx can be
// non-stripping. Emitting `<script src="/research/assets/...">` works
// in both prod (nginx forwards `/research/assets/...` upstream where
// Starlette strips the prefix and serves from `/assets/...`) and local
// dev (visiting localhost:8010/ returns this HTML; the browser then
// fetches `/research/assets/...`, Starlette strips, mount serves it).
export default defineConfig({
  base: "/research/",
  plugins: [vue()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
});
