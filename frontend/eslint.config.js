import js from "@eslint/js";
import globals from "globals";
import vue from "eslint-plugin-vue";

export default [
  {
    ignores: [
      "dist/**",
      "node_modules/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["src/**/*.{js,vue}", "tests/**/*.{js,vue}"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      "no-unused-vars": "off",
      "no-useless-assignment": "off",
      // Current SFC names follow route/panel names that are already stable.
      "vue/multi-word-component-names": "off",
      // Existing UI uses explicit line wrapping in templates; formatter rollout is separate.
      "vue/max-attributes-per-line": "off",
      "vue/html-indent": "off",
      "vue/html-closing-bracket-newline": "off",
      "vue/html-self-closing": "off",
      "vue/attributes-order": "off",
      "vue/first-attribute-linebreak": "off",
      "vue/singleline-html-element-content-newline": "off",
      "vue/no-v-html": "off",
      // Existing memo draft panels intentionally use mutable draft objects.
      "vue/no-mutating-props": "off",
      // Existing markdown sanitizer strips control characters with a literal regex.
      "no-control-regex": "off",
    },
  },
  {
    files: [
      "src/components/stock/StockHypothesesPanel.vue",
      "tests/StockResearchPanels.spec.js",
      "tests/StockResearchView.spec.js",
      "tests/browser/stock-memo-smoke.spec.js",
    ],
    rules: {
      "no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
      "no-useless-assignment": "error",
    },
  },
  {
    files: ["tests/**/*.{js,vue}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
  },
];
