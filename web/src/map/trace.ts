/**
 * The light that runs along a street.
 *
 * A search answers with one street, and saying which one in a panel is not the same as
 * showing it: the reader has to find it on the map themselves. Lighting the whole street
 * says where it is but not which way it runs, and a street lit end to end competes with the
 * coverage colour underneath it — the thing the map is actually for.
 *
 * So a short bright window travels the length of it and starts again. It reads as a
 * pointer rather than as a second coverage layer, it shows the extent by moving over it,
 * and because it is only ever lighting a fraction of the line at once, the colour beneath
 * stays legible.
 */

import type { Geometry } from "geojson";
import type { ExpressionSpecification, LayerSpecification } from "maplibre-gl";


export const TRACE = "trace";

/** How much of the street is lit at once. */
const WINDOW = 0.09;

/** How long one pass takes, in milliseconds. Slow: it is a pointer, not a loading bar. */
export const PASS_MS = 4200;

/** The hair's width that keeps two stops from becoming one. */
const STEP = 1e-6;

/** How much of the pass is spent arriving and leaving. */
const FADE = 0.22;

function clamp(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/** Ease in and out, so the light has no corners in it. */
function smooth(t: number): number {
  return t * t * (3 - 2 * t);
}

function white(alpha: number): string {
  return `rgba(255,255,255,${alpha.toFixed(4)})`;
}

/**
 * The gradient for one moment of the pass.
 *
 * `line-gradient` wants stops that ascend and stay inside the line, so the window is
 * clamped at both ends rather than wrapped: the light leaves by the far end and comes back
 * in at the near one. Stops that collide after clamping are dropped, because a repeated
 * stop makes the whole expression invalid and an invalid expression takes the style with it.
 *
 * Everything that varies is alpha, never the number of stops. Switching the light off by
 * removing its stop changes the shape of the expression between one frame and the next, and
 * that is a blink rather than an ending — so it dims to nothing instead, and the clamped
 * stops are free to collapse on top of each other once there is nothing left to see.
 */
export function bullet(progress: number, strength = 1): ExpressionSpecification {
  // The pass starts before the street and ends after it, so the light enters and leaves
  // rather than appearing already halfway along.
  const at = progress * (1 + 2 * WINDOW) - WINDOW;
  // Brightest well inside the line, nothing at all by the time it reaches either end.
  const peak = strength * smooth(clamp(Math.min(at, 1 - at) / FADE));

  const wanted: [number, string][] = [
    [0, white(0)],
    [clamp(at - WINDOW), white(0)],
    [clamp(at - WINDOW * 0.45), white(peak * 0.42)],
    [clamp(at), white(peak)],
    [clamp(at + WINDOW * 0.45), white(peak * 0.42)],
    [clamp(at + WINDOW), white(0)],
    [1, white(0)],
  ];

  // Nudged apart rather than dropped. Dropping a collided stop changes how many stops the
  // expression has from one frame to the next, and the frame that gains one is a visible
  // step however faint the colour on it; a hair's width between two stops is not.
  const places = wanted.map(([stop]) => stop);
  for (let at = 1; at < places.length; at++) {
    places[at] = Math.max(places[at] ?? 0, (places[at - 1] ?? 0) + STEP);
  }
  places[places.length - 1] = Math.min(places[places.length - 1] ?? 1, 1);
  for (let at = places.length - 1; at > 0; at--) {
    places[at - 1] = Math.min(places[at - 1] ?? 0, (places[at] ?? 1) - STEP);
  }

  const stops = wanted.flatMap(([, colour], at) => [places[at] ?? 0, colour]);
  return ["interpolate", ["linear"], ["line-progress"], ...stops] as ExpressionSpecification;
}

/** The dimmer, wider copy under the light, which is most of what makes it read as bright. */
export const GLOW = `${TRACE}-glow`;
/** How bright the blurred copy gets against the crisp one. */
const GLOW_PEAK = 0.5;

/**
 * The two layers the light is made of.
 *
 * The same shape as the selection highlight on the map page, because the reader has already
 * learned what a white glowing street means there: a crisp line at the width a street is
 * drawn, over a wide blurred copy of itself. A single unblurred three-pixel line is
 * technically the same colour and reads as a scratch.
 */
export function traceLayers(progress: number): LayerSpecification[] {
  return [
    {
      id: GLOW,
      type: "line",
      source: TRACE,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-gradient": bullet(progress, GLOW_PEAK),
        "line-blur": 6,
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
        "line-gradient": bullet(progress),
        "line-blur": 0.6,
        "line-width": [
          "interpolate", ["exponential", 1.6], ["zoom"],
          6, 1.6, 12, 3.4, 14, 5, 15, 7, 16, 9.5, 20, 32,
        ],
      },
    },
  ];
}

/** What each layer's gradient should be at this moment. */
export function traceGradients(progress: number): [string, ExpressionSpecification][] {
  return [
    [GLOW, bullet(progress, GLOW_PEAK)],
    [TRACE, bullet(progress)],
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

  const walk = (part: unknown): void => {
    if (!Array.isArray(part)) return;
    if (typeof part[0] === "number" && typeof part[1] === "number") {
      west = Math.min(west, part[0]);
      east = Math.max(east, part[0]);
      south = Math.min(south, part[1]);
      north = Math.max(north, part[1]);
      return;
    }
    for (const deeper of part) walk(deeper);
  };

  if (!("coordinates" in shape)) return null;
  walk(shape.coordinates);
  if (!Number.isFinite(west) || !Number.isFinite(south)) return null;
  return [
    [west, south],
    [east, north],
  ];
}
