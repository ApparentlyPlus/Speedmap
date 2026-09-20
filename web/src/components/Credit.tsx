/** The one click between a map and the people who made the data under it. */

import { strings, type Language } from "../i18n";

export function Credit({ language }: { readonly language: Language }): React.ReactElement {
  const path = language === "el" ? "/attribution" : "/en/attribution";
  return (
    <a className="credit" href={path}>
      {strings(language).creditsLink}
    </a>
  );
}
