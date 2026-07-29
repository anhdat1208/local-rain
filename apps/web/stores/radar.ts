import type { RadarFrame, RadarResponse } from "@local-rain/shared";
import { defineStore } from "pinia";

interface RadarState {
  frames: RadarFrame[];
  generatedAt: string | null;
  host: string | null;
  activeIndex: number;
  playing: boolean;
  loading: boolean;
  error: string | null;
  opacity: number;
}

function findCurrentFrameIndex(frames: RadarFrame[]): number {
  if (frames.length === 0) return 0;

  const nowSec = Math.floor(Date.now() / 1000);
  let bestIndex = 0;

  for (let index = 0; index < frames.length; index += 1) {
    const frame = frames[index];
    if (!frame) continue;
    if (frame.unixTime <= nowSec) {
      bestIndex = index;
    } else {
      break;
    }
  }

  return bestIndex;
}

export const useRadarStore = defineStore("radar", {
  state: (): RadarState => ({
    frames: [],
    generatedAt: null,
    host: null,
    activeIndex: 0,
    playing: false,
    loading: false,
    error: null,
    opacity: 0.72,
  }),
  getters: {
    frameCount: (state): number => state.frames.length,
    activeFrame(state): RadarFrame | null {
      if (state.frames.length === 0) return null;
      return state.frames[state.activeIndex] ?? null;
    },
    activeTimestamp(): string | null {
      return this.activeFrame?.timestamp ?? null;
    },
  },
  actions: {
    setLoading(loading: boolean) {
      this.loading = loading;
    },
    setError(error: string | null) {
      this.error = error;
      this.loading = false;
    },
    setPayload(payload: RadarResponse) {
      this.frames = payload.frames;
      this.generatedAt = payload.generatedAt;
      this.host = payload.host;
      this.activeIndex = findCurrentFrameIndex(payload.frames);
      this.playing = false;
      this.loading = false;
      this.error = null;
    },
    setActiveIndex(index: number) {
      if (this.frames.length === 0) {
        this.activeIndex = 0;
        return;
      }
      const normalized = ((index % this.frames.length) + this.frames.length) % this.frames.length;
      this.activeIndex = normalized;
    },
    nextFrame() {
      this.setActiveIndex(this.activeIndex + 1);
    },
    setPlaying(playing: boolean) {
      this.playing = playing;
    },
    togglePlaying() {
      this.playing = !this.playing;
    },
    setOpacity(opacity: number) {
      this.opacity = Math.min(1, Math.max(0.2, opacity));
    },
  },
});
