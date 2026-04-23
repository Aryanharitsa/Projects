import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Deep synaptic void
        void: {
          900: "#05060d",
          800: "#0a0b14",
          700: "#0f1120",
          600: "#151831",
        },
        // Neon synapse
        synapse: {
          cyan: "#22e4ff",
          violet: "#9a5bff",
          magenta: "#ff4fd8",
          amber: "#ffb547",
        },
        ink: {
          100: "#f5f7ff",
          200: "#d6dbf0",
          300: "#9ea4c4",
          400: "#6d7396",
          500: "#4a4f70",
        },
      },
      fontFamily: {
        sans: ["InterVariable", "Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        glow: "0 0 40px -8px rgba(34, 228, 255, 0.45)",
        glowViolet: "0 0 40px -8px rgba(154, 91, 255, 0.55)",
      },
      backgroundImage: {
        "synapse-gradient":
          "radial-gradient(circle at 20% 10%, rgba(34,228,255,0.15), transparent 40%), radial-gradient(circle at 80% 80%, rgba(154,91,255,0.18), transparent 45%), radial-gradient(circle at 60% 40%, rgba(255,79,216,0.10), transparent 50%)",
        "grid-lines":
          "linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px)",
      },
      animation: {
        "pulse-slow": "pulse 3.2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-up": "fadeUp 0.5s ease-out both",
        "spin-slow": "spin 18s linear infinite",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
