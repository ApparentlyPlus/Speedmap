/** The speed ramp and its units, defined once: a search dot and a street must agree. */

/** Units in the type. Free at runtime, and they refuse to be added together. */
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
 * Fastest first, so the first band a speed clears is its band. The fast end is picked for
 * separation rather than ranked by hue: those are the bands people choose between.
 */
export const RAMP: readonly Band[] = [
  { floor: mbps(1000), colour: "#a78bfa", name: "1 Gbps" },
  { floor: mbps(500), colour: "#7b8cf5", name: "500 Mbps" },
  { floor: mbps(300), colour: "#4da3ff", name: "300 Mbps" },
  { floor: mbps(200), colour: "#45c8e0", name: "200 Mbps" },
  { floor: mbps(100), colour: "#ffc93c", name: "100 Mbps" },
  { floor: mbps(50), colour: "#ff8c42", name: "50 Mbps" },
  { floor: mbps(0), colour: "#f4523b", name: "24 Mbps" },
];

/** Reaches here, filed no speed. Outside the ramp: through it, this goes near-black. */
export const UNFILED = "#9fb3c8";

/** Reaches nothing here. Dark enough to read as absence rather than as a slow street. */
export const UNSERVED = "#2a3038";

/**
 * The whole set a street can be retailed at, so the legend can drop bands coverage cannot paint.
 * technology.sold_mbps is the source of truth. A test fails if these drift apart.
 */
const RETAILED: readonly Mbps[] = [mbps(24), mbps(50), mbps(100), mbps(1000)];

/** The bands a view can actually paint, fastest first, for its legend. */
export function bandsPainted(continuous: boolean): readonly Band[] {
  if (continuous) return RAMP;
  const reached = new Set(RETAILED.map((speed) => bandFor(speed)?.name));
  return RAMP.filter((band) => reached.has(band.name));
}

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

/**
 * Fiber share per municipality, nought to one. One hue getting lighter, not a second rainbow:
 * the ramp already taught the reader that hue means megabits.
 */
export const SHARE: readonly (readonly [number, string])[] = [
  [0, "#161d26"],
  [0.15, "#1c2f3f"],
  [0.35, "#22485c"],
  [0.6, "#2a6b7d"],
  [0.85, "#3f96a0"],
  [1, "#67c7c4"],
];
