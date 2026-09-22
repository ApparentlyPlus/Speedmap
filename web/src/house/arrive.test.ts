/**
 * The result map, in a real browser. It is the only place that can say whether the camera
 * arrives at the street or travels to it, because a jump and a 1.6 second ease reach the
 * same frame and differ only in what the reader watches on the way.
 */

import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const WHERE = "http://127.0.0.1:5173";

/** A street with several filings on it, so the result page has something to draw. */
const ASKED = "Ermou";

/** The lean the camera settles at once it is framing a street. */
const TILT = 42;

async function up(): Promise<boolean> {
  try {
    const answer = await fetch(`${WHERE}/`, { signal: AbortSignal.timeout(1500) });
    return answer.ok;
  } catch {
    return false;
  }
}

const running = await up();

describe.skipIf(!running)("arriving at a street", () => {
  let browser: Browser;
  let page: Page;
  /** Every camera the recorder caught between the click and the street being on screen. */
  let seen: { ms: number; zoom: number; pitch: number }[] = [];

  beforeAll(async () => {
    browser = await chromium.launch({
      args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
    });
    page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`${WHERE}/`, { waitUntil: "load" });
    await page.getByRole("combobox").fill(ASKED);

    /**
     * Record the camera on the way, not once it has settled.
     *
     * Where it ends up says nothing about how it got there: a jump, a smooth fall and a
     * stuttering one all finish on the same frame. So the recorder starts before the click
     * and samples faster than any animation can hide in.
     */
    await page.evaluate(() => {
      const held = window as unknown as {
        seen: { ms: number; zoom: number; pitch: number }[];
        recorder: number;
      };
      held.seen = [];
      const began = performance.now();
      held.recorder = window.setInterval(() => {
        if (window.anchored !== undefined) {
          held.seen.push({
            ms: Math.round(performance.now() - began),
            zoom: window.anchored.getZoom(),
            pitch: window.anchored.getPitch(),
          });
        }
      }, 60);
    });

    await page.getByRole("option").first().click();
    await page.waitForTimeout(9000);

    seen = await page.evaluate(() => {
      const held = window as unknown as {
        seen: { ms: number; zoom: number; pitch: number }[];
        recorder: number;
      };
      window.clearInterval(held.recorder);
      return held.seen;
    });
  }, 90_000);

  afterAll(async () => {
    await browser?.close();
  });

  it("frames the street rather than the door", async () => {
    const pitch = await page.evaluate(() => Math.round(window.anchored.getPitch()));
    expect(pitch).toBe(TILT);
  });

  it("starts on the country and ends on the street", async () => {
    // Ten zoom levels of descent. Opening anywhere near the street is the version that
    // showed a road with no sense of where in Greece it was.
    const zooms = seen.map((at) => at.zoom);
    expect(Math.min(...zooms)).toBeLessThan(8);
    expect(Math.max(...zooms)).toBeGreaterThan(14);
  });

  it("falls the whole way without a jump in it", async () => {
    /**
     * What "jagged" meant, measured as a rate rather than as a step.
     *
     * The first version of this counted the zoom change between one sample and the next
     * and failed on a perfectly smooth descent, because the samples are not evenly
     * spaced: software rendering starves the recorder, so 50 ms of asking lands 150 ms
     * apart under load and a wide step is a dropped frame rather than a lurch. Dividing
     * by the time actually elapsed says how fast the camera moved, which is the thing
     * that has to stay bounded.
     *
     * A fall of ten zoom levels over 3.6 seconds peaks near eight levels a second. A cut
     * straight to the frame moves all ten inside one frame, which is two orders of
     * magnitude above this ceiling: the ceiling is generous on purpose, because it is
     * placed to catch a discontinuity and not to police the easing curve.
     */
    const moving = seen.filter((at) => at.zoom > 6.05);
    const rates = moving.slice(1).map((at, i) => {
      const before = moving[i];
      const elapsed = Math.max(at.ms - (before?.ms ?? 0), 1);
      return {
        zoom: Math.abs(at.zoom - (before?.zoom ?? 0)) / elapsed,
        pitch: Math.abs(at.pitch - (before?.pitch ?? 0)) / elapsed,
      };
    });
    expect(rates.length).toBeGreaterThan(8);
    expect(Math.max(...rates.map((r) => r.zoom))).toBeLessThan(0.03);
    // The lean arrives with the descent. Cutting to it was the jolt at the end.
    expect(Math.max(...rates.map((r) => r.pitch))).toBeLessThan(0.1);
  });

  it("takes long enough to be followed", async () => {
    // A descent the reader cannot watch is a jump with extra steps.
    const moving = seen.filter((at) => at.zoom > 6.05 && at.zoom < 14);
    const first = moving[0];
    const last = moving[moving.length - 1];
    expect(first).toBeDefined();
    expect(last).toBeDefined();
    expect((last?.ms ?? 0) - (first?.ms ?? 0)).toBeGreaterThan(1200);
  });

  it("lights the street it was asked for", async () => {
    const lit = await page.evaluate(
      () => window.anchored.getLayer("trace") !== undefined,
    );
    expect(lit).toBe(true);
  });
});
