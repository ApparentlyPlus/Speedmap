/**
 * The landing page: one question, one field, one quiet way out. The tagline sits at the
 * optical centre, a little above the true middle, since text centred at 50% reads low.
 */

import { Component, Suspense, lazy, useEffect, useState } from "react";

import { askFor, type Result } from "../api/client";
import { Network } from "../components/Network";
import { Search } from "../components/Search";
import { Waiting } from "../components/Waiting";
import { languageOf, strings } from "../i18n";
import { RouterList, Routers } from "./routers";

/*
 * The answer screens carry the map and the house, most of the site's script. We start
 * fetching them on the first keystroke, so the chunk is usually here by the time a
 * suggestion is picked, and the search field never waits on it.
 */
const results = (): Promise<typeof import("./results")> => import("./results");
const Place = lazy(() => results().then((m) => ({ default: m.Place })));
const Road = lazy(() => results().then((m) => ({ default: m.Road })));

/* The flyover carries MapLibre, so it comes after the field: typing never waits on the map. */
const Flyover = lazy(() => import("../components/Flyover").then((m) => ({ default: m.Flyover })));

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
  // the router page, opened over an answer: its own address in history, so back returns here
  const [routers, setRouters] = useState(false);

  useEffect(() => {
    const moved = (): void => setRouters(/\/routers\/?$/.test(window.location.pathname));
    window.addEventListener("popstate", moved);
    return () => window.removeEventListener("popstate", moved);
  }, []);

  const openRouters = (): void => {
    window.history.pushState(null, "", language === "el" ? "/routers" : "/en/routers");
    setRouters(true);
    window.scrollTo(0, 0);
  };

  // A proposed row is an unfiled door on a known street, so there's no address to open yet.
  const pick = (result: Result): void => {
    const street = result.street_id;
    if (result.kind !== "proposed" || street === null || street === undefined) {
      setPicked(result);
      return;
    }
    setFailed(false);
    setMaking(true);
    askFor(street, result.street_no ?? "").then(setPicked).catch(() => setFailed(true))
      .finally(() => setMaking(false));
  };

  // forward again after a new search: the answer is gone, so it's the page on its own
  if (routers && picked === null) return <Routers />;

  if (picked !== null) {
    // a street and a door are different questions, and only the door has a price
    const shown =
      picked.kind === "street" ? (
        <Road result={picked} language={language} onBack={() => setPicked(null)} />
      ) : (
        <Place result={picked} language={language} onBack={() => setPicked(null)} onRouters={openRouters} />
      );
    // The answer stays mounted under the router page, hidden, so coming back finds it where it
    // was: the same scroll, no second fetch, no descent played again.
    return (
      <main className={routers ? "credits routers" : "landing landing-open"} lang={language}>
        {!routers && <Network />}
        <div className="landing-answer" hidden={routers}>
          <Unloaded said={text.loadFailed}>
            <Suspense fallback={<Waiting />}>{shown}</Suspense>
          </Unloaded>
        </div>
        {routers && (
          <>
            <button className="back" type="button" onClick={() => window.history.back()}>
              <span aria-hidden="true">←</span> {text.routersBack}
            </button>
            <RouterList language={language} />
          </>
        )}
      </main>
    );
  }

  return (
    <main className="landing" lang={language}>
      {/* the map this site is about, drifting over one city after another */}
      <Suspense fallback={null}>
        <Flyover />
      </Suspense>

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

/**
 * The answer screens' chunk failing even after main.tsx reloaded for it. Without this the
 * rejection took down the whole tree and left a blank page.
 */
class Unloaded extends Component<
  { readonly said: string; readonly children: React.ReactNode },
  { failed: boolean }
> {
  override state = { failed: false };

  static getDerivedStateFromError(): { failed: boolean } {
    return { failed: true };
  }

  override render(): React.ReactNode {
    return this.state.failed ? <p className="load-failed">{this.props.said}</p> : this.props.children;
  }
}
