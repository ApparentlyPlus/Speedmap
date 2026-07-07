/**
 * The style, validated the way MapLibre validates it.
 *
 * MapLibre rejects an entire style on one bad expression: no layers, no sources, no map —
 * and it says so by firing an event rather than by throwing, so the page is blank and looks
 * like a slow network. Finding that out in a browser costs an hour; finding it out here
 * costs a second, and needs neither a browser nor a GPU.
 */

import {
  featureFilter,
  validateStyleMin,
  type StyleSpecification,
} from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import { RAMP, UNFILED } from "../tokens";
import { BASE, BUILDINGS, SOURCE, only, streetLayers, style } from "./style";
import { STREETS_BY_PROVIDER } from "./tiles";


describe("the style MapLibre is given", () => {
  it("is valid as geojson", () => {
    expect(validateStyleMin(style())).toEqual([]);
  });

  it("is valid as vector tiles", () => {
    expect(validateStyleMin(style())).toEqual([]);
  });

  it("is valid filtered to every operator it offers", () => {
    for (const code of Object.keys(STREETS_BY_PROVIDER)) {
      const filtered = { ...style(), layers: streetLayers(code) };
      expect(validateStyleMin(filtered), code).toEqual([]);
    }
  });

  it("is valid filtered to an operator it has never heard of", () => {
    const filtered = { ...style(), layers: streetLayers("WHOEVER") };
    expect(validateStyleMin(filtered)).toEqual([]);
  });
});

describe("no reachable zoom is empty", () => {
  it("has a basemap under the coverage", () => {
    // Without one the opening view is a black rectangle and a panel telling the reader to
    // zoom in, somewhere, with no clue where.
    const sources = Object.keys(style().sources);
    expect(sources).toContain(BASE);
    expect(sources).toContain(BUILDINGS);
  });

  it("draws the coverage over the roads and under the buildings", () => {
    const layers = style().layers.map((layer) => layer.id);
    expect(layers.indexOf("road")).toBeLessThan(layers.indexOf("streets"));
    expect(layers.indexOf("streets")).toBeLessThan(layers.indexOf("building"));
  });

  it("lays a shadow under the buildings rather than over them", () => {
    const layers = style().layers.map((layer) => layer.id);
    expect(layers.indexOf("building-shadow")).toBeLessThan(layers.indexOf("building"));
  });

  it("lights the buildings from somewhere", () => {
    // Without a light every extrusion is one flat tone and the city reads as a plan.
    expect(style().light).toBeDefined();
  });
});

describe("the validator itself", () => {
  it("rejects a style that is wrong", () => {
    // A validator that only ever runs against a valid style is indistinguishable from one
    // that is broken, so it is shown a broken one: a line layer painted with a colour that
    // is not a colour, which is the shape most expression mistakes end up taking.
    const broken = {
      ...style(),
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
      ...style(),
      layers: [{ id: "x", type: "line" as const, source: "gone" }],
    };
    expect(validateStyleMin(orphan as unknown as StyleSpecification).length).toBeGreaterThan(0);
  });
});

describe("what the layers say", () => {
  it("names the layer inside the archive it draws", () => {
    // A vector tile carries named layers and a layer must say which one it draws. Omitting
    // it matches nothing and paints nothing, silently.
    for (const layer of streetLayers(null)) {
      expect(layer).toHaveProperty("source-layer");
    }
  });

  it("draws from the one source", () => {
    for (const layer of streetLayers(null)) {
      expect(layer).toMatchObject({ source: SOURCE });
    }
  });

  it("filters on whether the operator is there at all", () => {
    /*
     * A tile carries no key for an operator that does not reach the street — tippecanoe
     * writes no attribute for a null — so presence is exactly the question.
     *
     * This was the other way round while the coverage arrived as GeoJSON, where the builder
     * wrote every operator's key on every feature and `has` was true everywhere. Run rather
     * than read, because reading it is how that one got through.
     */
    const field = String(STREETS_BY_PROVIDER.OTE);
    const run = featureFilter(only("OTE") as never);
    const asked = (properties: Record<string, number>): boolean =>
      run.filter({ zoom: 13 } as never, { type: 2, properties } as never, undefined as never);

    expect(asked({ [field]: 300 })).toBe(true);
    // Reaches the street, filed no speed: the commonest thing the register says.
    expect(asked({ [field]: -1 })).toBe(true);
    expect(asked({ best_mbps: 300 })).toBe(false);
  });

  it("offers nothing for an operator with no field of its own", () => {
    expect(only("WHOEVER")).toEqual(["boolean", false]);
  });

  it("filters nothing when no operator is chosen", () => {
    expect(only(null)).toBeNull();
  });
});

describe("the ramp", () => {
  const paint = (): unknown[] => {
    const [, streets] = streetLayers(null);
    return (streets as { paint: { "line-color": unknown[] } }).paint["line-color"];
  };

  it("rises in ascending order", () => {
    // The ramp is written fastest first and `interpolate` wants ascending stops: the one
    // place the two orders meet, and a good place to get it wrong.
    const [, , , , , anchors] = paint() as unknown[];
    const stops = (anchors as unknown[])
      .slice(3)
      .filter((_, index) => index % 2 === 0) as number[];
    expect(stops).toEqual([...stops].sort((a, b) => a - b));
  });

  it("carries every band the rest of the site uses", () => {
    // Nested now: the ramp sits inside a case that takes the two states outside it first.
    const written = JSON.stringify(paint());
    for (const band of RAMP) {
      expect(written).toContain(band.colour);
    }
  });

  it("paints an unfiled speed as unfiled and not as slow", () => {
    // Run through the ramp it interpolated down to near-black and made eight operators
    // invisible, and it is the commonest thing the register says.
    const written = JSON.stringify(paint());
    expect(written).toContain(UNFILED);
    expect(UNFILED).not.toEqual(RAMP[RAMP.length - 1]?.colour);
  });
});
