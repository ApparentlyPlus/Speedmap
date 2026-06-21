/**
 * The landing state.
 *
 * One question, one field, one quiet way out. The tagline sits at the optical centre rather
 * than the true middle, because text centred at 50% reads low.
 *
 * Nothing is outlined. A warm lamp sits below the fold and comes on with the page, and every
 * surface is told from the page behind it by how the light falls on it.
 */

import { useState } from "react";

import type { Result } from "../api/client";
import { Network } from "../components/Network";
import { Place } from "../components/Place";
import { Search } from "../components/Search";
import { languageOf, strings } from "../i18n";

export function Landing(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);
  /* Three states, one route, no reload: the lamp and the network never restart. */
  const [picked, setPicked] = useState<Result | null>(null);

  if (picked !== null) {
    return (
      <main className="landing landing-open" lang={language}>
        <Network />
        <div className="lamp" aria-hidden="true" />
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
        <Search language={language} onPick={setPicked} />
        <a className="browse" href={language === "el" ? "/map" : "/en/map"}>
          {text.browseMap} <span aria-hidden="true">→</span>
        </a>
      </div>
    </main>
  );
}
