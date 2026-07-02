/**
 * Tailwind config for bsh-research-center.
 *
 * Colors are defined as CSS variables in src/style.css (light + .dark)
 * so utilities like bg-surface and text-ink-primary respond to the theme.
 */
module.exports = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{vue,js,ts}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Inter", "ui-sans-serif", "system-ui"],
        body: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["SF Mono", "Roboto Mono", "ui-monospace", "Menlo", "monospace"],
      },
      colors: {
        canvas: "rgb(var(--color-canvas) / <alpha-value>)",
        surface: "rgb(var(--color-surface) / <alpha-value>)",
        "surface-muted": "rgb(var(--color-surface-muted) / <alpha-value>)",
        "surface-raised": "rgb(var(--color-surface-raised) / <alpha-value>)",
        subtle: "rgb(var(--color-border-subtle) / <alpha-value>)",
        strong: "rgb(var(--color-border-strong) / <alpha-value>)",
        "ink-primary": "rgb(var(--color-text-primary) / <alpha-value>)",
        "ink-secondary": "rgb(var(--color-text-secondary) / <alpha-value>)",
        "ink-muted": "rgb(var(--color-text-muted) / <alpha-value>)",
        "ink-subtle": "rgb(var(--color-text-subtle) / <alpha-value>)",
        accent: {
          DEFAULT: "rgb(var(--color-accent) / <alpha-value>)",
          hover: "rgb(var(--color-accent-hover) / <alpha-value>)",
          soft: "rgb(var(--color-accent-soft) / <alpha-value>)",
          ink: "rgb(var(--color-accent-ink) / <alpha-value>)",
        },
        success: {
          DEFAULT: "rgb(var(--color-success) / <alpha-value>)",
          soft: "rgb(var(--color-success-soft) / <alpha-value>)",
          ink: "rgb(var(--color-success-ink) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "rgb(var(--color-warning) / <alpha-value>)",
          soft: "rgb(var(--color-warning-soft) / <alpha-value>)",
          ink: "rgb(var(--color-warning-ink) / <alpha-value>)",
        },
        danger: {
          DEFAULT: "rgb(var(--color-danger) / <alpha-value>)",
          soft: "rgb(var(--color-danger-soft) / <alpha-value>)",
          ink: "rgb(var(--color-danger-ink) / <alpha-value>)",
        },
      },
      borderRadius: {
        chip: "7px",
        subbox: "12px",
        row: "14px",
        card: "18px",
        glass: "24px",
        pill: "99px",
      },
      boxShadow: {
        card: "var(--shadow)",
        "card-raised": "var(--shadow-hover)",
      },
    },
  },
  plugins: [],
};
