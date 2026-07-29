import { fileURLToPath } from "node:url";

// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: "2025-07-15",
  future: {
    compatibilityVersion: 4,
  },
  devtools: { enabled: true },
  css: ["~/assets/css/main.css"],
  components: [
    {
      path: "~/components",
      pathPrefix: false,
    },
  ],
  modules: [
    "@nuxtjs/tailwindcss",
    "@pinia/nuxt",
    "@vueuse/nuxt",
    "@vite-pwa/nuxt",
    "@nuxt/eslint",
    "@nuxtjs/i18n",
  ],
  i18n: {
    locales: [
      { code: "vi", language: "vi-VN", name: "Tiếng Việt" },
      { code: "en", language: "en-US", name: "English" },
    ],
    defaultLocale: "vi",
    strategy: "no_prefix",
    vueI18n: "i18n.config.ts",
    bundle: {
      optimizeTranslationDirective: false,
    },
    detectBrowserLanguage: {
      useCookie: true,
      cookieKey: "local_rain_lang",
      fallbackLocale: "vi",
      redirectOn: "root",
    },
  },
  runtimeConfig: {
    public: {
      apiBase: process.env.NUXT_PUBLIC_API_BASE || "http://localhost:8000",
    },
  },
  alias: {
    "@local-rain/shared": fileURLToPath(
      new URL("../../packages/shared/src/index.ts", import.meta.url),
    ),
  },
  app: {
    pageTransition: { name: "page", mode: "out-in" },
    layoutTransition: { name: "layout", mode: "out-in" },
    head: {
      title: "Local Rain",
      meta: [
        {
          name: "description",
          content: "AI-powered rain nowcasting — nearest rain, ETA, and advice.",
        },
        { name: "theme-color", content: "#0ea5e9" },
        { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
      ],
      link: [{ rel: "icon", type: "image/svg+xml", href: "/favicon.svg" }],
    },
  },
  pwa: {
    registerType: "autoUpdate",
    manifest: {
      name: "Local Rain",
      short_name: "LocalRain",
      description: "Nearest rain, direction, distance, and ETA.",
      theme_color: "#0ea5e9",
      background_color: "#f5f5f7",
      display: "standalone",
      orientation: "portrait",
      start_url: "/",
      icons: [
        {
          src: "/pwa-192.png",
          sizes: "192x192",
          type: "image/png",
        },
        {
          src: "/pwa-512.png",
          sizes: "512x512",
          type: "image/png",
        },
      ],
    },
    workbox: {
      // SSR output has no precached "/" document, so a navigate fallback would throw.
      globPatterns: ["**/*.{js,css,html,png,svg,ico,woff2}"],
      cleanupOutdatedCaches: true,
      skipWaiting: true,
      clientsClaim: true,
    },
    client: {
      installPrompt: true,
    },
    devOptions: {
      enabled: false,
    },
  },
  typescript: {
    strict: true,
    typeCheck: false,
  },
  eslint: {
    config: {
      stylistic: false,
    },
  },
});
