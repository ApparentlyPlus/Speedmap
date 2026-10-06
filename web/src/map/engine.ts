/**
 * The worker pool and the PMTiles protocol, shared by every map here. MapLibre keeps both on
 * the library, so they're set once. The defaults don't suit a page with four archives.
 */

import { addProtocol, setWorkerCount } from "maplibre-gl";
import { Protocol } from "pmtiles";

/**
 * MapLibre decodes on one worker unless told otherwise, so a zoom out wanting a dozen tiles
 * got them one by one. Measured over eight moves: 1379 ms at two workers, 1196 at eight, 1253
 * at fifteen. Each worker also keeps its own copy of the style and fonts.
 */
const WORKERS = 8;

/** One protocol per page, which caches archive headers and directories. */
const pmtiles = new Protocol();

let ready = false;

/** Call before building a map. Repeat calls do nothing. */
export function engine(): void {
  if (ready) return;
  ready = true;
  setWorkerCount(Math.max(2, Math.min(WORKERS, navigator.hardwareConcurrency || 4)));
  addProtocol("pmtiles", pmtiles.tile);
}
