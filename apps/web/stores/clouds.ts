import type { CloudsResponse } from "@local-rain/shared";
import { defineStore } from "pinia";

interface CloudsState {
  tileUrlTemplate: string | null;
  timestamp: string | null;
  source: string | null;
  mode: "day" | "night" | string;
  maxZoom: number;
  attribution: string | null;
  mapMode: boolean;
  loading: boolean;
  error: string | null;
  previousStreetZoom: number;
}

export const useCloudsStore = defineStore("clouds", {
  state: (): CloudsState => ({
    tileUrlTemplate: null,
    timestamp: null,
    source: null,
    mode: "night",
    maxZoom: 6,
    attribution: null,
    mapMode: false,
    loading: false,
    error: null,
    previousStreetZoom: 14,
  }),
  getters: {
    activeTileUrl(state): string | null {
      if (!state.mapMode) return null;
      return state.tileUrlTemplate;
    },
    effectiveOpacity(state): number {
      // Soft white RGBA night tiles sit on a black underlay
      return state.mapMode ? 1 : 0.42;
    },
    isDayMode(state): boolean {
      return state.mode === "day";
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
    setPayload(payload: CloudsResponse) {
      this.tileUrlTemplate =
        typeof payload.tileUrlTemplate === "string" && payload.tileUrlTemplate.length > 0
          ? payload.tileUrlTemplate
          : null;
      this.timestamp = payload.timestamp;
      this.source = payload.source;
      this.mode = payload.mode === "day" ? "day" : "night";
      this.maxZoom = Number.isFinite(payload.maxZoom) ? Number(payload.maxZoom) : 6;
      this.attribution = payload.attribution;
      this.loading = false;
      this.error = null;
    },
    enterMapMode(currentZoom: number) {
      this.previousStreetZoom = currentZoom;
      this.mapMode = true;
    },
    exitMapMode() {
      this.mapMode = false;
    },
    toggleMapMode(currentZoom: number) {
      if (this.mapMode) this.exitMapMode();
      else this.enterMapMode(currentZoom);
    },
  },
});
