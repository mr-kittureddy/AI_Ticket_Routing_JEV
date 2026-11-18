/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: token("canvas"),
        surface: token("surface"),
        raised: token("raised"),
        line: token("line"),
        ink: {
          DEFAULT: token("ink"),
          muted: token("ink-muted"),
          subtle: token("ink-subtle"),
        },
        brand: token("brand"),
        jev: token("jev"),
        gemini: token("gemini"),
        ok: token("ok"),
        warn: token("warn"),
        bad: token("bad"),
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgb(0 0 0 / 0.06), 0 1px 3px rgb(0 0 0 / 0.08)",
        "glow-jev": "0 0 0 1px rgb(var(--c-jev) / 0.45), 0 0 24px rgb(var(--c-jev) / 0.25)",
        "glow-bad": "0 0 0 1px rgb(var(--c-bad) / 0.4), 0 0 18px rgb(var(--c-bad) / 0.2)",
      },
      keyframes: {
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgb(var(--c-jev) / 0.55)" },
          "70%": { boxShadow: "0 0 0 10px rgb(var(--c-jev) / 0)" },
          "100%": { boxShadow: "0 0 0 0 rgb(var(--c-jev) / 0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
      animation: {
        "pulse-ring": "pulse-ring 1.8s ease-out infinite",
        shimmer: "shimmer 1.6s linear infinite",
      },
    },
  },
  plugins: [],
};
