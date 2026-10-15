// The map style in TS rather than JSON. MapLibre drops the whole style over one bad
// expression and only says so in an event, so style.test.ts catches it here.

import type {
  DataDrivenPropertyValueSpecification,
  ExpressionSpecification,
  FilterSpecification,
  LayerSpecification,
  StyleSpecification,
} from "maplibre-gl";

import { ACCENT, RAMP, SHARE, UNFILED, UNSERVED } from "../tokens";
import {
  CELLS_LAYER,
  REGIONS_LAYER,
  STREETS_BY_PROVIDER,
  STREETS_LAYER,
  type Cell,
  type Region,
  type Street,
} from "./tiles";

export const SOURCE = "speedmap";

// own archive, so the coverage map never fetches the squares
export const MEASURED = "measured";

// OSM via planetiler, footprints from Overture
export const BASE = "base";
export const BUILDINGS = "buildings";
export const EDGE = "edge";

// footprint layers and their opacity property, held back together (most expensive tiles to decode)
export const BUILDING_LAYERS: Readonly<Record<string, string>> = {
  building: "fill-extrusion-opacity",
  "building-shadow": "fill-opacity",
};

export const BUILDINGS_FROM = 14;

// Crete and the north in one view
export const HOME = { centre: [24.0, 38.4] as [number, number], zoom: 6.2 };

// Gavdos to Evros, Corfu to Kastellorizo, plus half a degree of sea
export const LIMITS: [[number, number], [number, number]] = [[18.6, 34.2], [30.4, 42.3]];

export const FLOOR_ZOOM = 5.6;

// relative to each other: lighter water inverts the coast, lighter occlusion makes the shadow glow
const C = {
  ground: "#141a22",
  // a shade up and cool, so hills read as rising
  landuse: "#1a2028",
  // near grey, green would fight the cool end of the ramp
  park: "#22272c",
  // coast by hue, dark because the ramp has the bright blues
  water: "#0d1117",
  building: "#1e2530",
  occlusion: "#0d121a",
  // city shape where coverage is a hairline, always under the ramp
  road: "#303945",
  roadMinor: "#1f252e",
  roadMajor: "#414d5b",
  // wide dark halo, readable on land, sea and a lit street
  label: "#d8dce3",
  labelQuiet: "#9fa7b4",
  labelHalo: "#05070a",
} as const;

// missing = nobody reaches it (UNSERVED), negative = reaches, no speed filed (UNFILED).
// Both kept off the ramp, which would interpolate them to near black
function ramp(field: keyof Street | keyof Cell): ExpressionSpecification {
  const rising = [...RAMP].reverse();
  const anchors = rising.flatMap((band) => [band.floor as number, band.colour]);
  return [
    "case",
    ["!", ["has", field]], UNSERVED,
    ["<", ["to-number", ["get", field], 0], 0], UNFILED,
    ["interpolate", ["linear"], ["to-number", ["get", field], 0], ...anchors],
  ] as ExpressionSpecification;
}

// Greek OSM rarely has heights, so derive one from the feature id: roughly a polykatoikia,
// and stable across zooms
const HEIGHT: DataDrivenPropertyValueSpecification<number> = [
  "case",
  ["has", "height"], ["max", 3, ["get", "height"]],
  ["has", "num_floors"], ["max", 3, ["*", 3.3, ["get", "num_floors"]]],
  ["+", 11, ["*", 1.7, ["%", ["to-number", ["coalesce", ["id"], 3]], 9]]],
];

const ROAD_KINDS: ExpressionSpecification = [
  "!",
  ["in", ["get", "class"], ["literal", ["ferry", "rail", "path"]]],
];

// the tile omits the key where an operator doesn't reach
export function only(provider: string | null): ExpressionSpecification | null {
  if (provider === null) return null;
  const field = STREETS_BY_PROVIDER[provider];
  if (field === undefined) return ["boolean", false] as ExpressionSpecification;
  return ["has", field] as ExpressionSpecification;
}

const LIGHT_MS = 800;
const LIGHT_WAIT = 500;

export const LIT: Record<string, DataDrivenPropertyValueSpecification<number>> = {
  "streets-picked-halo": ["interpolate", ["linear"], ["zoom"], 10, 0.55, 14, 0.4, 17, 0.25],
  "streets-picked": 0.9,
};

// matches nothing, until something is picked
const NOTHING: FilterSpecification = ["==", ["get", "id"], -1];

export function onlyStreet(id: number | null): FilterSpecification {
  return id === null ? NOTHING : ["==", ["get", "id"], id];
}

export function streetLayers(provider: string | null): LayerSpecification[] {
  const field: keyof Street =
    provider === null ? "best_mbps" : (STREETS_BY_PROVIDER[provider] ?? "best_mbps");
  const paint = ramp(field);
  const filter = only(provider);

  return [
    {
      // wide blurred copy under the line, a cheap glow
      id: "streets-halo",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      minzoom: 10,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": paint,
        "line-blur": 5,
        "line-opacity": [
          "interpolate", ["linear"], ["zoom"],
          8, 0.06, 13, 0.13, 15, 0.2, 16, 0.15, 18, 0.09,
        ],
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 10, 4, 13, 8, 16, 22, 20, 60],
      },
    },
    {
      id: "streets",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": paint,
        "line-opacity": [
          "interpolate", ["linear"], ["zoom"],
          7, 0.4, 11, 0.46, 13, 0.52, 14.5, 0.66, 16, 0.6, 18, 0.45,
        ],
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          6, 0.45, 12, 1.25, 14, 2.6, 15, 4.5, 16, 7, 20, 26,
        ],
      },
    },
    {
      // glow under the picked street. No operator filter, it was picked directly
      id: "streets-picked-halo",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      filter: NOTHING,
      // hidden, not just filtered: hidden layers are skipped at tile build
      layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
      paint: {
        "line-color": ACCENT,
        "line-blur": 6,
        "line-opacity": 0,
        "line-opacity-transition": { duration: LIGHT_MS, delay: LIGHT_WAIT },
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 10, 9, 13, 13, 16, 26, 20, 70],
      },
    },
    {
      id: "streets-picked",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      filter: NOTHING,
      layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
      paint: {
        "line-color": ACCENT,
        "line-opacity": 0,
        "line-opacity-transition": { duration: LIGHT_MS, delay: LIGHT_WAIT },
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          6, 1.6, 12, 3.4, 14, 5, 15, 7, 16, 9.5, 20, 32,
        ],
      },
    },
  ];
}

// Click padding per zoom, instead of an invisible 20px hit line under all 80,000 streets.
// Half the old width minus the street's own half width.
export const TOUCH: readonly (readonly [number, number])[] = [[11, 4.5], [16, 7.5], [20, 9]];

export function touchPad(zoom: number): number {
  const first = TOUCH[0] as readonly [number, number];
  const last = TOUCH[TOUCH.length - 1] as readonly [number, number];
  if (zoom <= first[0]) return first[1];
  if (zoom >= last[0]) return last[1];
  for (let i = 1; i < TOUCH.length; i++) {
    const [z0, p0] = TOUCH[i - 1] as readonly [number, number];
    const [z1, p1] = TOUCH[i] as readonly [number, number];
    if (zoom <= z1) return p0 + ((p1 - p0) * (zoom - z0)) / (z1 - z0);
  }
  return last[1];
}

// the other streets behind a result, grey so they don't bury it
export const ASIDE = "#2b3037";
export const ASIDE_OPACITY: DataDrivenPropertyValueSpecification<number> = [
  "interpolate", ["linear"], ["zoom"], 10, 0.24, 14, 0.3, 17, 0.34,
];

export function ramps(provider: string | null): Record<string, ExpressionSpecification> {
  const field: keyof Street =
    provider === null ? "best_mbps" : (STREETS_BY_PROVIDER[provider] ?? "best_mbps");
  const paint = ramp(field);
  return { "streets-halo": paint, streets: paint };
}

// coverage = what the line retails at, measured = what people got. Never drawn together
export const VIEWS = ["coverage", "measured", "mobile"] as const;
export type View = (typeof VIEWS)[number];

// opacity for confidence, dropping thin cells looks broken
const CONFIDENCE: ExpressionSpecification = [
  "interpolate", ["linear"], ["coalesce", ["get", "tests"], 1],
  1, 0.4, 5, 0.66, 25, 1,
];

// below z10 streets are subpixel, the choropleth fills in and hands over
const FADES_AT = 11;

// one paint per view. Coverage is a share on SHARE, the other two speeds on RAMP
export function regionPaint(view: View): ExpressionSpecification {
  if (view === "coverage") {
    return [
      "interpolate",
      ["linear"],
      ["coalesce", ["get", "fiber_share" satisfies keyof Region], 0],
      ...SHARE.flatMap(([at, colour]) => [at, colour]),
    ] as ExpressionSpecification;
  }
  const field: keyof Region = view === "mobile" ? "mobile_mbps" : "measured_mbps";
  const rising = [...RAMP].reverse();
  return [
    "case",
    // untested isn't slow
    ["!", ["has", field]], UNSERVED,
    ["interpolate", ["linear"], ["to-number", ["get", field], 0],
      ...rising.flatMap((band) => [band.floor as number, band.colour])],
  ] as ExpressionSpecification;
}

// coverage has no test count, full opacity
function regionConfidence(view: View): ExpressionSpecification | number {
  if (view === "coverage") return 1;
  const field: keyof Region = view === "mobile" ? "mobile_tests" : "measured_tests";
  return [
    "interpolate", ["linear"], ["coalesce", ["get", field], 0],
    0, 0.45, 50, 0.75, 500, 1,
  ] as ExpressionSpecification;
}

// Opacity changes with the view too, or a two-test municipality looks as sure as a
// two-thousand-test one
export function regionOpacity(view: View): ExpressionSpecification {
  const confidence = regionConfidence(view);
  // never fully opaque or 333 polygons hide the coastline. zoom has to feed a top level interpolate
  return [
    "interpolate", ["linear"], ["zoom"],
    5, ["*", 0.62, confidence],
    8, ["*", 0.56, confidence],
    9.5, ["*", 0.34, confidence],
    FADES_AT, 0,
  ] as ExpressionSpecification;
}

export function regionLayers(view: View = "coverage"): LayerSpecification[] {
  const paint = regionPaint(view);

  return [
    {
      id: "regions",
      type: "fill",
      source: SOURCE,
      "source-layer": REGIONS_LAYER,
      maxzoom: FADES_AT,
      // off unless asked for, this map is about lines
      layout: { visibility: "none" },
      paint: {
        "fill-color": paint,
        "fill-opacity": regionOpacity(view),
      },
    },
    {
      // or neighbours with similar figures merge into one blob
      id: "regions-edge",
      type: "line",
      source: SOURCE,
      "source-layer": REGIONS_LAYER,
      maxzoom: FADES_AT,
      layout: { visibility: "none" },
      paint: {
        "line-color": "#0d1117",
        "line-width": 0.5,
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 5, 0.5, 9.5, 0.3, FADES_AT, 0],
      },
    },
  ];
}

export const REGION_LAYERS = ["regions", "regions-edge"] as const;

export function cellLayers(family: "fixed" | "mobile"): LayerSpecification[] {
  const field: keyof Cell = "down_mbps";
  return [
    {
      id: "cells",
      type: "fill",
      source: MEASURED,
      "source-layer": CELLS_LAYER,
      filter: ["==", ["get", "family"], family],
      // off until Measured is picked
      layout: { visibility: "none" },
      paint: {
        "fill-color": ramp(field),
        // zoom outermost or the style is rejected
        "fill-opacity": [
          "interpolate", ["linear"], ["zoom"],
          5, ["*", 0.6, CONFIDENCE],
          11, ["*", 0.46, CONFIDENCE],
          16, ["*", 0.34, CONFIDENCE],
        ],
      },
    },
  ];
}

// Muted before the first frame. Doing it on load was a frame late and the country flashed
// full colour first.
export function hushed(spec: StyleSpecification): StyleSpecification {
  for (const layer of spec.layers) {
    if (layer.id === "streets-halo") {
      layer.layout = { ...layer.layout, visibility: "none" };
    }
    if (layer.id === "streets" && layer.type === "line") {
      layer.paint = { ...layer.paint, "line-color": ASIDE, "line-opacity": ASIDE_OPACITY };
    }
  }
  return spec;
}


// glyphs are fetched from a worker, so make the path absolute (no window in tests)
function glyphBase(base: string): string {
  if (typeof window === "undefined" || /^[a-z]+:/i.test(base)) return base;
  return new URL(base, window.location.origin).href.replace(/\/$/, "");
}

export function style(base = "/tiles"): StyleSpecification {
  return {
    version: 8,
    name: "speedmap",
    // self hosted (tools/fonts.py), CSP blocks fonts.openmaptiles.org anyway
    glyphs: `${glyphBase(base)}/fonts/{fontstack}/{range}.pbf`,
    sources: {
      [BASE]: { type: "vector", url: `pmtiles://${base}/greece.pmtiles` },
      // Overture has buildings outside Athens and Thessaloniki, OSM mostly doesn't
      [BUILDINGS]: { type: "vector", url: `pmtiles://${base}/buildings.pmtiles` },
      [SOURCE]: { type: "vector", url: `pmtiles://${base}/speedmap.pmtiles` },
      [MEASURED]: { type: "vector", url: `pmtiles://${base}/cells.pmtiles` },
      // wanted before any tile, a z4 coastline tile has thrown most of it away
      [EDGE]: { type: "geojson", data: `${base}/greece.json` },
    },
    // side light for a lit face and a dark one on extrusions
    light: { anchor: "viewport", color: "#ffffff", intensity: 0.35, position: [1.2, 210, 30] },
    layers: [
      // sea as background with land on top. The reverse needs a world ring with Greece cut out,
      // which tears into slabs across the Aegean
      { id: "ground", type: "background", paint: { "background-color": C.water } },
      {
        id: "land",
        type: "fill",
        source: EDGE,
        paint: { "fill-color": C.ground },
      },

      {
        id: "landuse",
        type: "fill",
        source: BASE,
        "source-layer": "landcover",
        paint: { "fill-color": C.landuse, "fill-opacity": 0.55 },
      },
      {
        id: "park",
        type: "fill",
        source: BASE,
        "source-layer": "park",
        paint: { "fill-color": C.park, "fill-opacity": 0.8 },
      },
      {
        id: "water",
        type: "fill",
        source: BASE,
        "source-layer": "water",
        paint: { "fill-color": C.water },
      },

      // dim casing under a bright core
      {
        id: "road-casing",
        type: "line",
        source: BASE,
        "source-layer": "transportation",
        filter: ROAD_KINDS,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": C.roadMinor,
          "line-width": [
            "interpolate", ["exponential", 1.6], ["zoom"],
            6, 0.8, 12, 2.1, 14, 4.5, 16, 13, 20, 48,
          ],
          "line-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.45, 13, 0.6, 15, 0.9],
        },
      },
      {
        id: "road",
        type: "line",
        source: BASE,
        "source-layer": "transportation",
        filter: ROAD_KINDS,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": [
            "match", ["get", "class"],
            ["motorway", "trunk"], C.roadMajor,
            ["primary", "secondary"], C.road,
            C.roadMinor,
          ],
          "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 6, 0.4, 12, 2, 16, 10, 20, 40],
        },
      },

      // gone before the streets are legible, so it's one map changing scale
      ...regionLayers(),
      ...streetLayers(null),
      ...cellLayers("fixed"),

      // dark offset copy under the extrusions
      {
        id: "building-shadow",
        type: "fill",
        source: BUILDINGS,
        "source-layer": "building",
        minzoom: 15,
        paint: {
          "fill-color": C.occlusion,
          "fill-opacity": ["interpolate", ["linear"], ["zoom"], 15, 0, 15.8, 0.6],
          "fill-translate": [3, 3],
          "fill-translate-anchor": "map",
        },
      },
      {
        id: "building",
        type: "fill-extrusion",
        source: BUILDINGS,
        "source-layer": "building",
        minzoom: 14,
        paint: {
          "fill-extrusion-color": C.building,
          "fill-extrusion-height": HEIGHT,
          "fill-extrusion-base": ["coalesce", ["get", "min_height"], 0],
          "fill-extrusion-opacity": ["interpolate", ["linear"], ["zoom"], 14, 0, 15.2, 1],
          "fill-extrusion-vertical-gradient": true,
        },
      },

      {
        id: "place-label",
        type: "symbol",
        source: BASE,
        "source-layer": "place",
        filter: ["in", ["get", "class"], ["literal", ["city", "town", "village"]]],
        layout: {
          "text-field": ["coalesce", ["get", "name:el"], ["get", "name"]],
          "text-font": ["Noto Sans Regular"],
          "text-size": ["interpolate", ["linear"], ["zoom"], 6, 10, 12, 15],
          "text-letter-spacing": 0.08,
        },
        paint: {
          "text-color": C.label,
          "text-halo-color": C.labelHalo,
          "text-halo-width": 1.6,
        },
      },
      {
        id: "street-label",
        type: "symbol",
        source: BASE,
        "source-layer": "transportation_name",
        minzoom: 14,
        layout: {
          "text-field": ["coalesce", ["get", "name:el"], ["get", "name"]],
          "text-font": ["Noto Sans Regular"],
          "text-size": 10.5,
          "symbol-placement": "line",
        },
        paint: {
          // more contrast than town labels, they sit on lit lines
          "text-color": C.labelQuiet,
          "text-halo-color": C.labelHalo,
          "text-halo-width": 1.8,
        },
      },
    ],
  };
}
