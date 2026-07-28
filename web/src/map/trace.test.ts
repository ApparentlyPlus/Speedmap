import { describe, expect, it } from "vitest";

import { bullet } from "./trace";

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

  it("enters at one end and leaves at the other", () => {
    // Lit nowhere at the start and nowhere at the end: the light arrives and departs
    // rather than blinking into existence halfway down the street.
    expect(JSON.stringify(bullet(0))).not.toContain("#ffffff");
    expect(JSON.stringify(bullet(1))).not.toContain("#ffffff");
    expect(JSON.stringify(bullet(0.5))).toContain("#ffffff");
  });
});
