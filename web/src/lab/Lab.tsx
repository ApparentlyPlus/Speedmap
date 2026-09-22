/**
 * The scratchpad. Not a page of the site: a bench for the result screen, so the layout can
 * be argued about against every shape of answer without waiting on the API, the ranker or a
 * network. Dev only, and main.tsx will not route to it in a build.
 *
 * The switcher along the bottom is the point. A screen that reads well on a gigabit address
 * in Athens and falls apart on an island with nothing but satellite is not finished, and
 * the only way to see that is to flip between them in one second.
 */

import { useEffect, useState } from "react";

import { languageOf, type Language } from "../i18n";
import { SCENARIOS, SHAPE, STREET_ID, WHERE } from "./fixtures";
import { Split } from "./Split";
import "../styles/lab.css";

export function Lab(): React.ReactElement {
  const [at, setAt] = useState(0);

  /**
   * The address arrives late, because it does.
   *
   * Place fetches it after the map is already on screen, and the map reads that: given a
   * position at construction it opens on the street, and given none it opens on the
   * country and falls to the street when one turns up. Handing the fixture over at mount
   * skipped the whole descent, so the bench was showing a screen nobody will ever see and
   * the thing most worth looking at could not be looked at.
   */
  const [found, setFound] = useState(false);
  useEffect(() => {
    setFound(false);
    const timer = window.setTimeout(() => setFound(true), 420);
    return () => window.clearTimeout(timer);
  }, [at]);
  const [language, setLanguage] = useState<Language>(languageOf(window.location.pathname));
  const scenario = SCENARIOS[at] ?? SCENARIOS[0];
  if (scenario === undefined) throw new Error("no scenarios to show");

  return (
    <>
      <Split
        key={`${scenario.key}-${language}`}
        name={scenario.name}
        place={scenario.place}
        answer={scenario.answer}
        shape={found ? SHAPE : null}
        where={found ? WHERE : null}
        streetId={found ? STREET_ID : null}
        language={language}
      />

      <div className="lab-bar">
        {SCENARIOS.map((one, index) => (
          <button
            key={one.key}
            type="button"
            className={`lab-pick${index === at ? " lab-pick-on" : ""}`}
            onClick={() => setAt(index)}
          >
            {one.key}
          </button>
        ))}
        <span className="lab-gap" />
        {(["el", "en"] as const).map((code) => (
          <button
            key={code}
            type="button"
            className={`lab-pick${language === code ? " lab-pick-on" : ""}`}
            onClick={() => setLanguage(code)}
          >
            {code}
          </button>
        ))}
      </div>
    </>
  );
}
