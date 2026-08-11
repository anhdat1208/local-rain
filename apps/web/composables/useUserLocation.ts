import type { LocationResponse } from "@local-rain/shared";
import { useGeolocation } from "@vueuse/core";

import { useLocationStore } from "~/stores/location";
import type { GeolocationPermissionState, LocationSource } from "~/types/location";

const FALLBACK_COORDS = {
  latitude: 10.7401,
  longitude: 106.6653,
  accuracy: null as number | null,
};

const LAST_COORDS_KEY = "lr:lastCoords";
const LAST_LABEL_KEY = "lr:lastLabel";

type CachedLabel = {
  latitude: number;
  longitude: number;
  label: string;
};

function readLastKnownCoords(): { latitude: number; longitude: number } | null {
  if (!import.meta.client) return null;
  try {
    const raw = window.localStorage.getItem(LAST_COORDS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { latitude?: number; longitude?: number };
    if (Number.isFinite(parsed.latitude) && Number.isFinite(parsed.longitude)) {
      return {
        latitude: parsed.latitude as number,
        longitude: parsed.longitude as number,
      };
    }
  } catch {
    // ignore corrupt cache
  }
  return null;
}

function readCachedLabel(latitude: number, longitude: number): string | null {
  if (!import.meta.client) return null;
  try {
    const raw = window.localStorage.getItem(LAST_LABEL_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedLabel;
    if (
      typeof parsed.label === "string" &&
      parsed.label.trim() &&
      Number.isFinite(parsed.latitude) &&
      Number.isFinite(parsed.longitude) &&
      Math.abs(parsed.latitude - latitude) < 0.002 &&
      Math.abs(parsed.longitude - longitude) < 0.002 &&
      !isCoordinateLabel(parsed.label)
    ) {
      return parsed.label.trim();
    }
  } catch {
    // ignore corrupt cache
  }
  return null;
}

function writeCachedLabel(latitude: number, longitude: number, label: string): void {
  if (!import.meta.client || isCoordinateLabel(label)) return;
  try {
    const payload: CachedLabel = { latitude, longitude, label };
    window.localStorage.setItem(LAST_LABEL_KEY, JSON.stringify(payload));
  } catch {
    // quota / private mode
  }
}

function isCoordinateLabel(label: string): boolean {
  const parts = label.split(",").map((p) => p.trim());
  if (parts.length !== 2) return false;
  return parts.every((p) => Number.isFinite(Number(p)));
}

function mapPermission(state: PermissionState | "unsupported"): GeolocationPermissionState {
  if (state === "unsupported") return "unsupported";
  return state;
}

export function useUserLocation() {
  const store = useLocationStore();
  const { t, locale } = useI18n();
  const { apiFetch } = useApiClient();
  let labelRequestId = 0;

  const { coords, error: geoError, resume, pause } = useGeolocation({
    enableHighAccuracy: false,
    maximumAge: 60_000,
    timeout: 8_000,
    immediate: false,
  });

  function pendingLabel(): string {
    return t("sheet.resolvingPlace");
  }

  function applyOptimisticLabel(latitude: number, longitude: number): void {
    const cached = readCachedLabel(latitude, longitude);
    if (cached) {
      store.setLabel(cached);
      return;
    }
    if (!store.label || store.label === "Finding location…" || isCoordinateLabel(store.label)) {
      store.setLabel(pendingLabel());
    }
  }

  /** Sync seed so weather can start before GPS — call before kickoff fetches. */
  function seedLastKnownCoords(): boolean {
    if (store.latitude != null && store.longitude != null) {
      applyOptimisticLabel(store.latitude, store.longitude);
      return true;
    }
    const last = readLastKnownCoords();
    if (!last) return false;
    store.setCoords(
      {
        latitude: last.latitude,
        longitude: last.longitude,
        accuracy: null,
      },
      "fallback",
    );
    applyOptimisticLabel(last.latitude, last.longitude);
    // Warm reverse-geocode immediately — don't wait for GPS settle
    void resolveLabel(last.latitude, last.longitude);
    return true;
  }

  async function detectPermission(): Promise<GeolocationPermissionState> {
    if (!import.meta.client || !("geolocation" in navigator)) {
      store.setPermission("unsupported");
      return "unsupported";
    }

    if (!("permissions" in navigator)) {
      store.setPermission("prompt");
      return "prompt";
    }

    try {
      const result = await navigator.permissions.query({ name: "geolocation" });
      const permission = mapPermission(result.state);
      store.setPermission(permission);
      result.onchange = () => {
        store.setPermission(mapPermission(result.state));
      };
      return permission;
    } catch {
      store.setPermission("prompt");
      return "prompt";
    }
  }

  async function resolveLabel(
    latitude: number,
    longitude: number,
    opts?: { attempt?: number },
  ): Promise<void> {
    const attempt = opts?.attempt ?? 0;
    const requestId = ++labelRequestId;
    const cached = readCachedLabel(latitude, longitude);
    if (cached) {
      store.setLabel(cached);
    } else if (!store.label || isCoordinateLabel(store.label)) {
      store.setLabel(pendingLabel());
    }

    const lang = locale.value === "en" ? "en" : "vi";

    const fetchOnce = () =>
      apiFetch<LocationResponse>("/api/location", {
        query: { lat: latitude, lng: longitude, lang },
        timeout: 6_000,
      });

    const scheduleRetry = () => {
      if (attempt >= 2) return;
      window.setTimeout(() => {
        void resolveLabel(latitude, longitude, { attempt: attempt + 1 });
      }, 2_500 * (attempt + 1));
    };

    try {
      let data: LocationResponse;
      try {
        data = await fetchOnce();
      } catch {
        // One quick retry — Nominatim is often cold on the first hit
        data = await fetchOnce();
      }
      if (requestId !== labelRequestId) return;
      if (isCoordinateLabel(data.label)) {
        // Keep cached / pending text instead of flashing raw coords
        if (!cached) store.setLabel(pendingLabel());
        scheduleRetry();
        return;
      }
      store.setLabel(data.label);
      writeCachedLabel(latitude, longitude, data.label);
    } catch {
      if (requestId !== labelRequestId) return;
      // Prefer last good name over ugly coordinate fallback
      if (cached) {
        store.setLabel(cached);
        return;
      }
      store.setLabel(pendingLabel());
      scheduleRetry();
    }
  }

  async function applyFallback(message: string): Promise<void> {
    store.setError(message);
    store.setCoords(FALLBACK_COORDS, "fallback");
    applyOptimisticLabel(FALLBACK_COORDS.latitude, FALLBACK_COORDS.longitude);
    void resolveLabel(FALLBACK_COORDS.latitude, FALLBACK_COORDS.longitude);
    store.setLoading(false);
  }

  async function setManualLocation(latitude: number, longitude: number): Promise<void> {
    pause();
    store.setLoading(true);
    store.setError(null);
    store.setCoords(
      {
        latitude,
        longitude,
        accuracy: null,
      },
      "manual",
    );
    applyOptimisticLabel(latitude, longitude);
    store.setLoading(false);
    void resolveLabel(latitude, longitude);
  }

  async function requestLocation(): Promise<void> {
    store.setLoading(true);
    store.setError(null);
    seedLastKnownCoords();
    if (store.latitude == null || store.longitude == null) {
      store.resetLabel(pendingLabel());
    }

    const permission = await detectPermission();
    if (permission === "unsupported") {
      await applyFallback(t("errors.geoUnsupported"));
      return;
    }

    if (permission === "denied") {
      store.setPermission("denied");
      await applyFallback(t("errors.geoDenied"));
      return;
    }

    resume();

    await new Promise<void>((resolve) => {
      let settled = false;

      const finish = async (fn: () => Promise<void> | void) => {
        if (settled) return;
        settled = true;
        stopWatch();
        window.clearTimeout(timeoutId);
        await fn();
        store.setLoading(false);
        resolve();
      };

      const stopWatch = watch([coords, geoError], ([nextCoords, nextError]) => {
        void (async () => {
          if (nextError) {
            await finish(async () => {
              await applyFallback(
                t("errors.geoFailed", {
                  message: nextError.message || "GPS",
                }),
              );
            });
            return;
          }

          if (
            nextCoords &&
            Number.isFinite(nextCoords.latitude) &&
            Number.isFinite(nextCoords.longitude)
          ) {
            await finish(() => {
              store.setPermission("granted");
              store.setCoords(
                {
                  latitude: nextCoords.latitude,
                  longitude: nextCoords.longitude,
                  accuracy: nextCoords.accuracy ?? null,
                },
                "gps",
              );
              try {
                window.localStorage.setItem(
                  LAST_COORDS_KEY,
                  JSON.stringify({
                    latitude: nextCoords.latitude,
                    longitude: nextCoords.longitude,
                  }),
                );
              } catch {
                // quota / private mode
              }
              applyOptimisticLabel(nextCoords.latitude, nextCoords.longitude);
              void resolveLabel(nextCoords.latitude, nextCoords.longitude);
            });
          }
        })();
      });

      // Fail fast to last-known / HCMC so rain can load; don't wait full 16s
      const timeoutId = window.setTimeout(() => {
        void finish(async () => {
          if (store.latitude != null && store.longitude != null) {
            // Keep seed coords — still resolve a place name if missing
            store.setError(null);
            applyOptimisticLabel(store.latitude, store.longitude);
            void resolveLabel(store.latitude, store.longitude);
            return;
          }
          await applyFallback(t("errors.geoTimeout"));
        });
      }, 4_500);
    });
  }

  function stopWatching() {
    pause();
  }

  return {
    store,
    requestLocation,
    setManualLocation,
    seedLastKnownCoords,
    stopWatching,
    detectPermission,
    fallbackCoords: FALLBACK_COORDS,
  };
}
