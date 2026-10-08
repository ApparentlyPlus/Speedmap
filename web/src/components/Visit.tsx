/**
 * The way from an operator's card to the operator. A link of its own, in a new tab, and never
 * the card: the plan card is already the thing you tap to see a plan on the house, and a card
 * that sometimes leaves the site is one nobody trusts. Wholesalers have no shop, so no link.
 */

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
      // inside a card that picks a plan when tapped, following the link mustn't also pick it
      onClick={(event) => event.stopPropagation()}
    >
      {fill(strings(language).visitSite, { site: hostOf(site) })}
      <span aria-hidden="true">↗</span>
    </a>
  );
}
