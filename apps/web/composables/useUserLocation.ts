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

function mapPermission(state: PermissionState | "unsupported"): GeolocationPermissionState {
  if (state === "unsupported") return "unsupported";
  return state;
}

export function useUserLocation() {
  const store = useLocationStore();
  const { t } = useI18n();
  const { apiFetch } = useApiClient();

  const { coords, error: geoError, resume, pause } = useGeolocation({
    enableHighAccuracy: false,
    maximumAge: 60_000,
    timeout: 8_000,
    immediate: false,
  });

  /** Sync seed so weather can start before GPS — call before kickoff fetches. */
  function seedLastKnownCoords(): boolean {
    if (store.latitude != null && store.longitude != null) return true;
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

  async function resolveLabel(latitude: number, longitude: number): Promise<void> {
    try {
      const data = await apiFetch<LocationResponse>("/api/location", {
        query: { lat: latitude, lng: longitude },
        timeout: 5_000,
      });
      store.setLabel(data.label);
    } catch {
      store.setLabel(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
    }
  }

  async function applyFallback(message: string): Promise<void> {
    store.setError(message);
    store.setCoords(FALLBACK_COORDS, "fallback");
    // Label is not on the critical path — resolve in background
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
    store.setLoading(false);
    void resolveLabel(latitude, longitude);
  }

  async function requestLocation(): Promise<void> {
    store.setLoading(true);
    store.setError(null);
    store.resetLabel();
    seedLastKnownCoords();

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
              void resolveLabel(nextCoords.latitude, nextCoords.longitude);
            });
          }
        })();
      });

      // Fail fast to last-known / HCMC so rain can load; don't wait full 16s
      const timeoutId = window.setTimeout(() => {
        void finish(async () => {
          if (store.latitude != null && store.longitude != null) {
            // Already have last-known coords — keep them, just stop waiting
            store.setError(null);
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

