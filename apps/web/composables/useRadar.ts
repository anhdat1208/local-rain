import type { RadarResponse } from "@local-rain/shared";

import { useRadarStore } from "~/stores/radar";

const FRAME_INTERVAL_MS = 700;
const PREFETCH_ZOOM = 7;

function latLonToTile(lat: number, lon: number, zoom: number): { x: number; y: number } {
  const n = 2 ** zoom;
  const x = Math.floor(((lon + 180) / 360) * n);
  const latRad = (lat * Math.PI) / 180;
  const y = Math.floor(
    ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n,
  );
  return { x: ((x % n) + n) % n, y: Math.min(n - 1, Math.max(0, y)) };
}

export function useRadar() {
  const store = useRadarStore();
  const { t } = useI18n();
  const { apiFetch, apiBase } = useApiClient();

  let timer: ReturnType<typeof setInterval> | null = null;

  async function fetchRadar(): Promise<void> {
    store.setLoading(true);
    store.setError(null);
    try {
      const data = await apiFetch<RadarResponse>("/api/radar");
      store.setPayload(data);
      store.setPlaying(false);
    } catch {
      store.setError(t("errors.radar"));
      store.setPlaying(false);
    }
  }

  /** Warm the filtered radar tiles around the user so the map paints without hitching. */
  function prefetchAround(latitude: number, longitude: number, radius = 1): void {
    if (!import.meta.client) return;
    const frame = store.activeFrame;
    if (!frame?.unixTime) return;
    const template = frame.tileUrlTemplate;
    if (!template) return;

    const origin = latLonToTile(latitude, longitude, PREFETCH_ZOOM);
    const n = 2 ** PREFETCH_ZOOM;
    const urls: string[] = [];
    for (let dx = -radius; dx <= radius; dx += 1) {
      for (let dy = -radius; dy <= radius; dy += 1) {
        const x = (((origin.x + dx) % n) + n) % n;
        const y = origin.y + dy;
        if (y < 0 || y >= n) continue;
        const path = template
          .replace("{z}", String(PREFETCH_ZOOM))
          .replace("{x}", String(x))
          .replace("{y}", String(y));
        const url = path.startsWith("http") ? path : `${apiBase.value}${path}`;
        urls.push(url);
      }
    }
    for (const url of urls) {
      void fetch(url, { mode: "cors", cache: "force-cache" }).catch(() => undefined);
    }
  }

  function clearTimer() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function startPlayback() {
    clearTimer();
    if (!import.meta.client || store.frameCount === 0) return;
    timer = setInterval(() => {
      store.nextFrame();
    }, FRAME_INTERVAL_MS);
  }

  function stopPlayback() {
    clearTimer();
  }

  watch(
    () => store.playing,
    (playing) => {
      if (playing) startPlayback();
      else stopPlayback();
    },
  );

  onBeforeUnmount(() => {
    stopPlayback();
    store.setPlaying(false);
  });

  return {
    store,
    fetchRadar,
    prefetchAround,
    startPlayback,
    stopPlayback,
  };
}
