/**
 * The landing state.
 *
 * One question, one field, one quiet way out. The tagline sits at the optical centre rather
 * than the true middle, because text centred at 50% reads low.
 */

import { Search } from "../components/Search";
import { languageOf, strings } from "../i18n";

export function Landing(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);

  return (
    <main className="landing" lang={language}>
      {/* One light source, from below. Everything else on this page is unlit. */}
      <div className="glow" aria-hidden="true" />

      <div className="landing-centre">
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
