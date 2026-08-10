import type { Map } from "maplibre-gl";

/** Force Vietnamese sovereignty labels for East Sea features on OpenFreeMap/OSM tiles. */

export const VN_ISLAND_SOURCE = "vn-sovereignty-labels";
export const VN_ISLAND_LAYER = "vn-sovereignty-labels-layer";
const SAT_LABEL_LAYER = "sat-place-label";

function blob() {
  // Concatenate every common name field so Chinese/English/Latin all get checked
  return [
    "downcase",
    [
      "concat",
      ["to-string", ["coalesce", ["get", "name"], ""]],
      " ",
      ["to-string", ["coalesce", ["get", "name:latin"], ""]],
      " ",
      ["to-string", ["coalesce", ["get", "name:nonlatin"], ""]],
      " ",
      ["to-string", ["coalesce", ["get", "name:en"], ["get", "name_en"], ""]],
      " ",
      ["to-string", ["coalesce", ["get", "name:zh"], ["get", "name:zh-Hans"], ["get", "name:zh-Hant"], ""]],
      " ",
      ["to-string", ["coalesce", ["get", "name:vi"], ["get", "name_vi"], ""]],
    ],
  ] as unknown[];
}

function hasAny(...needles: string[]) {
  return ["any", ...needles.map((needle) => ["in", needle, blob()])] as unknown[];
}

/** Prefer Vietnamese, then Latin/English — never append Chinese nonlatin. */
export const VI_PREFERRED_TEXT_FIELD = [
  "coalesce",
  ["get", "name:vi"],
  ["get", "name_vi"],
  ["get", "name:en"],
  ["get", "name_en"],
  ["get", "name:latin"],
  ["get", "name"],
  "",
] as unknown[];

/**
 * Rewrite known Chinese / colonial labels for Hoàng Sa & Trường Sa.
 * Checked against the combined name pool so either primary or nonlatin matches.
 */
export const VN_SOVEREIGNTY_TEXT_FIELD = [
  "case",
  hasAny("西沙", "paracel", "xisha", "hoang sa", "hoàng sa"),
  "Quần đảo Hoàng Sa",
  hasAny("南沙", "spratly", "nansha", "truong sa", "trường sa"),
  "Quần đảo Trường Sa",
  hasAny("中沙", "macclesfield"),
  "Bãi Macclesfield",
  hasAny("南海", "south china sea"),
  "Biển Đông",
  VI_PREFERRED_TEXT_FIELD,
] as unknown[];

export const VN_SOVEREIGNTY_FEATURES = {
  type: "FeatureCollection" as const,
  features: [
    {
      type: "Feature" as const,
      properties: { name: "Quần đảo Hoàng Sa", rank: 1 },
      geometry: { type: "Point" as const, coordinates: [112.0, 16.5] },
    },
    {
      type: "Feature" as const,
      properties: { name: "Quần đảo Trường Sa", rank: 1 },
      geometry: { type: "Point" as const, coordinates: [114.3, 10.0] },
    },
    {
      type: "Feature" as const,
      properties: { name: "Biển Đông", rank: 2 },
      geometry: { type: "Point" as const, coordinates: [113.2, 13.2] },
    },
  ],
};

export function applyVietnamPlaceNames(instance: Map) {
  const style = instance.getStyle();
  if (!style?.layers) return;

  for (const layer of style.layers) {
    if (layer.type !== "symbol") continue;
    if (!instance.getLayer(layer.id)) continue;
    if (layer.id === VN_ISLAND_LAYER || layer.id === SAT_LABEL_LAYER) continue;
    try {
      instance.setLayoutProperty(layer.id, "text-field", VN_SOVEREIGNTY_TEXT_FIELD as never);
    } catch {
      // Some symbol layers are icon-only
    }
  }
}

export function syncVietnamSovereigntyLabels(instance: Map, beforeId?: string) {
  applyVietnamPlaceNames(instance);

  if (!instance.getSource(VN_ISLAND_SOURCE)) {
    instance.addSource(VN_ISLAND_SOURCE, {
      type: "geojson",
      data: VN_SOVEREIGNTY_FEATURES,
    });
  }

  if (!instance.getLayer(VN_ISLAND_LAYER)) {
    instance.addLayer(
      {
        id: VN_ISLAND_LAYER,
        type: "symbol",
        source: VN_ISLAND_SOURCE,
        minzoom: 3,
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Noto Sans Bold", "Noto Sans Regular"],
          "text-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            3,
            ["match", ["get", "rank"], 2, 11, 13],
            6,
            ["match", ["get", "rank"], 2, 13, 15],
            9,
            ["match", ["get", "rank"], 2, 14, 17],
          ],
          "text-max-width": 10,
          "text-padding": 2,
          "text-allow-overlap": false,
          "symbol-sort-key": ["get", "rank"],
        },
        paint: {
          "text-color": "#0f172a",
          "text-halo-color": "rgba(255,255,255,0.92)",
          "text-halo-width": 1.6,
          "text-halo-blur": 0.4,
        },
      },
      beforeId,
    );
  } else if (beforeId && instance.getLayer(beforeId)) {
    try {
      instance.moveLayer(VN_ISLAND_LAYER, beforeId);
    } catch {
      // beforeId may not exist in current stack
    }
  }
}
