/**
 * The result map in a real browser. Only a browser shows whether the camera travels or
 * jumps: a cut and a 1.6 s ease end on the same frame and differ only on the way there.
 */

import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const WHERE = "http://127.0.0.1:5173";

/** A street with several filings, so the result page has something to draw. */
const ASKED = "Ermou";

/** Camera tilt once it's framing a street. */
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
  /** Every camera sampled between the click and the street showing. */
  let seen: { ms: number; zoom: number; pitch: number }[] = [];

  beforeAll(async () => {
    browser = await chromium.launch({
      args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
    });
    page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`${WHERE}/`, { waitUntil: "load" });
    await page.getByRole("combobox").fill(ASKED);

    // Sample on the way down. Where it ends up says nothing: a jump, a smooth fall and a
    // stuttering one all finish on the same frame. Start before the click and sample faster
    // than an animation can hide in.
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
    // ten zoom levels of descent: opening near the street lost all sense of where it was
    const zooms = seen.map((at) => at.zoom);
    expect(Math.min(...zooms)).toBeLessThan(8);
    expect(Math.max(...zooms)).toBeGreaterThan(14);
  });

  it("falls the whole way without a jump in it", async () => {
    /**
     * Jagged, measured as a rate. The first version compared consecutive samples and failed
     * on a smooth descent, because samples aren't evenly spaced: software rendering starves
     * the recorder, so 50 ms requests land 150 ms apart and a wide step is a dropped frame.
     * Dividing by elapsed time gives the camera's actual speed.
     *
     * Ten levels over 3.6 s peaks near eight a second. A cut moves all ten in one frame, about
     * a hundred times over this ceiling. The ceiling is loose on purpose: it's there to catch
     * a discontinuity, not to grade the easing curve.
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
    // the tilt comes with the descent. cutting to it was the jolt at the end
    expect(Math.max(...rates.map((r) => r.pitch))).toBeLessThan(0.1);
  });

  it("takes long enough to be followed", async () => {
    // a descent you can't watch is a jump with extra steps
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
