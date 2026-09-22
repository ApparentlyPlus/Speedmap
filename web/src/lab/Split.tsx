/**
 * The result screen, split down the middle: what was found on the left, where it is on the
 * right. The panel is not a card floating over a map any more, it is half the page, and the
 * map is the other half with nothing drawn over it.
 *
 * The two halves are one surface rather than two. The panel's ground runs solid under the
 * text and thins across the last stretch before the middle, so the map appears out of it
 * rather than starting at an edge. A border down the centre would say these are two things.
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

/** How many plans stand below the verdict before the reader has to ask for more. */
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
  /** The street to keep lit while the rest of the map goes quiet. */
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

  /**
   * How much of the heading size a long address gets to keep.
   *
   * "Ερμού 12" and "Λεωφόρος Μαραθώνος 104" are both addresses and one is three times the
   * other. At one size the short one is right and the long one wraps to three lines and
   * pushes the verdict off the fold. Measured in characters rather than in pixels because
   * the answer has to be known before the browser has laid anything out, and a heading
   * that resizes after it is on screen is worse than one that is slightly small.
   */
  const fit = name.length > 30 ? 0.62 : name.length > 22 ? 0.74 : name.length > 15 ? 0.87 : 1;

  return (
    <main className="split" lang={language}>
      <Anchored
        lon={where?.lon ?? null}
        lat={where?.lat ?? null}
        shape={shape}
        streetId={streetId}
      />

      <section className="split-panel">
        <div className="split-panel-ground" aria-hidden="true" />
        <div className="split-panel-body">
          {/*
* The drawing and the address, side by side and the same height.
 *
  * The house used to sit in a 232 pixel band with the list scrolling under it, which
   * cropped the roof on every mode and left the aerial off the top. It has the whole
    * upper band of the panel now and nothing clips it.
*/}
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

          {/* What the answer means, before the answer. */}
          <p className="split-verdict">{saidAbout(language, verdict, name)}</p>

          {/* No rule here. The plans are the sentence continuing, not a new section. */}
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
