/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./components/**/*.{vue,js,ts}",
    "./layouts/**/*.vue",
    "./pages/**/*.vue",
    "./plugins/**/*.{js,ts}",
    "./app.vue",
  ],
  theme: {
    extend: {
      colors: {
        rain: {
          DEFAULT: "#0ea5e9",
          soft: "#e0f2fe",
        },
        warning: "#f97316",
        danger: "#ef4444",
        surface: {
          DEFAULT: "#ffffff",
          muted: "#f5f5f7",
        },
      },
      borderRadius: {
        "2xl": "1rem",
      },
      boxShadow: {
        soft: "0 8px 30px rgba(15, 23, 42, 0.08)",
      },
      fontFamily: {
        sans: [
          "SF Pro Display",
          "SF Pro Text",
          "Segoe UI",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
