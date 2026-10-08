/** The routers worth buying where a mobile connection beats the wire. */

import { languageOf, strings } from "../i18n";
import { ROUTERS } from "../routers";

export function Routers(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);

  return (
    <main className="credits routers" lang={language}>
      <a className="back" href={language === "el" ? "/" : "/en/"}>
        <span aria-hidden="true">←</span> {text.creditsHome}
      </a>

      <h1 className="credits-name">{text.routersTitle}</h1>
      <p className="credits-said">{text.routersIntro}</p>

      <ul className="routers-list">
        {ROUTERS.map((router) => (
          <li className="routers-one" key={router.id}>
            <p className="routers-for">{text.routerFor[router.id]}</p>
            <h2 className="routers-name">{router.name}</h2>
            <p className="routers-why">{text.routerWhy[router.id]}</p>
            <a className="routers-link" href={router.href} target="_blank" rel="noopener noreferrer">
              {text.routersLink} <span aria-hidden="true">↗</span>
            </a>
          </li>
        ))}
      </ul>

      <p className="routers-check">{text.routersCheck}</p>
      <p className="routers-note">{text.routersNote}</p>
    </main>
  );
}
