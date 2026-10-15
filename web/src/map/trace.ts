// a short bright window running along a street, pointing at it without covering its colour

import type { Geometry, Position } from "geojson";
import type { LayerSpecification } from "maplibre-gl";

import { ACCENT } from "../tokens";

export const TRACE = "trace";
export const GLOW = `${TRACE}-glow`;

// share of the street lit at once
const WINDOW = 0.09;

// ms per pass, slow because it's a pointer and not a progress bar
export const PASS_MS = 4200;

export type Path = {
  readonly parts: readonly (readonly Position[])[];
  // where each part starts, as a fraction of the length
  readonly starts: readonly number[];
  readonly total: number;
};

function clamp(n: number): number {
  return Math.min(1, Math.max(0, n));
}

// flat length, x scaled by latitude since a degree of longitude shrinks away from the equator
function span(from: Position, to: Position): number {
  const lift = Math.cos((((from[1] ?? 0) + (to[1] ?? 0)) / 2) * (Math.PI / 180));
  const x = ((to[0] ?? 0) - (from[0] ?? 0)) * lift;
  const y = (to[1] ?? 0) - (from[1] ?? 0);
  return Math.hypot(x, y);
}

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

// where the light is at time t, wraps around and never fades
export function momentOf(path: Path, progress: number): { lines: Position[][] } {
  const head = clamp(progress);
  const tail = head - WINDOW;
  if (tail >= 0) return { lines: sliceOf(path, tail, head) };
  // straddling the join, the front has wrapped while the back's still at the end
  return { lines: [...sliceOf(path, 0, head), ...sliceOf(path, 1 + tail, 1)] };
}

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
        // tight around the line, not the mark itself
        "line-width": ["interpolate", ["exponential", 1.6], ["zoom"], 10, 3, 13, 5, 16, 11, 20, 34],
      },
    },
    {
      id: TRACE,
      type: "line",
      source: TRACE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ACCENT,
        // hard edged, blurred it smears into a wide soft one
        "line-blur": 0,
        "line-opacity": 0,
        // ~3/5 of the street's width at every zoom
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          6, 0.3, 12, 0.8, 14, 1.6, 15, 2.7, 16, 4.2, 20, 15,
        ],
      },
    },
  ];
}

// low and constant
export function traceOpacity(): [string, number][] {
  return [[GLOW, 0.14], [TRACE, 0.62]];
}

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

// holds the street whichever way the camera faces
export function turnable(
  extent: [[number, number], [number, number]],
): [[number, number], [number, number]] {
  const [[west, south], [east, north]] = extent;
  const midLon = (west + east) / 2;
  const midLat = (south + north) / 2;
  const lift = Math.cos(midLat * (Math.PI / 180)) || 1;
  const half = Math.max((east - west) * lift, north - south) / 2;
  return [[midLon - half / lift, midLat - half], [midLon + half / lift, midLat + half]];
}

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
  return [[west, south], [east, north]];
}
