/**
 * A street, when a street is what was asked for.
 *
 * Someone who types a street name without a number is not being vague, they are asking
 * about the road: which operators reach it and how fast. That is a real answer and the
 * register holds it, so it is given — rather than the search insisting on a door first.
 *
 * What it cannot do is price anything. A plan is sold to an address, and the cheapest
 * offer on a street is a different number at each end of it, so this lists who reaches the
 * street and at what speed and stops there.
 */

import { useEffect, useState } from "react";
import type { Geometry } from "geojson";

import { street, type Result, type StreetDetail } from "../api/client";
import { brandOf } from "../brands";
import { strings, type Language } from "../i18n";
import { Anchored } from "./Anchored";
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
      // An abort is this component being asked something else, not the street failing to
      // answer. Counted as a failure it puts "not indexed" beside the offers it did find.
      .catch(() => {
        if (!stop.signal.aborted) setFailed(true);
      });
    return () => stop.abort();
  }, [result.id]);

  const middle = found === null ? null : centre(found.bbox);
  // Nothing filed is not a failure to answer, it is the answer.
  const bare = found !== null && found.offers.length === 0;

  return (
    <>
      <Anchored
        lon={middle?.[0] ?? null}
        lat={middle?.[1] ?? null}
        shape={(found?.shape as unknown as Geometry | undefined) ?? null}
        streetId={found?.id ?? null}
      />

      <section className="place place-road">
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
                      {/*
                        Who built the line, when it was not the operator selling it. Three
                        retailers over one cabinet is one line resold three times, and
                        without this it reads as three networks reaching the street.
                      */}
                      {offer.infra_provider !== null &&
                        offer.infra_provider !== offer.provider && (
                          <span className="road-infra">
                            {" "}
                            · {text.over} {offer.infra_provider}
                          </span>
                        )}
                    </span>
                    <span className="road-speed">
                      {offer.speed === null ? text.unfiled : offer.speed.label}
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

/** A street has no point of its own; the middle of its extent is where to stand. */
function centre(bbox: readonly number[]): [number, number] | null {
  const [west, south, east, north] = bbox;
  if (west === undefined || south === undefined || east === undefined || north === undefined) {
    return null;
  }
  return [(west + east) / 2, (south + north) / 2];
}
