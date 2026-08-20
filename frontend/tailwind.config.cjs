/**
 * Tailwind config for bsh-research-center.
 *
 * Design language follows the Apple Human Interface Guidelines (macOS/iPadOS
 * idiom: source-list sidebar + translucent toolbar).
 *
 * Colors are defined as CSS variables in src/style.css (light + .dark) so
 * utilities like bg-surface and text-ink-primary respond to the theme.
 */
module.exports = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{vue,js,ts}"],
  theme: {
    extend: {
      fontFamily: {
        // The system stack resolves to SF Pro on Apple platforms, which is
        // what the HIG type scale below is metrically designed around.
        display: [
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Display",
          "ui-sans-serif",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
        body: [
          "ui-sans-serif",
          "-apple-system",
          "BlinkMacSystemFont",
          "SF Pro Text",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SF Mono",
          "SFMono-Regular",
          "Menlo",
          "Monaco",
          "Roboto Mono",
          "monospace",
        ],
      },
      // Apple's named text styles. SF tightens tracking as size grows and
      // opens it up at caption sizes; these pairs reproduce that optically.
      fontSize: {
        "large-title": ["2.125rem", { lineHeight: "2.5rem", letterSpacing: "-0.028em", fontWeight: "700" }],
        title1: ["1.75rem", { lineHeight: "2.125rem", letterSpacing: "-0.024em", fontWeight: "700" }],
        title2: ["1.375rem", { lineHeight: "1.75rem", letterSpacing: "-0.020em", fontWeight: "600" }],
        title3: ["1.125rem", { lineHeight: "1.5rem", letterSpacing: "-0.014em", fontWeight: "600" }],
        headline: ["0.9375rem", { lineHeight: "1.25rem", letterSpacing: "-0.010em", fontWeight: "600" }],
        callout: ["0.875rem", { lineHeight: "1.25rem", letterSpacing: "-0.006em" }],
        subheadline: ["0.8125rem", { lineHeight: "1.125rem", letterSpacing: "-0.003em" }],
        footnote: ["0.75rem", { lineHeight: "1rem", letterSpacing: "0" }],
        caption1: ["0.6875rem", { lineHeight: "0.875rem", letterSpacing: "0.006em" }],
        caption2: ["0.625rem", { lineHeight: "0.8125rem", letterSpacing: "0.012em" }],
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
        // Apple's fill hierarchy: translucent grays for control backgrounds
        // that sit correctly on any underlying surface or material.
        fill: {
          DEFAULT: "rgb(var(--color-fill) / <alpha-value>)",
          secondary: "rgb(var(--color-fill-secondary) / <alpha-value>)",
          tertiary: "rgb(var(--color-fill-tertiary) / <alpha-value>)",
        },
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
      // Apple's concentric corner radii. Values stay conservative because CSS
      // rounds circularly rather than with SF Symbols' continuous curvature —
      // oversized radii read as "bubbly" instead of "squircle".
      borderRadius: {
        chip: "6px",
        subbox: "10px",
        row: "12px",
        card: "16px",
        glass: "20px",
        sheet: "12px",
        pill: "99px",
      },
      boxShadow: {
        card: "var(--shadow)",
        "card-raised": "var(--shadow-hover)",
        sheet: "var(--shadow-sheet)",
        control: "var(--shadow-control)",
      },
      backdropBlur: {
        material: "20px",
      },
      transitionTimingFunction: {
        // Apple's default animation curve, plus the overshoot used for
        // presentation (sheets, popovers).
        standard: "cubic-bezier(0.25, 0.1, 0.25, 1)",
        emphasized: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      keyframes: {
        "sheet-in": {
          from: { opacity: "0", transform: "scale(0.96) translateY(8px)" },
          to: { opacity: "1", transform: "scale(1) translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "sheet-in": "sheet-in 0.32s cubic-bezier(0.32, 0.72, 0, 1)",
        "fade-in": "fade-in 0.2s cubic-bezier(0.25, 0.1, 0.25, 1)",
      },
    },
  },
  plugins: [],
};
