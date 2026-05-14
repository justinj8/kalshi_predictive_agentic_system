/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#02030a",
          900: "#05070f",
          800: "#0a0d18",
          700: "#101422",
        },
        f1: {
          red: "#E10600",
          redDim: "#7a0200",
          gold: "#FFD200",
          mint: "#00D2BE",
          chalk: "#F4F4F0",
          gray: "#7a7e88",
        },
      },
      fontFamily: {
        display: ["'Archivo Black'", "Inter", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: [
          "'JetBrains Mono'",
          "'IBM Plex Mono'",
          "ui-monospace",
          "monospace",
        ],
      },
      boxShadow: {
        hud: "0 0 0 1px rgba(244,244,240,0.06), 0 12px 40px -8px rgba(225,6,0,0.18)",
        glow: "0 0 30px -5px rgba(225,6,0,0.5)",
        mint: "0 0 30px -5px rgba(0,210,190,0.45)",
      },
      keyframes: {
        scan: {
          "0%": { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100%)" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
        pulseRed: {
          "0%,100%": {
            boxShadow: "0 0 0 0 rgba(225,6,0,0.6)",
            opacity: "1",
          },
          "50%": {
            boxShadow: "0 0 20px 8px rgba(225,6,0,0)",
            opacity: "0.85",
          },
        },
        flicker: {
          "0%,98%,100%": { opacity: "1" },
          "99%": { opacity: "0.4" },
        },
        speedlines: {
          "0%": { transform: "translateX(-200%)", opacity: "0" },
          "30%": { opacity: "0.6" },
          "100%": { transform: "translateX(200%)", opacity: "0" },
        },
      },
      animation: {
        scan: "scan 6s linear infinite",
        marquee: "marquee 60s linear infinite",
        marqueeFast: "marquee 28s linear infinite",
        pulseRed: "pulseRed 1.8s ease-in-out infinite",
        flicker: "flicker 4s linear infinite",
        speedlines: "speedlines 1.6s ease-out infinite",
      },
    },
  },
  plugins: [],
};
