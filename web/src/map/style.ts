/**
 * The map style, as typed code rather than a JSON file.
 *
 * MapLibre rejects an entire style on one bad paint expression: the map does not load at
 * all, and the error says which layer without saying what about it. A JSON file gets that
 * wrong at runtime in front of a reader; a builder gets it wrong at compile time in front of
 * whoever wrote it.
 *
 * Every field name here comes from the generated tile contract and every colour from the
 * one speed ramp, so the map and the suggestion list cannot teach different colours for the
 * same speed.
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

/** Reaches this street and filed no speed for it: below the ramp, but served. */
export const SERVED = -1;

/** Does not reach this street at all. Below that, so a filter can tell them apart. */
export const NOT_SERVED = -2;
export const REGIONS = "regions";

/**
 * Where the streets take over from the municipalities.
 *
 * Below this a street is a fraction of a pixel and there is nothing to see; above it the
 * regions would be a wash over the thing the reader came for. They cross rather than
 * switch, so neither zoom has a moment with nothing in it.
 */
export const HANDOVER = 9;

/** Greece, with room for Crete and the north in the same view. */
export const HOME = { centre: [24.0, 38.4] as [number, number], zoom: 6.2 };

/**
 * The ramp as a step expression over the same floors the rest of the system reasons in.
 *
 * A missing speed becomes one below the bottom of the ramp rather than being compared
 * against null: `==` promises to compare strings to strings and numbers to numbers, and
 * nothing about null, so the arithmetic says it without leaning on that.
 *
 * Not filed is not slow. It is the commonest state in the register, and painting it red
 * would invent a fact about six operators in one stroke.
 */
function ramp(field: keyof Street): ExpressionSpecification {
  // The ramp is written fastest first and `step` wants ascending stops: the one place the
  // two orders meet, and a good place to get it wrong.
  const rising = [...RAMP].reverse();
  const stops = rising.flatMap((band) => [band.floor as number, band.colour]);
  return [
    "step",
    ["coalesce", ["get", field], -1],
    UNFILED,
    ...stops,
  ] as ExpressionSpecification;
}

/** Thin where the country is in view, wide enough to click where a street is. */
const WIDTH: DataDrivenPropertyValueSpecification<number> = [
  "interpolate",
  ["linear"],
  ["zoom"],
  9, 0.6,
  12, 1.6,
  15, 3.4,
  18, 7,
];

/**
 * A filter for one operator, or none at all.
 *
 * Filtering on the street's overall best would paint a street in an operator's colour on
 * the strength of a different operator's filing, which is the whole reason the per-operator
 * fields exist.
 */
export function only(provider: string | null): ExpressionSpecification | undefined {
  if (provider === null) return undefined;
  const field = STREETS_BY_PROVIDER[provider];
  // An operator with no field of its own reaches nothing rather than everything.
  if (field === undefined) return ["boolean", false] as ExpressionSpecification;
  /*
   * The value, not the key. `has` asks whether the property is present, and the builder
   * writes every operator's field on every street — so it was true everywhere and the
   * filter showed the whole country whichever operator was picked.
   *
   * Three states to tell apart: null does not reach here, -1 reaches here and filed no
   * speed, a number is the speed. The middle one is the commonest thing the register says,
   * so it has to pass.
   */
  return [">=", ["coalesce", ["get", field], NOT_SERVED], SERVED] as ExpressionSpecification;
}

/**
 * Whether the streets arrive in a vector tile or as plain GeoJSON.
 *
 * The distinction is one property: a vector tile carries named layers inside it and a layer
 * must say which one it draws, while a GeoJSON source is the layer. Setting `source-layer`
 * on GeoJSON matches nothing and paints nothing, silently — which is exactly the class of
 * failure the generated contract exists to stop, arriving by a different door.
 */
export type Carried = "vector" | "geojson";

export function streetLayers(
  provider: string | null,
  carried: Carried = "geojson",
): LayerSpecification[] {
  const named = carried === "vector" ? { "source-layer": STREETS_LAYER } : {};
  // An operator with no field of its own is not painted as though it had one.
  const field: keyof Street =
    provider === null ? "best_mbps" : (STREETS_BY_PROVIDER[provider] ?? "best_mbps");
  const paint = ramp(field);
  const filter = only(provider);

  return [
    {
      // A wide, dim copy under the line. Cheaper than a real glow and it survives a phone.
      id: "streets-halo",
      type: "line",
      source: SOURCE,
      ...named,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": paint,
        "line-width": ["interpolate", ["linear"], ["zoom"], 9, 3, 15, 11],
        "line-opacity": 0.16,
        "line-blur": 3,
      },
    },
    {
      id: "streets",
      type: "line",
      source: SOURCE,
      ...named,
      ...(filter ? { filter } : {}),
      layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": paint, "line-width": WIDTH },
    },
  ];
}

/**
 * The country, shaded by how much of each municipality fibre reaches.
 *
 * Greyscale on purpose. This is a density and not a speed, and the speed ramp owns every
 * hue on this map: two colour languages on one screen is one too many, and a share painted
 * in the ramp would read as a band. Shape first, then streets.
 */
export function regionLayers(): LayerSpecification[] {
  const shade: ExpressionSpecification = [
    "interpolate",
    ["linear"],
    ["coalesce", ["get", "fibre_share"], 0],
    0, "#17171b",
    0.25, "#2b2b33",
    0.5, "#4a4a57",
    1, "#8b8b9c",
  ];
  return [
    {
      id: "regions",
      type: "fill",
      source: REGIONS,
      paint: {
        "fill-color": shade,
        // Handed over to the streets rather than switched off, so no zoom is ever empty.
        "fill-opacity": ["interpolate", ["linear"], ["zoom"], HANDOVER - 1, 1, HANDOVER + 2, 0.35],
      },
    },
    {
      id: "regions-edge",
      type: "line",
      source: REGIONS,
      paint: {
        "line-color": "#000",
        "line-width": 0.6,
        "line-opacity": ["interpolate", ["linear"], ["zoom"], HANDOVER - 1, 0.7, HANDOVER + 2, 0.25],
      },
    },
  ];
}

/**
 * The whole style.
 *
 * No basemap: this map is about one thing, and its own layers say it without borrowing
 * anyone's cartography or their tile bill. The municipalities are what gives the country a
 * shape at the zooms where a street cannot.
 */
export function style(
  source: StyleSpecification["sources"][string],
  carried: Carried = "geojson",
): StyleSpecification {
  return {
    version: 8,
    sources: {
      [SOURCE]: source,
      [REGIONS]: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
    },
    layers: [
      { id: "ground", type: "background", paint: { "background-color": "#08080a" } },
      ...regionLayers(),
      ...streetLayers(null, carried),
    ],
  };
}
