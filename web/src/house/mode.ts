/** Which picture to draw for an offer. */

import type { Mode } from "./house3d";

const BY_FAMILY: Readonly<Record<string, Mode>> = {
  fiber: "landline",
  copper: "landline",
  coax: "landline",
  wireless: "cellular",
  satellite: "satellite",
};

export function modeOf(family: string): Mode {
  return BY_FAMILY[family] ?? "landline";
}
