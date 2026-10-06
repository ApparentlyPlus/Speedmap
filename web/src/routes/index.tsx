/**
 * The landing page: one question, one field, one quiet way out. The tagline sits at the
 * optical centre, a little above the true middle, since text centred at 50% reads low.
 */

import { Suspense, lazy, useState } from "react";

import { askFor, type Result } from "../api/client";
import { Network } from "../components/Network";
import { Search } from "../components/Search";
import { Waiting } from "../components/Waiting";
import { languageOf, strings } from "../i18n";

/*
 * The answer screens carry the map and the house, most of the site's script. We start
 * fetching them on the first keystroke, so the chunk is usually here by the time a
 * suggestion is picked, and the search field never waits on it.
 */
const results = (): Promise<typeof import("./results")> => import("./results");
const Place = lazy(() => results().then((m) => ({ default: m.Place })));
const Road = lazy(() => results().then((m) => ({ default: m.Road })));

let warmed = false;
function warm(): void {
  if (warmed) return;
  warmed = true;
  void results();
}

export function Landing(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);
  // three states, one route, no reload, so the network animation never restarts
  const [picked, setPicked] = useState<Result | null>(null);
  const [making, setMaking] = useState(false);
  const [failed, setFailed] = useState(false);

  // A proposed row is an unfiled door on a known street, so there's no address to open yet.
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
    // a street and a door are different questions, and only the door has a price
    const shown =
      picked.kind === "street" ? (
        <Road result={picked} language={language} onBack={() => setPicked(null)} />
      ) : (
        <Place result={picked} language={language} onBack={() => setPicked(null)} />
      );
    return (
      <main className="landing landing-open" lang={language}>
        <Network />
        <Suspense fallback={<Waiting />}>{shown}</Suspense>
      </main>
    );
  }

  return (
    <main className="landing" lang={language}>
      {/* the map this site is about, faded down to texture */}
      <Network />

      {/* the lamp below the fold, lighting everything on the page */}
      <div className="lamp" aria-hidden="true" />

      <div className="landing-centre">
        <p className="eyebrow">{text.eyebrow}</p>
        <h1 className="tagline">{text.tagline}</h1>
        <p className="sub">{text.sub}</p>
        <Search language={language} onPick={pick} onType={warm} />
        {making && <p className="making">{text.asking}</p>}
        {failed && <p className="making making-failed">{text.askFailed}</p>}
        <a className="browse" href={language === "el" ? "/map" : "/en/map"}>
          {text.browseMap} <span aria-hidden="true">→</span>
        </a>
      </div>
    </main>
  );
}
