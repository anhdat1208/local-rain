import type { NearestRainResponse } from "@local-rain/shared";

import { useNearestRainStore } from "~/stores/nearestRain";

const STALE_KEY = "lr:nearestRain:v1";
const STALE_MAX_AGE_MS = 5 * 60 * 1000;

type StalePayload = {
  latitude: number;
  longitude: number;
  savedAt: number;
  data: NearestRainResponse;
};

function readStale(latitude: number, longitude: number): NearestRainResponse | null {
  if (!import.meta.client) return null;
  try {
    const raw = window.sessionStorage.getItem(STALE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StalePayload;
    if (
      !parsed?.data ||
      !Number.isFinite(parsed.latitude) ||
      !Number.isFinite(parsed.longitude) ||
      !Number.isFinite(parsed.savedAt)
    ) {
      return null;
    }
    if (Date.now() - parsed.savedAt > STALE_MAX_AGE_MS) return null;
    if (
      Math.abs(parsed.latitude - latitude) > 0.01 ||
      Math.abs(parsed.longitude - longitude) > 0.01
    ) {
      return null;
    }
    return parsed.data;
  } catch {
    return null;
  }
}

function writeStale(latitude: number, longitude: number, data: NearestRainResponse): void {
  if (!import.meta.client) return;
  try {
    const payload: StalePayload = {
      latitude,
      longitude,
      savedAt: Date.now(),
      data,
    };
    window.sessionStorage.setItem(STALE_KEY, JSON.stringify(payload));
  } catch {
    // quota / private mode
  }
}

export function useNearestRain() {
  const store = useNearestRainStore();
  const { t, locale } = useI18n();
  const { apiFetch } = useApiClient();

  async function fetchNearestRain(latitude: number, longitude: number): Promise<void> {
    const stale = readStale(latitude, longitude);
    if (stale) {
      // Paint last answer immediately; refresh in background
      store.setResult(stale);
    } else {
      store.setLoading(true);
    }
    store.setError(null);
    try {
      const data = await apiFetch<NearestRainResponse>("/api/nearest-rain", {
        query: { lat: latitude, lng: longitude, lang: locale.value },
        timeout: 16_000,
      });
      store.setResult(data);
      writeStale(latitude, longitude, data);
    } catch {
      if (!stale) {
        store.reset();
        store.setError(t("errors.nearestRain"));
      } else {
        // Keep stale card; soft-clear loading if any
        store.setLoading(false);
      }
    }
  }

  return {
    store,
    fetchNearestRain,
  };
}
