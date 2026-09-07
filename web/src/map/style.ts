/**
 * The map style, as typed code rather than a JSON file.
 *
 * MapLibre rejects an entire style on one bad expression: the map does not load at all, and
 * it reports that by firing an event rather than throwing, so the page is blank and looks
 * like a slow network. A JSON file gets that wrong in front of a reader; a builder gets it
 * wrong in front of whoever wrote it, and a unit test gets it wrong in a second.
 *
 * The look is the prototype's, which was right: a near-black ground, water and parks to
 * give the land a shape, roads as a dim wide casing under a brighter core, extruded
 * buildings with a fake occlusion shadow beneath them, and coverage laid over the streets
 * as a tint rather than as a replacement. What it did not have was types, or one definition
 * of the speed ramp shared with the rest of the site.
 */

import type {
  DataDrivenPropertyValueSpecification,
  ExpressionSpecification,
  FilterSpecification,
  LayerSpecification,
  StyleSpecification,
} from "maplibre-gl";

import { ACCENT, RAMP, UNFILED, UNSERVED } from "../tokens";
import { CELLS_LAYER, STREETS_BY_PROVIDER, STREETS_LAYER, type Cell, type Street } from "./tiles";

export const SOURCE = "speedmap";

/** The basemap and the footprints: OpenStreetMap through planetiler, and Overture. */
export const BASE = "base";
export const BUILDINGS = "buildings";
/** The country itself, as one polygon, drawn under everything else. */
export const EDGE = "edge";

/** Greece, with room for Crete and the north in the same view. */
export const HOME = { centre: [24.0, 38.4] as [number, number], zoom: 6.2 };

/**
 * As far out and as far afield as the map will go.
 *
 * The country runs from Gavdos to the Evros and from Corfu to Kastellorizo; the box is that
 * with about half a degree of sea around it, so an island on the edge is reachable without
 * being pinned to the frame. Past it there is nothing this site has measured or asked
 * about, and a reader who arrives in Bulgaria at zoom 3 has been shown an empty map and
 * told it is ours.
 */
export const LIMITS: [[number, number], [number, number]] = [
  [18.6, 34.2],
  [30.4, 42.3],
];

/** Far enough out to hold the country, and no further. */
export const FLOOR_ZOOM = 5.6;

/**
 * The ground, and the few things that give it a shape.
 *
 * Nothing here is a colour anyone picked to be pretty: water has to be darker than land or
 * the coast inverts, parks have to be greener than landuse or a city reads as one surface,
 * and the ambient occlusion has to be darker than the building or the shadow glows.
 */
const C = {
  // The land, and the whole stack that stands on it.
  //
  // These move together or not at all: relief, greenery, buildings and the three road
  // weights are all set against the land, and dropping the land on its own leaves a city
  // sitting brighter than the country it is in.
  //
  // Two steps below where the navy sea put it. Dim enough that the coverage is the only lit
  // thing on the map, and the land still reads as a surface rather than as more sea.
  ground: "#141a22",
  // Relief. A shade up from the land and faintly cool, so a hillside reads as a rise in the
  // ground rather than as a different kind of place.
  landuse: "#1a2028",
  // Greenery, desaturated almost to grey. Green on a map about cables is a colour spent on
  // the one thing the map is not about, and it fights the cool end of the ramp.
  park: "#22272c",
  // Under the land, and blue rather than grey.
  //
  // The coast reads by hue as much as by weight: a neutral sea a shade off a neutral land
  // is a boundary you have to look for, and the same two at the same weights with one of
  // them blue is a boundary you cannot miss. Dark enough that it is still the thing the
  // land sits on — the ramp owns the bright blues, and a sea anywhere near 300 Mbps would
  // be a speed as far as the eye is concerned.
  water: "#0d1117",
  building: "#1e2530",
  occlusion: "#0d121a",
  // Roads carry the city's shape at the zooms where coverage is a hairline, so they are
  // lighter than the land by more than they used to be — and still well under the dimmest
  // band of the ramp, which has to stay the brightest thing on the map.
  road: "#303945",
  roadMinor: "#1f252e",
  roadMajor: "#414d5b",
  // Names have to hold against three backgrounds: the land, the sea, and a lit street
  // running under them. Near white with a dark halo wide enough to cut the coverage, since
  // the one place a label is least readable is exactly where the map is most worth reading.
  label: "#d8dce3",
  // Street names, a step down from a town so the two are told apart at a glance.
  labelQuiet: "#9fa7b4",
  labelHalo: "#05070a",
} as const;

/**
 * The ramp, interpolated rather than stepped.
 *
 * Measured speeds are continuous and advertised ones are not, and both are drawn here, so
 * both run across the same anchors — the two stay comparable by eye instead of one being
 * banded and the other smooth.
 *
 * Three states before the ramp is consulted at all. A field that is absent is an operator
 * that does not reach this street; one at or below zero reaches it and filed no speed, which
 * is the commonest thing the register says and gets a colour of its own outside the ramp;
 * anything else is a speed. Running "no speed filed" through the ramp interpolated it down
 * to near-black and made eight operators invisible.
 */
function ramp(field: keyof Street | keyof Cell): ExpressionSpecification {
  const rising = [...RAMP].reverse();
  const anchors = rising.flatMap((band) => [band.floor as number, band.colour]);
  return [
    "case",
    ["!", ["has", field]], UNSERVED,
    ["<=", ["to-number", ["get", field], 0], 0], UNFILED,
    ["interpolate", ["linear"], ["to-number", ["get", field], 0], ...anchors],
  ] as ExpressionSpecification;
}

/**
 * How tall a building is, when almost none of them say.
 *
 * Greek OSM rarely carries height or levels. A constant fallback makes a city one flat
 * slab, which is the single clearest tell of a fake three-dimensional map, so the fallback
 * is derived from the feature's own id — anywhere in the range an Athens polykatoikia
 * actually occupies, and deterministic, so a building does not change height between one
 * zoom and the next.
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

/**
 * A filter for one operator, or none at all.
 *
 * Presence, because a tile carries no key at all for an operator that does not reach the
 * street. The GeoJSON this used to read wrote every operator's key on every feature, so
 * asking whether one was present was true everywhere and every filter matched everything.
 */
export function only(provider: string | null): ExpressionSpecification | null {
  if (provider === null) return null;
  const field = STREETS_BY_PROVIDER[provider];
  // An operator with no field of its own reaches nothing rather than everything.
  if (field === undefined) return ["boolean", false] as ExpressionSpecification;
  return ["has", field] as ExpressionSpecification;
}

/**
 * How the selection arrives.
 *
 * It used to appear the instant the street was chosen, which is while the camera is still
 * crossing the city — so the light was already burning on a street somewhere off the edge
 * of the screen by the time the reader got there. It waits for the journey instead, and
 * comes up rather than switching on.
 */
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
      /*
       * An invisible line, wide enough to hit.
       *
       * A street is drawn two or three pixels across, and a person aiming at one with a
       * mouse misses more often than not — with a thumb, almost always. So the thing that
       * is clicked is not the thing that is drawn: this one is transparent, twenty pixels
       * wide, and sits under the visible line where it catches everything aimed near it.
       */
      id: "streets-hit",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      minzoom: 11,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": "#000000",
        "line-opacity": 0,
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 10, 16, 22, 20, 44],
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
      /*
       * The one street that was chosen, drawn white over its own colour.
       *
       * Six streets in a city share a name, and naming one in a panel does not say which
       * of the six it is. White because the ramp owns every other hue on the map: any
       * colour bright enough to read as chosen would also read as a speed.
       *
       * It carries no operator filter. It was picked outright, and a selection that
       * disappears because a filter was pressed afterwards is a selection that lies.
       */
      /*
       * A glow under the selection, so it survives being zoomed out to.
       *
       * A long street is fitted, not flown to, and fitting one puts the camera at a zoom
       * where every street is a thread and the chosen one is no thicker than its
       * neighbours. Widest where the map is densest and the line is thinnest.
       */
      id: "streets-picked-halo",
      type: "line",
      source: SOURCE,
      "source-layer": STREETS_LAYER,
      filter: NOTHING,
      layout: { "line-cap": "round", "line-join": "round" },
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
      layout: { "line-cap": "round", "line-join": "round" },
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
 * The colour each coverage layer takes for one operator.
 *
 * Returned rather than rebuilt into new layers: switching operator is a paint change, and
 * removing a layer and adding it back moves it to the top of the style, above the
 * buildings, which drew the coverage straight over the roofs.
 */
/**
 * What the streets look like on a map that is about one of them.
 *
 * Behind a result the coverage of every other street is not the subject and competes with
 * it: forty thousand lit roads around the one being asked about, in the same colours, and
 * the answer is the least conspicuous thing on its own map. They go grey and quiet, the
 * subject keeps the ramp, and the reader has one thing to look at.
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
 * What the map is painted by.
 *
 * Filed is what the operators told the regulator reaches a street. Measured is what people
 * running a speed test actually got, which is a different claim about a different thing and
 * is usually lower. Mobile is the same measurement for phones, and is kept apart because a
 * mobile figure answers a question nobody asked when they were looking at a street.
 */
export const VIEWS = ["filed", "measured", "mobile"] as const;
export type View = (typeof VIEWS)[number];

/**
 * How much of a claim a measured cell is, drawn as opacity.
 *
 * A cell built from two tests is a weaker claim than one built from five hundred, and
 * showing it faintly is more honest than dropping it — dropping thin cells is what put most
 * of the holes in the prototype's map, and a hole reads as a broken layer rather than as a
 * quiet one.
 */
const CONFIDENCE: ExpressionSpecification = [
  "interpolate", ["linear"], ["coalesce", ["get", "tests"], 1],
  1, 0.4, 5, 0.66, 25, 1,
];

export function cellLayers(family: "fixed" | "mobile"): LayerSpecification[] {
  const field: keyof Cell = "down_mbps";
  return [
    {
      id: "cells",
      type: "fill",
      source: SOURCE,
      "source-layer": CELLS_LAYER,
      filter: ["==", ["get", "family"], family],
      // Off unless something turns it on. The map opens on filed coverage and switches to
      // these, and every other map on the site — the one behind a result, above all — wants
      // streets and not a grid of squares over them.
      layout: { visibility: "none" },
      paint: {
        "fill-color": ramp(field),
        // Zoom outermost, because `["zoom"]` has to be the input of a top-level interpolate;
        // nesting it inside the confidence term makes the whole style invalid and the map
        // never loads at all.
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
 * The whole style.
 *
 * The basemap comes from archives built elsewhere — planetiler needs more memory than the
 * machine this runs on — and is read by range request out of one file each. The coverage
 * comes from our own database, which is the half that changes.
 */
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
      /*
       * The sea is the background and the land is drawn on it.
       *
       * The other way round — land underneath, sea painted over it — is how this was, and
       * it means every stretch of open water depends on something being drawn there. Where
       * nothing was, the background showed through and the Aegean came out in rectangular
       * slabs of coastline-coloured land, because what was painting the sea was a polygon
       * with the country cut out of it, cut again into tiles, clipping badly.
       *
       * Drawn from underneath there is nothing to go wrong: what is not Greece is simply
       * not drawn, and what is underneath is already the sea.
       */
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

      ...streetLayers(null),
      ...cellLayers("fixed"),

      // A dark flat copy of the footprints, offset a few pixels, sitting under the
      // extrusions. It costs one fill layer and it is most of why an expensive-looking map
      // looks expensive.
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
          // A street name sits on the street, which at these zooms is a lit line — so it
          // needs more contrast than a town name floating on open ground, not less.
          "text-color": C.labelQuiet,
          "text-halo-color": C.labelHalo,
          "text-halo-width": 1.8,
        },
      },
    ],
  };
}
