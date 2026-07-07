/**
 * Which picture to draw for an offer.
 *
 * The scene has three modes and the catalogue has four families, because copper and fibre
 * are different things to sell and the same thing to look at: both arrive along a line in
 * the ground. Satellite and wireless each get their own, since where the signal comes from
 * is the entire subject of the picture.
 */

import type { Mode } from "./house3d";

const BY_FAMILY: Readonly<Record<string, Mode>> = {
  fibre: "landline",
  copper: "landline",
  coax: "landline",
  wireless: "cellular",
  satellite: "satellite",
};

export function modeOf(family: string): Mode {
  return BY_FAMILY[family] ?? "landline";
}
