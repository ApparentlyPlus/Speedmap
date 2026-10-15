// the answer screen for a street (Place is the one for a door)

import { useEffect, useState } from "react";
import type { Geometry } from "geojson";

import { street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { STREETS_INFRASTRUCTURE } from "../map/tiles";
import { colourFor, mbps } from "../tokens";
import { Logo } from "./Logo";
import { Split } from "./Split";
import { Visit } from "./Visit";
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
      // an abort means another street was asked for, not a failure
      .catch(() => {
        if (!stop.signal.aborted) setFailed(true);
      });
    return () => stop.abort();
  }, [result.id]);

  const middle = found === null ? null : centre(found.bbox);
  const bare = found !== null && found.offers.length === 0; // an empty list is a real answer
  const operators = found === null ? [] : byOperator(found.offers);
  // best a household can buy, wholesale fiber isn't on sale
  const sold = operators.filter((operator) => !WHOLESALE.has(operator.provider));
  const speeds = (sold.length > 0 ? sold : operators).flatMap((operator) => operator.lines.map(speedOf));
  const filed = speeds.filter((speed): speed is number => speed !== null);
  const best = filed.length > 0 ? Math.max(...filed) : null;

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
      {/* no house, a street isn't one door */}
      <header className="split-title split-road-head">
        <h1 className="split-name">{result.name}</h1>
        <p className="split-where">{result.municipality}</p>
      </header>

      {found === null && !failed && <Waiting />}

      {(failed || bare) && (
        <div className="bare">
          <span className="bare-mark" aria-hidden="true" />
          <p className="bare-said">{text.notIndexed}</p>
          <p className="bare-why">{text.notIndexedWhy}</p>
        </div>
      )}

      {found !== null && operators.length > 0 && (
        <>
          {/* how fast, before who sells it */}
          {best !== null && (
            <p className="road-best">
              <span className="road-best-speed" style={{ color: colourFor(mbps(best)) }}>
                {best}
                <span className="road-unit">Mbps</span>
              </span>
              <span className="road-best-said">{text.roadBest}</span>
            </p>
          )}

          <ol className="road-ops">
            {operators.map((operator, rank) => {
              const top = speedOf(operator.lines[0] as StreetOffer);
              // whose network, said once
              const over = [...new Set(
                operator.lines
                  .map((line) => line.infra_provider)
                  .filter((infra): infra is string => infra !== null && infra !== undefined && infra !== operator.provider),
              )];
              return (
                <li
                  className="road-op"
                  key={operator.provider}
                  style={
                    {
                      "--brand": brandOf(operator.provider).colour,
                      "--delay": `${Math.min(rank, 8) * 45}ms`,
                    } as React.CSSProperties
                  }
                >
                  <Logo provider={operator.provider} />
                  <h3 className="road-name">{operator.name}</h3>
                  {top === null ? (
                    <span className="road-speed road-speed-none">{text.unfiled}</span>
                  ) : (
                    <span className="road-speed" style={{ color: colourFor(mbps(top)) }}>
                      {top}
                      <span className="road-unit">Mbps</span>
                    </span>
                  )}
                  <div className="road-more">
                    {/* every line in one row, the same four on every card was noise */}
                    <p className="road-lines">
                      {operator.lines.map((offer) => (
                        <span className="road-line" key={offer.technology}>
                          {text.technology[offer.technology] ?? offer.technology}
                          {speedOf(offer) !== null && <b>{speedOf(offer)}</b>}
                        </span>
                      ))}
                    </p>
                    {over.length > 0 && (
                      <p className="road-infra">
                        {text.over} {new Intl.ListFormat(language, { type: "conjunction" }).format(over.map((code) => brandOf(code).name))}
                      </p>
                    )}
                    {WHOLESALE.has(operator.provider) ? (
                      <p className="road-infra">{text.infrastructure}</p>
                    ) : (
                      <Visit provider={operator.provider} language={language} />
                    )}
                  </div>
                </li>
              );
            })}
          </ol>

          <footer className="disclaimer road-foot">
            <p>{text.disclaimer}</p>
          </footer>
        </>
      )}
    </Split>
  );
}

type StreetOffer = StreetDetail["offers"][number];

function speedOf(offer: StreetOffer): number | null {
  return offer.sold_mbps === null || offer.sold_mbps === undefined
    ? null
    : Number(offer.sold_mbps);
}

// sell to other operators, not households
const WHOLESALE = new Set(STREETS_INFRASTRUCTURE);

// A card per operator, fastest first, lines fastest first inside. A row per line had Telekom
// four times down the list. Wholesalers last however fast.
function byOperator(offers: readonly StreetOffer[]): {
  provider: string;
  name: string;
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
      // the brand, the register spells some in capitals and runs United Fiber together
      return { provider, name: brandOf(provider).name, lines: sorted };
    })
    .sort(
      (a, b) =>
        Number(WHOLESALE.has(a.provider)) - Number(WHOLESALE.has(b.provider)) ||
        fastest(b.lines) - fastest(a.lines) ||
        a.name.localeCompare(b.name),
    );
}

// no point of its own, so the middle of its box
function centre(bbox: readonly number[]): [number, number] | null {
  const [west, south, east, north] = bbox;
  if (west === undefined || south === undefined || east === undefined || north === undefined) {
    return null;
  }
  return [(west + east) / 2, (south + north) / 2];
}
