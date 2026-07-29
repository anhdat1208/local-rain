import en from "./locales/en.json";
import vi from "./locales/vi.json";

export default defineI18nConfig(() => ({
  legacy: false,
  locale: "vi",
  fallbackLocale: "vi",
  messages: {
    vi,
    en,
  },
}));
