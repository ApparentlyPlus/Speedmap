/**
 * The map: every street in the country, coloured by the fastest line known to reach it.
 * Filterable to one operator, since "can I get Vodafone here" is what most people arrive asking.
 */

import { useEffect, useRef, useState } from "react";
import { Map as Maplibre, NavigationControl, type Point as MapPoint } from "maplibre-gl";
import type { Geometry } from "geojson";

import { address, search, street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { Credit } from "../components/Credit";
import { engine, whenLoaded } from "../map/engine";
import { Tilt } from "../map/tilt";
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
  regionOpacity,
  regionPaint,
  style,
  type View,
} from "../map/style";

/** Sources the page can live without. Anything else failing gets reported. */
const OPTIONAL_SOURCES = new Set<string>([BASE, BUILDINGS]);

/** Long enough to follow with the eye. */
const TRAVEL_MS = 2200;

/** As close as the camera will get to a short street. */
const CLOSEST = 16;

/** Gap between the street and whatever sits nearest it on screen. */
const EDGE = 44;

/**
 * Suppliers you can buy from, and networks you can't. Read off the tile contract so a new
 * provider in the schema lands in the right half of the panel without touching this file.
 */
const WHOLESALE = new Set(STREETS_INFRASTRUCTURE);
const OPERATORS = Object.keys(STREETS_BY_PROVIDER);
const RETAILERS = OPERATORS.filter((code) => !WHOLESALE.has(code));
const NETWORKS = OPERATORS.filter((code) => WHOLESALE.has(code));

/** Slow at both ends. Linear travel starts and stops at full speed and jolts at each end. */
const EASE = (t: number): number =>
  t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;

/** Long enough that a typist doesn't fire a request per letter. */
const SETTLE_MS = 250;

/** Fade-in for the footprints once the whole view has them. */
const RAISE_MS = 220;

/** Longest the city stays blank waiting on a tile that may never come. */
const WAIT_CAP = 3000;

type Showing = "ready" | "failed";

export function MapPage({ language }: { readonly language: Language }): React.ReactElement {
  const text = strings(language);
  const box = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Maplibre | null>(null);
  // the camera from the URL the reader arrived on, read before the map rewrites the hash
  const arrived = useRef(window.location.hash);
  const [provider, setProvider] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Result[]>([]);
  const [chosen, setChosen] = useState<StreetDetail | null>(null);
  // a measured square, straight off the tile: it carries everything shown, so no request
  const [cell, setCell] = useState<Cell | null>(null);
  const [view, setView] = useState<View>("coverage");
  const [regions, setRegions] = useState(false);
  const [showing, setShowing] = useState<Showing>("ready");
  // the filters and legend on a phone, shut until asked for (see the panel)
  const [more, setMore] = useState(false);

  useEffect(() => {
    if (box.current === null || mapRef.current !== null) return;

    engine();

    // The camera lives in the URL so a view is shareable. HOME only applies when the reader
    // didn't arrive on such a link.
    const linked = arrived.current.length > 1;
    if (linked && window.location.hash.length <= 1) {
      window.history.replaceState(null, "", arrived.current);
    }

    const map = new Maplibre({
      container: box.current,
      style: style(),
      ...(linked ? {} : { center: HOME.centre, zoom: HOME.zoom }),
      // credited on /attribution, behind the corner link
      attributionControl: false,
      hash: true,
      maxBounds: LIMITS,
      minZoom: FLOOR_ZOOM,
      // The default cache holds about five zooms. Zooming out four and back came to 96 ms a
      // move, all of it decoding tiles we'd already had.
      maxTileCacheZoomLevels: 12,
      // the archive is swapped whole, weekly, and its URL is stable within a session
      refreshExpiredTiles: false,
    });
    // Same width as the stylesheet's narrow layout
    const narrow = window.matchMedia("(width <= 560px)").matches;
    map.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    // phones only (see Tilt). Added after, so it sits above the zoom buttons
    if (narrow) map.addControl(new Tilt(text.tilt), "bottom-right");
    mapRef.current = map;

    // A phone held upright is narrower than Greece at FLOOR_ZOOM: Corfu and Rhodes sat off
    // either edge and no amount of pinching brought them in. There the floor, and the opening
    // view, come from fitting the country into what the panel leaves.
    //
    // The bounds grow to take in that whole view. MapLibre keeps the screen inside them, and
    // a tall screen fitted to Greece's width shows sea above and below LIMITS, so it zoomed
    // straight back in.
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
    // for the console and the browser test, which checks the map actually drew something
    if (import.meta.env.DEV) {
      window.atlas = map;
    }

    // squares under Measured, streets below
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

    // A line is three pixels across and a thumb isn't. Try the exact point first so a
    // direct hit wins, then a padded box around it.
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

    // Only the latest click may fill the panel. Two quick clicks used to race, and the
    // slower answer (often the first street clicked) won.
    let clicked = 0;
    map.on("click", (event) => {
      const id = streetUnder(event.point);
      if (id === null) return;
      setCell(null);
      const mine = ++clicked;
      street(id)
        .then((found) => {
          if (mine === clicked) setChosen(found);
        })
        .catch(() => {
          if (mine === clicked) setChosen(null);
        });
    });

    // At most once a frame, and never mid-drag: that's when the main thread is busiest,
    // and the answer is stale a frame later anyway.
    let asking = false;
    map.on("mousemove", (event) => {
      if (asking || map.isMoving()) return;
      asking = true;
      requestAnimationFrame(() => {
        asking = false;
        map.getCanvas().style.cursor = streetUnder(event.point) === null ? "" : "pointer";
      });
    });

    // Over Athens a building tile is 600 kB and takes a quarter second, so zooming in, the
    // footprints landed in four separate waves (600, 628, 674 and 718 ms). We hold them at
    // zero for the zoom and raise the whole view at once.
    //
    // Only when none were on screen to start with. Buildings already drawn stay put, so
    // panning around inside the city is unchanged.
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
      // a tile that never arrives can't leave the city blank
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
      // Basemap and footprints come out of planetiler, outside this repo, so a fresh clone
      // won't have them. Worth a console line. Telling the reader the map failed while it's
      // drawing every street they came for would be wrong.
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
    // built once. The language is fixed for the page, so the tilt label can't go stale
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Same index as the landing page. Two search boxes disagreeing about which streets exist
  // would be a bug report waiting to happen.
  useEffect(() => {
    const asked = query.trim();
    if (asked.length < 2) {
      setResults([]);
      return;
    }
    const stop = new AbortController();
    const timer = window.setTimeout(() => {
      // Streets only. A typed number picks its street, since a map has nowhere to put a door.
      search(asked, stop.signal, "street")
        .then(setResults)
        .catch(() => setResults([]));
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
    };
  }, [query]);

  // switching operator touches two properties on two layers
  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;

    const apply = (): void => {
      const filter = only(provider);
      for (const [layer, paint] of Object.entries(ramps(provider))) {
        // continue, don't return: a return here once left the filter half applied and skipped
        // the view switch below
        if (map.getLayer(layer) === undefined) continue;
        map.setPaintProperty(layer, "line-color", paint);
        map.setFilter(layer, filter);
      }

      // Filed and measured answer different questions, so only one shows at a time. Mixed,
      // a street coloured by a promise would sit beside a square coloured by a speed test.
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
      // the choropleth follows whichever view is on
      for (const layer of REGION_LAYERS) {
        if (map.getLayer(layer) === undefined) continue;
        map.setLayoutProperty(layer, "visibility", regions ? "visible" : "none");
      }
      if (map.getLayer("regions") !== undefined) {
        map.setPaintProperty("regions", "fill-color", regionPaint(view));
        map.setPaintProperty("regions", "fill-opacity", regionOpacity(view));
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

    return whenLoaded(map, apply);
  }, [provider, view, regions]);

  // light up the selected street, or nothing
  useEffect(() => {
    const map = mapRef.current;
    if (map === null) return;
    const apply = (): void => {
      const streetId = chosen?.id ?? null;
      const lit = onlyStreet(streetId);
      for (const layer of ["streets-picked-halo", "streets-picked"]) {
        if (map.getLayer(layer) === undefined) continue;
        // hidden when nothing's chosen, so no tile work for a layer drawing nothing
        map.setLayoutProperty(layer, "visibility", streetId === null ? "none" : "visible");
        map.setFilter(layer, lit);
        // filters can't transition and opacity can, so the fade lives on opacity
        map.setPaintProperty(layer, "line-opacity", streetId === null ? 0 : LIT[layer]);
      }
    };

    return whenLoaded(map, apply);
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
                    // select first, then travel (see travelTo for why)
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
                  {/* 7,320 names cover two or more roads in one municipality. The locality
                      their doors agree on is what tells them apart. No doors, no label. */}
                  <span className="atlas-hit-where">
                    {[result.locality, result.municipality].filter(Boolean).join(" · ")}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}

        {/* Phones only. The whole panel sat over the top half of the map with the bottom of
            it cut off, so on a narrow screen everything below the search folds behind this.
            It names the filter in force, which otherwise disappears with it. */}
        <button
          type="button"
          className="atlas-more-toggle"
          aria-expanded={more}
          aria-controls="atlas-more"
          onClick={() => setMore(!more)}
        >
          <span>{text.filters}</span>
          <span className="atlas-more-now">
            {view !== "coverage"
              ? text.views[view]
              : provider !== null
                ? brandOf(provider).name
                : null}
          </span>
        </button>

        <div className="atlas-more" id="atlas-more" data-open={more}>
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

          {/* A checkbox, since this is an overlay that's on or off. As a pill it sat in a row
              of mutually exclusive choices and looked like one of them. */}
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
                      {/* the brand people know: the code is a join key, and nobody shops at "OTE"
                          when the shop, the bill and the router all say Telekom */}
                      {brandOf(code).name}
                    </button>
                  </li>
                ))}
              </ul>

              {/* Wholesale builders, plus Metadosis (files services, publishes no tariff). Next
                  to Telekom and Vodafone they looked like suppliers you could pick. Dropping them
                  would hide the fiber that decides whether anyone sells a gigabit here. */}
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
          {/* Only the bands this view can paint. A filing can only cap a street below its retail
              speed, so coverage never lands between 100 and 1000 and three ramp rows would be
              colours the map never uses. Measured is continuous (median 60, p90 270). */}
          <ul className="atlas-ramp">
            {bandsPainted(view !== "coverage").map((band) => (
              <li className="atlas-band" key={band.name}>
                <span className="atlas-swatch" style={{ background: band.colour }} />
                {band.name}
              </li>
            ))}
            {/* Coverage: a street no line reaches, dark because it's absence and not a slow street.
                Measured and Mobile: nobody has ever run a speed test here, which is most of Greece.
                There used to be a third state, "reaches, no speed filed". The figure comes from
                the technology now, so anything that reaches a street has a number. */}
            <li className="atlas-band">
              <span className="atlas-swatch" style={{ background: UNSERVED }} />
              {view === "coverage" ? text.unreached : text.untested}
            </li>
          </ul>
        </div>

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
                    {/* The retail speed, held to the filing. The register's own band stays out of
                        the panel: it's missing on seven filings in ten. */}
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
 * The part of the map the panel doesn't cover. The panel floats over the map (232 px down the
 * left on wide screens, a band across the top on narrow ones, as tall as it's open), so
 * fitting a street to the whole canvas parked it under the panel about half the time.
 */
function clearOf(map: Maplibre): { top: number; right: number; bottom: number; left: number } {
  const pad = { top: EDGE, right: EDGE, bottom: EDGE, left: EDGE };
  const box = map.getContainer().getBoundingClientRect();
  const panel = document.querySelector(".atlas-panel")?.getBoundingClientRect();
  if (panel === undefined) return pad;

  // wide screens: a column down one side. narrow: a band across the top
  if (panel.width >= box.width * 0.75) {
    pad.top = Math.min(panel.bottom - box.top + EDGE, box.height * 0.6);
  } else {
    pad.left = Math.min(panel.right - box.left + EDGE, box.width * 0.6);
  }
  return pad;
}

/** Two frames, enough for React to commit and MapLibre to restyle. */
function settled(): Promise<void> {
  return new Promise((done) => {
    requestAnimationFrame(() => requestAnimationFrame(() => done()));
  });
}

/**
 * Light the street, then fly to it. In that order.
 *
 * Selecting a street switches two layers on, and MapLibre re-parses every tile in view for
 * them. Start the flight first and the re-parse lands on its opening frames: the camera
 * sets off, stalls, then lurches to catch up. So we pick, wait two frames, then move.
 *
 * The frame is the street's longest run. A name can cover two runs a few blocks apart,
 * and fitting both frames the empty gap between them.
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
    // same cast as Place and Road: the schema types this as an open record, PostGIS fills it
    const shape = found.shape as unknown as Geometry;
    const extent =
      focusOf(shape) ??
      extentOf(shape) ??
      ([[west, south], [east, north]] as [[number, number], [number, number]]);

    // cameraForBounds works out the frame without moving anything, so the trip is one eased
    // move. fitBounds re-decides its target mid-flight.
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
    // a camera that won't move isn't worth an error message
    pick(null);
  }
}

export const LAYER = STREETS_LAYER;
