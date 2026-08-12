/**
 * The light that runs along a street.
 *
 * A search answers with one street, and saying which one in a panel is not the same as
 * showing it: the reader has to find it on the map themselves. Lighting the whole street
 * says where it is but not which way it runs, and a street lit end to end competes with the
 * coverage colour underneath it — the thing the map is actually for.
 *
 * So a short bright window travels the length of it and starts again.
 *
 * It is drawn by cutting the piece out of the street and handing that to the map, rather
 * than by colouring the whole street with a gradient that is transparent except where the
 * light is. The gradient way reads `line-progress`, which runs nought to one along each
 * line separately — and a street is rarely one line. It is the handful of ways OSM drew it
 * in, so every one of them lit its own light and a road through six junctions had six.
 */

import type { Geometry, Position } from "geojson";
import type { LayerSpecification } from "maplibre-gl";

import { ACCENT } from "../tokens";

export const TRACE = "trace";
export const GLOW = `${TRACE}-glow`;

/** How much of the street is lit at once. */
const WINDOW = 0.09;

/** How long one pass takes, in milliseconds. Slow: it is a pointer, not a loading bar. */
export const PASS_MS = 4200;

/** A street, flattened into the pieces it is drawn in and measured end to end. */
export type Path = {
  readonly parts: readonly (readonly Position[])[];
  /** Where each part begins, as a fraction of the whole street's length. */
  readonly starts: readonly number[];
  readonly total: number;
};

function clamp(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/**
 * Length in a flat plane, which is what a highlight needs.
 *
 * Degrees of longitude are shorter than degrees of latitude everywhere but the equator, so
 * the x side is scaled by the latitude. Not a geodesic: this decides how fast a light
 * crosses a street, and a street is never long enough for the curve of the earth to show.
 */
function span(from: Position, to: Position): number {
  const lift = Math.cos((((from[1] ?? 0) + (to[1] ?? 0)) / 2) * (Math.PI / 180));
  const x = ((to[0] ?? 0) - (from[0] ?? 0)) * lift;
  const y = (to[1] ?? 0) - (from[1] ?? 0);
  return Math.hypot(x, y);
}

/** Every line in a geometry, whatever shape it arrived in. */
function lines(shape: Geometry): Position[][] {
  if (shape.type === "LineString") return [shape.coordinates];
  if (shape.type === "MultiLineString") return shape.coordinates;
  if (shape.type === "GeometryCollection") return shape.geometries.flatMap(lines);
  return [];
}

export function pathOf(shape: Geometry): Path | null {
  const parts = lines(shape).filter((part) => part.length >= 2);
  if (parts.length === 0) return null;

  const starts: number[] = [];
  let total = 0;
  for (const part of parts) {
    starts.push(total);
    for (let at = 1; at < part.length; at++) {
      total += span(part[at - 1] as Position, part[at] as Position);
    }
  }
  if (total <= 0) return null;
  return { parts, starts: starts.map((begins) => begins / total), total };
}

/**
 * The piece of the street between two points of its length.
 *
 * Comes back as several lines when the window straddles a gap, which is the whole reason
 * the cut is done here: the light crosses from one piece of the street to the next without
 * ever drawing the nothing in between them.
 */
export function sliceOf(path: Path, from: number, to: number): Position[][] {
  const cut: Position[][] = [];

  path.parts.forEach((part, index) => {
    const begins = path.starts[index] ?? 0;
    const ends = path.starts[index + 1] ?? 1;
    if (ends <= from || begins >= to) return;

    const piece: Position[] = [];
    let walked = begins;
    for (let at = 1; at < part.length; at++) {
      const one = part[at - 1] as Position;
      const two = part[at] as Position;
      const step = span(one, two) / path.total;
      const after = walked + step;

      if (after > from && walked < to && step > 0) {
        const head = Math.max(0, (from - walked) / step);
        const tail = Math.min(1, (to - walked) / step);
        if (piece.length === 0) piece.push(between(one, two, head));
        piece.push(between(one, two, tail));
      }
      walked = after;
    }
    if (piece.length >= 2) cut.push(piece);
  });

  return cut;
}

function between(one: Position, two: Position, at: number): Position {
  return [
    (one[0] ?? 0) + ((two[0] ?? 0) - (one[0] ?? 0)) * at,
    (one[1] ?? 0) + ((two[1] ?? 0) - (one[1] ?? 0)) * at,
  ];
}

/**
 * Where the light is at one moment of the pass.
 *
 * It wraps rather than fades. The light runs off the end of the street and the same length
 * of it comes back on at the start, so the pass never stops and never restarts — what
 * leaves by one end is already arriving at the other. Brightness is left alone entirely:
 * dimming at the ends is what you do when the light has nowhere to go.
 */
export function momentOf(path: Path, progress: number): { lines: Position[][] } {
  const head = clamp(progress);
  const tail = head - WINDOW;
  if (tail >= 0) return { lines: sliceOf(path, tail, head) };
  // Straddling the join: the front of the light is at the start of the street and the
  // back of it has not left the end yet.
  return { lines: [...sliceOf(path, 0, head), ...sliceOf(path, 1 + tail, 1)] };
}

/**
 * The two layers the light is made of.
 *
 * The same shape as the selection highlight on the map page, because the reader has already
 * learned what a white glowing street means there: a crisp line at the width a street is
 * drawn, over a wide blurred copy of itself. A single unblurred line is the same colour and
 * reads as a scratch.
 */
export function traceLayers(): LayerSpecification[] {
  return [
    {
      id: GLOW,
      type: "line",
      source: TRACE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ACCENT,
        "line-blur": 6,
        "line-opacity": 0,
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"], 10, 9, 13, 13, 16, 26, 20, 70,
        ],
      },
    },
    {
      id: TRACE,
      type: "line",
      source: TRACE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ACCENT,
        "line-blur": 0.6,
        "line-opacity": 0,
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          6, 1.6, 12, 3.4, 14, 5, 15, 7, 16, 9.5, 20, 32,
        ],
      },
    },
  ];
}

/** How bright each layer is. Constant: the light never dims, it only moves. */
export function traceOpacity(): [string, number][] {
  return [
    [GLOW, 0.5],
    [TRACE, 0.95],
  ];
}

/**
 * The box a street occupies.
 *
 * Read off the shape rather than asked for separately: the camera has to frame the same
 * line the light runs along, and a second source for the extent is a second thing that can
 * disagree with the first.
 */
export function extentOf(shape: Geometry): [[number, number], [number, number]] | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;

  for (const part of lines(shape)) {
    for (const point of part) {
      west = Math.min(west, point[0] ?? 0);
      east = Math.max(east, point[0] ?? 0);
      south = Math.min(south, point[1] ?? 0);
      north = Math.max(north, point[1] ?? 0);
    }
  }
  if (!Number.isFinite(west) || !Number.isFinite(south)) return null;
  return [
    [west, south],
    [east, north],
  ];
}
