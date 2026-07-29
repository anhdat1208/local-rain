import type { LocationResponse } from "@local-rain/shared";
import { useGeolocation } from "@vueuse/core";

import { useLocationStore } from "~/stores/location";
import type { GeolocationPermissionState, LocationSource } from "~/types/location";

const FALLBACK_COORDS = {
  latitude: 10.7401,
  longitude: 106.6653,
  accuracy: null as number | null,
};

function mapPermission(state: PermissionState | "unsupported"): GeolocationPermissionState {
  if (state === "unsupported") return "unsupported";
  return state;
}

export function useUserLocation() {
  const store = useLocationStore();
  const { t } = useI18n();
  const { apiFetch } = useApiClient();

  const { coords, error: geoError, resume, pause } = useGeolocation({
    enableHighAccuracy: true,
    maximumAge: 10_000,
    timeout: 15_000,
    immediate: false,
  });

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
      });
      store.setLabel(data.label);
    } catch {
      store.setLabel(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
    }
  }

  async function applyFallback(message: string): Promise<void> {
    store.setError(message);
    store.setCoords(FALLBACK_COORDS, "fallback");
    await resolveLabel(FALLBACK_COORDS.latitude, FALLBACK_COORDS.longitude);
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
    await resolveLabel(latitude, longitude);
    store.setLoading(false);
  }

  async function requestLocation(): Promise<void> {
    store.setLoading(true);
    store.setError(null);
    store.resetLabel();

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

      const finish = async (fn: () => Promise<void>) => {
        if (settled) return;
        settled = true;
        stopWatch();
        window.clearTimeout(timeoutId);
        await fn();
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
            await finish(async () => {
              store.setPermission("granted");
              store.setCoords(
                {
                  latitude: nextCoords.latitude,
                  longitude: nextCoords.longitude,
                  accuracy: nextCoords.accuracy ?? null,
                },
                "gps",
              );
              await resolveLabel(nextCoords.latitude, nextCoords.longitude);
            });
          }
        })();
      });

      const timeoutId = window.setTimeout(() => {
        void finish(async () => {
          await applyFallback(t("errors.geoTimeout"));
        });
      }, 16_000);
    });
  }

  function stopWatching() {
    pause();
  }

  return {
    store,
    requestLocation,
    setManualLocation,
    stopWatching,
    detectPermission,
    fallbackCoords: FALLBACK_COORDS,
  };
}
