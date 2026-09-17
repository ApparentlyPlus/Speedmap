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
 * is visible at a glance instead of being two neighbouring greens. The slow end runs red to
 * yellow the way a signal bar does; the fast end is picked for separation instead, because
 * the three bands people actually choose between are up there and they have to be told
 * apart at a glance rather than ranked by hue.
 *
 * The map interpolates between the anchors while the cards step between them — the same
 * colours either way, so the map and the list cannot teach different things about one
 * speed.
 *
 * It tops out at a gigabit because the register does: its fastest band is open-ended at
 * 1000, so no street can be known to be quicker. A 3 Gbps plan is real and clears this band
 * like any other, and the card for it is the same purple the top of the map is.
 *
 * WHERE THE WARM END STOPS IS NOT ARBITRARY. It stops at 100, and 100 is exactly where
 * copper stops: vectored VDSL retails at 100 and nothing on a phone line goes past it, while
 * fibre is filed at a gigabit and nothing else reaches that. So the hue turning cool between
 * 100 and 200 is the same boundary as the line under the street changing from copper to
 * fibre — the map reads warm for copper and cool for fibre without the colour ever having to
 * be told which is which.
 *
 * That is why 100 is yellow rather than blue. A vectored VDSL street at 100 Mbps is
 * qualitatively a different thing from fibre, however close the two numbers look, and giving
 * it the colour fibre wears would say they were the same.
 *
 * The consequence to know about: this works because copper tops out at 100 and fibre starts
 * at 1000, with nothing in between. If a technology ever lands between them — DOCSIS is
 * seeded at 300 and Greece files no coax today — it takes a cool colour, which is right for
 * cable but means the warm/cool split is a convention the data currently upholds rather
 * than something the ramp enforces.
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

/**
 * What a street can be retailed at, which is what the coverage map can paint.
 *
 * These are technology.sold_mbps for the lines the street map draws — ADSL 24, VDSL 50,
 * vectored VDSL 100, fibre 1000 — and they are the whole reachable set: a filing can only
 * cap a figure below its line's retail speed, never lift it above, so nothing can land in a
 * band higher than one of these.
 *
 * Kept here so the legend can list the bands the view is able to produce instead of all
 * seven. Three of the ramp's anchors — 200, 300 and 500 — cannot occur under coverage at
 * all, and a legend row showing a colour the map will never paint is a row that teaches the
 * reader something untrue.
 *
 * The source of truth is technology.sold_mbps in the database, not this list.
 * tests/test_street_reach.py::test_only_four_figures_are_possible reads that column and
 * fails if the two drift, which is what stops this from quietly going stale.
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
 * How much of a municipality fibre reaches, nought to one.
 *
 * A share, not a speed, and drawn so nobody can mistake it for one. The ramp above runs the
 * whole spectrum — red, orange, yellow, lime, cyan, green, violet — so any second scale
 * built out of hue would be read as a speed by a reader who has just learned that colours
 * mean megabits here. This is one hue getting lighter, which is the shape of "more of it"
 * rather than "faster", and it sits in the blues the land is already in so a municipality
 * with none of it reads as unlit ground rather than as a colour.
 *
 * Fibre rather than the fastest anything: the fastest anything is 5G, which reaches nearly
 * every address in the country, and a map of it is Greece in one colour. Fibre is what
 * varies — 124 municipalities have none at all and 77 have it almost everywhere.
 */
export const SHARE: readonly (readonly [number, string])[] = [
  [0, "#161d26"],
  [0.15, "#1c2f3f"],
  [0.35, "#22485c"],
  [0.6, "#2a6b7d"],
  [0.85, "#3f96a0"],
  [1, "#67c7c4"],
];
