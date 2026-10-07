/** The answer screen for a street (Place is the one for a door). */

import { useEffect, useState } from "react";
import type { Geometry } from "geojson";

import { street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { colourFor, mbps } from "../tokens";
import { Logo } from "./Logo";
import { Split } from "./Split";
import { Waiting } from "./Waiting";

export function Road({
  result,
  language,
  onBack,
}: {
  readonly result: Result;
  readonly language: Language;
  readonly onBack: () => void;
}): React.ReactElement {
  const text = strings(language);
  const [found, setFound] = useState<StreetDetail | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const stop = new AbortController();
    setFound(null);
    setFailed(false);
    street(result.id, stop.signal)
      .then((road) => {
        if (!stop.signal.aborted) setFound(road);
      })
      // An abort means we were asked about another street. Treating it as a failure put
      // "not indexed" next to offers it had in fact found.
      .catch(() => {
        if (!stop.signal.aborted) setFailed(true);
      });
    return () => stop.abort();
  }, [result.id]);

  const middle = found === null ? null : centre(found.bbox);
  const bare = found !== null && found.offers.length === 0; // an empty list is a real answer

  return (
    <Split
      where={middle === null ? null : { lon: middle[0], lat: middle[1] }}
      shape={(found?.shape as unknown as Geometry | undefined) ?? null}
      streetId={found?.id ?? null}
      language={language}
    >
      <button className="back split-back" type="button" onClick={onBack}>
        <span aria-hidden="true">←</span> {text.back}
      </button>
      {/* no house: a street isn't one door */}
      <header className="split-title split-road-head">
        <h1 className="split-name">{result.name}</h1>
        <p className="split-where">{result.municipality}</p>
      </header>

      <hr className="split-rule" />

      {found === null && !failed && <Waiting />}

      {(failed || bare) && (
        <div className="bare">
          <span className="bare-mark" aria-hidden="true" />
          <p className="bare-said">{text.notIndexed}</p>
          <p className="bare-why">{text.notIndexedWhy}</p>
        </div>
      )}

      {found !== null && found.offers.length > 0 && (
        <>
          <h2 className="group-head">
            <span className="group-index">/01</span>
            {text.streetHead}
            <span className="group-rule" aria-hidden="true" />
          </h2>
          <ol className="road-cards">
            {byOperator(found.offers).map((operator, rank) => (
              <li
                className="offer road-card"
                key={operator.provider}
                style={
                  {
                    "--brand": brandOf(operator.provider).colour,
                    "--delay": `${Math.min(rank, 8) * 45}ms`,
                  } as React.CSSProperties
                }
              >
                <header className="offer-head">
                  <Logo provider={operator.provider} />
                  <div className="offer-title">
                    <h3 className="offer-plan">{operator.name}</h3>
                    <p className="offer-sub">
                      {text.family[operator.family] ?? operator.family}
                    </p>
                  </div>
                </header>
                <ul className="road-lines">
                  {operator.lines.map((offer) => (
                    <li className="road-line" key={offer.technology}>
                      <span className="road-tech">
                        {text.technology[offer.technology] ?? offer.technology}
                        {/* who built the line, when that isn't the seller: three retailers over
                            one cabinet is one line resold, and read as three networks without
                            this */}
                        {offer.infra_provider !== null &&
                          offer.infra_provider !== offer.provider && (
                            <span className="road-infra">
                              {text.over} {offer.infra_provider}
                            </span>
                          )}
                      </span>
                      {/* Retail speed held to the filing, which is what the street is painted
                          with. The register's band read "not filed" on seven fiber lines in
                          ten. */}
                      {speedOf(offer) === null ? (
                        <span className="road-speed road-speed-none">{text.unfiled}</span>
                      ) : (
                        <span
                          className="road-speed"
                          style={{ color: colourFor(mbps(speedOf(offer) ?? 0)) }}
                        >
                          {speedOf(offer)}
                          <span className="road-unit">Mbps</span>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </>
      )}

      {found !== null && found.offers.length > 0 && (
        <footer className="disclaimer">
          <p>{text.disclaimer}</p>
        </footer>
      )}
    </Split>
  );
}

type StreetOffer = StreetDetail["offers"][number];

/** An offer's retail speed, or null where nothing was filed. */
function speedOf(offer: StreetOffer): number | null {
  return offer.sold_mbps === null || offer.sold_mbps === undefined
    ? null
    : Number(offer.sold_mbps);
}

/**
 * One card per operator, fastest first, and in each the lines fastest first. A row per line
 * type had Telekom four times down the list, split up by whoever sorted between them.
 */
function byOperator(offers: readonly StreetOffer[]): {
  provider: string;
  name: string;
  family: string;
  lines: StreetOffer[];
}[] {
  const groups = new Map<string, StreetOffer[]>();
  for (const offer of offers) {
    groups.set(offer.provider, [...(groups.get(offer.provider) ?? []), offer]);
  }
  const fastest = (lines: StreetOffer[]): number => Math.max(...lines.map((line) => speedOf(line) ?? -1));
  return [...groups.entries()]
    .map(([provider, lines]) => {
      const sorted = [...lines].sort((a, b) => (speedOf(b) ?? -1) - (speedOf(a) ?? -1));
      const first = sorted[0] as StreetOffer;
      return { provider, name: first.provider_name, family: first.family, lines: sorted };
    })
    .sort((a, b) => fastest(b.lines) - fastest(a.lines) || a.name.localeCompare(b.name));
}

/** A street has no point of its own, so stand in the middle of its box. */
function centre(bbox: readonly number[]): [number, number] | null {
  const [west, south, east, north] = bbox;
  if (west === undefined || south === undefined || east === undefined || north === undefined) {
    return null;
  }
  return [(west + east) / 2, (south + north) / 2];
}
