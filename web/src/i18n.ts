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
  readonly eyebrow: string;
  readonly tagline: string;
  readonly sub: string;
  readonly searchLabel: string;
  readonly searchPlaceholder: string;
  readonly browseMap: string;
  readonly mapTitle: string;
  readonly operator: string;
  readonly shown: string;
  readonly views: Readonly<Record<string, string>>;
  readonly anyOperator: string;
  readonly legend: Readonly<Record<string, string>>;
  readonly measuredHere: string;
  readonly down: string;
  readonly up: string;
  readonly tests: string;
  readonly mapZoomIn: string;
  readonly mapNothingHere: string;
  readonly mapTruncated: string;
  readonly noResults: string;
  readonly searching: string;
  readonly searchFailed: string;
  readonly unfiled: string;
  readonly street: string;
  readonly askThem: string;
  readonly asking: string;
  readonly askFailed: string;
  readonly address: string;
  readonly back: string;
  readonly nothingHere: string;
  readonly perMonth: string;
  readonly upfront: string;
  readonly notPriced: string;
  readonly unlimited: string;
  readonly disclaimer: string;
  readonly report: string;
  readonly bestHere: string;
  readonly upTo: string;
  readonly more: string;
  readonly fewer: string;
  readonly basis: Readonly<Record<string, string>>;
  readonly family: Readonly<Record<string, string>>;
  readonly technology: Readonly<Record<string, string>>;
  readonly groupEnough: string;
  readonly groupSlower: string;
  readonly groupUnpriced: string;
};

const el: Strings = {
  eyebrow: "Ευρυζωνική κάλυψη Ελλάδας",
  tagline: "Τι ίντερνετ μπορείς να πάρεις;",
  sub: "Κάλυψη, ταχύτητες και τιμές για κάθε διεύθυνση στην Ελλάδα.",
  searchLabel: "Διεύθυνση",
  searchPlaceholder: "Οδός και αριθμός, ή περιοχή",
  browseMap: "ή δες τον χάρτη",
  mapTitle: "Ο χάρτης κάλυψης",
  operator: "Πάροχος",
  shown: "Τι δείχνει",
  views: { filed: "Δηλωμένη", measured: "Μετρημένη", mobile: "Κινητή" },
  anyOperator: "Όλοι",
  legend: { filed: "Ταχύτητα δρόμου", measured: "Ταχύτητα που μετρήθηκε", mobile: "Κάλυψη κινητής" },
  measuredHere: "Μετρήσεις εδώ",
  down: "Λήψη",
  up: "Αποστολή",
  tests: "μετρήσεις",
  mapZoomIn: "Κάνε ζουμ για να δεις κάλυψη ανά δρόμο",
  mapNothingHere: "Κανένας δρόμος εδώ με δηλωμένη κάλυψη",
  mapTruncated: "Πολλοί δρόμοι στην οθόνη — κάνε ζουμ για όλους",
  noResults: "Καμία διεύθυνση",
  searching: "Αναζήτηση…",
  searchFailed: "Η αναζήτηση δεν απάντησε",
  unfiled: "χωρίς δηλωμένη ταχύτητα",
  street: "οδός",
  askThem: "ρώτα",
  asking: "Ετοιμάζουμε τη διεύθυνση…",
  askFailed: "Δεν μπορέσαμε να ετοιμάσουμε αυτή τη διεύθυνση",
  address: "διεύθυνση",
  back: "Νέα αναζήτηση",
  nothingHere: "Δεν βρέθηκε τίποτα για αυτή τη διεύθυνση",
  perMonth: "/μήνα",
  upfront: "αρχικό κόστος",
  notPriced: "χωρίς τιμή",
  unlimited: "απεριόριστα",
  disclaimer:
    "Η διαθεσιμότητα και οι τιμές είναι κατά προσέγγιση. Επιβεβαίωσέ τα πάντα με τον πάροχο.",
  report: "Κάτι δεν φαίνεται σωστό;",
  bestHere: "καλύτερο εδώ",
  upTo: "έως",
  more: "ακόμη",
  fewer: "λιγότερα",
  basis: {
    quoted: "από τον πάροχο",
    measured: "μετρημένο",
    filed: "δηλωμένο",
    advertised: "διαφημιζόμενο",
  },
  family: {
    fibre: "οπτική ίνα",
    copper: "χαλκός",
    wireless: "ασύρματο",
    satellite: "δορυφορικό",
  },
  technology: { FWA_5G: "5G", FWA_4G: "4G", VECT_VDSL: "VDSL+", MOBILE: "κινητό", SAT: "δορυφόρος" },
  groupEnough: "Φτάνουν για ένα σπιτικό",
  groupSlower: "Πιο αργά απ' όσο θέλει ένα σπιτικό",
  groupUnpriced: "Χωρίς δημοσιευμένη τιμή",
};

const en: Strings = {
  eyebrow: "Greek broadband coverage",
  tagline: "What internet can you get?",
  sub: "Coverage, speeds and prices for every address in Greece.",
  searchLabel: "Address",
  searchPlaceholder: "Street and number, or an area",
  browseMap: "or browse the map",
  mapTitle: "The coverage map",
  operator: "Operator",
  shown: "Showing",
  views: { filed: "Filed", measured: "Measured", mobile: "Mobile" },
  anyOperator: "Anyone",
  legend: { filed: "Street speed", measured: "Measured speed", mobile: "Mobile coverage" },
  measuredHere: "Measured here",
  down: "Down",
  up: "Up",
  tests: "tests",
  mapZoomIn: "Zoom in for coverage street by street",
  mapNothingHere: "No street here has coverage filed",
  mapTruncated: "More streets in view than shown — zoom in for all of them",
  noResults: "No address found",
  searching: "Searching…",
  searchFailed: "Search did not answer",
  unfiled: "no speed filed",
  street: "street",
  askThem: "ask",
  asking: "Preparing the address…",
  askFailed: "We could not prepare that address",
  address: "address",
  back: "New search",
  nothingHere: "Nothing found for this address",
  perMonth: "/month",
  upfront: "up front",
  notPriced: "not priced",
  unlimited: "unlimited",
  disclaimer:
    "Availability and prices are best effort. Always confirm with the provider.",
  report: "Something look wrong?",
  bestHere: "best here",
  upTo: "up to",
  more: "more",
  fewer: "fewer",
  basis: {
    quoted: "quoted",
    measured: "measured",
    filed: "filed",
    advertised: "advertised",
  },
  family: {
    fibre: "fibre",
    copper: "copper",
    wireless: "wireless",
    satellite: "satellite",
  },
  technology: { FWA_5G: "5G", FWA_4G: "4G", VECT_VDSL: "VDSL+", MOBILE: "mobile", SAT: "satellite" },
  groupEnough: "Enough for a household",
  groupSlower: "Slower than a household wants",
  groupUnpriced: "No published price",
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
