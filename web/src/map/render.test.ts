/**
 * The map, rendered by a real browser. The style validator says a style is well formed. It
 * cannot say the map draws.
 */

import { chromium, type Browser, type Page } from "playwright";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

const WHERE = "http://127.0.0.1:5173";

/** Thessaloniki, close enough in that streets are the point. */
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
    // Software rendering, because a test machine has no GPU and the point is the geometry
    // rather than the pixels.
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
    // False here is the symptom every one of those bugs produced.
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
    // Roads and water come out of an archive read by range request. If that is not wired
    // up the coverage floats on a black rectangle, which is what it used to do.
    const drawn = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["road", "water"] }).length,
    );
    expect(drawn).toBeGreaterThan(0);
  });

  it("draws buildings where there are buildings", async () => {
    // Footprints only start at zoom fourteen, so this one has to go and look. It puts the
    // camera back: the tests share a page, and the next one counts what is in view.
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
    // The button carries the name a reader knows rather than the register's code:
    // the panel said OTE while the data behind it said Telekom until that changed.
    await page.getByRole("button", { name: "ΔΕΗ Fiber", exact: true }).click();
    await page.waitForTimeout(2000);
    const theirs = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["streets"] }).length,
    );
    expect(theirs).toBeGreaterThan(0);
    expect(theirs).toBeLessThan(anyone);
  });

  it("keeps an operator that files no speeds at all", async () => {
    // Inalan reaches 112,739 addresses and files a speed for none of them. A filter that
    // tests for a number rather than for service would hide the lot.
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
