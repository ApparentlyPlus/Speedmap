// the map behind an answer, flown in once then left turning slowly

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

const SUBJECT = "subject";

const ZOOM = 16.6;
const PITCH = 58;
const BEARING = -20;

const TILT = 42;

const CLOSEST = 17.4;

// just off solid, a road behind a wall shows through
const SHEER = 0.9;

// back off for the tilt, the fit is computed flat
const PITCH_ROOM = 0.6;

// degrees/s, two minutes a turn
const SPIN = 3;

// country to street, ten zooms. At 3.6s the tiles arrived after the camera passed and it
// looked like a slideshow
const DESCENT_MS = 5200;

const RAISE_MS = 420;

// give up on a building tile after this
const RAISE_CAP = 2500;

// no arc, starting from the whole country any arc reads as a lurch backwards
const DESCENT_CURVE = 1;

const SMOOTH = (t: number): number => t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

function stillness(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

// min ms between light redraws
const TRACE_MS = 1000 / 30;

// the part of the map not under the panel
function clear(map: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const edge = 36;
  const pad = { top: edge, right: edge, bottom: edge, left: edge };
  const box = map.getContainer().getBoundingClientRect();
  // by data attribute, a class only matched one of the layouts
  const card = document.querySelector<HTMLElement>("[data-covers-map]");
  if (card === null) return pad;

  // Layout box, not the drawn one: measured mid slide-in the pivot was 14px off for good.
  // --covers is the share of the panel over the map, up to where its fade starts.
  const covers = Number(getComputedStyle(card).getPropertyValue("--covers")) || 1;
  const across = card.offsetWidth >= box.width * 0.75;

  // bottom on narrow screens, left on wide
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
  readonly shape?: Geometry | null;
  // so it alone keeps its colour
  readonly streetId?: number | null;
}): React.ReactElement {
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Maplibre | null>(null);
  // read once, after that a new point is a move
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
    // padding before the first paint, or the opening view centres behind the panel
    map.setPadding(clear(map));

    // fit Greece into what the panel leaves, a fixed zoom 6 cut off the Peloponnese
    if (here.current === null) {
      const opening = map.cameraForBounds(LIMITS);
      if (opening !== undefined) map.jumpTo(opening);
    }

    mapRef.current = map;
    // dev only, the browser test checks the light moves
    if (import.meta.env.DEV) {
      window.anchored = map;
    }

    // the grid is still settling when this is built
    const settle = requestAnimationFrame(() => map.resize());
    const watching = new ResizeObserver(() => {
      map.resize();
      // pivot moves with the window
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

  // Descent and turn. The light runs along the street if we hold it, otherwise turn around
  // the door (a third can't be pinned, mostly spelling differences).
  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;
    const door: [number, number] | null = lon !== null && lat !== null ? [lon, lat] : null;
    let running = 0;
    let stopped = false; // the map can be removed from under us
    let turning = false; // set once the camera lands, so the turn can start
    let last = 0;

    const path = shape === null || shape === undefined ? null : pathOf(shape);
    if (path === null && door === null) return;

    const reduced = stillness();

    // visible tab, on screen, motion allowed, or the loop idles
    let onScreen = true;
    let awake = !reduced && document.visibilityState === "visible";

    const wake = (): void => {
      awake = !reduced && onScreen && document.visibilityState === "visible";
      // reset while parked or the turn jumps by what it owed
      if (!awake) last = 0;
    };

    document.addEventListener("visibilitychange", wake);
    const watcher = new IntersectionObserver((entries) => {
      onScreen = entries.some((entry) => entry.isIntersecting);
      wake();
    });
    if (box.current !== null) watcher.observe(box.current);

    let giveUp = 0;
    let onSourceData: ((event: maplibregl.MapSourceDataEvent) => void) | null = null;

    const add = (): void => {
      if (map.getSource(TRACE) !== undefined) return;
      map.addSource(TRACE, {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // under the buildings, on top it climbs the roofs
      const under = ["building-shadow", "building", "place-label"].find(
        (layer) => map.getLayer(layer) !== undefined,
      );
      // footprints held at zero for the descent and raised together at the end, they start
      // at z14 and popped in tile by tile over a moving city
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
      // wait for the landing too, at z5 the source is "loaded" with nothing in it
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
      // don't leave the city blank forever
      giveUp = window.setTimeout(raise, DESCENT_MS + RAISE_CAP);
      const landed = (): void => {
        if (!arrived || map.isMoving()) return;
        if (map.isSourceLoaded(BUILDINGS)) raise();
      };
      onSourceData = (event) => {
        if (event.sourceId === BUILDINGS) landed();
      };
      map.on("sourcedata", onSourceData);

      if (path !== null && streetId !== null && streetId !== undefined && map.getLayer(SUBJECT) === undefined) {
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

      if (path !== null) {
        for (const layer of traceLayers()) map.addLayer(layer, under);
        // set once, the light moves but never dims
        for (const [layer, opacity] of traceOpacity()) {
          map.setPaintProperty(layer, "line-opacity", opacity);
        }
      }

      // frame the street, a fixed zoom on the door leaves the light off screen
      const extent = shape === null || shape === undefined ? null : focusOf(shape);
      const descend = (center: [number, number], zoom: number): void => {
        // one eased fall from country to street, then the turn starts where it lands
        map.flyTo({
          center,
          zoom,
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
      };
      if (extent === null && door !== null) descend(door, ZOOM);
      if (extent !== null) {
        // the street's own box however far out, squared by turnable() so it survives a quarter turn
        const camera = map.cameraForBounds(extent, { maxZoom: CLOSEST });
        // centre on the street's middle, cameraForBounds already shifts for the padding
        const middle: [number, number] = [
          (extent[0][0] + extent[1][0]) / 2,
          (extent[0][1] + extent[1][1]) / 2,
        ];

        if (camera !== undefined && camera.zoom !== undefined) {
          // room for the tilt, it throws the far half of the view off the top
          descend(middle, (camera.zoom ?? CLOSEST) - PITCH_ROOM);
        }
      }

      const began = performance.now();
      let painted = 0;

      const frame = (now: number): void => {
        running = requestAnimationFrame(frame);
        if (stopped || !awake) return;

        // per second, not per frame. Waits for the tilt to finish
        if (turning && last !== 0 && now > last) {
          map.setBearing(map.getBearing() + (SPIN * (now - last)) / 1000);
        }
        last = now;

        const source = map.getSource(TRACE);
        if (path === null || source === undefined || map.getLayer(TRACE) === undefined) return;
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
        // reduced motion: the whole street lit, standing still
        const source = map.getSource(TRACE);
        if (path !== null && source !== undefined) {
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
      try {
          for (const layer of [TRACE, GLOW, SUBJECT]) {
          if (map.getLayer(layer) !== undefined) map.removeLayer(layer);
        }
        if (map.getSource(TRACE) !== undefined) map.removeSource(TRACE);
      } catch {
      }
    };
  }, [shape, streetId, lon, lat]);

  return <div className="anchored" ref={box} aria-hidden="true" />;
}
