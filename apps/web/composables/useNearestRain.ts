import type { NearestRainResponse } from "@local-rain/shared";

import { useNearestRainStore } from "~/stores/nearestRain";

export function useNearestRain() {
  const store = useNearestRainStore();
  const { t, locale } = useI18n();
  const { apiFetch } = useApiClient();

  async function fetchNearestRain(latitude: number, longitude: number): Promise<void> {
    store.setLoading(true);
    store.setError(null);
    try {
      const data = await apiFetch<NearestRainResponse>("/api/nearest-rain", {
        query: { lat: latitude, lng: longitude, lang: locale.value },
      });
      store.setResult(data);
    } catch {
      store.reset();
      store.setError(t("errors.nearestRain"));
    }
  }

  return {
    store,
    fetchNearestRain,
  };
}
