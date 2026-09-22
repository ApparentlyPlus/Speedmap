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
  /** Every lean the camera was caught at between the click and the street being on screen. */
  let seen: number[] = [];

  beforeAll(async () => {
    browser = await chromium.launch({
      args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
    });
    page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    await page.goto(`${WHERE}/`, { waitUntil: "load" });
    await page.getByRole("combobox").fill(ASKED);

    /**
     * Record the lean on the way, not once it has settled.
     *
     * Waiting for the camera to stop and then reading it cannot tell a jump from an ease:
     * both end at the same frame, and the only difference is the second and a half in
     * between. So the recorder starts before the click and samples faster than any
     * animation can hide in.
     */
    await page.evaluate(() => {
      const held = window as unknown as { pitches: number[]; recorder: number };
      held.pitches = [];
      held.recorder = window.setInterval(() => {
        if (window.anchored !== undefined) {
          held.pitches.push(Math.round(window.anchored.getPitch()));
        }
      }, 60);
    });

    await page.getByRole("option").first().click();
    await page.waitForTimeout(9000);

    seen = await page.evaluate(() => {
      const held = window as unknown as { pitches: number[]; recorder: number };
      window.clearInterval(held.recorder);
      return held.pitches;
    });
  }, 90_000);

  afterAll(async () => {
    await browser?.close();
  });

  it("frames the street rather than the door", async () => {
    const pitch = await page.evaluate(() => Math.round(window.anchored.getPitch()));
    expect(pitch).toBe(TILT);
  });

  it("arrives at the lean rather than tilting into it", async () => {
    /**
     * An ease to the frame walks the pitch through every angle on the way, and at 60 ms a
     * sample a 1.6 second one leaves twenty-odd of them lying in the record. A jump leaves
     * none: the camera is at the angle it opened on, and then it is at TILT.
     *
     * Written as "no angle in between" rather than as a duration because the street
     * arrives from the API whenever it arrives, and a test that starts a stopwatch at the
     * click is timing the network.
     */
    const between = seen.filter((angle) => angle > 1 && angle < TILT);
    expect(between).toEqual([]);
    expect(seen).toContain(TILT);
  });

  it("lights the street it was asked for", async () => {
    const lit = await page.evaluate(
      () => window.anchored.getLayer("trace") !== undefined,
    );
    expect(lit).toBe(true);
  });
});
