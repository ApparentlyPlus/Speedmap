/**
 * The map behind an address, flown to it once and then frozen.
 *
 * Anchored rather than interactive: the reader is being shown one address, not invited to
 * go for a wander, so there is nothing here to drag, scroll or rotate. It is the same style
 * and the same archives the map page uses, which costs nothing extra — the tiles are
 * already in the browser's cache by the time anyone reaches a result.
 */

import { useEffect, useRef } from "react";
import maplibregl, {
  Map as Maplibre,
  addProtocol,
  type DataDrivenPropertyValueSpecification,
} from "maplibre-gl";
import type { Geometry } from "geojson";
import { Protocol } from "pmtiles";

import { ASIDE, ASIDE_OPACITY, ramps, style } from "../map/style";
import {
  GLOW,
  PASS_MS,
  TRACE,
  focusOf,
  momentOf,
  pathOf,
  traceLayers,
  traceOpacity,
} from "../map/trace";
import { SOURCE, onlyStreet } from "../map/style";
import { STREETS_LAYER } from "../map/tiles";

/** The one street this map is about, drawn in colour over the quiet ones. */
const SUBJECT = "subject";

/** Close enough that the building is a building, far enough that it has neighbours. */
const ZOOM = 16.6;
const PITCH = 58;
const BEARING = -20;

let registered = false;

/** How far the camera leans once it has arrived. Enough to see the city has sides. */
const TILT = 42;

/** As close as the camera will get to a short street. */
const CLOSEST = 17.4;

/** Degrees a second. A turn takes two minutes, which is slower than anyone will watch. */
const SPIN = 3;

/**
 * Lean the camera over and turn it, slowly, about the street.
 *
 * A result framed flat and held still is a diagram. Leaning it puts the buildings between
 * the reader and the far side of the street, which is what makes the street a place rather
 * than a line; turning it keeps showing a different face of the same block, so the picture
 * goes on saying something after the first second.
 *
 * About the centre, which is where the street was just put — so the thing being talked
 * about stays where the eye already is, and everything else moves around it.
 */
function showcase(drawn: Maplibre, stopped: () => boolean): void {
  if (stopped()) return;

  let last = 0;
  const turn = (now: number): void => {
    if (stopped() || drawn.getLayer(TRACE) === undefined) return;
    // Degrees a second rather than degrees a frame: the same speed on a slow map as a
    // fast one, and the opening lean is left to finish before the turn starts.
    if (last !== 0 && now > last) {
      drawn.setBearing(drawn.getBearing() + (SPIN * (now - last)) / 1000);
    }
    last = now;
    requestAnimationFrame(turn);
  };
  requestAnimationFrame(turn);
}

/**
 * The part of the map nothing is sitting on.
 *
 * The result card is over the map, not beside it, so fitting a street to the whole viewport
 * can put half of it behind the card. The card is down one side on a wide screen and along
 * the bottom on a narrow one, so which edge to keep clear is measured rather than assumed.
 */
function clear(drawn: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const edge = 36;
  const pad = { top: edge, right: edge, bottom: edge, left: edge };
  const box = drawn.getContainer().getBoundingClientRect();
  const card = document.querySelector(".place")?.getBoundingClientRect();
  if (card !== undefined) {
    if (card.width < box.width * 0.75) pad.left = card.right - box.left + 16;
    else pad.bottom = box.bottom - card.top + 16;
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
  streetId,
}: {
  readonly lon: number | null;
  readonly lat: number | null;
  /** The street this result is on, when it is one we hold. */
  readonly shape?: Geometry | null;
  /** Which street that is, so it alone keeps its colour. */
  readonly streetId?: number | null;
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
    // The map can be taken away underneath this. Both effects tear down together, and a
    // frame already asked for runs against a map whose style is gone — where every call is
    // a read of undefined, which takes the whole page down rather than the animation.
    let stopped = false;

    const path = pathOf(shape);
    if (path === null) return;

    const add = (): void => {
      if (drawn.getSource(TRACE) !== undefined) return;
      drawn.addSource(TRACE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Under the city, with the streets it belongs to. Added plainly it goes on top of
      // everything, and then the light climbs whatever roof the street runs behind.
      const under = ["building-shadow", "building", "place-label"].find(
        (layer) => drawn.getLayer(layer) !== undefined,
      );
      /*
       * Everything but the street in question goes quiet.
       *
       * The halo is the glow that makes coverage read as light on a road, and forty
       * thousand of them around the subject is a lit city with the answer somewhere in it.
       * Off entirely; the rest go one flat grey. The street being asked about is drawn
       * again above them, in the colour the ramp gives it, so it is the only thing on the
       * map wearing a speed.
       */
      if (drawn.getLayer("streets-halo") !== undefined) {
        drawn.setLayoutProperty("streets-halo", "visibility", "none");
      }
      if (drawn.getLayer("streets") !== undefined) {
        drawn.setPaintProperty("streets", "line-color", ASIDE);
        drawn.setPaintProperty("streets", "line-opacity", ASIDE_OPACITY);
      }
      if (streetId !== null && streetId !== undefined && drawn.getLayer(SUBJECT) === undefined) {
        drawn.addLayer(
          {
            id: SUBJECT,
            type: "line",
            source: SOURCE,
            "source-layer": STREETS_LAYER,
            filter: onlyStreet(streetId),
            layout: { "line-cap": "round", "line-join": "round" },
            paint: {
              "line-color": ramps(null)["streets"] as DataDrivenPropertyValueSpecification<string>,
              "line-opacity": [
                "interpolate", ["linear"], ["zoom"],
                7, 0.55, 13, 0.7, 16, 0.78, 18, 0.6,
              ],
              "line-width": [
                "interpolate", ["exponential", 1.6], ["zoom"],
                6, 0.45, 12, 1.25, 14, 2.6, 15, 4.5, 16, 7, 20, 26,
              ],
            },
          },
          under,
        );
      }

      for (const layer of traceLayers()) drawn.addLayer(layer, under);
      // Set once: the light never dims, it only moves.
      for (const [layer, opacity] of traceOpacity()) {
        drawn.setPaintProperty(layer, "line-opacity", opacity);
      }

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
      const extent = focusOf(shape);
      if (extent !== null) {
        // However far out that turns out to be. One name can cover thirty kilometres of
        // rural road, and thirty kilometres of rural road is the answer to what was asked.
        /*
         * Leaned first, then fitted.
         *
         * Fitting flat and leaning afterwards moves the street: a tilted camera keeps the
         * same centre on the ground but puts it lower on the screen, so the thing that was
         * dead centre ends up in the bottom third. Fitted under the lean, the framing is
         * the framing that gets looked at.
         */
        drawn.jumpTo({ pitch: TILT, bearing: 0 });
        drawn.fitBounds(extent, {
          padding: clear(drawn),
          maxZoom: CLOSEST,
          duration: 900,
        });
        drawn.once("moveend", () => showcase(drawn, () => stopped));
      }

      const began = performance.now();
      const step = (now: number): void => {
        if (stopped) return;
        const source = drawn.getSource(TRACE);
        if (source === undefined || drawn.getLayer(TRACE) === undefined) return;
        const along = ((now - began) % PASS_MS) / PASS_MS;
        const moment = momentOf(path, along);
        (source as maplibregl.GeoJSONSource).setData({
          type: "FeatureCollection",
          features: moment.lines.map((line) => ({
            type: "Feature",
            properties: {},
            geometry: { type: "LineString", coordinates: line },
          })),
        });
        running = requestAnimationFrame(step);
      };
      running = requestAnimationFrame(step);
    };

    if (drawn.isStyleLoaded()) add();
    else drawn.once("load", add);

    return () => {
      stopped = true;
      cancelAnimationFrame(running);
      drawn.off("load", add);
      // A map that has already been removed has nothing left to take the light off.
      try {
          for (const layer of [TRACE, GLOW, SUBJECT]) {
          if (drawn.getLayer(layer) !== undefined) drawn.removeLayer(layer);
        }
        if (drawn.getSource(TRACE) !== undefined) drawn.removeSource(TRACE);
      } catch {
        // Gone with the map it was drawn on.
      }
    };
  }, [shape, streetId, lon, lat]);

  return <div className="anchored" ref={holder} aria-hidden="true" />;
}
