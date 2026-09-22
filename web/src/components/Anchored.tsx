/** The map behind an address, flown to it once and then frozen. */

import { useEffect, useRef } from "react";
import maplibregl, {
  Map as Maplibre,
  type DataDrivenPropertyValueSpecification,
} from "maplibre-gl";
import type { Geometry, Position } from "geojson";

import { engine } from "../map/engine";
import { ASIDE, ASIDE_OPACITY, ramps, style } from "../map/style";
import {
  GLOW,
  PASS_MS,
  TRACE,
  focusOf,
  turnable,
  momentOf,
  pathOf,
  traceLayers,
  traceOpacity,
} from "../map/trace";
import { SOURCE, onlyStreet } from "../map/style";
import { STREETS_LAYER } from "../map/tiles";

/** The one street this map is about, map in colour over the quiet ones. */
const SUBJECT = "subject";

/** Close enough that the building is a building, far enough that it has neighbours. */
const ZOOM = 16.6;
const PITCH = 58;
const BEARING = -20;

/** How far the camera leans once it has arrived. Enough to see the city has sides. */
const TILT = 42;

/** As close as the camera will get to a short street. */
const CLOSEST = 17.4;

/** Just off solid, so a road behind a wall is a hint rather than a secret. */
const SHEER = 0.9;

/** How much zoom the lean is given back. A box is fitted as though the map were flat. */
const PITCH_ROOM = 0.6;

/** Degrees a second. A turn takes two minutes, which is slower than anyone will watch. */
const SPIN = 3;

/** Whether this reader wants things to move at all. */
function stillness(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** How fast the light is allowed to redraw, in milliseconds between frames. */
const TRACE_MS = 1000 / 30;

/** The part of the map nothing is sitting on. */
function clear(map: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const edge = 36;
  const pad = { top: edge, right: edge, bottom: edge, left: edge };
  const box = map.getContainer().getBoundingClientRect();
  const card = document.querySelector(".place")?.getBoundingClientRect();

  // Only where the card covers the map rather than sits beside it. On a narrow screen it
  // lies across the bottom, and a street fitted under it is a street nobody can see.
  if (card !== undefined && card.width >= box.width * 0.75) {
    pad.bottom = Math.min(box.bottom - card.top + 16, box.height * 0.6);
  }
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
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Maplibre | null>(null);
  // Read once, when the map is built. After that the point arrives as a move.
  const here = useRef<[number, number] | null>(
    lon !== null && lat !== null ? [lon, lat] : null,
  );

  useEffect(() => {
    if (box.current === null || mapRef.current !== null) return;
    engine();

    const map = new Maplibre({
      container: box.current,
      style: style(),
      // Where it opens.
      center: here.current ?? [24.0, 38.4],
      zoom: here.current === null ? 6 : ZOOM,
      pitch: here.current === null ? 0 : PITCH,
      bearing: BEARING,
      interactive: false,
      attributionControl: false,
    });
    mapRef.current = map;
    // The same handle the map page keeps, for the same reason: only a real browser can say
    // whether a light is running along a street. Development only. The build drops it.
    if (import.meta.env.DEV) {
      window.anchored = map;
    }

    // MapLibre measures its container once, when it is built, and this one is built while
    // the grid around it is reduced resolving.
    const settle = requestAnimationFrame(() => map.resize());
    const watching = new ResizeObserver(() => map.resize());
    watching.observe(box.current);

    return () => {
      cancelAnimationFrame(settle);
      watching.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // The address, when it arrives after the map did: a move rather than a rebuild.
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || lon === null || lat === null) return;
    if (here.current !== null) return;
    here.current = [lon, lat];
    /**
     * A street supersedes its own midpoint, so it is not visited on the way.
     *
     * Both arrive in the same render, out of one response, and the effect below frames the
     * whole road. Leaning into the door first meant the reader watched the camera climb to
     * one pitch over 1.2 seconds and then cut to another, which is the jolt: two moves to
     * reach a place neither of them was aiming at. An address has no road to frame and
     * still gets its move.
     */
    if (shape !== null && shape !== undefined) return;
    map.easeTo({ center: [lon, lat], zoom: ZOOM, pitch: PITCH, duration: 1200 });
  }, [lon, lat, shape]);

  /** The light, added once the street is known and taken away with it. */
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || shape === null || shape === undefined) return;
    let running = 0;
    // The map can be taken away underneath this.
    let stopped = false;
    // Whether the camera has finished arriving and may start turning.
    let turning = false;
    let last = 0;

    const path = pathOf(shape);
    if (path === null) return;

    const reduced = stillness();

    /** Showing, on screen, and wanted. All three, or the loop does no work. */
    let onScreen = true;
    let awake = !reduced && document.visibilityState === "visible";

    const wake = (): void => {
      awake = !reduced && onScreen && document.visibilityState === "visible";
      // Time does not stop while the loop is parked, so the turn would otherwise resume by
      // jumping however many degrees it owed for the minutes the tab spent in the back.
      if (!awake) last = 0;
    };

    document.addEventListener("visibilitychange", wake);
    const watcher = new IntersectionObserver((entries) => {
      onScreen = entries.some((entry) => entry.isIntersecting);
      wake();
    });
    if (box.current !== null) watcher.observe(box.current);

    const add = (): void => {
      if (map.getSource(TRACE) !== undefined) return;
      map.addSource(TRACE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Under the city, with the streets it belongs to. Added plainly it goes on top of
      // everything, and then the light climbs whatever roof the street runs behind.
      const under = ["building-shadow", "building", "place-label"].find(
        (layer) => map.getLayer(layer) !== undefined,
      );
 /** Everything but the street in question goes quiet. */
      /** Take the buildings just off solid. */
      if (map.getLayer("building") !== undefined) {
        map.setPaintProperty("building", "fill-extrusion-opacity", [
          "interpolate", ["linear"], ["zoom"], 14, 0, 15.2, SHEER,
        ]);
      }

      if (map.getLayer("streets-halo") !== undefined) {
        map.setLayoutProperty("streets-halo", "visibility", "none");
      }
      if (map.getLayer("streets") !== undefined) {
        map.setPaintProperty("streets", "line-color", ASIDE);
        map.setPaintProperty("streets", "line-opacity", ASIDE_OPACITY);
      }
      if (streetId !== null && streetId !== undefined && map.getLayer(SUBJECT) === undefined) {
        map.addLayer(
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

      for (const layer of traceLayers()) map.addLayer(layer, under);
      // Set once: the light never dims, it only moves.
      for (const [layer, opacity] of traceOpacity()) {
        map.setPaintProperty(layer, "line-opacity", opacity);
      }

      /**
       * Frame the street, not the door. A fixed zoom on the address shows the building and a
       * hundred metres of road, and the light spends most of its pass outside the frame.
       */
      const extent = focusOf(shape);
      if (extent !== null) {
        // However far out that turns out to be. One name can cover thirty kilometres of
        // rural road, and thirty kilometres of rural road is the answer to what was asked.
        /** One move, not four. */
        const camera = map.cameraForBounds(turnable(extent), {
          padding: clear(map),
          maxZoom: CLOSEST,
        });
        if (camera !== undefined && camera.center !== undefined) {
          /**
           * Arrive, rather than travel.
           *
           * This used to ease over 1.6 seconds from the camera the map opened on to the
           * one that frames the street, and those are two different places: the opening
           * camera is a fixed zoom on the door, the framed one is however far out the
           * road turns out to be. So the map spent its first second and a half sliding
           * and zooming between two arbitrary views before the thing the reader asked
           * for was on screen, and only then began to turn.
           *
           * Nothing was being shown during that move. The street is known by now, and
           * the reader has just asked for it by name, so the frame is put up whole and
           * the turn starts on it.
           */
          map.jumpTo({
            center: camera.center,
            // Room for the lean. The fit is worked out flat, and a tilted camera throws
            // the far half of what it is looking at up the screen and off the top of it.
            zoom: (camera.zoom ?? CLOSEST) - PITCH_ROOM,
            pitch: TILT,
            bearing: 0,
          });
          // No move to wait on: a jump fires moveend, but the turn can start on the
          // frame it is already standing in.
          turning = true;
        }
      }

      /** One loop, and only while anybody is looking at it. */
      const began = performance.now();
      let painted = 0;

      const frame = (now: number): void => {
        running = requestAnimationFrame(frame);
        if (stopped || !awake) return;
        const source = map.getSource(TRACE);
        if (source === undefined || map.getLayer(TRACE) === undefined) return;

        // Degrees a second rather than degrees a frame: the same speed on a slow map as a
        // fast one, and the opening lean is left to finish before the turn starts.
        if (turning && last !== 0 && now > last) {
          map.setBearing(map.getBearing() + (SPIN * (now - last)) / 1000);
        }
        last = now;

        if (now - painted < TRACE_MS) return;
        painted = now;
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
      };

      if (reduced) {
        // The street, lit along its whole length and left alone. Reduced motion is a
        // request for no movement, not for no answer.
        const source = map.getSource(TRACE);
        if (source !== undefined) {
          (source as maplibregl.GeoJSONSource).setData({
            type: "FeatureCollection",
            features: path.parts.map((line) => ({
              type: "Feature",
              properties: {},
              geometry: { type: "LineString", coordinates: line as Position[] },
            })),
          });
        }
        return;
      }
      running = requestAnimationFrame(frame);
    };

    if (map.isStyleLoaded()) add();
    else map.once("load", add);

    return () => {
      stopped = true;
      cancelAnimationFrame(running);
      document.removeEventListener("visibilitychange", wake);
      watcher.disconnect();
      map.off("load", add);
      // A map that has already been removed has nothing left to take the light off.
      try {
          for (const layer of [TRACE, GLOW, SUBJECT]) {
          if (map.getLayer(layer) !== undefined) map.removeLayer(layer);
        }
        if (map.getSource(TRACE) !== undefined) map.removeSource(TRACE);
      } catch {
        // Gone with the map it was map on.
      }
    };
  }, [shape, streetId, lon, lat]);

  return <div className="anchored" ref={box} aria-hidden="true" />;
}
