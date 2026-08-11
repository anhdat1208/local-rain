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
  skyState: "clear" | "partly" | "cloudy" | "cloudy_dry" | "raining" | string;
  cloudCoverPct: number;
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

export type AssistantChatRole = "user" | "assistant";

export interface AssistantChatMessage {
  id: string;
  role: AssistantChatRole;
  content: string;
  status?: string;
  facts?: AssistantWeatherFacts;
  error?: string;
}

export interface AssistantWeatherFacts {
  distanceM?: number | null;
  direction?: string | null;
  motionDirection?: string | null;
  speedKmh?: number | null;
  etaMinutes?: number | null;
  trend?: string | null;
  approaching?: boolean | null;
  confidence?: number | null;
}

export interface AssistantSelectedCell {
  latitude: number;
  longitude: number;
}

export interface AssistantSessionContext {
  latitude: number;
  longitude: number;
  lang: "vi" | "en";
  selectedCell?: AssistantSelectedCell;
  radarTimestamp?: string | null;
}

export interface AssistantHighlightAction {
  type: "highlight_rain_cell";
  latitude: number;
  longitude: number;
}

export type AssistantSSEEventType =
  | "status"
  | "text_delta"
  | "weather_facts"
  | "action"
  | "done"
  | "error";

export interface AssistantSSEEvent {
  type: AssistantSSEEventType;
  message?: string;
  content?: string;
  facts?: AssistantWeatherFacts;
  action?: AssistantHighlightAction;
  code?: string;
}
