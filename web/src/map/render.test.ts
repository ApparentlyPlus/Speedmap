/**
 * The map rendered in a real browser. The validator can say a style is well formed, but not
 * that the map draws.
 */

import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const WHERE = "http://127.0.0.1:5173";

/** Thessaloniki, close enough that the streets are the point. */
const CITY = "#13/40.635/22.945";

const SETTLE = 9000;

async function up(): Promise<boolean> {
  try {
    const answer = await fetch(`${WHERE}/`, { signal: AbortSignal.timeout(1500) });
    return answer.ok;
  } catch {
    return false;
  }
}

const running = await up();

describe.skipIf(!running)("the map in a browser", () => {
  let browser: Browser;
  let page: Page;
  const faults: string[] = [];

  beforeAll(async () => {
    // software GL: test machines have no GPU, and we're checking geometry, not pixels
    browser = await chromium.launch({
      args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
    });
    page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    page.on("pageerror", (fault) => faults.push(fault.message));
    page.on("console", (line) => {
      if (line.type() === "error") faults.push(line.text());
    });
    await page.goto(`${WHERE}/map${CITY}`, { waitUntil: "load" });
    await page.waitForTimeout(SETTLE);
  }, 90_000);

  afterAll(async () => {
    await browser?.close();
  });

  it("finishes loading", async () => {
    // false here is what every one of those bugs looked like
    expect(await page.evaluate(() => window.atlas?.loaded() ?? false)).toBe(true);
  });

  it("opens on the camera in the link", async () => {
    const zoom = await page.evaluate(() => Math.round(window.atlas.getZoom()));
    expect(zoom).toBe(13);
  });

  it("draws streets", async () => {
    const drawn = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["streets"] }).length,
    );
    expect(drawn).toBeGreaterThan(100);
  });

  it("draws the basemap under them", async () => {
    // Roads and water come from a range-read archive. Unwired, the coverage floats on a black
    // rectangle, as it once did.
    const drawn = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["road", "water"] }).length,
    );
    expect(drawn).toBeGreaterThan(0);
  });

  it("draws buildings where there are buildings", async () => {
    // footprints start at zoom 14, so go and look, then put the camera back: the tests share
    // a page and the next one counts what's in view
    await page.evaluate(() => window.atlas.jumpTo({ center: [22.9444, 40.6401], zoom: 16.5 }));
    await page.waitForTimeout(6000);
    const drawn = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["building"] }).length,
    );
    await page.evaluate(() => window.atlas.jumpTo({ center: [22.945, 40.635], zoom: 13 }));
    await page.waitForTimeout(4000);
    expect(drawn).toBeGreaterThan(0);
  }, 40_000);

  it("shows fewer streets for one operator than for anyone", async () => {
    const anyone = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["streets"] }).length,
    );
    // the button shows the brand, not the register code (it said OTE while the data said
    // Telekom, until that was fixed)
    await page.getByRole("button", { name: "ΔΕΗ Fiber", exact: true }).click();
    await page.waitForTimeout(2000);
    const theirs = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["streets"] }).length,
    );
    expect(theirs).toBeGreaterThan(0);
    expect(theirs).toBeLessThan(anyone);
  });

  it("keeps an operator that files no speeds at all", async () => {
    // Inalan reaches 112,739 addresses and files a speed for none of them, so a filter
    // testing for a number would hide them all
    await page.getByRole("button", { name: "Inalan", exact: true }).click();
    await page.waitForTimeout(2000);
    const theirs = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["streets"] }).length,
    );
    expect(theirs).toBeGreaterThan(0);
  });

  it("says nothing went wrong", () => {
    expect(faults).toEqual([]);
  });
});
