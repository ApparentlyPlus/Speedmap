import { describe, expect, it } from "vitest";

import { ORIGIN, REACH, openingAt, veilAt } from "./reveal";

describe("the sheet the map arrives from under", () => {
  it("covers the world and keeps a hole in it", () => {
    const rings = veilAt(1).geometry.coordinates;
    expect(rings).toHaveLength(2);
    // The outer ring has to reach the corners, or the sheet has an edge somebody can see.
    const outer = rings[0]!;
    expect(Math.min(...outer.map((point) => point[0]!))).toBe(-180);
    expect(Math.max(...outer.map((point) => point[0]!))).toBe(180);
  });

  it("opens the hole over Athens", () => {
    const hole = veilAt(2).geometry.coordinates[1]!;
    const lats = hole.map((point) => point[1]!);
    expect((Math.min(...lats) + Math.max(...lats)) / 2).toBeCloseTo(ORIGIN[1], 6);
  });

  it("closes the hole ring", () => {
    const hole = veilAt(1).geometry.coordinates[1]!;
    expect(hole[0]).toEqual(hole[hole.length - 1]);
  });
});

describe("the opening", () => {
  it("starts shut and ends gone", () => {
    expect(openingAt(0).radius).toBeCloseTo(0, 10);
    expect(openingAt(0).cover).toBe(1);
    expect(openingAt(1).cover).toBeCloseTo(0, 10);
  });

  it("has taken in the country before the sheet finishes going", () => {
    // Otherwise the opening ends with a ring still travelling over Thrace, which reads as
    // unfinished rather than as arrived.
    expect(openingAt(0.8).radius).toBeGreaterThan(REACH * 0.95);
    expect(openingAt(0.8).cover).toBeGreaterThan(0);
  });

  it("only ever widens", () => {
    let last = -1;
    for (let step = 0; step <= 100; step++) {
      const { radius } = openingAt(step / 100);
      expect(radius).toBeGreaterThanOrEqual(last);
      last = radius;
    }
  });
});
