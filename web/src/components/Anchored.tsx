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
import type { Geometry, Position } from "geojson";
import { Protocol } from "pmtiles";

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

/** Just off solid, so a road behind a wall is a hint rather than a secret. */
const SHEER = 0.9;

/** How long the one move to the street takes. */
const ARRIVE_MS = 1600;

/**
 * How much zoom the lean is given back.
 *
 * A box is fitted as though the map were flat. Tilt the camera afterwards and the far half
 * of the box is thrown up the screen and out of the top of it — so the street leaves the
 * frame for part of every turn, which is the rotation looking wrong.
 */
const PITCH_ROOM = 0.6;

/** Degrees a second. A turn takes two minutes, which is slower than anyone will watch. */
const SPIN = 3;

/**
 * Whether this reader wants things to move at all.
 *
 * A map that leans, turns and runs a light along a street is the whole of what this view
 * is, and for somebody with vestibular motion sensitivity it is also the whole of what
 * makes it unusable. Asked once, when the view is built: the camera still arrives at the
 * street and the street is still lit end to end, it just stops there instead of turning.
 */
function stillness(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/**
 * How fast the light is allowed to redraw, in milliseconds between frames.
 *
 * Every frame of it cuts a fresh piece out of the street, builds a GeoJSON feature
 * collection and hands it to `setData`, which parses it and re-uploads the buffer. At 60fps
 * that is sixty parse-and-upload cycles a second, for ever, on a page whose subject is a
 * static answer. The light travels one twentieth of the street in a fifth of a second: at
 * thirty frames it is the same light, at half the work.
 */
const TRACE_MS = 1000 / 30;

/**
 * The part of the map nothing is sitting on.
 *
 * On a wide screen the card is down one side and the middle of the map is still the middle
 * of the window, which is where the eye goes and where the street belongs — so the fit is
 * centred on the window and the card is left to overlap whatever it overlaps. Centring it
 * in the gap beside the card instead is defensible and looks wrong: the street comes out
 * sitting off to one side of the screen it is on.
 *
 * On a narrow screen the card is across the bottom, and a street fitted under it is a
 * street nobody can see, so that edge is kept clear.
 */
function clear(drawn: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const edge = 36;
  const pad = { top: edge, right: edge, bottom: edge, left: edge };
  const box = drawn.getContainer().getBoundingClientRect();
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
  const holder = useRef<HTMLDivElement>(null);
  const map = useRef<Maplibre | null>(null);
  // Read once, when the map is built. After that the point arrives as a move.
  const here = useRef<[number, number] | null>(
    lon !== null && lat !== null ? [lon, lat] : null,
  );

  useEffect(() => {
    if (holder.current === null || map.current !== null) return;
    if (!registered) {
      addProtocol("pmtiles", new Protocol().tile);
      registered = true;
    }

    const drawn = new Maplibre({
      container: holder.current,
      style: style(),
      // Where it opens. It is moved from here rather than rebuilt at each new answer: the
      // effect used to depend on the point, so learning where the address was tore the map
      // down and built another — a new context, the style read again, every tile fetched
      // again — which is the jump before the camera ever starts moving.
      center: here.current ?? [24.0, 38.4],
      zoom: here.current === null ? 6 : ZOOM,
      pitch: here.current === null ? 0 : PITCH,
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
  }, []);

  // The address, when it arrives after the map did: a move rather than a rebuild.
  useEffect(() => {
    const drawn = map.current;
    if (drawn === null || lon === null || lat === null) return;
    if (here.current !== null) return;
    here.current = [lon, lat];
    drawn.easeTo({ center: [lon, lat], zoom: ZOOM, pitch: PITCH, duration: 1200 });
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
    // Whether the camera has finished arriving and may start turning.
    let turning = false;
    let last = 0;

    const path = pathOf(shape);
    if (path === null) return;

    const still = stillness();

    /*
     * Showing, on screen, and wanted. All three, or the loop does no work.
     *
     * `visibilitychange` covers the tab being in the background; the observer covers the
     * map being scrolled past on a long page, which the browser considers perfectly
     * visible. Neither is free to ask every frame, so both are events that set a flag the
     * frame reads.
     */
    let onScreen = true;
    let awake = !still && document.visibilityState === "visible";

    const wake = (): void => {
      awake = !still && onScreen && document.visibilityState === "visible";
      // Time does not stop while the loop is parked, so the turn would otherwise resume by
      // jumping however many degrees it owed for the minutes the tab spent in the back.
      if (!awake) last = 0;
    };

    document.addEventListener("visibilitychange", wake);
    const seen = new IntersectionObserver((entries) => {
      onScreen = entries.some((entry) => entry.isIntersecting);
      wake();
    });
    if (holder.current !== null) seen.observe(holder.current);

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
      /*
       * Take the buildings just off solid.
       *
       * Every building, not the ones beside the street: opacity on an extrusion layer is
       * one number for the whole layer, and the shader throws away the alpha of a
       * per-building colour, so there is no way to thin only the near ones. The zoom fade
       * they arrive on is kept and scaled, rather than replaced by a flat number that
       * would pop them into existence at fourteen.
       */
      if (drawn.getLayer("building") !== undefined) {
        drawn.setPaintProperty("building", "fill-extrusion-opacity", [
          "interpolate", ["linear"], ["zoom"], 14, 0, 15.2, SHEER,
        ]);
      }

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
         * One move, not four.
         *
         * The camera for the box is worked out without touching the live one — which is
         * the only way to have it, since a camera for a box is computed as though the map
         * were flat and asking for one while tilted gives a zoom short of the street. Then
         * a single ease carries the centre, the zoom and the lean together. It used to cut
         * to flat, fly, lean, wait, and start turning: five stages, four of them visible.
         */
        const camera = drawn.cameraForBounds(turnable(extent), {
          padding: clear(drawn),
          maxZoom: CLOSEST,
        });
        if (camera !== undefined && camera.center !== undefined) {
          drawn.easeTo({
            center: camera.center,
            // Room for the lean. The fit is worked out flat, and a tilted camera throws
            // the far half of what it is looking at up the screen and off the top of it.
            zoom: (camera.zoom ?? CLOSEST) - PITCH_ROOM,
            pitch: TILT,
            bearing: 0,
            // A reader who asked for stillness gets the same frame, arrived at rather
            // than flown to.
            duration: still ? 0 : ARRIVE_MS,
          });
          drawn.once("moveend", () => {
            turning = true;
          });
        }
      }

      /*
       * One loop, and only while anybody is looking at it.
       *
       * This used to be two: a bearing loop started on `moveend` that called `setBearing`
       * every frame, and a light loop that called `setData` every frame. Neither had a
       * stopping condition other than the view being torn down, so a result left open in a
       * background tab went on re-rendering the whole map sixty times a second — a pinned
       * core and a flat battery to animate something nobody was watching. Neither asked
       * whether the reader wanted motion at all.
       *
       * requestAnimationFrame is already throttled hard in a hidden tab, but "already
       * throttled" is not "off", and a result scrolled out of view is still visible to the
       * browser. The gate is explicit: the page is showing, the map is on screen, and the
       * reader has not asked for stillness.
       */
      const began = performance.now();
      let painted = 0;

      const frame = (now: number): void => {
        running = requestAnimationFrame(frame);
        if (stopped || !awake) return;
        const source = drawn.getSource(TRACE);
        if (source === undefined || drawn.getLayer(TRACE) === undefined) return;

        // Degrees a second rather than degrees a frame: the same speed on a slow map as a
        // fast one, and the opening lean is left to finish before the turn starts.
        if (turning && last !== 0 && now > last) {
          drawn.setBearing(drawn.getBearing() + (SPIN * (now - last)) / 1000);
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

      if (still) {
        // The street, lit along its whole length and left alone. Reduced motion is a
        // request for no movement, not for no answer.
        const source = drawn.getSource(TRACE);
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

    if (drawn.isStyleLoaded()) add();
    else drawn.once("load", add);

    return () => {
      stopped = true;
      cancelAnimationFrame(running);
      document.removeEventListener("visibilitychange", wake);
      seen.disconnect();
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
