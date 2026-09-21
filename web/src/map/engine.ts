/**
 * The worker pool and the PMTiles protocol, which every map here shares.
 *
 * MapLibre hangs both off the library rather than off a map, so they are set once, and the
 * defaults are wrong for a page with four archives under it.
 */

import { addProtocol, setWorkerCount } from "maplibre-gl";
import { Protocol } from "pmtiles";

/**
 * MapLibre decodes tiles on one worker unless it is told otherwise, so a zoom out asking
 * for a dozen at once got them one after another. Eight rather than all fifteen cores:
 * measured over eight moves it went 1379 ms at two workers, 1196 at eight, and 1253 at
 * fifteen. Each worker also keeps its own copy of the style and the fonts.
 */
const WORKERS = 8;

/** One protocol for the page. Archive headers and directories are cached on it. */
const pmtiles = new Protocol();

let ready = false;

/** Call before building a map. The second call does nothing. */
export function engine(): void {
  if (ready) return;
  ready = true;
  setWorkerCount(Math.max(2, Math.min(WORKERS, navigator.hardwareConcurrency || 4)));
  addProtocol("pmtiles", pmtiles.tile);
}
