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
  LayerSpecification,
  StyleSpecification,
} from "maplibre-gl";

import { RAMP, UNFILED } from "../tokens";
import { STREETS_BY_PROVIDER, STREETS_LAYER, type Street } from "./tiles";

export const SOURCE = "speedmap";

/** The basemap and the footprints: OpenStreetMap through planetiler, and Overture. */
export const BASE = "base";
export const BUILDINGS = "buildings";

/** Reaches this street and filed no speed for it: below the ramp, but served. */
export const SERVED = -1;

/** Does not reach this street at all. Below that, so a filter can tell them apart. */
export const NOT_SERVED = -2;

/** Greece, with room for Crete and the north in the same view. */
export const HOME = { centre: [24.0, 38.4] as [number, number], zoom: 6.2 };

/**
 * The ground, and the few things that give it a shape.
 *
 * Nothing here is a colour anyone picked to be pretty: water has to be darker than land or
 * the coast inverts, parks have to be greener than landuse or a city reads as one surface,
 * and the ambient occlusion has to be darker than the building or the shadow glows.
 */
const C = {
  ground: "#07080a",
  landuse: "#12151a",
  park: "#0f1712",
  water: "#0a1420",
  building: "#171a21",
  occlusion: "#050608",
  road: "#242832",
  roadMinor: "#1b1e26",
  roadMajor: "#333846",
  label: "#8b93a3",
  labelHalo: "#05060a",
} as const;

/**
 * The ramp as a step expression over the same floors the rest of the system reasons in.
 *
 * Three states, not two. Null is an operator that does not reach this street; one below the
 * bottom of the ramp is one that reaches it and filed no speed, which is the commonest
 * thing the register says; a number is the speed. The first two are painted alike and the
 * filter tells them apart.
 *
 * Not filed is not slow: painting it at the bottom of the ramp would invent a fact about
 * six operators in one stroke.
 */
function ramp(field: keyof Street): ExpressionSpecification {
  // The ramp is written fastest first and `step` wants ascending stops: the one place the
  // two orders meet, and a good place to get it wrong.
  const rising = [...RAMP].reverse();
  const stops = rising.flatMap((band) => [band.floor as number, band.colour]);
  return ["step", ["coalesce", ["get", field], SERVED], UNFILED, ...stops] as ExpressionSpecification;
}

/**
 * A filter for one operator, or none at all.
 *
 * On the value, not the key: `has` asks whether a property is present, and the builder
 * writes every operator's field on every street, so it was true everywhere and the filter
 * showed the whole country whichever operator was picked.
 */
export function only(provider: string | null): ExpressionSpecification | undefined {
  if (provider === null) return undefined;
  const field = STREETS_BY_PROVIDER[provider];
  // An operator with no field of its own reaches nothing rather than everything.
  if (field === undefined) return ["boolean", false] as ExpressionSpecification;
  return [">=", ["coalesce", ["get", field], NOT_SERVED], SERVED] as ExpressionSpecification;
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
 * Whether the streets arrive in a vector tile or as plain GeoJSON.
 *
 * One property's worth of difference: a vector tile carries named layers inside it and a
 * layer must say which one it draws, while a GeoJSON source is the layer. Setting
 * `source-layer` on GeoJSON matches nothing and paints nothing, silently.
 */
export type Carried = "vector" | "geojson";

export function streetLayers(
  provider: string | null,
  carried: Carried = "geojson",
): LayerSpecification[] {
  const named = carried === "vector" ? { "source-layer": STREETS_LAYER } : {};
  const field: keyof Street =
    provider === null ? "best_mbps" : (STREETS_BY_PROVIDER[provider] ?? "best_mbps");
  const paint = ramp(field);
  const filter = only(provider);

  return [
    {
      // A wide, dim, blurred copy under the line. Cheaper than a real glow, and it is most
      // of what makes the coverage read as light on the street rather than paint on it.
      id: "streets-halo",
      type: "line",
      source: SOURCE,
      ...named,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": paint,
        "line-blur": 5,
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 10, 4, 13, 8, 16, 22, 20, 60],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.08, 13, 0.13, 15, 0.2, 18, 0.09],
      },
    },
    {
      id: "streets",
      type: "line",
      source: SOURCE,
      ...named,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": paint,
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 13, 0.62, 15, 0.72, 18, 0.5],
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          9, 0.6, 12, 1.4, 14, 2.8, 16, 7, 20, 26,
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
export function style(
  source: StyleSpecification["sources"][string],
  carried: Carried = "geojson",
  base = "/tiles",
): StyleSpecification {
  return {
    version: 8,
    name: "speedmap",
    glyphs: "https://fonts.openmaptiles.org/{fontstack}/{range}.pbf",
    sources: {
      [BASE]: { type: "vector", url: `pmtiles://${base}/greece.pmtiles` },
      // Overture conflates OSM with footprints derived from imagery, which is the only way
      // to have buildings outside Athens and Thessaloniki at all.
      [BUILDINGS]: { type: "vector", url: `pmtiles://${base}/buildings.pmtiles` },
      [SOURCE]: source,
    },
    // One light, from the side and above, so extrusions have a lit face and a dark one.
    // Without it every building is the same flat tone and the city reads as a printed plan.
    light: { anchor: "viewport", color: "#ffffff", intensity: 0.35, position: [1.2, 210, 30] },
    layers: [
      { id: "ground", type: "background", paint: { "background-color": C.ground } },

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

      ...streetLayers(null, carried),

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
          "text-halo-width": 1.4,
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
          "text-color": "#6b7383",
          "text-halo-color": C.labelHalo,
          "text-halo-width": 1.2,
        },
      },
    ],
  };
}
