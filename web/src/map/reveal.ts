/**
 * How the map arrives.
 *
 * A coverage map opened cold is a country already covered: forty thousand lit streets, all
 * of them there before the reader has looked at anything. It says nothing about what it is
 * or where it came from.
 *
 * So it arrives instead. A hole opens over Athens and widens until it has taken in the
 * whole country, and the network comes out of it — which is both a nice thing to watch and
 * true, because that is the order the cables were laid in.
 *
 * Done with a veil rather than by revealing the streets themselves: what a street layer can
 * be filtered on is what the tile says about it, and a tile says nothing about how far a
 * street is from Athens. A hole in a sheet over the map needs no such thing, and it takes
 * the basemap with it, so the country builds rather than the roads lighting up on it.
 */

import type { Feature, Polygon } from "geojson";

export const VEIL = "veil";

/** Where the network started, and where it opens from. */
export const ORIGIN: [number, number] = [23.7275, 37.9838];

/** How long the opening runs. Long enough to watch, short enough to sit through once. */
export const OPEN_MS = 5200;

/**
 * How far the hole has to reach, in degrees of latitude, to have taken in the country.
 *
 * Kastellorizo is the far corner, about six degrees of longitude east of Athens, and the
 * hole is drawn wider than it is tall by the same ratio a degree of longitude is short —
 * so five covers it and six leaves margin for the sea around it.
 */
export const REACH = 6;

/** The corners of the world, wound so the hole inside them reads as a hole. */
const WORLD: readonly [number, number][] = [
  [-180, -85],
  [180, -85],
  [180, 85],
  [-180, 85],
];

/** Enough sides that the edge of the hole is a curve rather than a decision. */
const SIDES = 96;

/**
 * The sheet over the map, with a hole of the given radius over Athens.
 *
 * The radius is in degrees of latitude and the hole is drawn wider than it is tall, because
 * a degree of longitude in Greece is about four fifths of a degree of latitude — a circle
 * in degrees is an egg on the ground.
 */
export function veilAt(radius: number): Feature<Polygon> {
  const lift = Math.cos(ORIGIN[1] * (Math.PI / 180));
  const hole: [number, number][] = [];
  for (let side = 0; side <= SIDES; side++) {
    const turn = (side / SIDES) * Math.PI * 2;
    hole.push([
      ORIGIN[0] + (Math.cos(turn) * radius) / lift,
      ORIGIN[1] + Math.sin(turn) * radius,
    ]);
  }

  return {
    type: "Feature",
    properties: {},
    geometry: {
      type: "Polygon",
      // Outer ring first, then the hole. A ring wound the other way is what makes it one.
      coordinates: [[...WORLD, WORLD[0] as [number, number]], hole],
    },
  };
}

/**
 * How wide the hole is, and how solid the sheet, at one moment of the opening.
 *
 * The hole runs ahead of the fade: it has taken in the country by four fifths of the way
 * through, and what is left is the last of the sheet going. Otherwise the opening ends with
 * a ring still travelling over Thrace, which reads as something unfinished rather than as
 * something arrived.
 */
export function openingAt(progress: number): { radius: number; cover: number } {
  // Slow away from Athens, quick across the middle of the country, easing off as it takes
  // in the last of the islands. An ease-out here put the whole country on the screen in the
  // first fifth of the opening and left four seconds of nothing happening.
  const reached = Math.min(1, Math.max(0, progress / 0.8));
  const eased = reached * reached * (3 - 2 * reached);
  return {
    radius: eased * REACH,
    cover: 1 - Math.min(1, Math.max(0, (progress - 0.8) / 0.2)),
  };
}
