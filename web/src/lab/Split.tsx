/**
 * The result screen split in half: findings on the left, the map on the right with nothing
 * drawn over it. The panel used to be a card floating on the map.
 *
 * One surface. The panel's background is solid under the text and thins out just before the
 * middle, so the map emerges from it. A border down the centre would split them into two things.
 */

import { useState } from "react";
import type { Geometry } from "geojson";

import type { Options } from "../api/client";
import { Anchored } from "../components/Anchored";
import { House } from "../components/House";
import { Offer } from "../components/Offer";
import { modeOf } from "../house/mode";
import { strings, type Language } from "../i18n";
import { colourFor, mbps } from "../tokens";
import { saidAbout, verdictOf } from "./verdict";

/** Plans shown under the verdict before "more". */
const SHOWN = 4;

export function Split({
  name,
  place,
  answer,
  shape,
  where,
  streetId,
  language,
}: {
  readonly name: string;
  readonly place: string;
  readonly answer: Options | null;
  readonly shape: Geometry | null;
  readonly where: { lon: number; lat: number } | null;
  /** Stays lit while the rest of the map goes quiet. */
  readonly streetId: number | null;
  readonly language: Language;
}): React.ReactElement {
  const text = strings(language);
  const [chosen, setChosen] = useState<string | null>(null);

  const offers = answer?.options ?? [];
  const selected =
    offers.find((o) => `${o.provider}-${o.plan}` === chosen) ?? offers[0] ?? null;
  const speed =
    selected?.expected_mbps === null || selected?.expected_mbps === undefined
      ? mbps(0)
      : mbps(Number(selected.expected_mbps));

  const verdict = verdictOf(answer);
  const shown = offers.slice(0, SHOWN);

  // Shrink long addresses. "Ερμού 12" and "Λεωφόρος Μαραθώνος 104" can't share one size:
  // at the right size for the short one, the long one wraps to three lines and shoves the
  // verdict below the fold. Counted in characters, since we need the answer before layout,
  // and a heading that resizes on screen is worse than one a touch small.
  const fit = name.length > 30 ? 0.62 : name.length > 22 ? 0.74 : name.length > 15 ? 0.87 : 1;

  return (
    <main className="split" lang={language}>
      <Anchored
        lon={where?.lon ?? null}
        lat={where?.lat ?? null}
        shape={shape}
        streetId={streetId}
      />

      <section className="split-panel" data-covers-map>
        <div className="split-panel-ground" aria-hidden="true" />
        <div className="split-panel-body">
          {/* House and address side by side, same height. In a 232 px band with the list
              scrolling under it, the house lost its roof and aerial in every mode. */}
          <header className="split-head">
            <div className="split-scene">
              <House
                mode={modeOf(selected?.family ?? "fiber")}
                colour={colourFor(speed)}
                mbps={Number(speed)}
                grounded={false}
              />
            </div>
            <div className="split-title">
              <h1 className="split-name" style={{ "--fit": fit } as React.CSSProperties}>
                {name}
              </h1>
              <p className="split-where">{place}</p>
            </div>
          </header>

          <hr className="split-rule" />

          {/* what it means, before the plans */}
          <p className="split-verdict">{saidAbout(language, verdict, name)}</p>

          {/* no rule: the plans continue the sentence */}
          {shown.length === 0 ? (
            <p className="split-empty">{text.nothingHere}</p>
          ) : (
            <ol className="split-offers">
              {shown.map((option, index) => (
                <Offer
                  key={`${option.provider}-${option.plan}`}
                  option={option}
                  language={language}
                  best={index === 0}
                  rank={index}
                  chosen={
                    `${option.provider}-${option.plan}` ===
                    `${selected?.provider}-${selected?.plan}`
                  }
                  onChoose={() => setChosen(`${option.provider}-${option.plan}`)}
                />
              ))}
            </ol>
          )}
        </div>
      </section>
    </main>
  );
}
