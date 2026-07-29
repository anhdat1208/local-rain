import { defineStore } from "pinia";

import type { LocationSource, UserCoordinates, UserLocationState } from "~/types/location";

const DEFAULT_LABEL = "Finding location…";

export const useLocationStore = defineStore("location", {
  state: (): UserLocationState => ({
    coords: null,
    label: DEFAULT_LABEL,
    loading: false,
    error: null,
    permission: "prompt",
    source: "gps",
    updatedAt: null,
  }),
  getters: {
    hasCoords: (state): boolean => state.coords !== null,
    latitude: (state): number | null => state.coords?.latitude ?? null,
    longitude: (state): number | null => state.coords?.longitude ?? null,
    isManual: (state): boolean => state.source === "manual",
  },
  actions: {
    setLoading(loading: boolean) {
      this.loading = loading;
    },
    setPermission(permission: UserLocationState["permission"]) {
      this.permission = permission;
    },
    setError(error: string | null) {
      this.error = error;
      this.loading = false;
    },
    setCoords(coords: UserCoordinates, source: LocationSource = "gps") {
      this.coords = coords;
      this.source = source;
      this.error = null;
      this.loading = false;
      this.updatedAt = new Date().toISOString();
    },
    setLabel(label: string) {
      this.label = label;
    },
    resetLabel() {
      this.label = DEFAULT_LABEL;
    },
  },
});
