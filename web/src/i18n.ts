/**
 * Greek is the language; English is the translation.
 *
 * Both exist from the first string rather than being retrofitted, because retrofitting is
 * how half a UI ends up hardcoded. A plain table, not a library: there are two languages
 * and no pluralisation rules worth a dependency.
 */

export const LANGUAGES = ["el", "en"] as const;
export type Language = (typeof LANGUAGES)[number];

export const DEFAULT: Language = "el";

type Strings = {
  readonly tagline: string;
  readonly sub: string;
  readonly searchLabel: string;
  readonly searchPlaceholder: string;
  readonly browseMap: string;
  readonly noResults: string;
  readonly searching: string;
  readonly searchFailed: string;
  readonly unfiled: string;
  readonly street: string;
  readonly address: string;
};

const el: Strings = {
  tagline: "Τι ίντερνετ μπορείς να πάρεις;",
  sub: "Κάλυψη, ταχύτητες και τιμές για κάθε διεύθυνση στην Ελλάδα.",
  searchLabel: "Διεύθυνση",
  searchPlaceholder: "Οδός και αριθμός, ή περιοχή",
  browseMap: "ή δες τον χάρτη",
  noResults: "Καμία διεύθυνση",
  searching: "Αναζήτηση…",
  searchFailed: "Η αναζήτηση δεν απάντησε",
  unfiled: "χωρίς δηλωμένη ταχύτητα",
  street: "οδός",
  address: "διεύθυνση",
};

const en: Strings = {
  tagline: "What internet can you get?",
  sub: "Coverage, speeds and prices for every address in Greece.",
  searchLabel: "Address",
  searchPlaceholder: "Street and number, or an area",
  browseMap: "or browse the map",
  noResults: "No address found",
  searching: "Searching…",
  searchFailed: "Search did not answer",
  unfiled: "no speed filed",
  street: "street",
  address: "address",
};

const TABLE: Record<Language, Strings> = { el, en };

/** The language from the path: /en/ is English, anything else is Greek. */
export function languageOf(pathname: string): Language {
  const first = pathname.split("/").filter(Boolean)[0];
  return LANGUAGES.includes(first as Language) ? (first as Language) : DEFAULT;
}

export function strings(language: Language): Strings {
  return TABLE[language];
}
