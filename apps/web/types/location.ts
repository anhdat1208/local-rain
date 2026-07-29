export type GeolocationPermissionState = "prompt" | "granted" | "denied" | "unsupported";

export type LocationSource = "gps" | "manual" | "fallback";

export interface UserCoordinates {
  latitude: number;
  longitude: number;
  accuracy: number | null;
}

export interface UserLocationState {
  coords: UserCoordinates | null;
  label: string;
  loading: boolean;
  error: string | null;
  permission: GeolocationPermissionState;
  source: LocationSource;
  updatedAt: string | null;
}
