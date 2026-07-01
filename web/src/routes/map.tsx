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
import { GeoJSONSource, Map as Maplibre, NavigationControl } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import {
  address,
  regions,
  search,
  street,
  streetsIn,
  type Drawn,
  type Result,
  type StreetDetail,
} from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { RAMP, UNFILED } from "../tokens";
import { STREETS_BY_PROVIDER, STREETS_LAYER } from "../map/tiles";
import { HOME, REGIONS, SOURCE, streetLayers, style, type Carried } from "../map/style";

/** Below this a viewport is a country, and the answer either way is nothing useful. */
const MIN_ZOOM = 9;

/*
 * Where the streets come from, said once.
 *
 * The style is built here and the layers are rebuilt on every filter change, and the two
 * must agree: a vector tile carries named layers and a layer must say which one it draws,
 * while a GeoJSON source is the layer. Disagreeing means layers that match nothing and
 * paint nothing, without a word of complaint. One constant, so they cannot.
 */
const CARRIED: Carried = "geojson";

/** Long enough that a drag does not become a request per frame. */
const SETTLE_MS = 250;

const EMPTY: Drawn = { type: "FeatureCollection", features: [], truncated: false };

type Showing = "far" | "asking" | "drawn" | "empty" | "failed";

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
  const [showing, setShowing] = useState<Showing>("far");
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    if (holder.current === null || map.current !== null) return;

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
      style: style({ type: "geojson", data: EMPTY }, CARRIED),
      ...(linked ? {} : { center: HOME.centre, zoom: HOME.zoom }),
      attributionControl: false,
      hash: true,
    });
    drawn.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
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
    drawn.on("error", (fault) => {
      setShowing("failed");
      // eslint-disable-next-line no-console
      console.error("map style", fault.error);
    });

    let timer = 0;
    let stop = new AbortController();
    // Its own controller: `look` aborts and replaces the viewport one on every move, and the
    // country's outline is fetched once and is not a viewport request.
    const shape = new AbortController();

    const look = (): void => {
      window.clearTimeout(timer);
      stop.abort();
      stop = new AbortController();
      const here = stop;

      if (drawn.getZoom() < MIN_ZOOM) {
        setShowing("far");
        return;
      }
      timer = window.setTimeout(() => {
        setShowing("asking");
        const bounds = drawn.getBounds();
        streetsIn(
          [bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()],
          drawn.getZoom(),
          here.signal,
        )
          .then((found) => {
            if (here.signal.aborted) return;
            const source = drawn.getSource(SOURCE);
            if (source instanceof GeoJSONSource) source.setData(found);
            setTruncated(found.truncated);
            setShowing(found.features.length === 0 ? "empty" : "drawn");
          })
          .catch((error: unknown) => {
            if (error instanceof DOMException && error.name === "AbortError") return;
            setShowing("failed");
          });
      }, SETTLE_MS);
    };

    /*
     * A street is the only thing on this map, so it is the only thing to click. What comes
     * back is the cabinets it runs through rather than a quote for a door on it: a street
     * has no address of its own, and pretending otherwise would be inventing one.
     */
    drawn.on("click", "streets", (event) => {
      const hit = event.features?.[0];
      const id = hit?.properties?.["id"];
      if (typeof id !== "number") return;
      street(id)
        .then(setPicked)
        .catch(() => setPicked(null));
    });
    drawn.on("mouseenter", "streets", () => {
      drawn.getCanvas().style.cursor = "pointer";
    });
    drawn.on("mouseleave", "streets", () => {
      drawn.getCanvas().style.cursor = "";
    });

    /*
     * The country's shape, fetched once and kept. Without it the first thing anyone sees is
     * a black rectangle and a panel telling them to zoom in, somewhere, with no clue where.
     */
    drawn.on("load", () => {
      regions(shape.signal)
        .then((shapes) => {
          const source = drawn.getSource(REGIONS);
          if (source instanceof GeoJSONSource) source.setData(shapes);
        })
        .catch(() => {
          // The streets are the point; a missing outline is not worth an error over them.
        });
    });

    drawn.on("load", look);
    drawn.on("moveend", look);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
      shape.abort();
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
      search(asked, stop.signal)
        .then((results) => setFound(results.filter((r) => r.kind !== "proposed")))
        .catch(() => setFound([]));
    }, SETTLE_MS);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
    };
  }, [query]);

  /*
   * Repainting is swapping two layers, not reloading the data: the features already carry
   * every operator's number, which is why they are on the feature rather than fetched per
   * filter.
   *
   * Deferred until the style is loaded rather than skipped, because a style that is still
   * loading when the filter changes would otherwise leave the map showing everyone while
   * the panel says one operator — and it is the panel the reader believes.
   */
  useEffect(() => {
    const drawn = map.current;
    if (drawn === null) return;

    const repaint = (): void => {
      for (const layer of ["streets-halo", "streets"]) {
        if (drawn.getLayer(layer) !== undefined) drawn.removeLayer(layer);
      }
      for (const layer of streetLayers(provider, CARRIED)) drawn.addLayer(layer);
    };

    if (drawn.isStyleLoaded()) {
      repaint();
      return;
    }
    drawn.once("styledata", repaint);
    return () => {
      drawn.off("styledata", repaint);
    };
  }, [provider]);

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
                    void flyTo(map.current, result);
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
                style={{ "--brand": brandOf(code).colour } as React.CSSProperties}
                onClick={() => setProvider(provider === code ? null : code)}
              >
                {code}
              </button>
            </li>
          ))}
        </ul>

        <h2 className="atlas-head">{text.byRegion}</h2>
        <div className="atlas-scale">
          <span className="atlas-scale-bar" aria-hidden="true" />
          <span className="atlas-scale-ends">
            <span>{text.noFibre}</span>
            <span>{text.allFibre}</span>
          </span>
        </div>

        <h2 className="atlas-head">{text.legend}</h2>
        <ul className="atlas-ramp">
          {RAMP.map((band) => (
            <li className="atlas-band" key={band.name}>
              <span className="atlas-swatch" style={{ background: band.colour }} />
              {band.floor} Mbps+
            </li>
          ))}
          <li className="atlas-band">
            <span className="atlas-swatch" style={{ background: UNFILED }} />
            {text.unfiled}
          </li>
        </ul>

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
          {showing === "far" && text.mapZoomIn}
          {showing === "asking" && text.searching}
          {showing === "empty" && text.mapNothingHere}
          {showing === "failed" && text.searchFailed}
          {showing === "drawn" && truncated && text.mapTruncated}
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
async function flyTo(drawn: Maplibre | null, result: Result): Promise<void> {
  if (drawn === null) return;
  try {
    if (result.kind === "street") {
      const found = await street(result.id);
      const [west, south, east, north] = found.bbox;
      drawn.fitBounds([west, south, east, north], {
        padding: 80,
        maxZoom: 16,
        duration: 900,
      });
      return;
    }
    const found = await address(result.id);
    drawn.flyTo({ center: [found.lon, found.lat], zoom: 16, duration: 900 });
  } catch {
    // A camera that cannot be moved is not worth an error message on a map.
  }
}

export const LAYER = STREETS_LAYER;
