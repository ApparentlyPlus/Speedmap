/**
 * The landing state.
 *
 * One question, one field, one quiet way out. The tagline sits at the optical centre rather
 * than the true middle, because text centred at 50% reads low.
 *
 * Nothing is lit by a gradient. Depth comes from shadow alone, which is why the page holds
 * together with no colour on it but the amber in the ramp.
 */

import { Search } from "../components/Search";
import { languageOf, strings } from "../i18n";

export function Landing(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);

  return (
    <main className="landing" lang={language}>
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
