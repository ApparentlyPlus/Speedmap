/**
 * The speed ramp, and the units that stop a number being the wrong one.
 *
 * One definition for both pages. A dot beside a search result and a street on the map must
 * agree, or the first teaches a colour the second contradicts.
 */

/**
 * Units in the type, because several of the prototype's bugs were a number in the wrong
 * one and nothing in the code objected. These cost nothing at runtime and refuse to be
 * added together at compile time.
 */
export type Mbps = number & { readonly unit: "Mbps" };
export type EurPerMonth = number & { readonly unit: "EUR/month" };

export const mbps = (n: number): Mbps => n as Mbps;
export const eur = (n: number): EurPerMonth => n as EurPerMonth;

export type Band = {
  readonly floor: Mbps;
  readonly colour: string;
  /** What this band is, in one word, for the legend and for a screen reader. */
  readonly name: string;
};

/**
 * Fastest first, so the first band a speed clears is its band.
 *
 * Seven anchors rather than five, so the gap between a 100 Mbps street and a 300 Mbps one
 * is visible at a glance instead of being two neighbouring greens. It runs warm to cool the
 * way a signal bar does, and the map interpolates between the anchors while the cards step
 * between them — the same colours either way, so the map and the list cannot teach
 * different things about the same speed.
 *
 * It tops out at a gigabit because the register does: its fastest band is open-ended at
 * 1000, so no street can be known to be quicker. A 3 Gbps plan is real and clears this band
 * like any other, and the card for it is the same violet the top of the map is.
 */
export const RAMP: readonly Band[] = [
  { floor: mbps(1000), colour: "#a78bfa", name: "1 Gbps" },
  { floor: mbps(500), colour: "#38bdf8", name: "500 Mbps" },
  { floor: mbps(300), colour: "#4ade80", name: "300 Mbps" },
  { floor: mbps(200), colour: "#b8e04a", name: "200 Mbps" },
  { floor: mbps(100), colour: "#ffc93c", name: "100 Mbps" },
  { floor: mbps(50), colour: "#ff8c42", name: "50 Mbps" },
  { floor: mbps(0), colour: "#f4523b", name: "24 Mbps" },
];

/**
 * Serves this street, filed no speed.
 *
 * Light, and outside the ramp on purpose. Run through the ramp it interpolated down to
 * near-black and made eight operators invisible — and it is the commonest thing the
 * register says, so that was most of the map going missing rather than an edge case.
 */
export const UNFILED = "#9fb3c8";

/** Reaches nothing here. Dark enough to read as absence rather than as a slow street. */
export const UNSERVED = "#2a3038";

export function bandFor(speed: Mbps | null): Band | null {
  if (speed === null) return null;
  return RAMP.find((band) => speed >= band.floor) ?? null;
}

export function colourFor(speed: Mbps | null): string {
  return bandFor(speed)?.colour ?? UNFILED;
}

/** The colour of the place: what is focused, what was chosen, and the lamp under the fold.
 * White, because five operators already own five hues and a sixth would read as a brand. */
export const ACCENT = "#ffffff";

/** Its cooler half, for the second strand of the network behind the page. */
export const FAR = "#6366f1";
