// The landing page. Tagline at the optical centre, a bit above the middle.

import { Component, Suspense, lazy, useEffect, useState } from "react";

import { askFor, type Result } from "../api/client";
import { Network } from "../components/Network";
import { Search } from "../components/Search";
import { Waiting } from "../components/Waiting";
import { languageOf, strings } from "../i18n";
import { RouterList, Routers } from "./routers";

// answer screens are most of the script, fetched from the first keystroke
const results = (): Promise<typeof import("./results")> => import("./results");
const Place = lazy(() => results().then((m) => ({ default: m.Place })));
const Road = lazy(() => results().then((m) => ({ default: m.Road })));

// MapLibre is in here, so it loads after the field
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
  // one route and no reload, so the network animation never restarts
  const [picked, setPicked] = useState<Result | null>(null);
  const [making, setMaking] = useState(false);
  const [failed, setFailed] = useState(false);
  // its own history entry, back returns to the answer
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

  // proposed = unfiled door on a known street, nothing to open yet
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

  // forward again after a new search, the answer's gone
  if (routers && picked === null) return <Routers />;

  if (picked !== null) {
    const shown =
      picked.kind === "street" ? (
        <Road result={picked} language={language} onBack={() => setPicked(null)} />
      ) : (
        <Place result={picked} language={language} onBack={() => setPicked(null)} onRouters={openRouters} />
      );
    // kept mounted and hidden under the router page, back finds it as it was
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

// the chunk failed even after main.tsx's reload, without this the page goes blank
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
