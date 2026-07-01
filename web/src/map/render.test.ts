/**
 * The map, rendered by a real browser.
 *
 * The style validator says a style is well formed; it cannot say the map draws. Three bugs
 * got past it in a row and every one of them produced the same symptom — a black rectangle
 * and no error anywhere:
 *
 *   - esbuild's dependency pre-bundling broke MapLibre's worker in development only, so the
 *     style never finished loading, `load` never fired, nothing was ever fetched, and the
 *     built site was perfect the whole time.
 *   - `["has", field]` asks whether a property is present, and the builder writes every
 *     operator's field on every street, so every filter matched everything.
 *   - tearing a map down takes the camera out of the URL, so in development the second map
 *     read a URL the first had already emptied.
 *
 * None of those is visible from a unit test and all of them are obvious here. It needs a
 * dev server and an API, and skips rather than fails when they are not up, which is the
 * same bargain the database tests make.
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

  it("draws the country under them", async () => {
    const drawn = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["regions"] }).length,
    );
    expect(drawn).toBeGreaterThan(0);
  });

  it("shows fewer streets for one operator than for anyone", async () => {
    const anyone = await page.evaluate(
      () => window.atlas.queryRenderedFeatures({ layers: ["streets"] }).length,
    );
    await page.getByRole("button", { name: "DEI", exact: true }).click();
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
    await page.getByRole("button", { name: "INALAN", exact: true }).click();
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
