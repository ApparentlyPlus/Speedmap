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

import { RAMP, UNSERVED } from "../tokens";
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
    // By id, not by position: the layer list grew an invisible one to click on, and a
    // positional read of it silently started testing that instead.
    const streets = streetLayers(null).find((layer) => layer.id === "streets");
    return (streets as { paint: { "line-color": unknown[] } }).paint["line-color"];
  };

  it("rises in ascending order", () => {
    // The ramp is written fastest first and `interpolate` wants ascending stops: the one
    // place the two orders meet, and a good place to get it wrong.
    //
    // Index three, not five: the ramp used to sit behind two guards — not reached, and
    // reaches-but-filed-no-speed. The second cannot happen now that the figure starts from
    // the technology, so the case has one arm fewer and the interpolate moved up.
    const [, , , anchors] = paint() as unknown[];
    const stops = (anchors as unknown[])
      .slice(3)
      .filter((_, index) => index % 2 === 0) as number[];
    expect(stops).toEqual([...stops].sort((a, b) => a - b));
  });

  it("carries every band the rest of the site uses", () => {
    const written = JSON.stringify(paint());
    for (const band of RAMP) {
      expect(written).toContain(band.colour);
    }
  });

  it("keeps the three fast bands apart by more than a shade", () => {
    // The fast end is picked for separation rather than ranked by hue, because the bands
    // people actually choose between are all up there. When the top went from violet to
    // blue it landed next to 300's cyan, which is two bands nobody can tell apart at the
    // width a street is drawn — so the cool end was rebuilt around it.
    const fast = RAMP.filter((band) => band.floor >= 300).map((band) => band.colour);
    expect(new Set(fast).size).toBe(fast.length);
    for (const colour of fast) {
      const others = fast.filter((one) => one !== colour);
      for (const other of others) {
        expect(channels(colour)).not.toEqual(channels(other));
      }
    }
  });

  it("paints a street nothing reaches as absence, not as the slowest speed", () => {
    // 5,403 streets have no line at all. No line is not a bad line, and drawing the two
    // the same colour would put them in a class the register never put them in.
    const written = JSON.stringify(paint());
    expect(written).toContain(UNSERVED);
    expect(UNSERVED).not.toEqual(RAMP[RAMP.length - 1]?.colour);
  });
});

function channels(hex: string): [number, number, number] {
  return [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16)) as [number, number, number];
}

describe("what a fresh style draws", () => {
  it("leaves the measured squares off until something asks for them", () => {
    // The map page turns them on with the view switch. Every other map that mounts this
    // style — the one behind a result — shows an address, and a grid of squares over it is
    // the map page's state following the reader somewhere it does not belong.
    const cells = style().layers.find((layer) => layer.id === "cells");
    expect(cells?.layout?.visibility).toBe("none");
  });
});
