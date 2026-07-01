/**
 * The style, validated the way MapLibre validates it.
 *
 * MapLibre rejects an entire style on one bad expression: no layers, no sources, no map —
 * and it says so by firing an event rather than by throwing, so the page is blank and looks
 * like a slow network. Finding that out in a browser costs an hour; finding it out here
 * costs a second, and needs neither a browser nor a GPU.
 */

import {
  validateStyleMin,
  type StyleSpecification,
} from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import { RAMP } from "../tokens";
import { HANDOVER, REGIONS, SOURCE, only, regionLayers, streetLayers, style } from "./style";
import { STREETS_BY_PROVIDER } from "./tiles";

const EMPTY = { type: "FeatureCollection" as const, features: [] };
const GEOJSON = { type: "geojson" as const, data: EMPTY };
const VECTOR = { type: "vector" as const, tiles: ["https://example.invalid/{z}/{x}/{y}"] };

describe("the style MapLibre is given", () => {
  it("is valid as geojson", () => {
    expect(validateStyleMin(style(GEOJSON, "geojson"))).toEqual([]);
  });

  it("is valid as vector tiles", () => {
    expect(validateStyleMin(style(VECTOR, "vector"))).toEqual([]);
  });

  it("is valid filtered to every operator it offers", () => {
    for (const code of Object.keys(STREETS_BY_PROVIDER)) {
      const filtered = { ...style(GEOJSON), layers: streetLayers(code) };
      expect(validateStyleMin(filtered), code).toEqual([]);
    }
  });

  it("is valid filtered to an operator it has never heard of", () => {
    const filtered = { ...style(GEOJSON), layers: streetLayers("WHOEVER") };
    expect(validateStyleMin(filtered)).toEqual([]);
  });
});

describe("no reachable zoom is empty", () => {
  it("draws the country before it draws streets", () => {
    // A map with no basemap and nothing at low zoom is a black rectangle telling the reader
    // to zoom in, somewhere, with no clue where.
    const layers = style(GEOJSON).layers.map((layer) => layer.id);
    expect(layers).toContain("regions");
    expect(layers).toContain("streets");
  });

  it("puts the streets above the country", () => {
    const layers = style(GEOJSON).layers.map((layer) => layer.id);
    expect(layers.indexOf("regions")).toBeLessThan(layers.indexOf("streets"));
  });

  it("hands over rather than switching", () => {
    // Both are drawn either side of the handover, so there is no zoom with nothing in it.
    const [fill] = regionLayers();
    const opacity = (fill as { paint: { "fill-opacity": unknown[] } }).paint["fill-opacity"];
    const stops = opacity.slice(3).filter((_, index) => index % 2 === 0) as number[];
    expect(Math.min(...stops)).toBeLessThan(HANDOVER);
    expect(Math.max(...stops)).toBeGreaterThan(HANDOVER);
    const shown = opacity.slice(3).filter((_, index) => index % 2 === 1) as number[];
    expect(Math.min(...shown)).toBeGreaterThan(0);
  });

  it("shades the country from its own source", () => {
    for (const layer of regionLayers()) {
      expect(layer).toMatchObject({ source: REGIONS });
    }
  });

  it("shades a municipality with nothing filed rather than dropping it", () => {
    // 204 of 333 have no fibre at all. Dropping them would put holes in the coastline.
    const [fill] = regionLayers();
    const colour = (fill as { paint: { "fill-color": unknown[] } }).paint["fill-color"];
    expect(JSON.stringify(colour)).toContain('["coalesce",["get","fibre_share"],0]');
  });
});

describe("the validator itself", () => {
  it("rejects a style that is wrong", () => {
    // A validator that only ever runs against a valid style is indistinguishable from one
    // that is broken, so it is shown a broken one: a line layer painted with a colour that
    // is not a colour, which is the shape most expression mistakes end up taking.
    const broken = {
      ...style(GEOJSON),
      layers: [
        {
          id: "streets",
          type: "line" as const,
          source: SOURCE,
          paint: { "line-color": ["step", ["zoom"], 12, 4, 16] },
        },
      ],
    };
    // Cast, because TypeScript already refuses this one — which is half the guarantee, and
    // the runtime validator is the other half for the styles that are built rather than
    // written out.
    expect(validateStyleMin(broken as unknown as StyleSpecification).length).toBeGreaterThan(0);
  });

  it("rejects a layer drawing from a source that is not there", () => {
    const orphan = {
      ...style(GEOJSON),
      layers: [{ id: "x", type: "line" as const, source: "gone" }],
    };
    expect(validateStyleMin(orphan as unknown as StyleSpecification).length).toBeGreaterThan(0);
  });
});

describe("what the layers say", () => {
  it("names the tile layer only where there is one to name", () => {
    // A GeoJSON source is the layer; `source-layer` on one matches nothing and paints
    // nothing, silently.
    for (const layer of streetLayers(null, "geojson")) {
      expect(layer).not.toHaveProperty("source-layer");
    }
    for (const layer of streetLayers(null, "vector")) {
      expect(layer).toHaveProperty("source-layer");
    }
  });

  it("draws from the one source", () => {
    for (const layer of streetLayers(null)) {
      expect(layer).toMatchObject({ source: SOURCE });
    }
  });

  it("asks whether a field is there rather than comparing it to null", () => {
    // `has` is the documented way to ask; `!= null` leans on `==` accepting a type it does
    // not promise to accept.
    expect(only("OTE")).toEqual(["has", STREETS_BY_PROVIDER.OTE]);
  });

  it("offers nothing for an operator with no field of its own", () => {
    expect(only("WHOEVER")).toEqual(["boolean", false]);
  });

  it("filters nothing when no operator is chosen", () => {
    expect(only(null)).toBeUndefined();
  });
});

describe("the ramp", () => {
  const paint = (): unknown[] => {
    const [, streets] = streetLayers(null);
    return (streets as { paint: { "line-color": unknown[] } }).paint["line-color"];
  };

  it("steps in ascending order", () => {
    // The ramp is written fastest first and `step` wants ascending stops: the one place the
    // two orders meet, and a good place to get it wrong.
    const stops = paint()
      .slice(3)
      .filter((_, index) => index % 2 === 0) as number[];
    expect(stops).toEqual([...stops].sort((a, b) => a - b));
  });

  it("carries every band the rest of the site uses", () => {
    const colours = paint().filter((value) => typeof value === "string" && value.startsWith("#"));
    for (const band of RAMP) {
      expect(colours).toContain(band.colour);
    }
  });

  it("paints an unfiled speed as unfiled and not as slow", () => {
    // Not filed is the commonest state in the register. Painting it red would invent a fact
    // about six operators in one stroke.
    const [, , base] = paint();
    expect(base).not.toEqual(RAMP[RAMP.length - 1]?.colour);
  });
});
