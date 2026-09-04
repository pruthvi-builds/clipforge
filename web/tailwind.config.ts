import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          50: "#f6f7f9",
          100: "#e7e9ee",
          200: "#c9cdd6",
          300: "#a2a8b6",
          400: "#7c8494",
          600: "#333a4d",
          700: "#262b3a",
          800: "#1b1f2b",
          850: "#151823",
          900: "#0f1117",
          950: "#0a0b0f",
        },
        brand: {
          400: "#8b7bff",
          500: "#6d5efc",
          600: "#5847e0",
        },
        accent: "#25d0a4",
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 0 rgba(255,255,255,0.04) inset, 0 20px 40px -20px rgba(0,0,0,0.6)",
      },
    },
  },
  plugins: [],
};

export default config;
