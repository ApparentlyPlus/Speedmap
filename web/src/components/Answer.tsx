// What an address can get: the house, a sentence, then the plans. No requests, Place fetches.

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

// shown before "more"
const SHOWN = 4;

export function Answer({
  name,
  place,
  answer,
  language,
  onBack,
  failed = false,
  addressId,
  onRouters,
}: {
  readonly name: string;
  readonly place: string;
  readonly answer: Options | null;
  readonly language: Language;
  readonly onBack: () => void;
  // or the panel waits forever
  readonly failed?: boolean;
  readonly addressId: number;
  readonly onRouters?: (() => void) | undefined;
}): React.ReactElement {
  const text = strings(language);
  const [chosen, setChosen] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const offers = answer?.options ?? [];
  // the house shows the fastest line until a plan is picked, the top ranked is often a
  // cheaper 100 and it drew copper next to gigabit fiber
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

  // shrink long addresses, by character count since layout hasn't happened yet
  const fit = name.length > 30 ? 0.62 : name.length > 22 ? 0.74 : name.length > 15 ? 0.87 : 1;

  return (
    <>
      <button className="back split-back" type="button" onClick={onBack}>
        <span aria-hidden="true">←</span> {text.back}
      </button>

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
          <p className="split-verdict">{saidAbout(language, verdictOf(answer), name)}</p>
          {/* the two answers that recommend a mobile router link to the router page */}
          {(verdictOf(answer) === "legacy" || verdictOf(answer) === "wireless") && (
            <a
              className="split-routers"
              href={language === "el" ? "/routers" : "/en/routers"}
              onClick={(event) => {
                if (onRouters === undefined || event.metaKey || event.ctrlKey || event.shiftKey) return;
                event.preventDefault();
                onRouters();
              }}
            >
              {text.whichRouter} <span aria-hidden="true">→</span>
            </a>
          )}

          {/* blocked operators are only shown from the cache, said once */}
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

function day(iso: string, language: Language): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString(language === "el" ? "el-GR" : "en-GB", {
    day: "numeric",
    month: "long",
  });
}
