import type { RadarResponse } from "@local-rain/shared";

import { useRadarStore } from "~/stores/radar";

const FRAME_INTERVAL_MS = 700;

export function useRadar() {
  const store = useRadarStore();
  const { t } = useI18n();
  const { apiFetch } = useApiClient();

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
    startPlayback,
    stopPlayback,
  };
}
