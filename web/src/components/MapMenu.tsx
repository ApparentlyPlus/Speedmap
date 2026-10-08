/**
 * The map's menu, and the card for whatever was pressed on the map. One surface in the corner
 * beside the search bar: shut, it's a button the bar's own height, and it grows out of that
 * button into the filters, a street or a measured square, and back into it.
 *
 * Its size is measured. Left to CSS, animating to height: auto guessed at sizes the content
 * hadn't reached, the content vanished the instant it shut, and the button shrank and slid while
 * the panel grew round it. Now the content is laid out at full size from the start, the surface
 * animates between two measured boxes and uncovers it, the button never moves, and the content
 * stays until the surface has closed over it.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { VIEWS, type View } from "../map/style";
import { STREETS_BY_PROVIDER, STREETS_INFRASTRUCTURE, type Cell } from "../map/tiles";
import { UNSERVED, bandsPainted, colourFor, mbps } from "../tokens";

/** What was pressed on the map, which the menu shows in place of itself. */
export type Picked =
  | { readonly kind: "street"; readonly street: StreetDetail }
  | { readonly kind: "cell"; readonly cell: Cell };

type Mode = "menu" | Picked["kind"];

/** The button, which is also the shut surface: the search bar's height. */
const KNOB = 46;

/** As long as the surface takes to shut, so the content isn't pulled out from under it. */
const CLOSE_MS = 340;

/**
 * Suppliers you can buy from, and networks you can't. Read off the tile contract, so a provider
 * added to the schema lands in the right group without touching this file.
 */
const WHOLESALE = new Set(STREETS_INFRASTRUCTURE);
const RETAILERS = Object.keys(STREETS_BY_PROVIDER).filter((code) => !WHOLESALE.has(code));
const NETWORKS = Object.keys(STREETS_BY_PROVIDER).filter((code) => WHOLESALE.has(code));

type Filters = {
  readonly language: Language;
  readonly view: View;
  readonly setView: (view: View) => void;
  readonly provider: string | null;
  readonly setProvider: (provider: string | null) => void;
  readonly regions: boolean;
  readonly setRegions: (on: boolean) => void;
};

export function MapMenu({
  open,
  setOpen,
  picked,
  shutPicked,
  ...filters
}: Filters & {
  readonly open: boolean;
  readonly setOpen: (open: boolean) => void;
  readonly picked: Picked | null;
  readonly shutPicked: () => void;
}): React.ReactElement {
  const text = strings(filters.language);
  const target: Mode | null = open ? "menu" : picked === null ? null : picked.kind;

  // what's drawn inside lags the target on the way shut
  const [shown, setShown] = useState<Mode | null>(target);
  const kept = useRef<Picked | null>(picked);
  if (picked !== null) kept.current = picked;

  useEffect(() => {
    if (target !== null) {
      setShown(target);
      return;
    }
    const timer = window.setTimeout(() => setShown(null), CLOSE_MS);
    return () => window.clearTimeout(timer);
  }, [target]);

  const inner = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  useLayoutEffect(() => {
    const box = inner.current;
    if (box === null) {
      setSize(null);
      return;
    }
    const measure = (): void => setSize({ width: box.offsetWidth, height: box.offsetHeight });
    measure();
    const watching = new ResizeObserver(measure);
    watching.observe(box);
    return () => watching.disconnect();
  }, [shown]);

  const grown = target !== null && size !== null;
  const surface = grown ? size : { width: KNOB, height: KNOB };
  const filtered = filters.provider !== null || filters.view !== "coverage" || filters.regions;
  const card = kept.current;
  const knob = target !== null ? " map-knob-open" : filtered ? " map-knob-filtered" : "";

  return (
    <div
      className={`map-menu${grown ? " map-menu-grown" : ""}${target === null ? " map-menu-shutting" : ""}`}
      style={{ width: surface.width, height: surface.height }}
    >
      {shown !== null && (
        <div className={`map-menu-inner map-menu-${shown}`} ref={inner} key={shown} inert={target === null}>
          {shown === "menu" && (
            <>
              <h1 className="map-menu-title">{text.mapTitle}</h1>
              <Choices {...filters} />
            </>
          )}
          {shown === "street" && card?.kind === "street" && (
            <StreetCard language={filters.language} street={card.street} />
          )}
          {shown === "cell" && card?.kind === "cell" && (
            <CellCard language={filters.language} cell={card.cell} />
          )}
        </div>
      )}
      <button
        type="button"
        className={`map-knob${knob}`}
        aria-label={target === null ? text.mapOptions : text.mapClose}
        aria-expanded={target !== null}
        onClick={() => {
          if (target === "menu") setOpen(false);
          else if (target !== null) shutPicked();
          else setOpen(true);
        }}
      >
        <span className="map-knob-bar" aria-hidden="true" />
        <span className="map-knob-bar" aria-hidden="true" />
        <span className="map-knob-bar" aria-hidden="true" />
      </button>
    </div>
  );
}

function Choices(props: Filters): React.ReactElement {
  const { language, view, setView, regions, setRegions } = props;
  const text = strings(language);
  return (
    <div className="map-choices">
      <div className="map-seg" role="radiogroup" aria-label={text.shown}>
        {VIEWS.map((one) => (
          <button
            key={one}
            type="button"
            role="radio"
            aria-checked={view === one}
            className={`map-seg-one${view === one ? " map-seg-on" : ""}`}
            onClick={() => setView(one)}
          >
            {text.views[one]}
          </button>
        ))}
      </div>

      {view === "coverage" && (
        <>
          <h2 className="map-choices-head">{text.operator}</h2>
          <Operators {...props} codes={RETAILERS} anyone />
          {/* Wholesale builders, plus Metadosis (files services, publishes no tariff). Beside
              Telekom and Vodafone they looked like suppliers you could pick, and leaving them out
              would hide the fiber that decides whether anyone sells a gigabit here. */}
          <h2 className="map-choices-head" title={text.infrastructureHint}>
            {text.infrastructure}
          </h2>
          <Operators {...props} codes={NETWORKS} />
        </>
      )}

      {/* a switch, since it's an overlay that's on or off and not one of the choices above */}
      <label className="map-switch" title={text.regionsHint}>
        <input type="checkbox" checked={regions} onChange={(event) => setRegions(event.target.checked)} />
        <span className="map-switch-track" aria-hidden="true" />
        {text.regions}
      </label>

      <Legend language={language} view={view} />

      <a className="map-choices-back" href={language === "el" ? "/" : "/en/"}>
        {text.back}
      </a>
    </div>
  );
}

function Operators({
  language,
  provider,
  setProvider,
  codes,
  anyone = false,
}: Filters & { readonly codes: readonly string[]; readonly anyone?: boolean }): React.ReactElement {
  const text = strings(language);
  return (
    <ul className="map-ops">
      {anyone && (
        <li>
          <button
            type="button"
            className={`map-op map-op-any${provider === null ? " map-op-on" : ""}`}
            aria-pressed={provider === null}
            onClick={() => setProvider(null)}
          >
            <span className="map-op-dot" aria-hidden="true" />
            {text.anyOperator}
          </button>
        </li>
      )}
      {codes.map((code) => {
        const brand = brandOf(code);
        const on = provider === code;
        return (
          <li key={code}>
            <button
              type="button"
              className={`map-op${on ? " map-op-on" : ""}`}
              style={{ "--brand": brand.colour } as React.CSSProperties}
              aria-pressed={on}
              onClick={() => setProvider(on ? null : code)}
            >
              <span className="map-op-dot" aria-hidden="true" />
              {/* the brand people know: nobody shops at "OTE" when the bill says Telekom */}
              {brand.name}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The ramp as one bar, labelled at the bands this view paints. Coverage never lands between
 * 100 and 1000, so it shows four bands and not the seven the measured views can use.
 */
function Legend({ language, view }: { readonly language: Language; readonly view: View }) {
  const text = strings(language);
  const bands = [...bandsPainted(view !== "coverage")].reverse();
  return (
    <div className="map-legend">
      <h2 className="map-choices-head">{text.legend[view]}</h2>
      <div className="map-legend-bar" aria-hidden="true">
        {bands.map((band) => (
          <span key={band.name} style={{ background: band.colour }} />
        ))}
      </div>
      <div className="map-legend-marks">
        {bands.map((band) => (
          <span key={band.name}>{band.name.replace(" Mbps", "")}</span>
        ))}
      </div>
      {/* Coverage: no line reaches the street, dark because it's absence and not a slow
          street. Measured: nobody has run a speed test here, which is most of Greece. */}
      <p className="map-legend-none">
        <span style={{ background: UNSERVED }} aria-hidden="true" />
        {view === "coverage" ? text.unreached : text.untested}
      </p>
    </div>
  );
}

type Line = StreetDetail["offers"][number];

/**
 * One row per operator and each operator's lines fastest first. Retailers come before the
 * wholesalers, however fast: a wholesaler's gigabit topped the list on Ερμού, and nobody can
 * buy from them.
 */
function byOperator(offers: readonly Line[]): { code: string; lines: Line[] }[] {
  const groups = new Map<string, Line[]>();
  for (const offer of offers) groups.set(offer.provider, [...(groups.get(offer.provider) ?? []), offer]);
  const speed = (line: Line): number => Number(line.sold_mbps ?? -1);
  const best = (lines: Line[]): number => Math.max(...lines.map(speed));
  return [...groups.entries()]
    .map(([code, lines]) => ({ code, lines: [...lines].sort((a, b) => speed(b) - speed(a)) }))
    .sort((a, b) =>
      Number(WHOLESALE.has(a.code)) - Number(WHOLESALE.has(b.code)) || best(b.lines) - best(a.lines));
}

function StreetCard({ language, street }: { readonly language: Language; readonly street: StreetDetail }) {
  const text = strings(language);
  const operators = byOperator(street.offers);
  return (
    <article className="map-card">
      <h2 className="map-card-name">{street.name}</h2>
      <p className="map-card-where">{street.municipality}</p>
      {operators.length === 0 ? (
        <p className="map-card-none">{text.mapNothingHere}</p>
      ) : (
        <ul className="map-card-rows">
          {operators.map((op) => (
            <li key={op.code} style={{ "--brand": brandOf(op.code).colour } as React.CSSProperties}>
              <span className="map-card-op">
                <span className="map-op-dot" aria-hidden="true" />
                {brandOf(op.code).name}
              </span>
              <span className="map-card-lines">
                {op.lines.map((line) => (
                  <span key={line.technology}>
                    {text.technology[line.technology] ?? line.technology}
                    {/* who built it, when that isn't the seller: three retailers over one
                        cabinet is one line resold, and read as three networks without this */}
                    {line.infra_provider !== null && line.infra_provider !== line.provider && (
                      <span className="map-card-over">
                        {" "}
                        {text.over} {line.infra_provider}
                      </span>
                    )}
                    {/* the retail speed held to the filing, which is what the street is painted
                        with. The register's own band is missing on seven fiber filings in ten */}
                    {line.sold_mbps === null || line.sold_mbps === undefined ? (
                      <b className="map-card-unfiled">{text.unfiled}</b>
                    ) : (
                      <b style={{ color: colourFor(mbps(Number(line.sold_mbps))) }}>
                        {Number(line.sold_mbps)}
                      </b>
                    )}
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

/** A measured square, straight off the tile: it carries everything shown, so no request. */
function CellCard({ language, cell }: { readonly language: Language; readonly cell: Cell }) {
  const text = strings(language);
  return (
    <article className="map-card">
      <h2 className="map-card-name">{text.measuredHere}</h2>
      <p className="map-card-where">
        {text.views[cell.family === "mobile" ? "mobile" : "measured"]}, {cell.tests} {text.tests}
      </p>
      <ul className="map-card-rows">
        <li>
          <span className="map-card-op">{text.down}</span>
          <b style={{ color: colourFor(mbps(Number(cell.down_mbps))) }}>
            {Math.round(Number(cell.down_mbps))} Mbps
          </b>
        </li>
        <li>
          <span className="map-card-op">{text.up}</span>
          <b>{Math.round(Number(cell.up_mbps))} Mbps</b>
        </li>
      </ul>
    </article>
  );
}
