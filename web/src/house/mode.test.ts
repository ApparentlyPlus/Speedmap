/** Which picture an offer gets. */

import { describe, expect, it } from "vitest";

import { MODES } from "./house3d";
import { modeOf } from "./mode";

describe("the picture an offer gets", () => {
  it("draws copper and fiber the same way", () => {
    // different products, same picture: both arrive along a line in the ground
    expect(modeOf("fiber")).toBe("landline");
    expect(modeOf("copper")).toBe("landline");
  });

  it("gives wireless and satellite their own", () => {
    expect(modeOf("wireless")).toBe("cellular");
    expect(modeOf("satellite")).toBe("satellite");
  });

  it("never invents a mode the scene does not have", () => {
    for (const family of ["fiber", "copper", "coax", "wireless", "satellite", "who knows"]) {
      expect(MODES).toContain(modeOf(family));
    }
  });

  it("falls back to the commonest rather than to nothing", () => {
    // a family the catalogue adds later should still draw something, not crash the scene or
    // leave an empty canvas
    expect(modeOf("something new")).toBe("landline");
  });
});
