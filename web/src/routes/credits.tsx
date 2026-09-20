/** Where the credits live, so the map itself can stay a map. */

import { SOURCES, TOOLS, type Credit } from "../credits";
import { languageOf, strings, type Language } from "../i18n";

export function Credits(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);

  return (
    <main className="credits" lang={language}>
      <a className="back" href={home(language)}>
        <span aria-hidden="true">←</span> {text.creditsHome}
      </a>

      <h1 className="credits-name">{text.creditsTitle}</h1>
      <p className="credits-said">{text.creditsIntro}</p>

      <h2 className="credits-head">{text.creditsData}</h2>
      <ul className="credits-list">
        {SOURCES.map((source) => (
          <li className="credits-source" key={source.id}>
            <Named source={source} />
            <p className="credits-gives">{text.provides[source.id]}</p>
            <p className="credits-line">{source.line}</p>
          </li>
        ))}
      </ul>

      <h2 className="credits-head">{text.creditsTools}</h2>
      <ul className="credits-list credits-list-tight">
        {TOOLS.map((tool) => (
          <li className="credits-source" key={tool.id}>
            <Named source={tool} />
          </li>
        ))}
      </ul>

      <h2 className="credits-head">{text.creditsCode}</h2>
      <p className="credits-said">{text.creditsTerms}</p>
    </main>
  );
}

function Named({ source }: { source: Credit }): React.ReactElement {
  return (
    <p className="credits-who">
      <a href={source.href} target="_blank" rel="noreferrer">
        {source.name}
      </a>
      <a className="credits-licence" href={source.licenceHref} target="_blank" rel="noreferrer">
        {source.licence}
      </a>
    </p>
  );
}

function home(language: Language): string {
  return language === "el" ? "/" : "/en/";
}
