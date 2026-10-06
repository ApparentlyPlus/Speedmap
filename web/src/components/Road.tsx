/** The answer screen for a street (Place is the one for a door). */

import { useEffect, useState } from "react";
import type { Geometry } from "geojson";

import { street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { Anchored } from "./Anchored";
import { Credit } from "./Credit";
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
  // an empty list is a real answer
  const bare = found !== null && found.offers.length === 0;

  return (
    <>
      <Anchored
        lon={middle?.[0] ?? null}
        lat={middle?.[1] ?? null}
        shape={(found?.shape as unknown as Geometry | undefined) ?? null}
        streetId={found?.id ?? null}
      />
      <Credit language={language} />

      <section className="place place-road" data-covers-map>
        <div className="place-body">
          <header className="place-head">
            <button className="back" type="button" onClick={onBack}>
              <span aria-hidden="true">←</span> {text.back}
            </button>
            <h1 className="place-name">{result.name}</h1>
            <p className="place-where">{result.municipality}</p>
          </header>

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
              <ul className="road-offers">
                {found.offers.map((offer) => (
                  <li className="road-offer" key={`${offer.provider}-${offer.technology}`}>
                    <span
                      className="road-dot"
                      style={{ background: brandOf(offer.provider).colour }}
                    />
                    <span className="road-name">{offer.provider_name}</span>
                    <span className="road-tech">
                      {offer.technology}
                      {/* who built the line, when that isn't the seller: three retailers over one cabinet
                          is one line resold, and read as three networks without this */}
                      {offer.infra_provider !== null &&
                        offer.infra_provider !== offer.provider && (
                          <span className="road-infra">
                            {" "}
                            · {text.over} {offer.infra_provider}
                          </span>
                        )}
                    </span>
                    {/* Retail speed held to the filing, which is what the street is painted with. The
                        register's band read "not filed" on seven fiber lines in ten. */}
                    <span className="road-speed">
                      {offer.sold_mbps === null || offer.sold_mbps === undefined
                        ? text.unfiled
                        : `${Number(offer.sold_mbps)} Mbps`}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {found !== null && found.offers.length > 0 && (
            <footer className="disclaimer">
              <p>{text.disclaimer}</p>
            </footer>
          )}
        </div>
      </section>
    </>
  );
}

/** A street has no point of its own, so stand in the middle of its box. */
function centre(bbox: readonly number[]): [number, number] | null {
  const [west, south, east, north] = bbox;
  if (west === undefined || south === undefined || east === undefined || north === undefined) {
    return null;
  }
  return [(west + east) / 2, (south + north) / 2];
}
