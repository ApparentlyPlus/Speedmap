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

import type { ExpressionSpecification, LayerSpecification } from "maplibre-gl";

import { ACCENT } from "../tokens";

export const TRACE = "trace";

/** How much of the street is lit at once. */
const WINDOW = 0.09;

/** How long one pass takes, in milliseconds. Slow: it is a pointer, not a loading bar. */
export const PASS_MS = 4200;

const CLEAR = "rgba(255,255,255,0)";

function clamp(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/**
 * The gradient for one moment of the pass.
 *
 * `line-gradient` wants stops that ascend and stay inside the line, so the window is
 * clamped at both ends rather than wrapped: the light leaves by the far end and comes back
 * in at the near one. Stops that collide after clamping are dropped, because a repeated
 * stop makes the whole expression invalid and an invalid expression takes the style with it.
 */
export function bullet(progress: number, peak: string = ACCENT): ExpressionSpecification {
  // The pass starts before the street and ends after it, so the light enters and leaves
  // rather than appearing already halfway along.
  const at = progress * (1 + 2 * WINDOW) - WINDOW;
  // Off the line entirely at either extreme. Clamping the centre alone would pin the light
  // to whichever end it had run past and leave it burning there.
  const lit = at > 0 && at < 1;
  const wanted: [number, string][] = [
    [0, CLEAR],
    [clamp(at - WINDOW), CLEAR],
    ...(lit ? ([[at, peak]] as [number, string][]) : []),
    [clamp(at + WINDOW), CLEAR],
    [1, CLEAR],
  ];

  const stops: (number | string)[] = [];
  let last = -1;
  for (const [stop, colour] of wanted) {
    if (stop <= last) continue;
    stops.push(stop, colour);
    last = stop;
  }

  return ["interpolate", ["linear"], ["line-progress"], ...stops] as ExpressionSpecification;
}

/** The dimmer, wider copy under the light, which is most of what makes it read as bright. */
export const GLOW = `${TRACE}-glow`;
const GLOW_PEAK = "rgba(255,255,255,0.5)";

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
