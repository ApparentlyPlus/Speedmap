// Every street in the country, coloured by the fastest line known to reach it. Filterable
// by operator, "can I get Vodafone here" is what most people come asking.

import { useEffect, useRef, useState } from "react";
import { Map as Maplibre, NavigationControl, type Point as MapPoint } from "maplibre-gl";
import type { Geometry } from "geojson";

import { address, street, type Result, type StreetDetail } from "../api/client";
import { Credit } from "../components/Credit";
import { MapMenu, type Picked } from "../components/MapMenu";
import { MapSearch } from "../components/MapSearch";
import { engine, whenLoaded } from "../map/engine";
import { Tilt } from "../map/tilt";
import { strings, type Language } from "../i18n";
import {
  STREETS_LAYER,
  type Cell,
} from "../map/tiles";
import { extentOf, focusOf } from "../map/trace";
import {
  BASE,
  BUILDINGS,
  BUILDINGS_FROM,
  BUILDING_LAYERS,
  FLOOR_ZOOM,
  HOME,
  LIMITS,
  REGION_LAYERS,
  only,
  LIT,
  onlyStreet,
  ramps,
  touchPad,
  regionOpacity,
  regionPaint,
  style,
  type View,
} from "../map/style";

// sources the page can live without
const OPTIONAL_SOURCES = new Set<string>([BASE, BUILDINGS]);

const TRAVEL_MS = 2200;

const CLOSEST = 16;

// gap between the street and whatever's nearest it on screen
const EDGE = 44;

const EASE = (t: number): number => t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

const RAISE_MS = 220;

const WAIT_CAP = 3000;

type Showing = "ready" | "failed";

export function MapPage({ language }: { readonly language: Language }): React.ReactElement {
  const text = strings(language);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Maplibre | null>(null);
  // only the latest click or pick may fill the panel, they used to race
  const asked = useRef(0);
  // read before the map rewrites the hash
  const arrived = useRef(window.location.hash);
  const [provider, setProvider] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<StreetDetail | null>(null);
  // straight off the tile, no request needed
  const [cell, setCell] = useState<Cell | null>(null);
  const [view, setView] = useState<View>("coverage");
  const [regions, setRegions] = useState(false);
  const [showing, setShowing] = useState<Showing>("ready");

  useEffect(() => {
    if (box.current === null || mapRef.current !== null) return;

    engine();

    // camera in the URL so views are shareable, HOME only without one
    const linked = arrived.current.length > 1;
    if (linked && window.location.hash.length <= 1) {
      window.history.replaceState(null, "", arrived.current);
    }

    const map = new Maplibre({
      container: box.current,
      style: style(),
      ...(linked ? {} : { center: HOME.centre, zoom: HOME.zoom }),
      attributionControl: false,
      hash: true,
      maxBounds: LIMITS,
      minZoom: FLOOR_ZOOM,
      // default cache is ~5 zooms, zooming out 4 and back was 96ms of redecoding
      maxTileCacheZoomLevels: 12,
      refreshExpiredTiles: false,
    });
    // same width as the narrow layout in the CSS
    const narrow = window.matchMedia("(width <= 560px)").matches;
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    // phones only (see Tilt), added after so it's above the zoom buttons
    if (narrow) map.addControl(new Tilt(text.tilt), "bottom-right");
    mapRef.current = map;

    // an upright phone is narrower than Greece at FLOOR_ZOOM, so fit the country and grow
    // the bounds to match or MapLibre zooms straight back in
    if (narrow) {
      const whole = map.cameraForBounds(LIMITS, { padding: clearOf(map) });
      if (whole?.zoom !== undefined) {
        const camera = { center: map.getCenter(), zoom: map.getZoom() };
        map.setMaxBounds(null);
        map.setMinZoom(Math.min(FLOOR_ZOOM, whole.zoom));
        map.jumpTo(whole);
        const seen = map.getBounds().extend(LIMITS);
        if (linked) map.jumpTo(camera);
        map.setMaxBounds(seen);
      }
    }
    // for the console and the browser test
    if (import.meta.env.DEV) {
      window.atlas = map;
    }

    map.on("click", "cells", (event) => {
      const hit = event.features?.[0]?.properties;
      if (hit === undefined) return;
      setOpen(false);
      setChosen(null);
      setCell(hit as Cell);
    });
    for (const moving of ["mouseenter", "mouseleave"] as const) {
      map.on(moving, "cells", () => {
        map.getCanvas().style.cursor = moving === "mouseenter" ? "pointer" : "";
      });
    }

    // exact point first so a direct hit wins, then a padded box for thumbs
    const streetUnder = (at: MapPoint): number | null => {
      if (map.getLayer(STREETS_LAYER) === undefined) return null;
      const exact = map.queryRenderedFeatures(at, { layers: [STREETS_LAYER] });
      const pad = touchPad(map.getZoom());
      const near = exact.length > 0
          ? exact
          : map.queryRenderedFeatures(
              [[at.x - pad, at.y - pad], [at.x + pad, at.y + pad]],
              { layers: [STREETS_LAYER] },
            );
      const id = near[0]?.properties?.["id"];
      return typeof id === "number" ? id : null;
    };

    map.on("click", (event) => {
      const id = streetUnder(event.point);
      if (id === null) return;
      setOpen(false);
      setCell(null);
      const mine = ++asked.current;
      street(id)
        .then((found) => {
          if (mine === asked.current) setChosen(found);
        })
        .catch(() => {
          if (mine === asked.current) setChosen(null);
        });
    });

    // once a frame at most, never mid drag
    let asking = false;
    map.on("mousemove", (event) => {
      if (asking || map.isMoving()) return;
      asking = true;
      requestAnimationFrame(() => {
        asking = false;
        map.getCanvas().style.cursor = streetUnder(event.point) === null ? "" : "pointer";
      });
    });

    // Over Athens a building tile is 600kB and they landed in four waves while zooming in.
    // Hold them at zero and raise the view at once, unless some were already on screen.
    const raise = (opacity: "hold" | "show"): void => {
      for (const [layer, property] of Object.entries(BUILDING_LAYERS)) {
        if (map.getLayer(layer) === undefined) continue;
        map.setPaintProperty(layer, `${property}-transition`, {
          duration: opacity === "show" ? RAISE_MS : 0,
          delay: 0,
        });
        map.setPaintProperty(layer, property, opacity === "show" ? painted[layer] : 0);
      }
    };
    const painted: Record<string, unknown> = {};
    let held = false;
    let giveUp = 0;

    const show = (): void => {
      if (!held) return;
      held = false;
      window.clearTimeout(giveUp);
      raise("show");
    };

    map.on("zoomstart", () => {
      if (held || map.getZoom() >= BUILDINGS_FROM) return;
      for (const layer of Object.keys(BUILDING_LAYERS)) {
        if (map.getLayer(layer) === undefined) continue;
        painted[layer] ??= map.getPaintProperty(layer, BUILDING_LAYERS[layer] as string);
      }
      held = true;
      raise("hold");
      giveUp = window.setTimeout(show, WAIT_CAP);
    });

    const settled = (): void => {
      if (!held || map.isZooming()) return;
      if (map.getZoom() < BUILDINGS_FROM || map.isSourceLoaded(BUILDINGS)) show();
    };
    map.on("zoomend", settled);
    map.on("sourcedata", (event) => {
      if (event.sourceId === BUILDINGS) settled();
    });

    map.on("error", (fault) => {
      // basemap and footprints come from planetiler outside this repo, so a fresh clone has
      // neither. Log it, the streets still draw fine
      const missing = (fault as { sourceId?: string }).sourceId;
      if (missing !== undefined && OPTIONAL_SOURCES.has(missing)) {
        // eslint-disable-next-line no-console
        console.warn(`map: no ${missing} archive, drawing without it`, fault.error);
        return;
      }
      setShowing("failed");
      // eslint-disable-next-line no-console
      console.error("map style", fault.error);
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // built once, the language is fixed for the page
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Escape shuts the menu first, then a picked street or square
  useEffect(() => {
    const shut = (event: KeyboardEvent): void => {
      if (event.key !== "Escape") return;
      if (open) {
        setOpen(false);
      } else {
        setChosen(null);
        setCell(null);
      }
    };
    window.addEventListener("keydown", shut);
    return () => window.removeEventListener("keydown", shut);
  }, [open]);

  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;

    const apply = (): void => {
      const filter = only(provider);
      for (const [layer, paint] of Object.entries(ramps(provider))) {
        // continue, not return, or the filter is left half applied
        if (map.getLayer(layer) === undefined) continue;
        map.setPaintProperty(layer, "line-color", paint);
        map.setFilter(layer, filter);
      }

      // filed and measured never show together
      const streets = view === "coverage";
      for (const layer of ["streets-halo", "streets"]) {
        if (map.getLayer(layer) !== undefined) {
          map.setLayoutProperty(layer, "visibility", streets ? "visible" : "none");
        }
      }
      for (const layer of REGION_LAYERS) {
        if (map.getLayer(layer) === undefined) continue;
        map.setLayoutProperty(layer, "visibility", regions ? "visible" : "none");
      }
      if (map.getLayer("regions") !== undefined) {
        map.setPaintProperty("regions", "fill-color", regionPaint(view));
        map.setPaintProperty("regions", "fill-opacity", regionOpacity(view));
      }

      if (map.getLayer("cells") !== undefined) {
        map.setLayoutProperty("cells", "visibility", streets ? "none" : "visible");
        map.setFilter("cells", ["==", ["get", "family"], view === "mobile" ? "mobile" : "fixed"]);
      }
    };

    return whenLoaded(map, apply);
  }, [provider, view, regions]);

  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;
    const apply = (): void => {
      const streetId = chosen?.id ?? null;
      const lit = onlyStreet(streetId);
      for (const layer of ["streets-picked-halo", "streets-picked"]) {
        if (map.getLayer(layer) === undefined) continue;
        // hidden when nothing's chosen, no tile work for it
        map.setLayoutProperty(layer, "visibility", streetId === null ? "none" : "visible");
        map.setFilter(layer, lit);
        // filters don't transition, opacity does
        map.setPaintProperty(layer, "line-opacity", streetId === null ? 0 : LIT[layer]);
      }
    };

    return whenLoaded(map, apply);
  }, [chosen]);

  const picked: Picked | null =
    chosen !== null ? { kind: "street", street: chosen } : cell !== null ? { kind: "cell", cell } : null;

  return (
    <main className="atlas" lang={language}>
      <div className="atlas-canvas" ref={box} />
      <Credit language={language} />

      <MapSearch
        language={language}
        onPick={(result) => {
          setOpen(false);
          setCell(null);
          const mine = ++asked.current;
          void travelTo(mapRef.current, result, setChosen, () => mine === asked.current);
        }}
      />
      {showing === "failed" && <p className="map-failed">{text.searchFailed}</p>}

      <MapMenu
        language={language}
        open={open}
        setOpen={setOpen}
        view={view}
        setView={(one) => {
          setCell(null);
          setView(one);
        }}
        provider={provider}
        setProvider={setProvider}
        regions={regions}
        setRegions={setRegions}
        picked={picked}
        shutPicked={() => {
          setChosen(null);
          setCell(null);
        }}
      />
    </main>
  );
}

// What the search bar and menu card don't cover. The card is laid out at full size while
// still growing, so it can be measured the moment a street is picked.
function clearOf(map: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const pad = { top: EDGE, right: EDGE, bottom: EDGE, left: EDGE };
  const box = map.getContainer().getBoundingClientRect();
  const bar = document.querySelector(".map-search")?.getBoundingClientRect();
  if (bar !== undefined) pad.top = bar.bottom - box.top + EDGE;

  const card = document.querySelector(".map-menu-inner")?.getBoundingClientRect();
  if (card === undefined) return pad;
  if (card.width >= box.width * 0.75) {
    pad.top = Math.min(Math.max(pad.top, card.bottom - box.top + EDGE), box.height * 0.6);
  } else {
    pad.right = Math.min(box.right - card.left + EDGE, box.width * 0.6);
  }
  return pad;
}

// two frames, for React to commit and MapLibre to restyle
function settled(): Promise<void> {
  return new Promise((done) => {
    requestAnimationFrame(() => requestAnimationFrame(() => done()));
  });
}

// Select first, then fly. Selecting re-parses every tile in view, and if the flight has
// started it stalls and lurches. Frames the longest run, two runs of a name can be blocks apart.
async function travelTo(
  map: Maplibre | null,
  result: Result,
  pick: (found: StreetDetail | null) => void,
  latest: () => boolean,
): Promise<void> {
  if (map === null) return;
  try {
    if (result.kind !== "street") {
      const door = await address(result.id);
      if (!latest()) return;
      pick(null);
      await settled();
      if (!latest()) return;
      map.flyTo({
        center: [door.lon, door.lat],
        zoom: CLOSEST,
        duration: TRAVEL_MS,
        easing: EASE,
      });
      return;
    }

    // asked about something else since
    const found = await street(result.id);
    if (!latest()) return;
    pick(found);
    await settled();
    if (!latest()) return;

    const [west, south, east, north] = found.bbox;
    // same cast as Place and Road, PostGIS fills it
    const shape = found.shape as unknown as Geometry;
    const extent =
      focusOf(shape) ??
      extentOf(shape) ??
      ([[west, south], [east, north]] as [[number, number], [number, number]]);

    // one eased move, fitBounds re-aims mid flight
    const camera = map.cameraForBounds(extent, {
      padding: clearOf(map),
      maxZoom: CLOSEST,
    });
    if (camera?.center === undefined) return;
    map.easeTo({
      center: camera.center,
      zoom: camera.zoom ?? CLOSEST,
      duration: TRAVEL_MS,
      easing: EASE,
    });
  } catch {
    if (latest()) pick(null);
  }
}

export const LAYER = STREETS_LAYER;
