/**
 * The map style, as typed code rather than JSON: MapLibre rejects a whole style on one bad
 * expression and reports it by firing an event, so a unit test catches what a reader would.
 */

import type {
  DataDrivenPropertyValueSpecification,
  ExpressionSpecification,
  FilterSpecification,
  LayerSpecification,
  StyleSpecification,
} from "maplibre-gl";

import { ACCENT, RAMP, SHARE, UNSERVED } from "../tokens";
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

/** The basemap and the footprints: OpenStreetMap through planetiler, and Overture. */
export const BASE = "base";
export const BUILDINGS = "buildings";
/** The country itself, as one polygon, drawn under everything else. */
export const EDGE = "edge";

/**
 * The footprint layers, and the paint property each one's opacity sits under. A city tile of
 * buildings is the most expensive thing this map decodes, so the two are held back and
 * brought up together rather than landing a tile at a time.
 */
export const BUILDING_LAYERS: Readonly<Record<string, string>> = {
  building: "fill-extrusion-opacity",
  "building-shadow": "fill-opacity",
};

/** The zoom the footprints start at. Below it there are none to wait for. */
export const BUILDINGS_FROM = 14;

/** Greece, with room for Crete and the north in the same view. */
export const HOME = { centre: [24.0, 38.4] as [number, number], zoom: 6.2 };

/** Gavdos to the Evros, Corfu to Kastellorizo, plus half a degree of sea. Past it we have
 * nothing to say. */
export const LIMITS: [[number, number], [number, number]] = [
  [18.6, 34.2],
  [30.4, 42.3],
];

/** Far enough out to hold the country, and no further. */
export const FLOOR_ZOOM = 5.6;

/** The ground. These are relative, not decorative: water under land or the coast inverts,
 * occlusion under building or the shadow glows. */
const C = {
  // The land. Everything below is set against it, so they move together or not at all.
  ground: "#141a22",
  // Relief. A shade up from the land and faintly cool, so a hillside reads as a rise in the
  // ground rather than as a different kind of place.
  landuse: "#1a2028",
  // Greenery, desaturated almost to grey. Green on a map about cables is a colour spent on
  // the one thing the map is not about, and it fights the cool end of the ramp.
  park: "#22272c",
  // Blue rather than grey, so the coast reads by hue. Dark: the ramp owns the bright blues.
  water: "#0d1117",
  building: "#1e2530",
  occlusion: "#0d121a",
  // Roads carry the city's shape where coverage is a hairline, but stay under the ramp.
  road: "#303945",
  roadMinor: "#1f252e",
  roadMajor: "#414d5b",
  // Must hold against land, sea and a lit street, so: near white with a wide dark halo.
  label: "#d8dce3",
  // Street names, a step down from a town so the two are told apart at a glance.
  labelQuiet: "#9fa7b4",
  labelHalo: "#05070a",
} as const;

/**
 * The speed ramp. Absent means nothing reaches here and takes UNSERVED, outside the ramp: run
 * through it, absence interpolates to near-black and reads as a very slow street.
 */
function ramp(field: keyof Street | keyof Cell): ExpressionSpecification {
  const rising = [...RAMP].reverse();
  const anchors = rising.flatMap((band) => [band.floor as number, band.colour]);
  return [
    "case",
    ["!", ["has", field]], UNSERVED,
    ["interpolate", ["linear"], ["to-number", ["get", field], 0], ...anchors],
  ] as ExpressionSpecification;
}

/**
 * Greek OSM rarely carries height, and a constant fallback makes a city one flat slab. This one
 * is derived from the feature id: plausible for a polykatoikia, and stable across zooms.
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

/** A filter for one operator. Presence: the tile omits the key where they do not reach. */
export function only(provider: string | null): ExpressionSpecification | null {
  if (provider === null) return null;
  const field = STREETS_BY_PROVIDER[provider];
  // An operator with no field of its own reaches nothing rather than everything.
  if (field === undefined) return ["boolean", false] as ExpressionSpecification;
  return ["has", field] as ExpressionSpecification;
}

/** The selection waits for the camera to arrive, then comes up rather than switching on. */
const LIGHT_MS = 800;
const LIGHT_WAIT = 500;

/** What each selection layer fades up to, once there is something to show. */
export const LIT: Record<string, DataDrivenPropertyValueSpecification<number>> = {
  "streets-picked-halo": ["interpolate", ["linear"], ["zoom"], 10, 0.55, 14, 0.4, 17, 0.25],
  "streets-picked": 0.9,
};

/** Matches nothing: what the selection layer draws until something is selected. */
const NOTHING: FilterSpecification = ["==", ["get", "id"], -1];

/** The filter that lights one street, or none. */
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
      // A wide, blurred, dim copy under the line. Cheaper than a real glow, and most of
      // what makes coverage read as light lying on the street rather than paint on it.
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
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"], 10, 4, 13, 8, 16, 22, 20, 60,
        ],
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
      // A glow under the chosen street, so it survives the zoom a long street is fitted
      // at. No operator filter: it was picked outright and must not vanish under one.
      id: "streets-picked-halo",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      filter: NOTHING,
      // Hidden rather than merely filtered: a hidden layer is skipped when a tile is built,
      // where a filtered one still has its filter run against every street in the tile.
      layout: { "line-cap": "round", "line-join": "round", visibility: "none" },
      paint: {
        "line-color": ACCENT,
        "line-blur": 6,
        "line-opacity": 0,
        "line-opacity-transition": { duration: LIGHT_MS, delay: LIGHT_WAIT },
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"], 10, 9, 13, 13, 16, 26, 20, 70,
        ],
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
 * An invisible twenty-pixel line used to run under every street so that a thumb had
 * something to hit. It was a second copy of eighty thousand streets, tessellated and
 * uploaded per tile, drawing nothing. Padding the click does the same job for one query.
 *
 * Half the old width, less the half-width of the street itself, because a query already
 * counts a line as being as wide as it is drawn.
 */
export const TOUCH: readonly (readonly [number, number])[] = [
  [11, 4.5],
  [16, 7.5],
  [20, 9],
];

/** The padding in pixels at a zoom, between the stops and flat outside them. */
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
 * How the other streets look behind a result: grey and quiet, so the subject is the only lit
 * thing. Forty thousand lit roads around the answer bury it.
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
 * Coverage is the line reaching a street at what it retails for. Measured is what people
 * actually got. Different claims about different things, so never drawn together.
 */
export const VIEWS = ["coverage", "measured", "mobile"] as const;
export type View = (typeof VIEWS)[number];

/** Confidence as opacity. Dropping thin cells instead leaves holes, which read as broken. */
const CONFIDENCE: ExpressionSpecification = [
  "interpolate", ["linear"], ["coalesce", ["get", "tests"], 1],
  1, 0.4, 5, 0.66, 25, 1,
];

/**
 * The country before it has streets: below zoom ten a street is a fraction of a pixel and the
 * map was an empty coastline. Drawn under the streets and handed over as they arrive.
 */
const FADES_AT = 11;

/**
 * Per view, because a filed claim must not sit under a measured map. Coverage is a share and
 * runs on SHARE; the other two are speeds and run on the same RAMP a street does.
 */
export function regionPaint(view: View): ExpressionSpecification {
  if (view === "coverage") {
    return [
      "interpolate",
      ["linear"],
      ["coalesce", ["get", "fibre_share" satisfies keyof Region], 0],
      ...SHARE.flatMap(([at, colour]) => [at, colour]),
    ] as ExpressionSpecification;
  }
  const field: keyof Region = view === "mobile" ? "mobile_mbps" : "measured_mbps";
  const rising = [...RAMP].reverse();
  return [
    "case",
    // Untested is most of the country, and is not the same thing as slow.
    ["!", ["has", field]], UNSERVED,
    ["interpolate", ["linear"], ["to-number", ["get", field], 0],
      ...rising.flatMap((band) => [band.floor as number, band.colour])],
  ] as ExpressionSpecification;
}

/** Confidence as opacity, as the cells do. Coverage has no test count and is drawn full. */
function regionConfidence(view: View): ExpressionSpecification | number {
  if (view === "coverage") return 1;
  const field: keyof Region = view === "mobile" ? "mobile_tests" : "measured_tests";
  return [
    "interpolate", ["linear"], ["coalesce", ["get", field], 0],
    0, 0.45, 50, 0.75, 500, 1,
  ] as ExpressionSpecification;
}

export function regionLayers(view: View = "coverage"): LayerSpecification[] {
  const paint = regionPaint(view);
  const confidence = regionConfidence(view);

  return [
    {
      id: "regions",
      type: "fill",
      source: SOURCE,
      "source-layer": REGIONS_LAYER,
      maxzoom: FADES_AT,
      // Off unless asked for: this summarises places, and the map is about lines.
      layout: { visibility: "none" },
      paint: {
        "fill-color": paint,
        // Never fully opaque, or 333 polygons become the coastline. Zoom outermost:
        // ["zoom"] must be the input of a top-level interpolate or the style is invalid.
        "fill-opacity": [
          "interpolate", ["linear"], ["zoom"],
          5, ["*", 0.62, confidence],
          8, ["*", 0.56, confidence],
          9.5, ["*", 0.34, confidence],
          FADES_AT, 0,
        ],
      },
    },
    {
      // A hairline between one municipality and the next. Without it a run of neighbours
      // at similar figures is one blob, and the choropleth stops being a map of places.
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

/** The two layers the choropleth is made of, for turning it on and off together. */
export const REGION_LAYERS = ["regions", "regions-edge"] as const;

export function cellLayers(family: "fixed" | "mobile"): LayerSpecification[] {
  const field: keyof Cell = "down_mbps";
  return [
    {
      id: "cells",
      type: "fill",
      source: SOURCE,
      "source-layer": CELLS_LAYER,
      filter: ["==", ["get", "family"], family],
      // Off unless something turns it on: every other map here wants streets, not squares.
      layout: { visibility: "none" },
      paint: {
        "fill-color": ramp(field),
        // Zoom outermost: ["zoom"] must be the top-level interpolate input, or the style
        // is rejected whole.
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

/** The whole style. Basemap archives are built elsewhere. The coverage is ours. */
export function style(base = "/tiles"): StyleSpecification {
  return {
    version: 8,
    name: "speedmap",
    glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
    sources: {
      [BASE]: { type: "vector", url: `pmtiles://${base}/greece.pmtiles` },
      // Overture conflates OSM with footprints derived from imagery, which is the only way
      // to have buildings outside Athens and Thessaloniki at all.
      [BUILDINGS]: { type: "vector", url: `pmtiles://${base}/buildings.pmtiles` },
      // Our own coverage, cut from the database by the same tool that cut the basemap.
      [SOURCE]: { type: "vector", url: `pmtiles://${base}/speedmap.pmtiles` },
      // One shape, wanted before the first tile arrives, and a vector tile of a coastline
      // at zoom 4 is a coastline someone has already thrown most of away.
      [EDGE]: { type: "geojson", data: `${base}/greece.json` },
    },
    // One light, from the side and above, so extrusions have a lit face and a dark one.
    // Without it every building is the same flat tone and the city reads as a printed plan.
    light: { anchor: "viewport", color: "#ffffff", intensity: 0.35, position: [1.2, 210, 30] },
    layers: [
      // Sea as background, land drawn on it. The other way round needs a world-ring with
      // Greece cut out, which clips into slabs of land across the Aegean.
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

      // A wide dim casing under a narrow brighter core: one line drawn twice is what makes
      // a road read as a lit ribbon rather than as a stroke.
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
          "line-width": [
            "interpolate", ["exponential", 1.6], ["zoom"],
            6, 0.4, 12, 2, 16, 10, 20, 40,
          ],
        },
      },

      // Under the streets, and gone before they are legible: the two never compete, and
      // what the reader sees is one map changing scale rather than two maps swapping over.
      ...regionLayers(),
      ...streetLayers(null),
      ...cellLayers("fixed"),

      // A dark offset copy under the extrusions: one fill layer, most of the depth.
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
          // A street name sits on the street, which at these zooms is a lit line, so it
          // needs more contrast than a town name floating on open ground, not less.
          "text-color": C.labelQuiet,
          "text-halo-color": C.labelHalo,
          "text-halo-width": 1.8,
        },
      },
    ],
  };
}
