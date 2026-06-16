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
 * A heat ramp, dark red through to pale gold. It orders by lightness as well as by hue, so
 * it survives being read by someone who cannot separate red from green, and it is warm
 * throughout rather than a cool accent sitting on a warm page.
 */
export const RAMP: readonly Band[] = [
  { floor: mbps(1000), colour: "#fde68a", name: "gigabit" },
  { floor: mbps(300), colour: "#fbbf24", name: "fast" },
  { floor: mbps(100), colour: "#f59e0b", name: "enough" },
  { floor: mbps(30), colour: "#ea580c", name: "slow" },
  { floor: mbps(0), colour: "#b91c1c", name: "poor" },
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

/** The accent everything else is lit by: one light source, from below, and warm. */
export const ACCENT = "#f59e0b";
