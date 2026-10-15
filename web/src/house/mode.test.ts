
import { describe, expect, it } from "vitest";

import { MODES } from "./house3d";
import { modeOf } from "./mode";

describe("the picture an offer gets", () => {
  it("draws copper and fiber the same way", () => {
    // different products, both come in along a line in the ground
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
    // a family added later still draws something
    expect(modeOf("something new")).toBe("landline");
  });
});
