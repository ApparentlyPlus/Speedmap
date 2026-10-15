// Link from an operator's card to the operator, in a new tab and never the card itself (tapping
// the card picks the plan). Wholesalers have no shop.

import { brandOf, hostOf } from "../brands";
import { fill, strings, type Language } from "../i18n";

export function Visit({ provider, language }: { readonly provider: string; readonly language: Language }) {
  const site = brandOf(provider).site;
  if (site === null) return null;
  return (
    <a
      className="visit"
      href={site}
      target="_blank"
      rel="noopener noreferrer"
      // or the card picks the plan too
      onClick={(event) => event.stopPropagation()}
    >
      {fill(strings(language).visitSite, { site: hostOf(site) })}
      <span aria-hidden="true">↗</span>
    </a>
  );
}
