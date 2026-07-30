export type CompassDirection =
  | "N"
  | "NE"
  | "E"
  | "SE"
  | "S"
  | "SW"
  | "W"
  | "NW";

export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  postgres: boolean;
  redis: boolean;
  version: string;
}

export interface LocationResponse {
  latitude: number;
  longitude: number;
  label: string;
}

export interface RadarFrame {
  timestamp: string;
  unixTime: number;
  tileUrlTemplate: string;
}

export interface RadarResponse {
  frames: RadarFrame[];
  generatedAt: string;
  host: string;
}

export interface CloudsResponse {
  tileUrlTemplate: string;
  timestamp: string;
  source: string;
  mode: "day" | "night" | string;
  maxZoom: number;
  attribution: string;
}

export interface NearestRainResponse {
  distance: number;
  eta: number;
  direction: CompassDirection;
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
  rainChance: "none" | "low" | "medium" | "high" | string;
  rainChancePct: number;
  rainIn1h: boolean;
  rainIn2h: boolean;
  rainingHere: boolean;
  radarTimestamp: string | null;
  radarAgeMinutes: number;
}

export interface RainVectorItem {
  latitude: number;
  longitude: number;
  toLatitude: number;
  toLongitude: number;
  speedKmh: number;
  direction: CompassDirection;
  dbz: number;
}

export interface RainVectorsResponse {
  vectors: RainVectorItem[];
  generatedAt: string;
}
