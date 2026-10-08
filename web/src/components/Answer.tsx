/**
 * What an address can get, as the panel shows it: the house, one sentence on what the answer
 * means, then the plans. Holds no requests: Place fetches, and this draws whatever it's handed.
 */

import { useState } from "react";

import type { Options } from "../api/client";
import { brandOf } from "../brands";
import { modeOf } from "../house/mode";
import { fill, strings, type Language } from "../i18n";
import { colourFor, mbps } from "../tokens";
import { House } from "./House";
import { Offer } from "./Offer";
import { Report } from "./Report";
import { saidAbout, verdictOf } from "./verdict";
import { Waiting } from "./Waiting";

/** Plans shown under the verdict before "more". */
const SHOWN = 4;

export function Answer({
  name,
  place,
  answer,
  language,
  onBack,
  failed = false,
  addressId,
}: {
  readonly name: string;
  readonly place: string;
  /** Null while the first answer is on its way. */
  readonly answer: Options | null;
  readonly language: Language;
  readonly onBack: () => void;
  /** The first answer isn't coming. Without this the panel waited for it forever. */
  readonly failed?: boolean;
  readonly addressId: number;
}): React.ReactElement {
  const text = strings(language);
  const [chosen, setChosen] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const offers = answer?.options ?? [];
  // Until a plan is picked the house shows the fastest line here, not the top of the list.
  // The list is ranked by what's worth buying, often a cheaper 100 Mbps plan, and the house
  // drew copper at an address with gigabit fiber. Ties go to the higher-ranked plan.
  const fastest = offers.reduce<(typeof offers)[number] | null>(
    (best, o) =>
      best === null || Number(o.expected_mbps ?? 0) > Number(best.expected_mbps ?? 0) ? o : best,
    null,
  );
  const selected = offers.find((o) => `${o.provider}-${o.plan}` === chosen) ?? fastest;
  const speed = selected?.expected_mbps === null || selected?.expected_mbps === undefined
    ? mbps(0)
    : mbps(Number(selected.expected_mbps));

  const shown = open ? offers : offers.slice(0, SHOWN);
  const held = offers.length - shown.length;

  // Shrink long addresses. "Ερμού 12" and "Λεωφόρος Μαραθώνος 104" can't share one size:
  // at the right size for the short one, the long one wraps to three lines and shoves the
  // verdict below the fold. Counted in characters, since we need the answer before layout,
  // and a heading that resizes on screen is worse than one a touch small.
  const fit = name.length > 30 ? 0.62 : name.length > 22 ? 0.74 : name.length > 15 ? 0.87 : 1;

  return (
    <>
      <button className="back split-back" type="button" onClick={onBack}>
        <span aria-hidden="true">←</span> {text.back}
      </button>

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

      {answer === null && failed ? (
        <p className="split-empty">{text.answerFailed}</p>
      ) : answer === null ? (
        <Waiting />
      ) : (
        <>
          {/* what it means, before the plans */}
          <p className="split-verdict">{saidAbout(language, verdictOf(answer), name)}</p>

          {/* An operator blocking us is asked nothing until its rest is over, so what shows for
              it is the cache. Said once, quietly, and only then. */}
          {answer.operators
            .filter((operator) => operator.state === "blocked")
            .map((operator) => (
              <p className="split-cached" key={operator.provider}>
                {fill(operator.answered_on ? text.cachedFrom : text.cachedNever, {
                  operator: brandOf(operator.provider).name,
                  date: operator.answered_on ? day(operator.answered_on, language) : "",
                })}
              </p>
            ))}

          {/* no rule: the plans continue the sentence */}
          {offers.length === 0 ? (
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

          {(held > 0 || open) && (
            <button
              className="expand"
              type="button"
              aria-expanded={open}
              onClick={() => setOpen(!open)}
            >
              <span className={`expand-arrow${open ? " expand-arrow-up" : ""}`} aria-hidden="true">
                ↓
              </span>
              {open ? text.fewer : `+${held} ${text.more}`}
            </button>
          )}

          <footer className="disclaimer">
            <p>{text.disclaimer}</p>
            <Report addressId={addressId} language={language} />
          </footer>
        </>
      )}
    </>
  );
}

/** "3 October", in the reader's language. */
function day(iso: string, language: Language): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(language === "el" ? "el-GR" : "en-GB", {
    day: "numeric",
    month: "long",
  });
}
