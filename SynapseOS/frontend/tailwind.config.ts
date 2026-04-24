import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          900: "#05070d",
          800: "#0a0d18",
          700: "#121627",
          600: "#1a1f35",
          500: "#242a44",
          400: "#38405f",
          300: "#5b6590",
          200: "#8a95bf",
          100: "#c3c9e8",
        },
        synapse: {
          cyan: "#22d3ee",
          violet: "#a855f7",
          pink: "#ec4899",
          lime: "#a3e635",
          amber: "#fbbf24",
        },
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 24px -4px rgba(168,85,247,0.45), 0 0 48px -12px rgba(34,211,238,0.35)",
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 8px 24px -12px rgba(0,0,0,0.6)",
      },
      backgroundImage: {
        "grid-fade":
          "radial-gradient(ellipse 80% 60% at 50% 0%, rgba(168,85,247,0.15), transparent 60%), radial-gradient(ellipse 70% 50% at 20% 100%, rgba(34,211,238,0.12), transparent 60%)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in": "fade-in 0.35s ease-out",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
