/** The map behind an answer: flown in once, then left to turn slowly. */

import { useEffect, useRef } from "react";
import maplibregl, {
  Map as Maplibre,
  type DataDrivenPropertyValueSpecification,
} from "maplibre-gl";
import type { Geometry, Position } from "geojson";

import { engine, whenLoaded } from "../map/engine";
import { BUILDINGS, BUILDING_LAYERS, LIMITS, hushed, ramps, style } from "../map/style";
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

/** The street the answer is about, kept in colour over the quiet ones. */
const SUBJECT = "subject";

/** Close enough to see the building, far enough to see its neighbours. */
const ZOOM = 16.6;
const PITCH = 58;
const BEARING = -20;

/** Camera tilt once it's arrived. Enough to show the city has sides. */
const TILT = 42;

/** Closest the camera gets to a short street. */
const CLOSEST = 17.4;

/** Just off solid, so a road behind a wall shows through a little. */
const SHEER = 0.9;

/** Zoom given back for the tilt, since the box is fitted as if the map were flat. */
const PITCH_ROOM = 0.6;

/** Degrees a second. A full turn takes two minutes. */
const SPIN = 3;

/**
 * The fall from the whole country to the street, ten zoom levels down. Slow on purpose:
 * the reader should come out of it knowing where in Greece the street is. At 3.6 s too many
 * tiles arrived after the camera had passed their zoom, and the descent looked like a
 * slideshow. Five seconds lets most of them land in time.
 */
const DESCENT_MS = 5200;

/** Fade-in for the footprints once the whole view has them. */
const RAISE_MS = 420;

/** Longest the city waits for a building tile that may never come. */
const RAISE_CAP = 2500;

/**
 * flyTo's arc. One is a straight line in. An arc helps when crossing the country at street
 * zoom, but this camera starts on the whole country, so any arc reads as a lurch backwards.
 */
const DESCENT_CURVE = 1;

/** Slow at both ends. Linear starts and stops at full speed, which jolts. */
const SMOOTH = (t: number): number => t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

/** prefers-reduced-motion */
function stillness(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** Minimum ms between redraws of the light. */
const TRACE_MS = 1000 / 30;

/** The part of the map not under the panel. */
function clear(map: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const edge = 36;
  const pad = { top: edge, right: edge, bottom: edge, left: edge };
  const box = map.getContainer().getBoundingClientRect();
  /*
   * Find the cover by its data attribute. A class selector only matched one layout, so the
   * split panel went unnoticed and the street was centred behind it.
   */
  const card = document.querySelector<HTMLElement>("[data-covers-map]");
  if (card === null) return pad;

  /*
   * The layout box, not the drawn one. The panel slides in as the map is built, and measured
   * mid-slide it put the pivot 14 px off for the life of the screen.
   *
   * --covers is how much of the panel hides the map, as a share of its size across the join.
   * Its ground thins out at the open edge, and the map shows from where the thinning starts:
   * framed beside the whole panel, the street turned well to one side of the space it had.
   */
  const covers = Number(getComputedStyle(card).getPropertyValue("--covers")) || 1;
  const across = card.offsetWidth >= box.width * 0.75;

  // The card overlaps the map in both layouts: across the bottom on narrow screens, down
  // the left on wide ones. Only the narrow case used to be handled.
  if (across) {
    const top = card.offsetTop + card.offsetHeight * (1 - covers);
    pad.bottom = Math.min(box.bottom - top + edge, box.height * 0.6);
  } else {
    pad.left = Math.min(card.offsetLeft + card.offsetWidth * covers + edge, box.width * 0.6);
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
  /** The street this result is on, if we hold it. */
  readonly shape?: Geometry | null;
  /** Its id, so it alone keeps its colour. */
  readonly streetId?: number | null;
}): React.ReactElement {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Maplibre | null>(null);
  // read once at construction, after that a new point is a move
  const here = useRef<[number, number] | null>(lon !== null && lat !== null ? [lon, lat] : null);

  useEffect(() => {
    if (box.current === null || mapRef.current !== null) return;
    engine();

    const map = new Maplibre({
      container: box.current,
      style: hushed(style()),
      center: here.current ?? [24.0, 38.4],
      zoom: here.current === null ? 6 : ZOOM,
      pitch: here.current === null ? 0 : PITCH,
      bearing: BEARING,
      interactive: false,
      attributionControl: false,
    });
    /*
     * Padding before the first paint. Arriving with the flight, it centred the opening view on
     * the whole window, half of Greece sat behind the panel, and the view slid across mid-descent.
     */
    map.setPadding(clear(map));

    /*
     * Fit Greece to the space left, instead of a fixed zoom. Zoom 6 dated from when the map had
     * the whole window. With the panel over about six tenths of it, Greece sat high and to one
     * side with the Peloponnese cut off.
     */
    if (here.current === null) {
      const opening = map.cameraForBounds(LIMITS);
      if (opening !== undefined) map.jumpTo(opening);
    }

    mapRef.current = map;
    // for the browser test, which needs to see the light actually move. dev builds only
    if (import.meta.env.DEV) {
      window.anchored = map;
    }

    // MapLibre measures its container once, and this one is built while the grid is still
    // settling.
    const settle = requestAnimationFrame(() => map.resize());
    const watching = new ResizeObserver(() => {
      map.resize();
      // the panel is a share of the window, so the pivot point moves when the window does
      if (map.getSource(TRACE) !== undefined) map.easeTo({ padding: clear(map), duration: 0 });
    });
    watching.observe(box.current);

    return () => {
      cancelAnimationFrame(settle);
      watching.disconnect();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // a late-arriving address is a move, not a rebuild
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || lon === null || lat === null) return;
    if (here.current !== null) return;
    here.current = [lon, lat];
    /**
     * With a street, skip the door. Both come from one response, and the effect below frames
     * the whole road. Flying to the door first meant one 1.2 s climb to one pitch and then a cut
     * to another. An address with no street still gets this move.
     */
    if (shape !== null && shape !== undefined) return;
    map.easeTo({ center: [lon, lat], zoom: ZOOM, pitch: PITCH, duration: 1200 });
  }, [lon, lat, shape]);

  /** The light runs once the street is known and goes with it. */
  useEffect(() => {
    const map = mapRef.current;
    if (map === null || shape === null || shape === undefined) return;
    let running = 0;
    let stopped = false; // the map can be removed from under us
    let turning = false; // set once the camera lands, so the turn can start
    let last = 0;

    const path = pathOf(shape);
    if (path === null) return;

    const reduced = stillness();

    /** Visible tab, on screen, motion allowed: all three, or the loop idles. */
    let onScreen = true;
    let awake = !reduced && document.visibilityState === "visible";

    const wake = (): void => {
      awake = !reduced && onScreen && document.visibilityState === "visible";
      // Reset the clock while parked. Otherwise the turn jumps by however many degrees it owed
      // for the minutes the tab sat in the background.
      if (!awake) last = 0;
    };

    document.addEventListener("visibilitychange", wake);
    const watcher = new IntersectionObserver((entries) => {
      onScreen = entries.some((entry) => entry.isIntersecting);
      wake();
    });
    if (box.current !== null) watcher.observe(box.current);

    /** Cleared on unmount, whether or not the descent finished. */
    let giveUp = 0;
    let onSourceData: ((event: maplibregl.MapSourceDataEvent) => void) | null = null;

    const add = (): void => {
      if (map.getSource(TRACE) !== undefined) return;
      map.addSource(TRACE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Below the buildings. Added on top, the light climbed whatever roof the street runs behind.
      const under = ["building-shadow", "building", "place-label"].find(
        (layer) => map.getLayer(layer) !== undefined,
      );
      /*
       * Hold the footprints at zero for the whole descent and raise them together at the end.
       * They start drawing at zoom 14, two levels before the camera lands, so the last second
       * of the flight was buildings popping in tile by tile over a moving city.
       */
      const raised: [string, unknown][] = Object.entries(BUILDING_LAYERS)
        .filter(([layer]) => map.getLayer(layer) !== undefined)
        .map(([layer, property]) => {
          const painted = layer === "building"
            ? (["interpolate", ["linear"], ["zoom"], 14, 0, 15.2, SHEER] as unknown)
            : map.getPaintProperty(layer, property);
          map.setPaintProperty(layer, `${property}-transition`, { duration: 0, delay: 0 });
          map.setPaintProperty(layer, property, 0);
          return [layer, painted];
        });

      let up = false;
      /*
       * Wait for the landing too. The first version only asked whether the map was still and the
       * source loaded. Both are true at zoom 5, where there are no buildings to load, so the
       * footprints were released before the descent began and streamed in on the way down.
       */
      let arrived = false;
      const raise = (): void => {
        if (up) return;
        up = true;
        window.clearTimeout(giveUp);
        for (const [layer, painted] of raised) {
          const property = BUILDING_LAYERS[layer] as string;
          map.setPaintProperty(layer, `${property}-transition`, {
            duration: RAISE_MS,
            delay: 0,
          });
          map.setPaintProperty(layer, property, painted as never);
        }
      };
      // a tile that never arrives can't leave the city blank for good
      giveUp = window.setTimeout(raise, DESCENT_MS + RAISE_CAP);
      const landed = (): void => {
        if (!arrived || map.isMoving()) return;
        if (map.isSourceLoaded(BUILDINGS)) raise();
      };
      onSourceData = (event) => {
        if (event.sourceId === BUILDINGS) landed();
      };
      map.on("sourcedata", onSourceData);

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
              "line-opacity": ["interpolate", ["linear"], ["zoom"], 7, 0.55, 13, 0.7, 16, 0.78, 18, 0.6],
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
      // set once, the light moves but never dims
      for (const [layer, opacity] of traceOpacity()) {
        map.setPaintProperty(layer, "line-opacity", opacity);
      }

      /**
       * Frame the street. A fixed zoom on the door shows a building and 100 m of road, and the
       * light spends most of its pass off screen.
       */
      const extent = focusOf(shape);
      if (extent !== null) {
        // However far out that is. One name can be 30 km of rural road, and then that's the answer.
        //
        // Fit the street's own box. turnable() squares it so an east-west street survives a
        // 90-degree turn, which framed a 1.9 km street inside a 1.9 km square of city. The turn is
        // 3 degrees a second, so the ends drift out slowly and back.
        //
        // The map's transform has carried the panel's padding since construction (see above), so
        // the turn pivots on the clear part of the screen. Don't pass padding here as well: counted
        // twice it leaves a negative box and no camera at all.
        const camera = map.cameraForBounds(extent, { maxZoom: CLOSEST });
        // Centre on the street's own middle. cameraForBounds already shifts its centre for the
        // padding, and with the transform padded too the street sat about 250 px off the pivot,
        // circling it every turn. Its zoom is fine to keep.
        const middle: [number, number] = [
          (extent[0][0] + extent[1][0]) / 2,
          (extent[0][1] + extent[1][1]) / 2,
        ];

        if (camera !== undefined && camera.zoom !== undefined) {
          /**
           * One continuous fall from the country to the street, eased at both ends, and the turn
           * starts where it lands. It used to be two moves (1.2 s to the midpoint at a fixed zoom,
           * then 1.6 s to the real frame at another pitch), and the camera lurched twice. Cutting
           * straight to the frame fixed that and lost the sense of where in Greece the street was.
           */
          map.flyTo({
            center: middle,
            // Room for the tilt. The fit is computed flat, and a tilted camera throws the far half
            // of the view up and off the top.
            zoom: (camera.zoom ?? CLOSEST) - PITCH_ROOM,
            pitch: TILT,
            bearing: 0,
            curve: DESCENT_CURVE,
            easing: SMOOTH,
            // reduced motion: arrive, don't fly
            duration: reduced ? 0 : DESCENT_MS,
          });
          map.once("moveend", () => {
            turning = true;
            arrived = true;
            landed();
          });
        }
      }

      /** One loop, idle while nobody's looking. */
      const began = performance.now();
      let painted = 0;

      const frame = (now: number): void => {
        running = requestAnimationFrame(frame);
        if (stopped || !awake) return;
        const source = map.getSource(TRACE);
        if (source === undefined || map.getLayer(TRACE) === undefined) return;

        // Degrees per second, not per frame, so slow and fast machines turn alike. The turn waits
        // for the tilt to finish.
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
        // Reduced motion still gets an answer: the whole street lit, standing still.
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

    const unwait = whenLoaded(map, add);

    return () => {
      stopped = true;
      cancelAnimationFrame(running);
      document.removeEventListener("visibilitychange", wake);
      watcher.disconnect();
      unwait();
      window.clearTimeout(giveUp);
      if (onSourceData !== null) map.off("sourcedata", onSourceData);
      // a removed map has nothing left to clean
      try {
          for (const layer of [TRACE, GLOW, SUBJECT]) {
          if (map.getLayer(layer) !== undefined) map.removeLayer(layer);
        }
        if (map.getSource(TRACE) !== undefined) map.removeSource(TRACE);
      } catch {
        // went with the map
      }
    };
  }, [shape, streetId, lon, lat]);

  return <div className="anchored" ref={box} aria-hidden="true" />;
}
