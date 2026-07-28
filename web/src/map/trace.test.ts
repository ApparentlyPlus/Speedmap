import { describe, expect, it } from "vitest";

import { bullet, extentOf } from "./trace";

describe("the light that runs along a street", () => {
  const stops = (progress: number): number[] =>
    (bullet(progress).slice(3) as unknown[]).filter((_, at) => at % 2 === 0) as number[];

  it("never repeats a stop, at any moment of the pass", () => {
    // A repeated stop is not a dim highlight, it is an invalid expression — and an invalid
    // expression does not fail the layer, it fails the whole style and the map is blank.
    for (let step = 0; step <= 100; step++) {
      const written = stops(step / 100);
      expect(written).toEqual([...new Set(written)]);
      expect([...written].sort((a, b) => a - b)).toEqual(written);
    }
  });

  it("stays inside the line it is lighting", () => {
    for (let step = 0; step <= 100; step++) {
      for (const stop of stops(step / 100)) {
        expect(stop).toBeGreaterThanOrEqual(0);
        expect(stop).toBeLessThanOrEqual(1);
      }
    }
  });

  const brightest = (progress: number): number =>
    Math.max(
      ...(bullet(progress).slice(3) as unknown[])
        .filter((_, at) => at % 2 === 1)
        .map((colour) => Number(/,([\d.]+)\)$/.exec(String(colour))?.[1] ?? 0)),
    );

  it("arrives and leaves rather than blinking", () => {
    expect(brightest(0)).toBeCloseTo(0);
    expect(brightest(1)).toBeCloseTo(0);
    expect(brightest(0.5)).toBeGreaterThan(0.9);
  });

  it("never jumps in brightness between one frame and the next", () => {
    // The blink this replaces was a stop appearing and disappearing. Nothing about the
    // light may change faster than the eye reads as motion.
    let previous = brightest(0);
    for (let step = 1; step <= 400; step++) {
      const now = brightest(step / 400);
      expect(Math.abs(now - previous)).toBeLessThan(0.05);
      previous = now;
    }
  });

  it("keeps the same number of stops all the way through", () => {
    // A frame that gains or loses a stop is a step, however faint the colour on it.
    const counts = new Set<number>();
    for (let step = 0; step <= 400; step++) counts.add(bullet(step / 400).length);
    expect(counts.size).toBe(1);
  });
});

describe("the box a street occupies", () => {
  it("covers every part of a street drawn in pieces", () => {
    // A street is several OSM ways, and framing only the first one frames a third of it.
    const found = extentOf({
      type: "MultiLineString",
      coordinates: [
        [
          [23.0, 37.9],
          [23.1, 38.0],
        ],
        [
          [22.8, 38.2],
          [23.3, 37.7],
        ],
      ],
    });
    expect(found).toEqual([
      [22.8, 37.7],
      [23.3, 38.2],
    ]);
  });

  it("says nothing rather than an empty box when there is no line", () => {
    expect(extentOf({ type: "GeometryCollection", geometries: [] })).toBeNull();
  });
});
