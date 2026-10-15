// what the site keeps about a reader, and who else sees anything

import { languageOf, strings } from "../i18n";

// alias forwarded on Cloudflare, no personal inbox shown
const EMAIL = "privacy@speedmap.gr";

export function Privacy(): React.ReactElement {
  const language = languageOf(window.location.pathname);
  const text = strings(language);

  return (
    <main className="credits" lang={language}>
      <a className="back" href={language === "el" ? "/" : "/en/"}>
        <span aria-hidden="true">←</span> {text.creditsHome}
      </a>

      <h1 className="credits-name">{text.privacyTitle}</h1>
      <p className="credits-said">{text.privacyIntro}</p>

      <h2 className="credits-head">{text.privacyKeepHead}</h2>
      <p className="credits-said">{text.privacyLog}</p>
      <p className="credits-said">{text.privacyThrottle}</p>
      <p className="credits-said">{text.privacyReport}</p>
      <p className="credits-said">{text.privacyBrowser}</p>

      <h2 className="credits-head">{text.privacyOthersHead}</h2>
      <p className="credits-said">{text.privacyCloudflare}</p>
      <p className="credits-said">{text.privacyOperators}</p>
      <p className="credits-said">{text.privacyLinks}</p>

      <h2 className="credits-head">{text.privacyRightsHead}</h2>
      <p className="credits-said">{text.privacyRights}</p>

      <h2 className="credits-head">{text.privacyWhoHead}</h2>
      <p className="credits-said">{text.privacyWho}</p>
      <p className="credits-said">
        {/* split around the address so it can be a link */}
        {text.privacyContact.split("{email}")[0]}
        <a className="credits-mail" href={`mailto:${EMAIL}`}>{EMAIL}</a>
        {text.privacyContact.split("{email}")[1]}
      </p>
    </main>
  );
}
