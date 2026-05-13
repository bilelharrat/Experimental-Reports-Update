import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

// Separate config so `vite build` (used by the dev/prod build) doesn't
// load the test plugin chain. Mirrors the prod base path so component
// tests can import the same modules without surprise URL rewriting.
export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "jsdom",
    globals: false,
    include: ["tests/**/*.spec.{js,ts}"],
  },
});
