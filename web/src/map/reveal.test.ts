import { describe, expect, it } from "vitest";

import { OPEN_MS, doneAt, frontAt, reachAt } from "./reveal";

describe("the front the coverage arrives on", () => {
  it("starts at Athens and ends past the furthest street", () => {
    expect(reachAt(0)).toBe(0);
    // Kastellorizo is about 570 km out; the front has to clear it and its own soft edge.
    expect(reachAt(1)).toBeGreaterThan(600);
  });

  it("only ever moves outward", () => {
    let last = -1;
    for (let step = 0; step <= 200; step++) {
      const now = reachAt(step / 200);
      expect(now).toBeGreaterThanOrEqual(last);
      last = now;
    }
  });

  it("is over when it is over", () => {
    expect(doneAt(0.99)).toBe(false);
    expect(doneAt(1)).toBe(true);
  });
});

describe("how lit a street is", () => {
  it("multiplies what the layer already was rather than replacing it", () => {
    // The ramp, the zoom curve and the halo's own faintness all still apply: the opening
    // dims the map it is arriving on, and the last frame is the map that was there.
    expect(JSON.stringify(frontAt(100, 0.42))).toContain("0.42");
    expect((frontAt(100, 0.42) as unknown[])[0]).toBe("*");
  });

  it("reads the distance off the street rather than asking the tile", () => {
    expect(JSON.stringify(frontAt(100, 1))).toContain('["get","far"]');
  });

  it("runs the whole opening inside one sensible stretch of time", () => {
    expect(OPEN_MS).toBeGreaterThan(2000);
    expect(OPEN_MS).toBeLessThan(9000);
  });
});
