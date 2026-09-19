/**
 * A short bright window travelling the length of a street, to point at it without burying the
 * coverage colour underneath.
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
 * Length in a flat plane, which is what a highlight needs. Degrees of longitude are shorter than
 * degrees of latitude everywhere but the equator, so the x side is scaled by the latitude.
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

/** The piece of the street between two points of its length. */
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

/** Where the light is at one moment of the pass. It wraps rather than fades. */
export function momentOf(path: Path, progress: number): { lines: Position[][] } {
  const head = clamp(progress);
  const tail = head - WINDOW;
  if (tail >= 0) return { lines: sliceOf(path, tail, head) };
  // Straddling the join: the front of the light is at the start of the street and the
  // back of it has not left the end yet.
  return { lines: [...sliceOf(path, 0, head), ...sliceOf(path, 1 + tail, 1)] };
}

/** The two layers the light is made of. */
export function traceLayers(): LayerSpecification[] {
  return [
    {
      id: GLOW,
      type: "line",
      source: TRACE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ACCENT,
        "line-blur": 3,
        "line-opacity": 0,
        // Close around the line rather than a halo over the neighbourhood. Its job is to
        // stop the mark looking cut out, not to be the mark.
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"], 10, 3, 13, 5, 16, 11, 20, 34,
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
        // Hard edged. The blur was making a narrow mark read as a wide soft one, which is
        // the difference between a highlighter and a smear.
        "line-blur": 0,
        "line-opacity": 0,
        // Narrower than the street it is marking, at every zoom, about three fifths of it.
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          6, 0.3, 12, 0.8, 14, 1.6, 15, 2.7, 16, 4.2, 20, 15,
        ],
      },
    },
  ];
}

/** How bright each layer is. Constant: the light never dims, it only moves. Low. */
export function traceOpacity(): [string, number][] {
  return [
    [GLOW, 0.14],
    [TRACE, 0.62],
  ];
}

/** The box worth pointing a camera at. */
export function focusOf(shape: Geometry): [[number, number], [number, number]] | null {
  const path = pathOf(shape);
  if (path === null) return null;

  let best: readonly Position[] | null = null;
  let longest = -1;
  path.parts.forEach((part, index) => {
    const span = (path.starts[index + 1] ?? 1) - (path.starts[index] ?? 0);
    if (span > longest) {
      longest = span;
      best = part;
    }
  });
  if (best === null) return null;
  return extentOf({ type: "LineString", coordinates: best as Position[] });
}

/** A box that holds the street whichever way the camera is pointing. */
export function turnable(
  extent: [[number, number], [number, number]],
): [[number, number], [number, number]] {
  const [[west, south], [east, north]] = extent;
  const midLon = (west + east) / 2;
  const midLat = (south + north) / 2;
  const lift = Math.cos(midLat * (Math.PI / 180)) || 1;
  const half = Math.max((east - west) * lift, north - south) / 2;
  return [
    [midLon - half / lift, midLat - half],
    [midLon + half / lift, midLat + half],
  ];
}

/** The box a street occupies. */
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
