/**
 * The map. Every street in the country, coloured by the fastest thing known to reach it, and
 * filterable to one operator at a time, which is the question people actually arrive with.
 */

import { useEffect, useRef, useState } from "react";
import { Map as Maplibre, NavigationControl, addProtocol } from "maplibre-gl";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";

import { address, search, street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { Credit } from "../components/Credit";
import { strings, type Language } from "../i18n";
import { UNSERVED, bandsPainted, colourFor, mbps } from "../tokens";
import { STREETS_BY_PROVIDER, STREETS_LAYER, type Cell } from "../map/tiles";
import {
  FLOOR_ZOOM,
  HOME,
  LIMITS,
  REGION_LAYERS,
  VIEWS,
  only,
  LIT,
  onlyStreet,
  ramps,
  regionPaint,
  style,
  type View,
} from "../map/style";

/** How long the map takes to arrive somewhere that was asked for. Long enough to be followed. */
const TRAVEL_MS = 2200;

/**
 * Slow at both ends, quick through the middle. Linear travel starts and stops at full speed,
 * which reads as a jolt at each end however long the journey is.
 */
const EASE = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

/** Long enough that a typist does not generate a request per letter. */
const SETTLE_MS = 250;

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

    /**
     * One archive per basemap layer, read by range request rather than as a directory of a
     * million small files.
     */
    const pmtiles = new Protocol();
    addProtocol("pmtiles", pmtiles.tile);

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

    map.on("click", "streets-hit", (event) => {
      const hit = event.features?.[0];
      const id = hit?.properties?.["id"];
      if (typeof id !== "number") return;
      setCell(null);
      street(id)
        .then(setChosen)
        .catch(() => setChosen(null));
    });
    map.on("mouseenter", "streets-hit", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "streets-hit", () => {
      map.getCanvas().style.cursor = "";
    });

    map.on("error", (fault) => {
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
      // The hit line is filtered with them, so an operator's filter hides what it hides
      // rather than leaving invisible streets still clickable underneath.
      if (map.getLayer("streets-hit") !== undefined)
        map.setFilter("streets-hit", filter);

      /**
       * Filed and measured are two claims about different things, so only one is on at a time:
       * map together, a street tinted by what an operator promised and a square tinted by what
       */
      const streets = view === "coverage";
      for (const layer of ["streets-halo", "streets", "streets-hit"]) {
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
                    // Picking a street selects it.
                    void flyTo(mapRef.current, result).then(setChosen);
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
             {Object.keys(STREETS_BY_PROVIDER).map((code) => (
               <li key={code}>
                 <button
                   type="button"
                   className={`atlas-operator${provider === code ? " atlas-operator-on" : ""}`}
                   style={
                     { "--brand": brandOf(code).colour } as React.CSSProperties
                   }
                   onClick={() => setProvider(provider === code ? null : code)}
                 >
                   {code}
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

/** Take the camera to a result. */
async function flyTo(map: Maplibre | null, result: Result): Promise<StreetDetail | null> {
  if (map === null) return null;
  try {
    if (result.kind === "street") {
      const results = await street(result.id);
      const [west, south, east, north] = results.bbox;
      map.fitBounds([west, south, east, north], {
        padding: 80,
        maxZoom: 16,
        duration: TRAVEL_MS,
        easing: EASE,
      });
      return results;
    }
    const results = await address(result.id);
    map.flyTo({
      center: [results.lon, results.lat],
      zoom: 16,
      duration: TRAVEL_MS,
      easing: EASE,
    });
    return null;
  } catch {
    // A camera that cannot be moved is not worth an error message on a map.
    return null;
  }
}

export const LAYER = STREETS_LAYER;
