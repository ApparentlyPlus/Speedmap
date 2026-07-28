/**
 * The map behind an address, flown to it once and then frozen.
 *
 * Anchored rather than interactive: the reader is being shown one address, not invited to
 * go for a wander, so there is nothing here to drag, scroll or rotate. It is the same style
 * and the same archives the map page uses, which costs nothing extra — the tiles are
 * already in the browser's cache by the time anyone reaches a result.
 */

import { useEffect, useRef } from "react";
import { Map as Maplibre, addProtocol } from "maplibre-gl";
import type { Geometry } from "geojson";
import { Protocol } from "pmtiles";

import { style } from "../map/style";
import { GLOW, PASS_MS, TRACE, extentOf, traceGradients, traceLayers } from "../map/trace";

/** Close enough that the building is a building, far enough that it has neighbours. */
const ZOOM = 16.6;
const PITCH = 58;
const BEARING = -20;

let registered = false;

/**
 * The part of the map nothing is sitting on.
 *
 * The result card is over the map, not beside it, so fitting a street to the whole viewport
 * can put half of it behind the card. The card is down one side on a wide screen and along
 * the bottom on a narrow one, so which edge to keep clear is measured rather than assumed.
 */
function clear(drawn: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const edge = 56;
  const pad = { top: edge, right: edge, bottom: edge, left: edge };
  const box = drawn.getContainer().getBoundingClientRect();
  const card = document.querySelector(".place")?.getBoundingClientRect();
  if (card !== undefined) {
    if (card.width < box.width * 0.75) pad.left = card.right - box.left + 24;
    else pad.bottom = box.bottom - card.top + 24;
  }
  // MapLibre refuses a fit whose padding leaves no room, and a refused fit is no frame.
  pad.left = Math.min(pad.left, box.width * 0.6);
  pad.bottom = Math.min(pad.bottom, box.height * 0.6);
  return pad;
}

export function Anchored({
  lon,
  lat,
  shape,
}: {
  readonly lon: number | null;
  readonly lat: number | null;
  /** The street this result is on, when it is one we hold. */
  readonly shape?: Geometry | null;
}): React.ReactElement {
  const holder = useRef<HTMLDivElement>(null);
  const map = useRef<Maplibre | null>(null);

  useEffect(() => {
    if (holder.current === null || map.current !== null) return;
    if (!registered) {
      addProtocol("pmtiles", new Protocol().tile);
      registered = true;
    }

    const drawn = new Maplibre({
      container: holder.current,
      style: style(),
      // An address that failed to geolocate gets the country rather than a wrong building.
      center: lon !== null && lat !== null ? [lon, lat] : [24.0, 38.4],
      zoom: lon !== null && lat !== null ? ZOOM : 6,
      pitch: lon !== null && lat !== null ? PITCH : 0,
      bearing: BEARING,
      interactive: false,
      attributionControl: false,
    });
    map.current = drawn;
    // The same handle the map page keeps, for the same reason: only a real browser can say
    // whether a light is running along a street. Development only; the build drops it.
    if (import.meta.env.DEV) {
      window.anchored = drawn;
    }

    // MapLibre measures its container once, when it is built, and this one is built while
    // the grid around it is still resolving.
    const settle = requestAnimationFrame(() => drawn.resize());
    const watching = new ResizeObserver(() => drawn.resize());
    watching.observe(holder.current);

    return () => {
      cancelAnimationFrame(settle);
      watching.disconnect();
      drawn.remove();
      map.current = null;
    };
  }, [lon, lat]);

  /*
   * The light, added once the street is known and taken away with it.
   *
   * Its own source rather than the street layer already on the map: `line-gradient` reads
   * `line-progress`, which only exists on a source asked to measure its lines, and a vector
   * tile is not asked anything.
   */
  useEffect(() => {
    const drawn = map.current;
    if (drawn === null || shape === null || shape === undefined) return;
    let running = 0;

    const add = (): void => {
      if (drawn.getSource(TRACE) !== undefined) return;
      drawn.addSource(TRACE, {
        type: "geojson",
        lineMetrics: true,
        data: { type: "Feature", properties: {}, geometry: shape },
      });
      // Under the city, with the streets it belongs to. Added plainly it goes on top of
      // everything, and then the light climbs whatever roof the street runs behind.
      const under = ["building-shadow", "building", "place-label"].find(
        (layer) => drawn.getLayer(layer) !== undefined,
      );
      for (const layer of traceLayers(0)) drawn.addLayer(layer, under);

      /*
       * Frame the street, not the door.
       *
       * A fixed zoom on the address shows the building and a hundred metres of road, and
       * the light spends most of its pass outside the frame. Fitting the line puts the
       * whole of what is being talked about on the screen at once — which is what the
       * light is for.
       *
       * Flat, because a long street fitted at a steep pitch is mostly horizon.
       */
      const extent = extentOf(shape);
      if (extent !== null) {
        drawn.fitBounds(extent, { padding: clear(drawn), pitch: 0, bearing: 0, duration: 900 });
      }

      const began = performance.now();
      const step = (now: number): void => {
        if (drawn.getLayer(TRACE) === undefined) return;
        const along = ((now - began) % PASS_MS) / PASS_MS;
        for (const [layer, gradient] of traceGradients(along)) {
          drawn.setPaintProperty(layer, "line-gradient", gradient);
        }
        running = requestAnimationFrame(step);
      };
      running = requestAnimationFrame(step);
    };

    if (drawn.isStyleLoaded()) add();
    else drawn.once("load", add);

    return () => {
      cancelAnimationFrame(running);
      for (const layer of [TRACE, GLOW]) {
        if (drawn.getLayer(layer) !== undefined) drawn.removeLayer(layer);
      }
      if (drawn.getSource(TRACE) !== undefined) drawn.removeSource(TRACE);
    };
  }, [shape, lon, lat]);

  return <div className="anchored" ref={holder} aria-hidden="true" />;
}
