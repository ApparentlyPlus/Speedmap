/**
 * The worker pool and the PMTiles protocol, shared by every map here. MapLibre keeps both on
 * the library, so they're set once. The defaults don't suit a page with four archives.
 */

import { addProtocol, setWorkerCount, type Map as Maplibre } from "maplibre-gl";
import { FetchSource, PMTiles, Protocol, type RangeResponse, type Source } from "pmtiles";

/**
 * MapLibre decodes on one worker unless told otherwise, so a zoom out wanting a dozen tiles
 * got them one by one. Measured over eight moves: 1379 ms at two workers, 1196 at eight, 1253
 * at fifteen. Each worker also keeps its own copy of the style and fonts.
 */
const WORKERS = 8;

/** One protocol per page, which caches archive headers and directories. */
const pmtiles = new Protocol();

/**
 * Chrome's HTTP cache lets one request per URL through at a time, and a range is still the
 * same URL. Every tile of an archive waited for the one before it to answer: a pan over Athens
 * took eight round trips for eight basemap tiles, 600 ms on a 60 ms link for 284 kB. Each range
 * gets its own URL here, so they go out together and each can still be cached. The servers
 * ignore the query.
 */
class Ranges implements Source {
  constructor(private readonly url: string) {}

  getKey(): string {
    return this.url;
  }

  getBytes(
    offset: number,
    length: number,
    signal?: AbortSignal,
    etag?: string,
  ): Promise<RangeResponse> {
    return new FetchSource(`${this.url}?r=${offset}-${length}`).getBytes(
      offset, length, signal, etag,
    );
  }
}

/** The archive a pmtiles:// URL reads, for its TileJSON and for each tile. */
const ARCHIVE = /^pmtiles:\/\/(.+?\.pmtiles)/;

let ready = false;

/** Call before building a map. Repeat calls do nothing. */
export function engine(): void {
  if (ready) return;
  ready = true;
  setWorkerCount(Math.max(2, Math.min(WORKERS, navigator.hardwareConcurrency || 4)));
  addProtocol("pmtiles", (params, abort) => {
    const url = ARCHIVE.exec(params.url)?.[1];
    if (url !== undefined && pmtiles.get(url) === undefined) {
      pmtiles.add(new PMTiles(new Ranges(url)));
    }
    return pmtiles.tile(params, abort);
  });
}

/**
 * Runs `then` once the map has had its first load, straight away if it already has. Returns
 * the undo, for an effect's cleanup.
 *
 * Not isStyleLoaded(). That's also false while any tile is in flight, and the event the pages
 * then waited on had already fired: an operator picked mid-pan stayed unpicked until the next
 * zoom, and an answer landing mid-load never got its descent. `_loaded` is MapLibre's own
 * record of the load event, and is in its typings.
 */
export function whenLoaded(map: Maplibre, then: () => void): () => void {
  if (map._loaded) {
    then();
    return () => undefined;
  }
  map.once("load", then);
  return () => {
    map.off("load", then);
  };
}
