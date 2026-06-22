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
 * The thresholds are the ones the rest of the system already reasons in: a hundred is what
 * a household needs, three hundred is where copper cannot follow, a gigabit is settled.
 *
 * Red, amber, green, blue, violet. The order everyone already knows from a signal. The
 * page's own colour is white and is spent on chrome — what is focused, what was chosen —
 * so the ramp keeps every hue to itself and the two can never be told apart by accident.
 *
 * Five hues rather than a gradient, because the bands are the point. An address is in one
 * of them, and a reader should be able to say which from across a room.
 */
export const RAMP: readonly Band[] = [
  { floor: mbps(1000), colour: "#a855f7", name: "gigabit" },
  { floor: mbps(300), colour: "#3b82f6", name: "fast" },
  { floor: mbps(100), colour: "#22c55e", name: "enough" },
  { floor: mbps(30), colour: "#eab308", name: "slow" },
  { floor: mbps(0), colour: "#ef4444", name: "poor" },
];

/**
 * The colour for a speed nobody has filed.
 *
 * Deliberately not the bottom of the ramp, and deliberately outside its hue: "serves this
 * street, files no speed" is the most common state for six of the eleven operators, and
 * painting it as slow invents a fact.
 */
export const UNFILED = "#3f3f46";

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
