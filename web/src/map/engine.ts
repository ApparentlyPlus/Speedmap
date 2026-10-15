// worker pool and PMTiles protocol, set once on the library for every map here

import { addProtocol, setWorkerCount, type Map as Maplibre } from "maplibre-gl";
import { FetchSource, PMTiles, Protocol, type RangeResponse, type Source } from "pmtiles";

// one worker by default decodes a dozen tiles one by one. 8 moves measured: 1379ms at 2,
// 1196 at 8, 1253 at 15. Each worker holds its own copy of the style and fonts
const WORKERS = 8;

const pmtiles = new Protocol();

// Chrome's cache lets one request per URL through at a time, ranges included. A query per
// range sends them together, the servers ignore it.
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

const ARCHIVE = /^pmtiles:\/\/(.+?\.pmtiles)/;

let ready = false;

// safe to call twice
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

// runs `then` after the first load (now if it's happened), returns the undo. Not
// isStyleLoaded(), that's false whenever a tile is in flight
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
