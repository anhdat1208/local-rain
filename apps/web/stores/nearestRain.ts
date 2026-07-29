import type { CompassDirection, NearestRainResponse } from "@local-rain/shared";
import { defineStore } from "pinia";

interface NearestRainState {
  distance: number;
  eta: number;
  direction: CompassDirection | null;
  confidence: number;
  explanation: string;
  advice: string;
  hasRain: boolean;
  rainLatitude: number | null;
  rainLongitude: number | null;
  motionDirection: CompassDirection | null;
  speedKmh: number;
  approaching: boolean;
  previousDistance: number | null;
  rainChance: string;
  rainChancePct: number;
  rainIn1h: boolean;
  rainIn2h: boolean;
  loading: boolean;
  error: string | null;
}

const initialState = (): NearestRainState => ({
  distance: -1,
  eta: 0,
  direction: null,
  confidence: 0,
  explanation: "",
  advice: "",
  hasRain: false,
  rainLatitude: null,
  rainLongitude: null,
  motionDirection: null,
  speedKmh: 0,
  approaching: false,
  previousDistance: null,
  rainChance: "none",
  rainChancePct: 0,
  rainIn1h: false,
  rainIn2h: false,
  loading: false,
  error: null,
});

export const useNearestRainStore = defineStore("nearestRain", {
  state: initialState,
  getters: {
    distanceKm(state): number | null {
      if (!state.hasRain || state.distance < 0) return null;
      return state.distance / 1000;
    },
    distanceLabel(state): string {
      if (!state.hasRain || state.distance < 0) return "—";
      if (state.distance >= 1000) return `${(state.distance / 1000).toFixed(1)} km`;
      return `${Math.round(state.distance)} m`;
    },
    etaLabel(state): string {
      if (!state.hasRain || !state.approaching || state.eta <= 0) return "—";
      return `${state.eta} min`;
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
    setResult(payload: NearestRainResponse) {
      this.distance = payload.distance;
      this.eta = payload.eta;
      this.direction = payload.direction;
      this.confidence = payload.confidence;
      this.explanation = payload.explanation;
      this.advice = payload.advice;
      this.hasRain = payload.hasRain;
      this.rainLatitude = payload.rainLatitude;
      this.rainLongitude = payload.rainLongitude;
      this.motionDirection = payload.motionDirection;
      this.speedKmh = payload.speedKmh;
      this.approaching = payload.approaching;
      this.previousDistance = payload.previousDistance;
      this.rainChance = payload.rainChance ?? "none";
      this.rainChancePct = payload.rainChancePct ?? 0;
      this.rainIn1h = payload.rainIn1h ?? false;
      this.rainIn2h = payload.rainIn2h ?? false;
      this.loading = false;
      this.error = null;
    },
    reset() {
      Object.assign(this, initialState());
    },
  },
});
