/**
 * The landing state.
 *
 * One question, one field, one quiet way out. The tagline sits at the optical centre rather
 * than the true middle, because text centred at 50% reads low.
 *
 * Nothing is outlined. A warm lamp sits below the fold and comes on with the page, and every
 * surface is told from the page behind it by how the light falls on it.
 */

import { Search } from "../components/Search";
import { languageOf, strings } from "../i18n";

export function Landing(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);

  return (
    <main className="landing" lang={language}>
      {/* The lamp below the fold. Everything on the page is lit by it or in shadow. */}
      <div className="lamp" aria-hidden="true" />

      <div className="landing-centre">
        <p className="eyebrow">{text.eyebrow}</p>
        <h1 className="tagline">{text.tagline}</h1>
        <p className="sub">{text.sub}</p>
        <Search language={language} />
        <a className="browse" href={language === "el" ? "/map" : "/en/map"}>
          {text.browseMap} <span aria-hidden="true">→</span>
        </a>
      </div>
    </main>
  );
}
