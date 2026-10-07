/** The style, validated the way MapLibre validates it. */

import {
  featureFilter,
  validateStyleMin,
  type StyleSpecification,
} from "@maplibre/maplibre-gl-style-spec";
import { describe, expect, it } from "vitest";

import { RAMP, UNSERVED } from "../tokens";
import { ASIDE, BASE, BUILDINGS, SOURCE, hushed, only, streetLayers, style } from "./style";
import { BASEMAP, STREETS_BY_PROVIDER } from "./tiles";


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
    // without it the opening view is a black rectangle and a panel saying zoom in somewhere
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
    // no light, and every extrusion is one flat tone
    expect(style().light).toBeDefined();
  });
});

/** Every field a value reads with get or has, at any depth. */
function reads(value: unknown, into: Set<string> = new Set()): Set<string> {
  if (Array.isArray(value)) {
    const [op, field] = value as unknown[];
    // a third argument means another object's field, not the feature's
    if ((op === "get" || op === "has") && typeof field === "string" && value.length === 2) {
      into.add(field);
    }
    for (const part of value) reads(part, into);
  } else if (value !== null && typeof value === "object") {
    for (const part of Object.values(value)) reads(part, into);
  }
  return into;
}

/** Each layer reading a layer or field of an archive built elsewhere that slimming drops. */
function unkept(spec: StyleSpecification): string[] {
  const wrong: string[] = [];
  for (const layer of spec.layers) {
    if (!("source" in layer) || !("source-layer" in layer)) continue;
    const source = spec.sources[layer.source];
    const url = source !== undefined && "url" in source ? (source.url ?? "") : "";
    const kept = BASEMAP[url.split("/").pop() ?? ""];
    if (kept === undefined) continue;
    const fields = kept[layer["source-layer"] as string];
    if (fields === undefined) {
      wrong.push(`${layer.id}: layer ${String(layer["source-layer"])}`);
      continue;
    }
    const { filter, layout, paint } = layer as Record<string, unknown>;
    for (const field of reads([filter, layout, paint])) {
      if (!fields.includes(field)) wrong.push(`${layer.id}: field ${field}`);
    }
  }
  return wrong;
}

describe("the archives built elsewhere, slimmed", () => {
  // tools/slim_basemap.py drops what schema/tiles.yaml doesn't list. A style reading a
  // dropped field gets nothing and draws its fallback without a word.
  it("keep every layer and field the style reads", () => {
    expect(unkept(style())).toEqual([]);
  });

  it("keep every layer and field the result map's style reads", () => {
    expect(unkept(hushed(style()))).toEqual([]);
  });

  it("are checked by a test that can fail", () => {
    const spec = style();
    const label = spec.layers.find((layer) => layer.id === "place-label");
    expect(label).toBeDefined();
    const english = { ...label, id: "english", layout: { "text-field": ["get", "name:en"] } };
    const elsewhere = { ...label, id: "peaks", "source-layer": "mountain_peak" };
    const broken = { ...spec, layers: [...spec.layers, english, elsewhere] } as StyleSpecification;
    expect(unkept(broken)).toEqual(["english: field name:en", "peaks: layer mountain_peak"]);
  });
});

describe("the validator itself", () => {
  it("rejects a style that is wrong", () => {
    // a validator that only ever sees valid styles can't be told apart from a broken one
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
    // cast, since TypeScript already rejects this, which is half the guarantee
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
    // A layer must name its source-layer. Without it, it matches and paints nothing, silently.
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
    // tippecanoe writes no attribute for null, so a missing key means "doesn't reach"
    const field = String(STREETS_BY_PROVIDER.TELEKOM);
    const run = featureFilter(only("TELEKOM") as never);
    const asked = (properties: Record<string, number>): boolean =>
      run.filter({ zoom: 13 } as never, { type: 2, properties } as never, undefined as never);

    expect(asked({ [field]: 300 })).toBe(true);
    // reaches the street, no speed filed: the register's most common answer
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
    // by id: the layer list once gained an invisible click layer and a positional read
    // silently tested that instead
    const streets = streetLayers(null).find((layer) => layer.id === "streets");
    return (streets as { paint: { "line-color": unknown[] } }).paint["line-color"];
  };

  it("rises in ascending order", () => {
    // the ramp is written fastest first and interpolate wants ascending stops, an easy place
    // to get the order wrong
    const [, , , anchors] = paint() as unknown[];
    const stops = (anchors as unknown[]).slice(3).filter((_, index) => index % 2 === 0) as number[];
    expect(stops).toEqual([...stops].sort((a, b) => a - b));
  });

  it("carries every band the rest of the site uses", () => {
    const written = JSON.stringify(paint());
    for (const band of RAMP) {
      expect(written).toContain(band.colour);
    }
  });

  it("keeps the three fast bands apart by more than a shade", () => {
    // the fast end is spaced for contrast, since those are the bands people choose between
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
    // 5,403 streets have no line at all, which isn't the same as a bad line
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
    // the map page turns them on with the view switch
    const cells = style().layers.find((layer) => layer.id === "cells");
    expect(cells?.layout?.visibility).toBe("none");
  });
});


describe("the result map's style", () => {
  it("is already quiet when it is handed over", () => {
    // Colours used to be turned down after the style loaded, so the result map showed one
    // frame of full colour over the whole country and then dropped it. That flinch read
    // as jagged before the camera had moved.
    const quiet = hushed(style());
    const halo = quiet.layers.find((layer) => layer.id === "streets-halo");
    const streets = quiet.layers.find((layer) => layer.id === "streets");
    expect(halo?.layout?.visibility).toBe("none");
    expect(streets?.type).toBe("line");
    expect(
      (streets as { paint?: Record<string, unknown> }).paint?.["line-color"],
    ).toBe(ASIDE);
  });

  it("leaves the map page's own style painted", () => {
    // only the result map hushes. the atlas is the coverage, and hushed it'd be all grey
    const streets = style().layers.find((layer) => layer.id === "streets");
    expect(
      (streets as { paint?: Record<string, unknown> }).paint?.["line-color"],
    ).not.toBe(ASIDE);
  });
});
