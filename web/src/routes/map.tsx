/**
 * The map.
 *
 * Every street in the country, coloured by the fastest thing known to reach it, and
 * filterable to one operator at a time — which is the question people actually arrive with.
 *
 * Only about four per cent of Greece has ever been speed-tested and half the streets have no
 * filed speed at all, so empty is the normal case here and must never be rendered as a
 * failure. The panel says which of the two silences it is looking at.
 */

import { useEffect, useRef, useState } from "react";
import {
  Map as Maplibre,
  NavigationControl,
  addProtocol,
  type GeoJSONSource,
} from "maplibre-gl";
import { Protocol } from "pmtiles";
import "maplibre-gl/dist/maplibre-gl.css";

import { address, search, street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { RAMP, UNFILED, VOID, colourFor, mbps } from "../tokens";
import { OPEN_MS, VEIL, openingAt, veilAt } from "../map/reveal";
import { STREETS_BY_PROVIDER, STREETS_LAYER, type Cell } from "../map/tiles";
import {
  FLOOR_ZOOM,
  HOME,
  LIMITS,
  VIEWS,
  only,
  LIT,
  onlyStreet,
  ramps,
  style,
  type View,
} from "../map/style";

/**
 * How long the map takes to arrive somewhere that was asked for.
 *
 * Long enough to be followed. The camera crossing a city in under a second is a cut rather
 * than a journey: the reader arrives without having seen where they came from, and has to
 * work out from scratch where the street sits relative to anything they already knew.
 */
const TRAVEL_MS = 2200;

/**
 * Slow at both ends, quick through the middle.
 *
 * Linear travel starts and stops at full speed, which reads as a jolt at each end however
 * long the journey is. The cubic is the same curve a drawer runs on.
 */
const EASE = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

/** Long enough that a typist does not generate a request per letter. */
const SETTLE_MS = 250;

type Showing = "ready" | "failed";

/**
 * Let the country arrive rather than be there already.
 *
 * The camera pulls in while a sheet over the map opens from Athens, so the network comes
 * out of the middle of the country and the ground comes with it. Both run on the same
 * clock: the zoom has to finish when the sheet does, or it lands on a map that has been
 * sitting there waiting.
 */
function open(drawn: Maplibre): void {
  drawn.addSource(VEIL, { type: "geojson", data: veilAt(0) });
  drawn.addLayer({
    id: VEIL,
    type: "fill",
    source: VEIL,
    paint: { "fill-color": VOID, "fill-opacity": 1 },
  });

  drawn.jumpTo({ center: HOME.centre, zoom: HOME.zoom - 1.15 });
  drawn.easeTo({
    center: HOME.centre,
    zoom: HOME.zoom,
    duration: OPEN_MS,
    // Nothing abrupt at either end: it is already moving when you notice it, and it stops
    // without arriving anywhere in particular.
    easing: (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  });

  const began = performance.now();
  const step = (now: number): void => {
    if (drawn.getLayer(VEIL) === undefined) return;
    const along = (now - began) / OPEN_MS;
    const { radius, cover } = openingAt(along);
    (drawn.getSource(VEIL) as GeoJSONSource).setData(veilAt(radius));
    drawn.setPaintProperty(VEIL, "fill-opacity", cover);
    if (along < 1) {
      requestAnimationFrame(step);
      return;
    }
    drawn.removeLayer(VEIL);
    drawn.removeSource(VEIL);
  };
  requestAnimationFrame(step);
}

export function MapPage({ language }: { readonly language: Language }): React.ReactElement {
  const text = strings(language);
  const holder = useRef<HTMLDivElement>(null);
  const map = useRef<Maplibre | null>(null);
  /*
   * The camera the reader arrived on, kept from the first render.
   *
   * Tearing a map down takes the camera out of the URL, and in development React builds
   * one, throws it away, and builds another — so the second map read a URL the first had
   * already emptied, and a link to a neighbourhood opened on the whole country. Held here
   * and put back, so the link survives however many maps get built.
   */
  const arrived = useRef(window.location.hash);
  const [provider, setProvider] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [found, setFound] = useState<Result[]>([]);
  const [picked, setPicked] = useState<StreetDetail | null>(null);
  /*
   * A measured square, read straight off the tile.
   *
   * Everything the square says is already in the feature the renderer handed over, so
   * picking one asks the server nothing. A street needs a request because its offers live
   * in the database; a measurement is the tile.
   */
  const [cell, setCell] = useState<Cell | null>(null);
  const [view, setView] = useState<View>("filed");
  const [showing, setShowing] = useState<Showing>("ready");

  useEffect(() => {
    if (holder.current === null || map.current !== null) return;

    /*
     * One archive per basemap layer, read by range request rather than as a directory of a
     * million small files. Registered before any map is built, because a source naming a
     * protocol nobody has registered fails quietly.
     */
    const pmtiles = new Protocol();
    addProtocol("pmtiles", pmtiles.tile);

    /*
     * The camera in the URL, so a view of one neighbourhood is a link to it.
     *
     * The opening camera is passed only when the reader did not arrive on a link to one.
     * Handing MapLibre both leaves which wins to the order two things happen in.
     */
    const linked = arrived.current.length > 1;
    if (linked && window.location.hash.length <= 1) {
      window.history.replaceState(null, "", arrived.current);
    }

    const drawn = new Maplibre({
      container: holder.current,
      style: style(),
      ...(linked ? {} : { center: HOME.centre, zoom: HOME.zoom }),
      attributionControl: false,
      hash: true,
      maxBounds: LIMITS,
      minZoom: FLOOR_ZOOM,
    });
    drawn.addControl(new NavigationControl({ showCompass: false }), "bottom-right");

    /*
     * The opening.
     *
     * Only on a map nobody asked anything of: a link with a camera in it is somebody being
     * shown a place, and making them sit through the country assembling first is making
     * them wait for a thing they did not ask for. Same for anyone who has said they would
     * rather things did not move.
     */
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!linked && !still) {
      drawn.once("load", () => open(drawn));
    }
    map.current = drawn;
    // A handle for the console and for the browser test, which is the only thing that can
    // tell a map that draws from a map that merely has no errors. Development only: the
    // build strips the branch, so nothing reaches a reader.
    if (import.meta.env.DEV) {
      window.atlas = drawn;
    }

    /*
     * MapLibre rejects a whole style on one bad expression, and says so by firing an event
     * rather than by throwing. Without this the map is simply blank: no error, no tiles, no
     * clue, and the page looks like a slow network.
     */
    /*
     * A street is the only thing on this map, so it is the only thing to click. What comes
     * back is the cabinets it runs through rather than a quote for a door on it: a street
     * has no address of its own, and pretending otherwise would be inventing one.
     */
    drawn.on("click", "cells", (event) => {
      const hit = event.features?.[0]?.properties;
      if (hit === undefined) return;
      setPicked(null);
      setCell(hit as Cell);
    });
    for (const moving of ["mouseenter", "mouseleave"] as const) {
      drawn.on(moving, "cells", () => {
        drawn.getCanvas().style.cursor = moving === "mouseenter" ? "pointer" : "";
      });
    }

    drawn.on("click", "streets-hit", (event) => {
      const hit = event.features?.[0];
      const id = hit?.properties?.["id"];
      if (typeof id !== "number") return;
      setCell(null);
      street(id)
        .then(setPicked)
        .catch(() => setPicked(null));
    });
    drawn.on("mouseenter", "streets-hit", () => {
      drawn.getCanvas().style.cursor = "pointer";
    });
    drawn.on("mouseleave", "streets-hit", () => {
      drawn.getCanvas().style.cursor = "";
    });

    drawn.on("error", (fault) => {
      setShowing("failed");
      // eslint-disable-next-line no-console
      console.error("map style", fault.error);
    });

    return () => {
      drawn.remove();
      map.current = null;
    };
  }, []);

  /*
   * The same index the landing searches, because a street is a place on this map as much as
   * it is a row in a list, and two search boxes that disagree about what exists would be
   * two products.
   */
  useEffect(() => {
    const asked = query.trim();
    if (asked.length < 2) {
      setFound([]);
      return;
    }
    const stop = new AbortController();
    const timer = window.setTimeout(() => {
      // Streets only. A number picks the street it is on rather than a door on the map,
      // because there is nothing on a map for a door to be.
      search(asked, stop.signal, "street")
        .then(setFound)
        .catch(() => setFound([]));
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
    };
  }, [query]);

  /*
   * Switching operator changes two properties on two layers. It used to remove the layers
   * and add them back, which appended them to the end of the style — above the buildings,
   * so the coverage drew straight over the roofs and the city looked transparent.
   */
  useEffect(() => {
    const drawn = map.current;
    if (drawn === null) return;

    const apply = (): void => {
      const filter = only(provider);
      for (const [layer, paint] of Object.entries(ramps(provider))) {
        if (drawn.getLayer(layer) === undefined) return;
        drawn.setPaintProperty(layer, "line-color", paint);
        drawn.setFilter(layer, filter);
      }
      // The hit line is filtered with them, so an operator's filter hides what it hides
      // rather than leaving invisible streets still clickable underneath.
      if (drawn.getLayer("streets-hit") !== undefined)
        drawn.setFilter("streets-hit", filter);

      /*
       * Filed and measured are two claims about different things, so only one is on at a
       * time: drawn together, a street tinted by what an operator promised and a square
       * tinted by what somebody got would be read as one figure disagreeing with itself.
       */
      const streets = view === "filed";
      for (const layer of ["streets-halo", "streets", "streets-hit"]) {
        if (drawn.getLayer(layer) !== undefined) {
          drawn.setLayoutProperty(
            layer,
            "visibility",
            streets ? "visible" : "none",
          );
        }
      }
      if (drawn.getLayer("cells") !== undefined) {
        drawn.setLayoutProperty(
          "cells",
          "visibility",
          streets ? "none" : "visible",
        );
        drawn.setFilter("cells", [
          "==",
          ["get", "family"],
          view === "mobile" ? "mobile" : "fixed",
        ]);
      }
    };

    if (drawn.isStyleLoaded()) {
      apply();
      return;
    }
    drawn.once("styledata", apply);
    return () => {
      drawn.off("styledata", apply);
    };
  }, [provider, view]);

  // Light whichever street is selected, and put the light out when none is.
  useEffect(() => {
    const drawn = map.current;
    if (drawn === null) return;
    const apply = (): void => {
      const chosen = picked?.id ?? null;
      const lit = onlyStreet(chosen);
      for (const layer of ["streets-picked-halo", "streets-picked"]) {
        if (drawn.getLayer(layer) === undefined) continue;
        drawn.setFilter(layer, lit);
        // Filters do not transition, opacity does: the street is always drawn, and what
        // fades is how much of it there is to see.
        drawn.setPaintProperty(layer, "line-opacity", chosen === null ? 0 : LIT[layer]);
      }
    };

    if (drawn.isStyleLoaded()) {
      apply();
      return;
    }
    drawn.once("styledata", apply);
    return () => {
      drawn.off("styledata", apply);
    };
  }, [picked]);

  return (
    <main className="atlas" lang={language}>
      <div className="atlas-canvas" ref={holder} />

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
        {found.length > 0 && (
          <ul className="atlas-found">
            {found.slice(0, 6).map((result) => (
              <li key={`${result.kind}-${result.id}`}>
                <button
                  type="button"
                  className="atlas-hit"
                  onClick={() => {
                    // Picking a street selects it. Moving the camera to a street and
                    // leaving it unselected asks the reader to find it again and click
                    // the thing they just named.
                    void flyTo(map.current, result).then(setPicked);
                    setQuery("");
                    setFound([]);
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

        {view === "filed" && (
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
        <ul className="atlas-ramp">
          {RAMP.map((band) => (
            <li className="atlas-band" key={band.name}>
              <span className="atlas-swatch" style={{ background: band.colour }} />
              {band.name}
            </li>
          ))}
          <li className="atlas-band">
            <span className="atlas-swatch" style={{ background: UNFILED }} />
            {text.unfiled}
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

        {picked !== null && (
          <section className="atlas-picked">
            <button
              type="button"
              className="atlas-shut"
              onClick={() => setPicked(null)}
              aria-label={text.back}
            >
              ×
            </button>
            <h2 className="atlas-picked-name">{picked.name}</h2>
            <p className="atlas-picked-where">{picked.municipality}</p>
            {picked.offers.length === 0 ? (
              <p className="atlas-picked-none">{text.mapNothingHere}</p>
            ) : (
              <ul className="atlas-offers">
                {picked.offers.map((offer) => (
                  <li className="atlas-offer" key={`${offer.provider}-${offer.technology}`}>
                    <span
                      className="atlas-offer-dot"
                      style={{ background: brandOf(offer.provider).colour }}
                    />
                    <span className="atlas-offer-name">{offer.provider_name}</span>
                    <span className="atlas-offer-tech">{offer.technology}</span>
                    <span className="atlas-offer-speed">
                      {offer.speed === null ? text.unfiled : offer.speed.label}
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
 * Take the camera to a result.
 *
 * A street is fitted rather than flown to: it has no point of its own, and flying to the
 * middle of a long one puts most of it off the screen when the street is the thing that was
 * picked. An address does have a point, and gets one.
 */
async function flyTo(drawn: Maplibre | null, result: Result): Promise<StreetDetail | null> {
  if (drawn === null) return null;
  try {
    if (result.kind === "street") {
      const found = await street(result.id);
      const [west, south, east, north] = found.bbox;
      drawn.fitBounds([west, south, east, north], {
        padding: 80,
        maxZoom: 16,
        duration: TRAVEL_MS,
        easing: EASE,
      });
      return found;
    }
    const found = await address(result.id);
    drawn.flyTo({
      center: [found.lon, found.lat],
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
