import { describe, expect, it } from "vitest";

import { extentOf, focusOf, momentOf, pathOf, sliceOf } from "./trace";

/** A street drawn in two pieces with a gap between them, which is the normal case. */
const BROKEN = pathOf({
  type: "MultiLineString",
  coordinates: [
    [
      [0, 0],
      [0, 1],
    ],
    [
      [0, 2],
      [0, 3],
    ],
  ],
});

const STRAIGHT = pathOf({
  type: "LineString",
  coordinates: [
    [0, 0],
    [0, 4],
  ],
});

describe("measuring a street", () => {
  it("counts every piece it is drawn in", () => {
    expect(BROKEN?.parts).toHaveLength(2);
    // Two equal pieces: the second starts halfway through the street's length.
    expect(BROKEN?.starts[1]).toBeCloseTo(0.5);
  });

  it("says nothing about a shape with no line in it", () => {
    expect(pathOf({ type: "Point", coordinates: [0, 0] })).toBeNull();
  });
});

describe("the light that runs along a street", () => {
  it("is one light, not one per piece", () => {
    // The bug this replaces: a gradient restarts on every line of a multi-line street, so
    // a road through six junctions lit six lights at once.
    for (let step = 0; step <= 200; step++) {
      const { lines } = momentOf(BROKEN!, step / 200);
      // At most two, and only while straddling the gap between the two pieces.
      expect(lines.length).toBeLessThanOrEqual(2);
    }
  });

  it("never draws the gap between two pieces", () => {
    // Everything drawn has to lie on the street: nothing may appear between y=1 and y=2.
    for (let step = 0; step <= 200; step++) {
      for (const line of momentOf(BROKEN!, step / 200).lines) {
        for (const point of line) {
          const y = point[1] ?? 0;
          expect(y <= 1.0001 || y >= 1.9999).toBe(true);
        }
      }
    }
  });

  it("travels from one end to the other", () => {
    const low = sliceOf(STRAIGHT!, 0, 0.1).flat();
    const high = sliceOf(STRAIGHT!, 0.9, 1).flat();
    expect(Math.max(...low.map((p) => p[1] ?? 0))).toBeLessThan(1);
    expect(Math.min(...high.map((p) => p[1] ?? 0))).toBeGreaterThan(3);
  });

  it("comes back on at the start as it leaves the end", () => {
    // Early in the pass the light straddles the join: part of it is at the beginning of
    // the street and the rest has not finished leaving the end.
    const straddling = momentOf(STRAIGHT!, 0.02).lines.flat().map((point) => point[1] ?? 0);
    expect(Math.min(...straddling)).toBeLessThan(0.5);
    expect(Math.max(...straddling)).toBeGreaterThan(3.5);
  });

  it("is always the same length of street, wherever it is", () => {
    // Nothing is lost at the join, so the light neither shrinks into the end of the
    // street nor grows out of the start of it.
    const length = (progress: number): number =>
      momentOf(STRAIGHT!, progress)
        .lines.flatMap((line) =>
          line.slice(1).map((point, at) => Math.abs((point[1] ?? 0) - (line[at]?.[1] ?? 0))),
        )
        .reduce((all, one) => all + one, 0);

    for (let step = 0; step <= 200; step++) {
      expect(length(step / 200)).toBeCloseTo(length(0.5), 5);
    }
  });
});

describe("the box a street occupies", () => {
  it("covers every part of a street drawn in pieces", () => {
    expect(
      extentOf({
        type: "MultiLineString",
        coordinates: [
          [
            [23.0, 37.9],
            [23.1, 38.0],
          ],
          [
            [22.8, 38.2],
            [23.3, 37.7],
          ],
        ],
      }),
    ).toEqual([
      [22.8, 37.7],
      [23.3, 38.2],
    ]);
  });

  it("says nothing rather than an empty box when there is no line", () => {
    expect(extentOf({ type: "GeometryCollection", geometries: [] })).toBeNull();
  });
});

describe("the box worth pointing a camera at", () => {
  it("frames the longest road of the name, not all of them", () => {
    // Μακεδονίας in Κατερίνη is nine unconnected stretches over thirteen kilometres.
    // Framing every one of them frames the town and shows the street to nobody.
    const found = focusOf({
      type: "MultiLineString",
      coordinates: [
        [
          [22.45, 40.27],
          [22.46, 40.27],
        ],
        [
          [22.6, 40.27],
          [22.6001, 40.2701],
        ],
      ],
    });
    expect(found).not.toBeNull();
    // The long western stretch, with nothing of the far eastern scrap in the frame.
    expect(found![1][0]).toBeLessThan(22.5);
  });

  it("frames a street drawn in one piece as itself", () => {
    expect(
      focusOf({
        type: "LineString",
        coordinates: [
          [23.0, 37.9],
          [23.1, 38.0],
        ],
      }),
    ).toEqual([
      [23.0, 37.9],
      [23.1, 38.0],
    ]);
  });
});
