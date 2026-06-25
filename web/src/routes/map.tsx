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

import { streetsIn, type Drawn } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { RAMP, UNFILED } from "../tokens";
import { STREETS_BY_PROVIDER, STREETS_LAYER } from "../map/tiles";
import { HOME, SOURCE, streetLayers, style } from "../map/style";

/** Below this a viewport is a country, and the answer either way is nothing useful. */
const MIN_ZOOM = 9;

/** Long enough that a drag does not become a request per frame. */
const SETTLE_MS = 250;

const EMPTY: Drawn = { type: "FeatureCollection", features: [], truncated: false };

type Showing = "far" | "asking" | "drawn" | "empty" | "failed";

export function MapPage({ language }: { readonly language: Language }): React.ReactElement {
  const text = strings(language);
  const holder = useRef<HTMLDivElement>(null);
  const map = useRef<Maplibre | null>(null);
  const [provider, setProvider] = useState<string | null>(null);
  const [showing, setShowing] = useState<Showing>("far");
  const [truncated, setTruncated] = useState(false);

  useEffect(() => {
    if (holder.current === null || map.current !== null) return;

    const drawn = new Maplibre({
      container: holder.current,
      style: style({ type: "geojson", data: EMPTY }),
      center: HOME.centre,
      zoom: HOME.zoom,
      attributionControl: false,
      // The camera in the URL, so a view of one neighbourhood is a link to it. Restores on
      // reload too, which is the half that matters while working on a style.
      hash: true,
    });
    drawn.addControl(new NavigationControl({ showCompass: false }), "bottom-right");
    map.current = drawn;
    // A handle for the console while a style is being worked on. Development only: the
    // build strips the branch, so nothing reaches a reader.
    if (import.meta.env.DEV) {
      (window as unknown as { atlas?: Maplibre }).atlas = drawn;
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

    drawn.on("load", look);
    drawn.on("moveend", look);
    return () => {
      window.clearTimeout(timer);
      stop.abort();
      drawn.remove();
      map.current = null;
    };
  }, []);

  // Repainting is swapping two layers, not reloading the data: the features already carry
  // every operator's number, which is why they are on the feature rather than fetched per
  // filter.
  useEffect(() => {
    const drawn = map.current;
    if (drawn === null || !drawn.isStyleLoaded()) return;
    for (const layer of ["streets-halo", "streets"]) {
      if (drawn.getLayer(layer) !== undefined) drawn.removeLayer(layer);
    }
    for (const layer of streetLayers(provider)) drawn.addLayer(layer);
  }, [provider]);

  return (
    <main className="atlas" lang={language}>
      <div className="atlas-canvas" ref={holder} />

      <section className="atlas-panel">
        <a className="atlas-back" href={language === "el" ? "/" : "/en/"}>
          <span aria-hidden="true">←</span> {text.back}
        </a>
        <h1 className="atlas-name">{text.mapTitle}</h1>

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

export const LAYER = STREETS_LAYER;
