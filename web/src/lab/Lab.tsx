/**
 * A bench for the result screen, not a page of the site. Lets the layout be argued over
 * against every shape of answer without the API, the ranker or a network. Dev only, and
 * main.tsx won't route to it in a build.
 *
 * The switcher at the bottom is the point. A screen that works for gigabit Athens and falls
 * apart on an island with only satellite isn't finished, and you only see that by flipping
 * between them.
 */

import { useEffect, useState } from "react";

import { languageOf, type Language } from "../i18n";
import { SCENARIOS, SHAPE, STREET_ID, WHERE } from "./fixtures";
import { Split } from "./Split";
import "../styles/lab.css";

export function Lab(): React.ReactElement {
  const [at, setAt] = useState(0);

  /**
   * The address arrives late, like it does for real. Place fetches it after the map is on
   * screen. Given a position at construction the map opens on the street, given none it
   * opens on Greece and falls to the street. Handing the fixture over at mount skipped the
   * descent, the part most worth looking at.
   */
  const [found, setFound] = useState(false);
  const [language, setLanguage] = useState<Language>(languageOf(window.location.pathname));
  // the language as well: switching remounts the screen, and with the address already
  // found it opened on the street and skipped the descent
  useEffect(() => {
    setFound(false);
    const timer = window.setTimeout(() => setFound(true), 420);
    return () => window.clearTimeout(timer);
  }, [at, language]);
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
