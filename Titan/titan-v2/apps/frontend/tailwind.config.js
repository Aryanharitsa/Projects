/** @type {import('tailwindcss').Config} */
export default {
  content: ["./app/**/*.{ts,tsx,js,jsx}", "./components/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {
      colors: {
        // TITAN brand: deep ink + electric teal + violet accent
        ink: {
          950: "#070b14",
          900: "#0a1020",
          800: "#0e1730",
          700: "#1a2547",
        },
        teal: {
          400: "#2DE1C2",
          500: "#1FC9AB",
        },
        violet: {
          400: "#8B7CFF",
          500: "#6E5BFF",
        },
        risk: {
          low: "#22d3a8",
          medium: "#fbbf24",
          high: "#fb923c",
          critical: "#ef4444",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "Menlo", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(45,225,194,0.18), 0 10px 40px -10px rgba(45,225,194,0.25)",
        violet: "0 0 0 1px rgba(139,124,255,0.18), 0 10px 40px -10px rgba(139,124,255,0.25)",
      },
      animation: {
        pulseSoft: "pulseSoft 2.4s ease-in-out infinite",
        floatSlow: "floatSlow 18s ease-in-out infinite",
      },
      keyframes: {
        pulseSoft: {
          "0%,100%": { opacity: 0.7 },
          "50%": { opacity: 1 },
        },
        floatSlow: {
          "0%,100%": { transform: "translate3d(0,0,0)" },
          "50%": { transform: "translate3d(20px,-30px,0)" },
        },
      },
    },
  },
  plugins: [],
};
