/**
 * The landing state.
 *
 * One question, one field, one quiet way out. The tagline sits at the optical centre rather
 * than the true middle, because text centred at 50% reads low.
 *
 * A lamp sits below the fold and comes on with the page. It belongs to this state only: a
 * light rising through a column of prices lights nothing and reads as a smudge under the
 * last card, so the results are lit by nothing and bounded by hairlines instead.
 */

import { useState } from "react";

import { askFor, type Result } from "../api/client";
import { Network } from "../components/Network";
import { Place } from "../components/Place";
import { Search } from "../components/Search";
import { languageOf, strings } from "../i18n";

export function Landing(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);
  /* Three states, one route, no reload: the network never restarts. */
  const [picked, setPicked] = useState<Result | null>(null);
  const [making, setMaking] = useState(false);
  const [failed, setFailed] = useState(false);

  /*
   * A proposed row is a door on a known street that nobody filed, so it has no address to
   * open yet. Choosing it is what makes it — once, and kept — and from the next line down
   * it is an address like any other.
   */
  const pick = (result: Result): void => {
    const street = result.street_id;
    if (result.kind !== "proposed" || street === null || street === undefined) {
      setPicked(result);
      return;
    }
    setFailed(false);
    setMaking(true);
    askFor(street, result.street_no ?? "")
      .then(setPicked)
      .catch(() => setFailed(true))
      .finally(() => setMaking(false));
  };

  if (picked !== null) {
    return (
      <main className="landing landing-open" lang={language}>
        <Network />
        <Place result={picked} language={language} onBack={() => setPicked(null)} />
      </main>
    );
  }

  return (
    <main className="landing" lang={language}>
      {/* The map this site is about, reduced until it is texture rather than information. */}
      <Network />

      {/* The lamp below the fold. Everything on the page is lit by it or in shadow. */}
      <div className="lamp" aria-hidden="true" />

      <div className="landing-centre">
        <p className="eyebrow">{text.eyebrow}</p>
        <h1 className="tagline">{text.tagline}</h1>
        <p className="sub">{text.sub}</p>
        <Search language={language} onPick={pick} />
        {making && <p className="making">{text.asking}</p>}
        {failed && <p className="making making-failed">{text.askFailed}</p>}
        <a className="browse" href={language === "el" ? "/map" : "/en/map"}>
          {text.browseMap} <span aria-hidden="true">→</span>
        </a>
      </div>
    </main>
  );
}
