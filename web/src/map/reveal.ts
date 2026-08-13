/**
 * How the coverage arrives.
 *
 * The map opens as a map: dark ground, the roads a city actually has, nothing claimed
 * about any of them. Then the network comes out of Athens and runs to the edges of the
 * country along the streets themselves, which is both a nice thing to watch and the order
 * the cables were laid in.
 *
 * Only the coverage moves. The basemap is there from the first frame, so what the reader
 * watches is the answer arriving on a map rather than a map being assembled.
 *
 * It works by painting, not by filtering. A filter change re-lays out every tile on screen,
 * which at eighty thousand streets is a stutter per frame; opacity is a paint property and
 * costs a uniform. And it asks the feature how far out it is rather than asking the tile,
 * because a tile cannot answer that — the distance is carried on every street by the build.
 */

import type { DataDrivenPropertyValueSpecification } from "maplibre-gl";

/** How long the opening runs. Long enough to watch, short enough to sit through once. */
export const OPEN_MS = 4600;

/** Kilometres from Athens to the furthest street in the country, with room to spare. */
const REACH = 620;

/**
 * How wide the band is where a street is arriving rather than arrived, in kilometres.
 *
 * Without it the network has a hard rim running over the country like a scanner. With it
 * the edge is a front the streets come up through, which is what reads as spreading.
 */
const EDGE = 90;

/**
 * How lit a street is, given how far out the front has reached.
 *
 * Multiplies whatever opacity the layer already had: the ramp, the zoom curve and the
 * halo's own faintness all still apply, so the opening dims the map rather than repainting
 * it, and the last frame is exactly the map that was there before.
 */
export function frontAt(
  reached: number,
  settled: DataDrivenPropertyValueSpecification<number>,
): DataDrivenPropertyValueSpecification<number> {
  return [
    "*",
    settled,
    [
      "interpolate",
      ["linear"],
      ["-", reached, ["to-number", ["get", "far"], 0]],
      0,
      0,
      EDGE,
      1,
    ],
  ] as DataDrivenPropertyValueSpecification<number>;
}

/** How far the front has reached, in kilometres, at one moment of the opening. */
export function reachAt(progress: number): number {
  const along = Math.min(1, Math.max(0, progress));
  // At a steady rate, with the corners taken off both ends. Anything front-loaded puts
  // most of the country on the screen inside the first second and leaves the rest of the
  // opening to the empty sea past Rhodes, which is not a thing worth watching.
  const eased = along < 0.5 ? 2 * along * along : 1 - (-2 * along + 2) ** 2 / 2;
  return eased * (REACH + EDGE);
}

/** Whether the opening has anything left to show. */
export function doneAt(progress: number): boolean {
  return progress >= 1;
}
