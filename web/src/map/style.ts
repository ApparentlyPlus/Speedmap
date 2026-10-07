/**
 * The map style, in TypeScript instead of JSON. MapLibre drops a whole style over one bad
 * expression and only says so through an event, so a unit test is the cheap place to catch it.
 */

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

/**
 * Measured squares get their own archive. At country zooms they were half of every tile, and
 * the coverage map never draws them. MapLibre won't fetch a source until a visible layer
 * reads it, so they stay unloaded until someone picks Measured.
 */
export const MEASURED = "measured";

/** Basemap from OpenStreetMap via planetiler, footprints from Overture. */
export const BASE = "base";
export const BUILDINGS = "buildings";
/** Greece as one polygon, under everything. */
export const EDGE = "edge";

/**
 * Footprint layers and the paint property holding each one's opacity. Building tiles are the
 * most expensive thing this map decodes, so both get held back and raised together.
 */
export const BUILDING_LAYERS: Readonly<Record<string, string>> = {
  building: "fill-extrusion-opacity",
  "building-shadow": "fill-opacity",
};

/** Footprints start here, so below it there's nothing to wait for. */
export const BUILDINGS_FROM = 14;

/** Crete and the north in one view. */
export const HOME = { centre: [24.0, 38.4] as [number, number], zoom: 6.2 };

/** Gavdos to the Evros, Corfu to Kastellorizo, plus half a degree of sea. */
export const LIMITS: [[number, number], [number, number]] = [[18.6, 34.2], [30.4, 42.3]];

/** Far enough out to hold the country, no further. */
export const FLOOR_ZOOM = 5.6;

/**
 * Ground colours. They're relative to each other: water lighter than land inverts the coast,
 * occlusion lighter than building makes the shadow glow.
 */
const C = {
  // land, which everything below is tuned against
  ground: "#141a22",
  // a shade up and faintly cool, so a hillside reads as rising ground
  landuse: "#1a2028",
  // Parks, grey almost. Green on a map about cables spends colour on the wrong subject and
  // fights the cool end of the ramp.
  park: "#22272c",
  // blue-ish so the coast reads by hue, dark because the ramp owns the bright blues
  water: "#0d1117",
  building: "#1e2530",
  occlusion: "#0d121a",
  // roads give the city its shape where coverage is a hairline, always under the ramp
  road: "#303945",
  roadMinor: "#1f252e",
  roadMajor: "#414d5b",
  // near white with a wide dark halo, readable on land, sea and a lit street
  label: "#d8dce3",
  // a step down from towns, to tell the two apart
  labelQuiet: "#9fa7b4",
  labelHalo: "#05070a",
} as const;

/**
 * The speed ramp. A missing field means nothing reaches the street, drawn UNSERVED outside
 * the ramp (inside it, absence interpolates to near black and looks like a slow street).
 * A negative value is the tile's "reaches, no speed filed" (SERVED_UNFILED in
 * publish/features.py) and gets UNFILED. The ramp used to clamp it to the slowest copper red.
 */
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

/**
 * Greek OSM rarely has heights, and one constant turns a city into a slab. Derived from the
 * feature id instead: about right for a polykatoikia, and stable across zooms.
 */
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

/** Filter to one operator. The tile omits the key where they don't reach. */
export function only(provider: string | null): ExpressionSpecification | null {
  if (provider === null) return null;
  const field = STREETS_BY_PROVIDER[provider];
  // an operator without a field reaches nothing, not everything
  if (field === undefined) return ["boolean", false] as ExpressionSpecification;
  return ["has", field] as ExpressionSpecification;
}

/** The selection fades up after the camera arrives. */
const LIGHT_MS = 800;
const LIGHT_WAIT = 500;

/** Target opacity per selection layer. */
export const LIT: Record<string, DataDrivenPropertyValueSpecification<number>> = {
  "streets-picked-halo": ["interpolate", ["linear"], ["zoom"], 10, 0.55, 14, 0.4, 17, 0.25],
  "streets-picked": 0.9,
};

/** Matches nothing. The selection layer's filter until something is picked. */
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
      // A wide, blurred, dim copy under the line. Cheaper than a real glow, and it's most of
      // why coverage looks like light lying on the street.
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
      // Glow under the picked street, so a long street fitted far out stays visible. No
      // operator filter: it was picked directly and shouldn't vanish under one.
      id: "streets-picked-halo",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      filter: NOTHING,
      // hidden as well as filtered: a hidden layer is skipped at tile build, and a filtered one
      // still runs its filter on every street in the tile
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

/**
 * Click padding per zoom. There used to be an invisible 20 px line under every street for
 * thumbs to hit, a second copy of 80,000 streets tessellated and uploaded per tile to draw
 * nothing. Padding the query does the same job. Half the old width minus the street's own
 * half-width, since a query already counts a line as wide as it's drawn.
 */
export const TOUCH: readonly (readonly [number, number])[] = [[11, 4.5], [16, 7.5], [20, 9]];

/** Padding in px at a zoom, interpolated between stops and flat outside them. */
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

/**
 * The other streets behind a result: grey and quiet. Forty thousand lit roads around the
 * answer bury it.
 */
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

/**
 * Coverage: what the line on a street retails at. Measured: what people actually got.
 * Different claims, so they're never drawn together.
 */
export const VIEWS = ["coverage", "measured", "mobile"] as const;
export type View = (typeof VIEWS)[number];

/** Confidence as opacity. Dropping thin cells leaves holes that look broken. */
const CONFIDENCE: ExpressionSpecification = [
  "interpolate", ["linear"], ["coalesce", ["get", "tests"], 1],
  1, 0.4, 5, 0.66, 25, 1,
];

/**
 * Below zoom ten a street is a fraction of a pixel and the map was an empty coastline. The
 * choropleth fills that and hands over as the streets come in.
 */
const FADES_AT = 11;

/**
 * One paint per view, so a filed claim never sits under a measured map. Coverage is a share
 * on SHARE. The other two are speeds on the same RAMP the streets use.
 */
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
    // untested is most of the country, and it isn't the same as slow
    ["!", ["has", field]], UNSERVED,
    ["interpolate", ["linear"], ["to-number", ["get", field], 0],
      ...rising.flatMap((band) => [band.floor as number, band.colour])],
  ] as ExpressionSpecification;
}

/** Confidence as opacity, like the cells. Coverage has no test count and draws full. */
function regionConfidence(view: View): ExpressionSpecification | number {
  if (view === "coverage") return 1;
  const field: keyof Region = view === "mobile" ? "mobile_tests" : "measured_tests";
  return [
    "interpolate", ["linear"], ["coalesce", ["get", field], 0],
    0, 0.45, 50, 0.75, 500, 1,
  ] as ExpressionSpecification;
}

/**
 * Choropleth opacity for a view. Exported because it changes with the view. Only the colour
 * used to switch, so a two-test municipality under Measured looked as sure as a two-thousand one.
 */
export function regionOpacity(view: View): ExpressionSpecification {
  const confidence = regionConfidence(view);
  // Never fully opaque, or 333 polygons turn into the coastline. ["zoom"] has to feed a
  // top-level interpolate or the style is invalid.
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
      // off unless asked for: it summarises places, and this map is about lines
      layout: { visibility: "none" },
      paint: {
        "fill-color": paint,
        "fill-opacity": regionOpacity(view),
      },
    },
    {
      // A hairline between municipalities. Without it, neighbours with similar figures
      // merge into one blob.
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

/** Both choropleth layers, toggled together. */
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
      // off until Measured is picked: everything else here wants streets
      layout: { visibility: "none" },
      paint: {
        "fill-color": ramp(field),
        // zoom outermost, or the whole style is rejected
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

/**
 * Coverage colours turned down before the first frame. On the result map the rest of the city
 * is context. Anchored used to quiet the colours once the style loaded, one frame late: the
 * country flashed in full colour, then dropped to grey, and the descent started on that flinch.
 */
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


/**
 * MapLibre fetches glyphs from a worker, where a bare path has nothing to resolve against.
 * Made absolute in the browser, left alone without a window (tests).
 */
function glyphBase(base: string): string {
  if (typeof window === "undefined" || /^[a-z]+:/i.test(base)) return base;
  return new URL(base, window.location.origin).href.replace(/\/$/, "");
}

export function style(base = "/tiles"): StyleSpecification {
  return {
    version: 8,
    name: "speedmap",
    // Self-hosted beside the archives (tools/fonts.py). The site's own CSP blocked
    // fonts.openmaptiles.org, and that host now serves HTML for glyph URLs anyway.
    glyphs: `${glyphBase(base)}/fonts/{fontstack}/{range}.pbf`,
    sources: {
      [BASE]: { type: "vector", url: `pmtiles://${base}/greece.pmtiles` },
      // Overture merges OSM with imagery-derived footprints, the only way to get buildings
      // outside Athens and Thessaloniki
      [BUILDINGS]: { type: "vector", url: `pmtiles://${base}/buildings.pmtiles` },
      [SOURCE]: { type: "vector", url: `pmtiles://${base}/speedmap.pmtiles` },
      [MEASURED]: { type: "vector", url: `pmtiles://${base}/cells.pmtiles` },
      // A single shape we want before any tile lands. A zoom 4 vector tile of a coastline
      // has already thrown most of it away.
      [EDGE]: { type: "geojson", data: `${base}/greece.json` },
    },
    // One light from the side and above gives extrusions a lit face and a dark one. Without
    // it the city looks like a printed plan.
    light: { anchor: "viewport", color: "#ffffff", intensity: 0.35, position: [1.2, 210, 30] },
    layers: [
      // Sea as background, land on top. The reverse needs a world ring with Greece cut out,
      // which clips into slabs of land across the Aegean.
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

      // dim wide casing under a brighter core, so a road reads as a lit ribbon
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

      // Under the streets and gone before they're legible, so it reads as one map changing
      // scale and not two maps swapping.
      ...regionLayers(),
      ...streetLayers(null),
      ...cellLayers("fixed"),

      // dark offset copy under the extrusions, one fill layer for most of the depth
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
          // Street names sit on lit lines, so they need more contrast than a town label on
          // open ground.
          "text-color": C.labelQuiet,
          "text-halo-color": C.labelHalo,
          "text-halo-width": 1.8,
        },
      },
    ],
  };
}
