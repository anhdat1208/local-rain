<script setup lang="ts">
import type {
  GeoJSONSource,
  Map,
  MapSourceDataEvent,
  Marker,
  RasterTileSource,
} from "maplibre-gl";

import type { RainVectorItem } from "@local-rain/shared";
import type { LocationSource } from "~/types/location";
import {
  syncVietnamSovereigntyLabels,
  VN_ISLAND_LAYER,
  VN_SOVEREIGNTY_TEXT_FIELD,
} from "~/utils/vietnamMapLabels";

type MapLibreModule = typeof import("maplibre-gl");
let maplibregl: MapLibreModule["default"] | null = null;

const RADAR_BUFFERS = [
  { sourceId: "radar-source-a", layerId: "radar-layer-a" },
  { sourceId: "radar-source-b", layerId: "radar-layer-b" },
] as const;

const CLOUD_SOURCE_ID = "cloud-source";
const CLOUD_LAYER_ID = "cloud-layer";
const CLOUD_NIGHT_BG_LAYER = "cloud-night-bg";
const GEO_SOURCE_ID = "openmaptiles";
const SAT_COAST_LAYER = "sat-coastline";
const SAT_BOUNDARY_LAYER = "sat-boundary";
const SAT_LABEL_LAYER = "sat-place-label";
const SAT_GEO_LAYERS = [SAT_COAST_LAYER, SAT_BOUNDARY_LAYER, SAT_LABEL_LAYER] as const;
const RAIN_LINE_SOURCE = "nearest-rain-line";
const RAIN_LINE_LAYER = "nearest-rain-line-layer";
const RAIN_VECTOR_SOURCE = "rain-vectors-source";
const RAIN_VECTOR_LINE_LAYER = "rain-vectors-line-layer";
const RAIN_VECTOR_ARROW_LAYER = "rain-vectors-arrow-layer";

const BASEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty";
const CROSSFADE_MS = 220;
const CLOUD_VIEW_ZOOM = 5.6;


const props = withDefaults(
  defineProps<{
    latitude: number;
    longitude: number;
    zoom?: number;
    followUser?: boolean;
    pickMode?: boolean;
    locationSource?: LocationSource;
    radarTileUrl?: string | null;
    radarOpacity?: number;
    cloudTileUrl?: string | null;
    cloudOpacity?: number;
    cloudMaxZoom?: number;
    cloudMapMode?: boolean;
    cloudDayMode?: boolean;
    rainVectors?: RainVectorItem[];
    rainLatitude?: number | null;
    rainLongitude?: number | null;
  }>(),
  {
    zoom: 13,
    followUser: true,
    pickMode: false,
    locationSource: "gps",
    radarTileUrl: null,
    radarOpacity: 0.65,
    cloudTileUrl: null,
    cloudOpacity: 0.42,
    cloudMaxZoom: 6,
    cloudMapMode: false,
    cloudDayMode: false,
    rainVectors: () => [],
    rainLatitude: null,
    rainLongitude: null,
  },
);

const emit = defineEmits<{
  ready: [map: Map];
  userinteract: [];
  mapclick: [point: { latitude: number; longitude: number }];
}>();

const containerRef = ref<HTMLElement | null>(null);
const map = shallowRef<Map | null>(null);
const marker = shallowRef<Marker | null>(null);
const rainMarker = shallowRef<Marker | null>(null);
const isReady = ref(false);

let activeBuffer = 0;
let currentTileUrl: string | null = null;
let pendingSwapTimer: ReturnType<typeof setTimeout> | null = null;
let pendingSourceHandler: ((event: MapSourceDataEvent) => void) | null = null;
let styleSwapToken = 0;
let disposed = false;

function safeNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function createUserMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "lr-user-marker";
  el.dataset.source = props.locationSource;
  el.innerHTML = `
    <span class="lr-user-marker__pulse"></span>
    <span class="lr-user-marker__dot"></span>
  `;
  return el;
}

function createRainMarkerElement(): HTMLDivElement {
  const el = document.createElement("div");
  el.className = "lr-rain-marker";
  el.innerHTML = `<span class="lr-rain-marker__dot"></span>`;
  return el;
}

function activeMap(): Map | null {
  const instance = map.value;
  if (!instance || disposed || !isReady.value) return null;
  return instance;
}

function arrowHeadCoordinates(
  from: [number, number],
  to: [number, number],
): [number, number][] {
  const latScale = Math.cos((to[1] * Math.PI) / 180) || 1;
  const dx = (to[0] - from[0]) * latScale;
  const dy = to[1] - from[1];
  const length = Math.hypot(dx, dy);
  if (length === 0) return [];

  const headLength = length * 0.27;
  const angle = Math.atan2(dy, dx);
  const wing = (offset: number): [number, number] => {
    const theta = angle + Math.PI + offset;
    return [
      to[0] + (Math.cos(theta) * headLength) / latScale,
      to[1] + Math.sin(theta) * headLength,
    ];
  };

  const spread = Math.PI / 7;
  return [wing(-spread), to, wing(spread)];
}

function syncRainVectors() {
  const instance = activeMap();
  if (!instance) return;

  const vectors = props.rainVectors ?? [];
  if (vectors.length === 0 || cloudsStoreLikeSatellite()) {
    if (instance.getLayer(RAIN_VECTOR_ARROW_LAYER)) instance.removeLayer(RAIN_VECTOR_ARROW_LAYER);
    if (instance.getLayer(RAIN_VECTOR_LINE_LAYER)) instance.removeLayer(RAIN_VECTOR_LINE_LAYER);
    if (instance.getSource(RAIN_VECTOR_SOURCE)) instance.removeSource(RAIN_VECTOR_SOURCE);
    return;
  }

  // Keep arrows a constant share of the viewport so they read at any zoom level
  const bounds = instance.getBounds();
  const targetSpan = Math.abs(bounds.getEast() - bounds.getWest()) * 0.12;

  const geojson = {
    type: "FeatureCollection" as const,
    features: vectors.flatMap((item) => {
      if (
        !Number.isFinite(item.longitude) ||
        !Number.isFinite(item.latitude) ||
        !Number.isFinite(item.toLongitude) ||
        !Number.isFinite(item.toLatitude)
      ) {
        return [];
      }
      const from: [number, number] = [item.longitude, item.latitude];
      const latScale = Math.cos((item.latitude * Math.PI) / 180) || 1;
      const dx = (item.toLongitude - item.longitude) * latScale;
      const dy = item.toLatitude - item.latitude;
      const length = Math.hypot(dx, dy);
      if (length === 0) return [];
      const scale = targetSpan / length;
      const to: [number, number] = [
        item.longitude + ((dx * scale) / latScale),
        item.latitude + dy * scale,
      ];
      const head = arrowHeadCoordinates(from, to);
      const features = [
        {
          type: "Feature" as const,
          properties: { kind: "shaft", speedKmh: item.speedKmh },
          geometry: { type: "LineString" as const, coordinates: [from, to] },
        },
      ];
      if (head.length > 0) {
        features.push({
          type: "Feature" as const,
          properties: { kind: "head", speedKmh: item.speedKmh },
          geometry: { type: "LineString" as const, coordinates: head },
        });
      }
      return features;
    }),
  };

  const existing = instance.getSource(RAIN_VECTOR_SOURCE) as GeoJSONSource | undefined;
  if (existing) {
    existing.setData(geojson);
    return;
  }

  instance.addSource(RAIN_VECTOR_SOURCE, { type: "geojson", data: geojson });
  instance.addLayer({
    id: RAIN_VECTOR_LINE_LAYER,
    type: "line",
    source: RAIN_VECTOR_SOURCE,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#0e7490",
      "line-width": 2.6,
      "line-opacity": 0.95,
    },
  });
  // Second pass draws a light core so the arrows read on both radar and basemap
  instance.addLayer({
    id: RAIN_VECTOR_ARROW_LAYER,
    type: "line",
    source: RAIN_VECTOR_SOURCE,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: {
      "line-color": "#ffffff",
      "line-width": 1,
      "line-opacity": 0.9,
    },
  });
}

function cloudsStoreLikeSatellite(): boolean {
  return props.cloudMapMode;
}

function syncNearestRainOverlay() {
  const instance = map.value;
  if (!instance || !isReady.value) return;

  const hasRain =
    props.rainLatitude != null &&
    props.rainLongitude != null &&
    Number.isFinite(props.rainLatitude) &&
    Number.isFinite(props.rainLongitude);

  const hasUser =
    Number.isFinite(props.latitude) && Number.isFinite(props.longitude);

  if (!hasRain || !hasUser) {
    rainMarker.value?.remove();
    rainMarker.value = null;
    if (instance.getLayer(RAIN_LINE_LAYER)) instance.removeLayer(RAIN_LINE_LAYER);
    if (instance.getSource(RAIN_LINE_SOURCE)) instance.removeSource(RAIN_LINE_SOURCE);
    return;
  }

  const rainLngLat: [number, number] = [props.rainLongitude!, props.rainLatitude!];

  if (!rainMarker.value) {
    if (!maplibregl) return;
    rainMarker.value = new maplibregl.Marker({
      element: createRainMarkerElement(),
      anchor: "center",
    })
      .setLngLat(rainLngLat)
      .addTo(instance);
  } else {
    rainMarker.value.setLngLat(rainLngLat);
  }

  const lineData = {
    type: "Feature" as const,
    properties: {},
    geometry: {
      type: "LineString" as const,
      coordinates: [
        [props.longitude, props.latitude],
        rainLngLat,
      ],
    },
  };

  const existing = instance.getSource(RAIN_LINE_SOURCE) as GeoJSONSource | undefined;
  if (existing) {
    existing.setData(lineData);
  } else {
    instance.addSource(RAIN_LINE_SOURCE, {
      type: "geojson",
      data: lineData,
    });
    instance.addLayer({
      id: RAIN_LINE_LAYER,
      type: "line",
      source: RAIN_LINE_SOURCE,
      paint: {
        "line-color": "#0ea5e9",
        "line-width": 2.5,
        "line-opacity": 0.75,
        "line-dasharray": [1.2, 1.2],
      },
    });
  }
}

function syncMarkerAppearance() {
  const el = marker.value?.getElement();
  if (!el) return;
  el.dataset.source = props.locationSource;
}

function clearPendingSwap(instance: Map) {
  if (pendingSwapTimer !== null) {
    clearTimeout(pendingSwapTimer);
    pendingSwapTimer = null;
  }
  if (pendingSourceHandler) {
    instance.off("sourcedata", pendingSourceHandler);
    pendingSourceHandler = null;
  }
}

function upsertRadarBuffer(instance: Map, bufferIndex: number, tileUrl: string, opacity: number) {
  const buffer = RADAR_BUFFERS[bufferIndex];
  if (!buffer) return;

  const existing = instance.getSource(buffer.sourceId) as RasterTileSource | undefined;
  if (existing) {
    existing.setTiles([tileUrl]);
  } else {
    // RainViewer radar tiles only exist for z0–z7; maxzoom lets MapLibre overzoom.
    instance.addSource(buffer.sourceId, {
      type: "raster",
      tiles: [tileUrl],
      tileSize: 256,
      minzoom: 0,
      maxzoom: 7,
      attribution: "RainViewer",
    });
  }

  if (!instance.getLayer(buffer.layerId)) {
    instance.addLayer({
      id: buffer.layerId,
      type: "raster",
      source: buffer.sourceId,
      paint: {
        "raster-opacity": opacity,
        "raster-opacity-transition": { duration: CROSSFADE_MS, delay: 0 },
        "raster-fade-duration": 0,
      },
    });
  } else {
    instance.setPaintProperty(buffer.layerId, "raster-opacity", opacity);
  }
}

function removeRadarBuffers(instance: Map) {
  clearPendingSwap(instance);
  for (const buffer of RADAR_BUFFERS) {
    if (instance.getLayer(buffer.layerId)) {
      instance.removeLayer(buffer.layerId);
    }
    if (instance.getSource(buffer.sourceId)) {
      instance.removeSource(buffer.sourceId);
    }
  }
  activeBuffer = 0;
  currentTileUrl = null;
}

function applyActiveOpacity(opacity: number) {
  const instance = map.value;
  if (!instance || !isReady.value) return;

  const active = RADAR_BUFFERS[activeBuffer];
  if (active && instance.getLayer(active.layerId)) {
    instance.setPaintProperty(active.layerId, "raster-opacity", opacity);
  }

  const inactive = RADAR_BUFFERS[1 - activeBuffer];
  if (inactive && instance.getLayer(inactive.layerId)) {
    instance.setPaintProperty(inactive.layerId, "raster-opacity", 0);
  }
}

function swapToBuffer(instance: Map, nextBuffer: number, tileUrl: string) {
  const next = RADAR_BUFFERS[nextBuffer];
  const prev = RADAR_BUFFERS[activeBuffer];
  if (!next || !prev) return;

  instance.setPaintProperty(next.layerId, "raster-opacity", props.radarOpacity);
  if (instance.getLayer(prev.layerId) && nextBuffer !== activeBuffer) {
    instance.setPaintProperty(prev.layerId, "raster-opacity", 0);
  }

  activeBuffer = nextBuffer;
  currentTileUrl = tileUrl;
}

function showRadarFrame(tileUrl: string) {
  const instance = map.value;
  if (!instance || !isReady.value) return;

  if (tileUrl === currentTileUrl) {
    applyActiveOpacity(props.radarOpacity);
    return;
  }

  // First frame: no crossfade needed.
  if (!currentTileUrl) {
    upsertRadarBuffer(instance, 0, tileUrl, props.radarOpacity);
    activeBuffer = 0;
    currentTileUrl = tileUrl;
    return;
  }

  clearPendingSwap(instance);

  const nextBuffer = 1 - activeBuffer;
  const next = RADAR_BUFFERS[nextBuffer];
  if (!next) return;

  upsertRadarBuffer(instance, nextBuffer, tileUrl, 0);

  const finish = () => {
    clearPendingSwap(instance);
    swapToBuffer(instance, nextBuffer, tileUrl);
  };

  pendingSourceHandler = (event: MapSourceDataEvent) => {
    if (event.sourceId === next.sourceId && event.isSourceLoaded) {
      finish();
    }
  };
  instance.on("sourcedata", pendingSourceHandler);
  pendingSwapTimer = setTimeout(finish, 450);
}

function syncRadarFrame() {
  const instance = map.value;
  if (!instance || !isReady.value) return;

  // Satellite mode focuses on cloud field; hide radar colors to avoid visual clash.
  if (props.cloudMapMode) {
    removeRadarBuffers(instance);
    return;
  }

  if (!props.radarTileUrl) {
    removeRadarBuffers(instance);
    return;
  }

  showRadarFrame(props.radarTileUrl);
}

function cloudBeforeId(instance: Map): string | undefined {
  for (const buffer of RADAR_BUFFERS) {
    if (instance.getLayer(buffer.layerId)) return buffer.layerId;
  }
  if (instance.getLayer(RAIN_LINE_LAYER)) return RAIN_LINE_LAYER;
  return undefined;
}

function styleVietnamSovereigntyOverlay(instance: Map, satellite: boolean) {
  if (!instance.getLayer(VN_ISLAND_LAYER)) return;
  if (satellite) {
    instance.setPaintProperty(VN_ISLAND_LAYER, "text-color", "#f8fafc");
    instance.setPaintProperty(VN_ISLAND_LAYER, "text-halo-color", "rgba(2,6,23,0.9)");
  } else {
    instance.setPaintProperty(VN_ISLAND_LAYER, "text-color", "#0f172a");
    instance.setPaintProperty(VN_ISLAND_LAYER, "text-halo-color", "rgba(255,255,255,0.92)");
  }
}

function removeCloudLayer(instance: Map) {
  if (instance.getLayer(CLOUD_LAYER_ID)) {
    instance.removeLayer(CLOUD_LAYER_ID);
  }
  if (instance.getSource(CLOUD_SOURCE_ID)) {
    instance.removeSource(CLOUD_SOURCE_ID);
  }
  if (instance.getLayer(CLOUD_NIGHT_BG_LAYER)) {
    instance.removeLayer(CLOUD_NIGHT_BG_LAYER);
  }
  removeSatelliteGeography(instance);
}

function removeSatelliteGeography(instance: Map) {
  for (const layerId of SAT_GEO_LAYERS) {
    if (instance.getLayer(layerId)) instance.removeLayer(layerId);
  }
}

function syncSatelliteGeography(instance: Map) {
  // Satellite imagery alone is unreadable — coastlines, borders and city names sit
  // above the cloud raster so the viewer can tell what they are looking at.
  if (!props.cloudMapMode || !instance.getSource(GEO_SOURCE_ID)) {
    removeSatelliteGeography(instance);
    return;
  }

  const dayMode = props.cloudDayMode;
  const coastColor = dayMode ? "rgba(226,240,255,0.70)" : "rgba(150,196,235,0.34)";
  const borderColor = dayMode ? "rgba(255,255,255,0.55)" : "rgba(190,205,225,0.32)";
  const labelColor = dayMode ? "#f8fafc" : "#e2e8f0";

  if (!instance.getLayer(SAT_COAST_LAYER)) {
    instance.addLayer({
      id: SAT_COAST_LAYER,
      type: "line",
      source: GEO_SOURCE_ID,
      "source-layer": "water",
      filter: ["!=", ["get", "brunnel"], "tunnel"],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": coastColor,
        "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.3, 6, 0.6, 10, 1.1],
      },
    });
  } else {
    instance.setPaintProperty(SAT_COAST_LAYER, "line-color", coastColor);
  }

  if (!instance.getLayer(SAT_BOUNDARY_LAYER)) {
    instance.addLayer({
      id: SAT_BOUNDARY_LAYER,
      type: "line",
      source: GEO_SOURCE_ID,
      "source-layer": "boundary",
      filter: [
        "all",
        ["<=", ["get", "admin_level"], 2],
        ["!=", ["get", "maritime"], 1],
      ],
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": borderColor,
        "line-dasharray": [3, 2],
        "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 8, 1.1],
      },
    });
  } else {
    instance.setPaintProperty(SAT_BOUNDARY_LAYER, "line-color", borderColor);
  }

  if (!instance.getLayer(SAT_LABEL_LAYER)) {
    instance.addLayer({
      id: SAT_LABEL_LAYER,
      type: "symbol",
      source: GEO_SOURCE_ID,
      "source-layer": "place",
      filter: ["in", ["get", "class"], ["literal", ["city", "country"]]],
      layout: {
        "text-field": VN_SOVEREIGNTY_TEXT_FIELD as never,
        "text-font": ["Noto Sans Regular"],
        "text-size": ["interpolate", ["linear"], ["zoom"], 3, 10, 7, 12.5, 11, 15],
        "text-max-width": 8,
        "text-padding": 6,
      },
      paint: {
        "text-color": labelColor,
        "text-halo-color": "rgba(2,6,23,0.85)",
        "text-halo-width": 1.4,
        "text-halo-blur": 0.6,
      },
    });
  } else {
    instance.setPaintProperty(SAT_LABEL_LAYER, "text-color", labelColor);
    instance.setLayoutProperty(SAT_LABEL_LAYER, "text-field", VN_SOVEREIGNTY_TEXT_FIELD as never);
  }

  // Above the imagery, but still below the rain overlays.
  const beforeId = [RAIN_VECTOR_LINE_LAYER, RAIN_LINE_LAYER].find((layerId) =>
    instance.getLayer(layerId),
  );
  for (const layerId of SAT_GEO_LAYERS) {
    if (instance.getLayer(layerId)) instance.moveLayer(layerId, beforeId);
  }

  styleVietnamSovereigntyOverlay(instance, dayMode);
  syncVietnamSovereigntyLabels(instance, beforeId);
}

function syncNightUnderlay(instance: Map) {
  // Zoom Earth night: deep black field under soft white cloud tiles
  const wantDark = props.cloudMapMode && !props.cloudDayMode;
  const hasBg = Boolean(instance.getLayer(CLOUD_NIGHT_BG_LAYER));
  if (!wantDark) {
    if (hasBg) instance.removeLayer(CLOUD_NIGHT_BG_LAYER);
    return;
  }
  if (!hasBg) {
    instance.addLayer(
      {
        id: CLOUD_NIGHT_BG_LAYER,
        type: "background",
        paint: {
          "background-color": "#020617",
          "background-opacity": 1,
        },
      },
      instance.getLayer(CLOUD_LAYER_ID) ? CLOUD_LAYER_ID : cloudBeforeId(instance),
    );
  }
}

function applyCloudPaint(instance: Map) {
  syncNightUnderlay(instance);
  if (!instance.getLayer(CLOUD_LAYER_ID)) {
    removeSatelliteGeography(instance);
    return;
  }
  const mapMode = props.cloudMapMode;
  const dayMode = props.cloudDayMode;
  const nightMap = mapMode && !dayMode;
  const opacity = safeNumber(props.cloudOpacity, 0.42);
  instance.setPaintProperty(CLOUD_LAYER_ID, "raster-opacity", opacity);
  instance.setPaintProperty(CLOUD_LAYER_ID, "raster-resampling", "linear");
  // Night tiles already carry the finished grey ramp; any extra contrast or
  // brightness clamp here would crush the midtones back into blotches.
  instance.setPaintProperty(
    CLOUD_LAYER_ID,
    "raster-contrast",
    nightMap ? 0 : mapMode ? 0.3 : 0.08,
  );
  instance.setPaintProperty(
    CLOUD_LAYER_ID,
    "raster-saturation",
    nightMap ? 0 : mapMode ? -0.12 : -0.15,
  );
  instance.setPaintProperty(CLOUD_LAYER_ID, "raster-brightness-max", 1);
  instance.setPaintProperty(CLOUD_LAYER_ID, "raster-brightness-min", 0);
  syncSatelliteGeography(instance);
}

function syncCloudLayer() {
  const instance = map.value;
  if (!instance || !isReady.value) return;

  if (!props.cloudTileUrl) {
    removeCloudLayer(instance);
    return;
  }

  const existing = instance.getSource(CLOUD_SOURCE_ID) as RasterTileSource | undefined;
  if (existing) {
    existing.setTiles([props.cloudTileUrl]);
  } else {
    const maxZoom = safeNumber(props.cloudMaxZoom, 6);
    instance.addSource(CLOUD_SOURCE_ID, {
      type: "raster",
      tiles: [props.cloudTileUrl],
      tileSize: 256,
      minzoom: 0,
      maxzoom: maxZoom,
      attribution: "NASA GIBS / Himawari",
    });
  }

  if (!instance.getLayer(CLOUD_LAYER_ID)) {
    const opacity = safeNumber(props.cloudOpacity, 0.42);
    instance.addLayer(
      {
        id: CLOUD_LAYER_ID,
        type: "raster",
        source: CLOUD_SOURCE_ID,
        paint: {
          "raster-opacity": opacity,
          "raster-fade-duration": 0,
          "raster-resampling": "linear",
          "raster-contrast": 0.08,
          "raster-saturation": -0.2,
        },
      },
      cloudBeforeId(instance),
    );
  }

  applyCloudPaint(instance);
}

function reapplyOverlaysAfterStyle() {
  currentTileUrl = null;
  activeBuffer = 0;
  if (!props.cloudMapMode) {
    syncCloudLayer();
  } else {
    applyCloudPaint(map.value!);
  }
  syncRadarFrame();
  syncRainVectors();
  syncNearestRainOverlay();
}

function applyBasemapForMode() {
  const instance = map.value;
  if (!instance || !isReady.value) return;
  // Stability-first mode: keep base style, only update cloud overlay.
  syncCloudLayer();
  applyCloudPaint(instance);
  syncRadarFrame();
  syncRainVectors();
  syncNearestRainOverlay();
  syncVietnamSovereigntyLabels(instance);
  styleVietnamSovereigntyOverlay(instance, Boolean(props.cloudMapMode));
}

function syncCursor() {
  const canvas = map.value?.getCanvas();
  if (!canvas) return;
  canvas.style.cursor = props.pickMode ? "crosshair" : "";
}

function initMap() {
  if (!containerRef.value || map.value) return;

  void (async () => {
    if (!maplibregl) {
      const mod = await import("maplibre-gl");
      await import("maplibre-gl/dist/maplibre-gl.css");
      maplibregl = mod.default;
    }
    if (!containerRef.value || map.value || disposed) return;

    const instance = new maplibregl.Map({
      container: containerRef.value,
      style: BASEMAP_STYLE,
      center: [props.longitude, props.latitude],
      zoom: props.zoom,
      attributionControl: { compact: true },
      maxTileCacheSize: 80,
      fadeDuration: 0,
      cancelPendingTileRequestsWhileZooming: true,
      transformRequest: (url) => {
        if (!needsNgrokBypass(url)) return { url };
        return {
          url,
          headers: withNgrokHeaders(url),
        };
      },
    });

    instance.on("load", () => {
      if (disposed) return;
      isReady.value = true;
      // Handle used by the scripts/e2e browser checks to assert layer state
      (window as unknown as { __lrMap?: Map }).__lrMap = instance;
      instance.addControl(
        new maplibregl!.NavigationControl({ showCompass: false }),
        "top-right",
      );
      syncVietnamSovereigntyLabels(instance);
      styleVietnamSovereigntyOverlay(instance, Boolean(props.cloudMapMode));
      syncCloudLayer();
      syncRadarFrame();
      syncRainVectors();
      syncNearestRainOverlay();
      syncCursor();
      emit("ready", instance);
    });

    instance.on("zoomend", () => syncRainVectors());
    instance.on("dragstart", () => emit("userinteract"));
    instance.on("zoomstart", (event) => {
      if (event.originalEvent) emit("userinteract");
    });
    instance.on("click", (event) => {
      emit("mapclick", {
        latitude: event.lngLat.lat,
        longitude: event.lngLat.lng,
      });
    });

    const userMarker = new maplibregl.Marker({
      element: createUserMarkerElement(),
      anchor: "center",
    })
      .setLngLat([props.longitude, props.latitude])
      .addTo(instance);

    map.value = instance;
    marker.value = userMarker;
  })();
}

function flyToUser(latitude: number, longitude: number) {
  if (!map.value) return;
  map.value.flyTo({
    center: [longitude, latitude],
    zoom: Math.max(map.value.getZoom(), 14),
    essential: true,
    duration: 900,
  });
}

function flyToCloudView(latitude: number, longitude: number) {
  if (!map.value) return;
  map.value.flyTo({
    center: [longitude, latitude],
    zoom: CLOUD_VIEW_ZOOM,
    essential: true,
    duration: 1100,
  });
}

function flyToStreetView(latitude: number, longitude: number, zoom = 14) {
  if (!map.value) return;
  map.value.flyTo({
    center: [longitude, latitude],
    zoom,
    essential: true,
    duration: 1000,
  });
}

function getZoom(): number {
  return map.value?.getZoom() ?? 14;
}

function recenter() {
  flyToUser(props.latitude, props.longitude);
}

watch(
  () => [props.latitude, props.longitude] as const,
  ([latitude, longitude]) => {
    marker.value?.setLngLat([longitude, latitude]);
    if (props.followUser && isReady.value) {
      flyToUser(latitude, longitude);
    }
  },
);

watch(
  () => props.radarTileUrl,
  () => syncRadarFrame(),
);

watch(
  () => props.radarOpacity,
  (opacity) => applyActiveOpacity(opacity),
);

watch(
  () => props.cloudMapMode,
  () => {
    if (!isReady.value) return;
    applyBasemapForMode();
  },
);

watch(
  () => [props.cloudTileUrl, props.cloudMaxZoom, props.cloudDayMode] as const,
  () => {
    if (!isReady.value) return;

    // Tile URL often arrives after Satellite mode is already on — rebuild style then.
    if (props.cloudMapMode) {
      if (!props.cloudTileUrl) return;
      const instance = map.value;
      if (!instance) return;
      const existing = instance.getSource(CLOUD_SOURCE_ID) as RasterTileSource | undefined;
      if (existing) {
        existing.setTiles([props.cloudTileUrl]);
        applyCloudPaint(instance);
      } else {
        applyBasemapForMode();
      }
      return;
    }

    syncCloudLayer();
  },
);

watch(
  () => [props.cloudOpacity, props.cloudMapMode, props.cloudDayMode] as const,
  () => {
    const instance = activeMap();
    if (!instance?.getLayer(CLOUD_LAYER_ID)) return;
    applyCloudPaint(instance);
  },
);

watch(
  () => props.pickMode,
  () => syncCursor(),
);

watch(
  () => props.locationSource,
  () => syncMarkerAppearance(),
);

watch(
  () =>
    [props.rainLatitude, props.rainLongitude, props.latitude, props.longitude] as const,
  () => syncNearestRainOverlay(),
);

watch(
  () => props.rainVectors,
  () => syncRainVectors(),
  { deep: true },
);

onMounted(() => {
  nextTick(() => initMap());
});

onBeforeUnmount(() => {
  disposed = true;
  isReady.value = false;
  if (map.value) {
    clearPendingSwap(map.value);
  }
  rainMarker.value?.remove();
  marker.value?.remove();
  map.value?.remove();
  rainMarker.value = null;
  marker.value = null;
  map.value = null;
});

defineExpose({
  recenter,
  flyToCloudView,
  flyToStreetView,
  getZoom,
  getMap: () => map.value,
});
</script>

<template>
  <div
    class="relative h-full w-full overflow-hidden bg-slate-100"
    :class="{ 'lr-map--pick': pickMode }"
  >
    <div ref="containerRef" class="h-full w-full" />
    <div
      v-if="!isReady"
      class="pointer-events-none absolute inset-0 flex items-center justify-center bg-surface-muted/70"
    >
      <div class="h-10 w-10 animate-pulse rounded-full bg-rain/40" />
    </div>
  </div>
</template>

<style scoped>
:deep(.lr-user-marker) {
  position: relative;
  width: 22px;
  height: 22px;
}

:deep(.lr-user-marker__dot) {
  position: absolute;
  inset: 4px;
  border-radius: 9999px;
  background: #0ea5e9;
  border: 2px solid #ffffff;
  box-shadow: 0 2px 10px rgba(14, 165, 233, 0.5);
}

:deep(.lr-user-marker[data-source="manual"] .lr-user-marker__dot) {
  background: #0284c7;
  inset: 3px;
}

:deep(.lr-user-marker__pulse) {
  position: absolute;
  inset: 0;
  border-radius: 9999px;
  background: rgba(14, 165, 233, 0.35);
  animation: lr-pulse 2s ease-out infinite;
}

:deep(.lr-user-marker[data-source="manual"] .lr-user-marker__pulse) {
  animation: none;
  background: transparent;
}

:deep(.lr-rain-marker) {
  width: 16px;
  height: 16px;
}

:deep(.lr-rain-marker__dot) {
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 9999px;
  background: #38bdf8;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.25);
}

@keyframes lr-pulse {
  0% {
    transform: scale(0.7);
    opacity: 0.8;
  }
  100% {
    transform: scale(2.4);
    opacity: 0;
  }
}
</style>
