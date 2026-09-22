/**
 * The map. Every street in the country, coloured by the fastest thing known to reach it, and
 * filterable to one operator at a time, which is the question people actually arrive with.
 */

import { useEffect, useRef, useState } from "react";
import { Map as Maplibre, NavigationControl, type Point as MapPoint } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Geometry } from "geojson";

import { address, search, street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { Credit } from "../components/Credit";
import { engine } from "../map/engine";
import { strings, type Language } from "../i18n";
import { UNSERVED, bandsPainted, colourFor, mbps } from "../tokens";
import {
  STREETS_BY_PROVIDER,
  STREETS_INFRASTRUCTURE,
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
  VIEWS,
  only,
  LIT,
  onlyStreet,
  ramps,
  touchPad,
  regionPaint,
  style,
  type View,
} from "../map/style";

/**
 * Sources the page can do without. Everything else failing is a failure worth saying so.
 */
const OPTIONAL_SOURCES = new Set<string>([BASE, BUILDINGS]);

/** How long the map takes to arrive somewhere that was asked for. Long enough to be followed. */
const TRAVEL_MS = 2200;

/** As close as the camera will get to a short street. */
const CLOSEST = 16;

/** The gap left between the street and whatever is nearest it on screen. */
const EDGE = 44;

/**
 * Which operators are a choice of supplier and which are only a network. Read off the tile
 * contract rather than listed again here, so a provider added to the schema lands in the
 * right half of the panel without this file being touched.
 */
const WHOLESALE = new Set(STREETS_INFRASTRUCTURE);
const OPERATORS = Object.keys(STREETS_BY_PROVIDER);
const RETAILERS = OPERATORS.filter((code) => !WHOLESALE.has(code));
const NETWORKS = OPERATORS.filter((code) => WHOLESALE.has(code));

/**
 * Slow at both ends, quick through the middle. Linear travel starts and stops at full speed,
 * which reads as a jolt at each end however long the journey is.
 */
const EASE = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

/** Long enough that a typist does not generate a request per letter. */
const SETTLE_MS = 250;

/** How long the footprints take to come up once the whole view has them. */
const RAISE_MS = 220;

/** The longest the city is left blank waiting for a tile that may never arrive. */
const WAIT_CAP = 3000;

type Showing = "ready" | "failed";

export function MapPage({ language }: { readonly language: Language }): React.ReactElement {
  const text = strings(language);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Maplibre | null>(null);
  /** The camera the reader arrived on, kept from the first render. */
  const arrived = useRef(window.location.hash);
  const [provider, setProvider] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [chosen, setChosen] = useState<StreetDetail | null>(null);
  /**
   * A measured square, read straight off the tile. Everything the square says is already in the
   * feature the renderer handed over, so picking one asks the server nothing.
   */
  const [cell, setCell] = useState<Cell | null>(null);
  const [view, setView] = useState<View>("coverage");
  /** The prefecture choropleth, off until asked for. */
  const [regions, setRegions] = useState(false);
  const [showing, setShowing] = useState<Showing>("ready");

  useEffect(() => {
    if (box.current === null || mapRef.current !== null) return;

    // The worker pool and the PMTiles protocol, shared with every other map here.
    engine();

    /**
     * The camera in the URL, so a view of one neighbourhood is a link to it. The opening camera
     * is passed only when the reader did not arrive on a link to one.
     */
    const linked = arrived.current.length > 1;
    if (linked && window.location.hash.length <= 1) {
      window.history.replaceState(null, "", arrived.current);
    }

    const map = new Maplibre({
      container: box.current,
      style: style(),
      ...(linked ? {} : { center: HOME.centre, zoom: HOME.zoom }),
      // Credited on /attribution instead, which the corner link goes to.
      attributionControl: false,
      hash: true,
      maxBounds: LIMITS,
      minZoom: FLOOR_ZOOM,
      // Keep what has already been decoded. The default holds about five zooms' worth, which
      // a zoom out of four levels walks straight past, so coming back to a place cost 96 ms
      // a move instead of nothing.
      maxTileCacheZoomLevels: 12,
      // The archive is replaced whole, weekly, and its URL never changes inside a session.
      refreshExpiredTiles: false,
    });
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    mapRef.current = map;
    // A handle for the console and for the browser test, which is the only thing that can tell
    // a map that draws from a map that merely has no errors.
    if (import.meta.env.DEV) {
      window.atlas = map;
    }

 /**
  * MapLibre rejects a whole style on one bad expression, and says so by firing an event
  * rather than by throwing.
  */
    /** A street is the only thing on this map, so it is the only thing to click. */
    map.on("click", "cells", (event) => {
      const hit = event.features?.[0]?.properties;
      if (hit === undefined) return;
      setChosen(null);
      setCell(hit as Cell);
    });
    for (const moving of ["mouseenter", "mouseleave"] as const) {
      map.on(moving, "cells", () => {
        map.getCanvas().style.cursor = moving === "mouseenter" ? "pointer" : "";
      });
    }

    /**
     * The street under the pointer, allowing for a line three pixels across and a thumb that
     * is not. The exact point first so an outright hit wins, then the padded box.
     */
    const streetUnder = (at: MapPoint): number | null => {
      if (map.getLayer(STREETS_LAYER) === undefined) return null;
      const exact = map.queryRenderedFeatures(at, { layers: [STREETS_LAYER] });
      const pad = touchPad(map.getZoom());
      const near =
        exact.length > 0
          ? exact
          : map.queryRenderedFeatures(
              [
                [at.x - pad, at.y - pad],
                [at.x + pad, at.y + pad],
              ],
              { layers: [STREETS_LAYER] },
            );
      const id = near[0]?.properties?.["id"];
      return typeof id === "number" ? id : null;
    };

    map.on("click", (event) => {
      const id = streetUnder(event.point);
      if (id === null) return;
      setCell(null);
      street(id)
        .then(setChosen)
        .catch(() => setChosen(null));
    });

    /**
     * The cursor, once a frame at most and never while the map is moving. Dragging is when
     * the main thread has least to spare, and the answer is stale by the next frame anyway.
     */
    let asking = false;
    map.on("mousemove", (event) => {
      if (asking || map.isMoving()) return;
      asking = true;
      requestAnimationFrame(() => {
        asking = false;
        map.getCanvas().style.cursor = streetUnder(event.point) === null ? "" : "pointer";
      });
    });

    /**
     * Buildings arrive a tile at a time, and over Athens one tile is 600 kB and a quarter of
     * a second, so a zoom in from above them showed the near ones land before the far ones.
     * Four separate arrivals, at 600, 628, 674 and 718 ms. Hold them at nothing for the
     * length of the zoom and bring the whole view up at once instead.
     *
     * Only when there were none on screen to begin with. Buildings already drawn are never
     * taken away, so panning and zooming inside the city look as they always did.
     */
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
      // A tile that never arrives must not leave the city blank.
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
      // The basemap and the building footprints are built by planetiler from an OSM
      // extract, not by this repository, and a checkout without them is the normal state
      // of a fresh clone. Losing the land underneath the streets is worth a line in the
      // console. It is not worth telling the reader the map failed while the map is
      // drawing every street they came for.
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
  }, []);

  /**
   * The same index the landing searches, because a street is a place on this map as much as it
   * is a row in a list, and two search boxes that disagree about what exists would be two
   */
  useEffect(() => {
    const asked = query.trim();
    if (asked.length < 2) {
      setResults([]);
      return;
    }
    const stop = new AbortController();
    const timer = window.setTimeout(() => {
      // Streets only. A number picks the street it is on rather than a door on the map,
      // because there is nothing on a map for a door to be.
      search(asked, stop.signal, "street")
        .then(setResults)
        .catch(() => setResults([]));
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
    };
  }, [query]);

  /** Switching operator changes two properties on two layers. */
  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;

    const apply = (): void => {
      const filter = only(provider);
      for (const [layer, paint] of Object.entries(ramps(provider))) {
        // Skip the missing layer, do not abandon the rest of the function: `return` here meant
        // that one absent layer left the operator filter half applied and the view switch below.
        if (map.getLayer(layer) === undefined) continue;
        map.setPaintProperty(layer, "line-color", paint);
        map.setFilter(layer, filter);
      }

      /**
       * Filed and measured are two claims about different things, so only one is on at a time:
       * map together, a street tinted by what an operator promised and a square tinted by what
       */
      const streets = view === "coverage";
      for (const layer of ["streets-halo", "streets"]) {
        if (map.getLayer(layer) !== undefined) {
          map.setLayoutProperty(
            layer,
            "visibility",
            streets ? "visible" : "none",
          );
        }
      }
      /** The choropleth follows the view rather than sitting under all three. */
      for (const layer of REGION_LAYERS) {
        if (map.getLayer(layer) === undefined) continue;
        map.setLayoutProperty(layer, "visibility", regions ? "visible" : "none");
      }
      if (map.getLayer("regions") !== undefined) {
        map.setPaintProperty("regions", "fill-color", regionPaint(view));
      }

      if (map.getLayer("cells") !== undefined) {
        map.setLayoutProperty(
          "cells",
          "visibility",
          streets ? "none" : "visible",
        );
        map.setFilter("cells", [
          "==",
          ["get", "family"],
          view === "mobile" ? "mobile" : "fixed",
        ]);
      }
    };

    if (map.isStyleLoaded()) {
      apply();
      return;
    }
    map.once("styledata", apply);
    return () => {
      map.off("styledata", apply);
    };
  }, [provider, view, regions]);

  // Light whichever street is selected, and put the light out when none is.
  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;
    const apply = (): void => {
      const streetId = chosen?.id ?? null;
      const lit = onlyStreet(streetId);
      for (const layer of ["streets-picked-halo", "streets-picked"]) {
        if (map.getLayer(layer) === undefined) continue;
        // Off entirely when nothing is chosen, so tiles are not built for a layer that is
        // drawing no streets.
        map.setLayoutProperty(layer, "visibility", streetId === null ? "none" : "visible");
        map.setFilter(layer, lit);
        // Filters do not transition, opacity does: the street is always drawn, and what
        // fades is how much of it there is to see.
        map.setPaintProperty(layer, "line-opacity", streetId === null ? 0 : LIT[layer]);
      }
    };

    if (map.isStyleLoaded()) {
      apply();
      return;
    }
    map.once("styledata", apply);
    return () => {
      map.off("styledata", apply);
    };
  }, [chosen]);

  return (
    <main className="atlas" lang={language}>
      <div className="atlas-canvas" ref={box} />
      <Credit language={language} />

      <section className="atlas-panel">
        <a className="atlas-back" href={language === "el" ? "/" : "/en/"}>
          <span aria-hidden="true">←</span> {text.back}
        </a>
        <h1 className="atlas-name">{text.mapTitle}</h1>

        <label className="atlas-search">
          <span className="visually-hidden">{text.searchLabel}</span>
          <input
            type="search"
            value={query}
            placeholder={text.searchPlaceholder}
            autoComplete="off"
            spellCheck={false}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        {results.length > 0 && (
          <ul className="atlas-found">
            {results.slice(0, 6).map((result) => (
              <li key={`${result.kind}-${result.id}`}>
                <button
                  type="button"
                  className="atlas-hit"
                  onClick={() => {
                    // Picking a street selects it, and only then travels to it.
                    setCell(null);
                    void travelTo(mapRef.current, result, setChosen);
                    setQuery("");
                    setResults([]);
                  }}
                >
                  <span className="atlas-hit-name">
                    {result.street_no === null
                      ? result.name
                      : `${result.name} ${result.street_no}`}
                  </span>
                  <span className="atlas-hit-where">{result.municipality}</span>
                </button>
              </li>
            ))}
          </ul>
        )}

        <h2 className="atlas-head">{text.shown}</h2>
        <ul className="atlas-operators">
          {VIEWS.map((one) => (
            <li key={one}>
              <button
                type="button"
                className={`atlas-operator${view === one ? " atlas-operator-on" : ""}`}
                onClick={() => {
                  setCell(null);
                  setView(one);
                }}
              >
                {text.views[one]}
              </button>
            </li>
          ))}
        </ul>

        {/*
* A checkbox rather than another pill.
 *
  * The pills above it are a choice between three views and the operator pills are a
   * choice of one operator. This is neither. It is an overlay that either is or is
    * not on, and dressing it as a pill put it in a row of things that look like
     * alternatives to each other.
*/}
       <label className="atlas-toggle" title={text.regionsHint}>
         <input
           type="checkbox"
           checked={regions}
           onChange={(event) => setRegions(event.target.checked)}
         />
         <span>{text.regions}</span>
       </label>

       {view === "coverage" && (
         <>
           <h2 className="atlas-head">{text.operator}</h2>
           <ul className="atlas-operators">
             <li>
               <button
                 type="button"
                 className={`atlas-operator${provider === null ? " atlas-operator-on" : ""}`}
                 onClick={() => setProvider(null)}
               >
                 {text.anyOperator}
               </button>
             </li>
             {RETAILERS.map((code) => (
               <li key={code}>
                 <button
                   type="button"
                   className={`atlas-operator${provider === code ? " atlas-operator-on" : ""}`}
                   style={
                     { "--brand": brandOf(code).colour } as React.CSSProperties
                   }
                   onClick={() => setProvider(provider === code ? null : code)}
                 >
                   {/*
* The name the reader knows, rather than the register's code.
 *
  * The code is a join key. OTE is a holding company nobody shops for, and
   * the shop, the bill and the router all say Telekom. A button reading one
    * thing over data saying another leaves the reader to do a translation
     * we have already done.
*/}
                   {brandOf(code).name}
                 </button>
               </li>
             ))}
           </ul>

           {/*
* The networks, under their own heading.
 *
  * These reach streets and sell to nobody: wholesale builders who pass premises
   * for other operators to retail over, and Metadosis, which files services and
    * publishes no tariff to compare. Sat in the same row as Telekom and Vodafone
     * they look like two more suppliers a reader could pick between. Dropped
      * altogether they take the fiber with them, and that fiber decides whether
       * anyone will ever sell a gigabit down the street.
*/}
           <h2 className="atlas-head" title={text.infrastructureHint}>
             {text.infrastructure}
           </h2>
           <ul className="atlas-operators">
             {NETWORKS.map((code) => (
               <li key={code}>
                 <button
                   type="button"
                   className={`atlas-operator${provider === code ? " atlas-operator-on" : ""}`}
                   style={
                     { "--brand": brandOf(code).colour } as React.CSSProperties
                   }
                   onClick={() => setProvider(provider === code ? null : code)}
                 >
                   {brandOf(code).name}
                 </button>
               </li>
             ))}
           </ul>
         </>
       )}

       <h2 className="atlas-head">{text.legend[view]}</h2>
       {/*
* The bands this view can actually produce, not all seven.
 *
  * Coverage tops each street out at what its line is retailed at and a filing can
   * only cap that further, so nothing ever lands between 100 Mbps and a gigabit:
    * three of the ramp's rows would show a colour the map will never paint. Measured
     * is a real continuum, median 60, p90 270, and uses the lot.
*/}
       <ul className="atlas-ramp">
         {bandsPainted(view !== "coverage").map((band) => (
           <li className="atlas-band" key={band.name}>
             <span className="atlas-swatch" style={{ background: band.colour }} />
             {band.name}
           </li>
         ))}
         {/*
* The last row is a different silence under each view.
 *
  * Under Coverage it is a street no line reaches, map dark because it is
   * absence rather than a slow street. The third state this legend used to carry —
    * reaches here, filed no speed, is gone: the figure comes from the technology
     * now, so anything that reaches a street has a number.
      *
       * Under Measured and Mobile it is a place nobody has ever run a speed test in,
        * which is most of Greece.
*/}
         <li className="atlas-band">
           <span className="atlas-swatch" style={{ background: UNSERVED }} />
           {view === "coverage" ? text.unreached : text.untested}
         </li>
       </ul>

       {cell !== null && (
         <section className="atlas-picked">
           <button
             type="button"
             className="atlas-shut"
             onClick={() => setCell(null)}
             aria-label={text.back}
           >
             ×
           </button>
           <h2 className="atlas-picked-name">{text.measuredHere}</h2>
           <p className="atlas-picked-where">
             {text.views[cell.family === "mobile" ? "mobile" : "measured"]} · {cell.tests}{" "}
             {text.tests}
           </p>
           <ul className="atlas-measured">
             <li className="atlas-measure">
               <span className="atlas-measure-name">{text.down}</span>
               <span
                 className="atlas-measure-speed"
                 style={{ color: colourFor(mbps(Number(cell.down_mbps))) }}
               >
                 {Math.round(Number(cell.down_mbps))} Mbps
               </span>
             </li>
             <li className="atlas-measure">
               <span className="atlas-measure-name">{text.up}</span>
               <span className="atlas-measure-speed">
                 {Math.round(Number(cell.up_mbps))} Mbps
               </span>
             </li>
           </ul>
         </section>
       )}

       {chosen !== null && (
         <section className="atlas-picked">
           <button
             type="button"
             className="atlas-shut"
             onClick={() => setChosen(null)}
             aria-label={text.back}
           >
             ×
           </button>
           <h2 className="atlas-picked-name">{chosen.name}</h2>
           <p className="atlas-picked-where">{chosen.municipality}</p>
           {chosen.offers.length === 0 ? (
             <p className="atlas-picked-none">{text.mapNothingHere}</p>
           ) : (
             <ul className="atlas-offers">
               {chosen.offers.map((offer) => (
                 <li className="atlas-offer" key={`${offer.provider}-${offer.technology}`}>
                   <span
                     className="atlas-offer-dot"
                     style={{ background: brandOf(offer.provider).colour }}
                   />
                   <span className="atlas-offer-name">{offer.provider_name}</span>
                   <span className="atlas-offer-tech">
                     {offer.technology}
                     {offer.infra_provider !== null &&
                       offer.infra_provider !== offer.provider && (
                         <span className="atlas-offer-infra">
                           {" "}
                           · {text.over} {offer.infra_provider}
                         </span>
                       )}
                   </span>
                   {/*
* What the line is sold at, not what the register filed for it. The
 * band is still in the response and is deliberately not shown: it is
  * absent on seven filings in ten, and where it is present it is a
   * class the line often cannot carry.
*/}
                   <span className="atlas-offer-speed">
                     {offer.sold_mbps === null || offer.sold_mbps === undefined
                       ? text.unfiled
                       : `${Number(offer.sold_mbps)} Mbps`}
                   </span>
                 </li>
               ))}
             </ul>
           )}
         </section>
       )}

       <p className={`atlas-state atlas-state-${showing}`}>
         {showing === "failed" && text.searchFailed}
       </p>
     </section>
   </main>
 );
}

/**
 * The part of the map nothing is sitting on.
 *
 * The panel sits on top of the map rather than beside it: 232 pixels down the left on a
 * wide screen, the top 46% on a narrow one. Fitting a street to the whole canvas therefore
 * fitted it to a rectangle the reader can only see part of, and parked it under the panel
 * about half the time.
 */
function clearOf(map: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const pad = { top: EDGE, right: EDGE, bottom: EDGE, left: EDGE };
  const box = map.getContainer().getBoundingClientRect();
  const panel = document.querySelector(".atlas-panel")?.getBoundingClientRect();
  if (panel === undefined) return pad;

  // Wide: the panel is a column down one side. Narrow: it lies across the top.
  if (panel.width >= box.width * 0.75) {
    pad.top = Math.min(panel.bottom - box.top + EDGE, box.height * 0.6);
  } else {
    pad.left = Math.min(panel.right - box.left + EDGE, box.width * 0.6);
  }
  return pad;
}

/** Two frames: long enough for React to have committed and MapLibre to have restyled. */
function settled(): Promise<void> {
  return new Promise((done) => {
    requestAnimationFrame(() => requestAnimationFrame(() => done()));
  });
}

/**
 * Take the camera to a result, once the street it is going to has been lit.
 *
 * The order matters more than anything else here. Selecting a street turns two layers from
 * `visibility: none` to visible, and MapLibre answers that by re-parsing every tile in view
 * for the new layers. Start the flight first and that work lands on its opening frames,
 * which is the jolt: the camera sets off, stalls while the viewport is rebuilt, then
 * catches up. So the street is chosen, two frames are allowed to pass, and only then does
 * anything move.
 *
 * The box is the longest run of the street rather than all of it. A name can still cover
 * two runs a few streets apart, and a camera fitted to both frames the gap between them
 * and shows neither.
 */
async function travelTo(
  map: Maplibre | null,
  result: Result,
  pick: (found: StreetDetail | null) => void,
): Promise<void> {
  if (map === null) return;
  try {
    if (result.kind !== "street") {
      const door = await address(result.id);
      pick(null);
      await settled();
      map.flyTo({
        center: [door.lon, door.lat],
        zoom: CLOSEST,
        duration: TRAVEL_MS,
        easing: EASE,
      });
      return;
    }

    const found = await street(result.id);
    pick(found);
    await settled();

    const [west, south, east, north] = found.bbox;
    // The same cast Place and Road make: the generated type is the open record the schema
    // describes, and every producer of it is PostGIS writing GeoJSON.
    const shape = found.shape as unknown as Geometry;
    const extent =
      focusOf(shape) ??
      extentOf(shape) ??
      ([[west, south], [east, north]] as [[number, number], [number, number]]);

    // One move rather than a fit: cameraForBounds works the frame out without touching the
    // camera, so the whole journey is a single eased easeTo instead of fitBounds deciding
    // where it is going while it is already going there.
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
    // A camera that cannot be moved is not worth an error message on a map.
    pick(null);
  }
}

export const LAYER = STREETS_LAYER;
