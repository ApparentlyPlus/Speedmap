/** Which picture an offer gets. */

import { describe, expect, it } from "vitest";

import { MODES } from "./house3d";
import { modeOf } from "./mode";

describe("the picture an offer gets", () => {
  it("draws copper and fiber the same way", () => {
    // Different things to sell, the same thing to look at: both arrive along a line in the
    // ground, and that is what the drawing is about.
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
    // A family the catalogue grows later should draw something plausible, not crash the
    // scene or leave an empty canvas where the address ought to be.
    expect(modeOf("something new")).toBe("landline");
  });
});
