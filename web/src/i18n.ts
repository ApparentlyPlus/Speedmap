/**
 * Greek is the language; English is the translation. Both exist from the first string rather
 * than being retrofitted, because retrofitting is how half a UI ends up hardcoded.
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
  /** The prefecture choropleth, which is off until the reader asks for it. */
  readonly untested: string;
  readonly unreached: string;
  readonly regions: string;
  readonly regionsHint: string;
  readonly over: string;
  readonly streetHead: string;
  readonly notIndexed: string;
  readonly notIndexedWhy: string;
  readonly street: string;
  readonly askThem: string;
  readonly asking: string;
  readonly askFailed: string;
  readonly address: string;
  readonly back: string;
  readonly nothingHere: string;
  readonly perMonth: string;
  readonly upfront: string;
  readonly priceFrom: string;
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
  /** The credits page, and the small way in to it from a corner of the map. */
  readonly creditsLink: string;
  readonly creditsHome: string;
  readonly creditsTitle: string;
  readonly creditsIntro: string;
  readonly creditsData: string;
  readonly creditsTools: string;
  readonly creditsCode: string;
  readonly creditsTerms: string;
  readonly provides: Readonly<Record<string, string>>;
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
  views: { coverage: "Κάλυψη", measured: "Μετρημένη", mobile: "Κινητή" },
  anyOperator: "Όλοι",
  legend: { coverage: "Ταχύτητα δρόμου", measured: "Ταχύτητα που μετρήθηκε", mobile: "Κάλυψη κινητής" },
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
  untested: "χωρίς μέτρηση",
  unreached: "χωρίς γραμμή",
  regions: "Ανά δήμο",
  regionsHint: "Σύνοψη ανά δήμο, όσο ο χάρτης είναι μακριά",
  over: "σε δίκτυο",
  streetHead: "Σε αυτόν τον δρόμο",
  notIndexed: "Αυτός ο δρόμος δεν έχει καταχωρηθεί ακόμα",
  notIndexedWhy: "Κανένας πάροχος δεν έχει δηλώσει κάλυψη εδώ.",
  street: "οδός",
  askThem: "ρώτα",
  asking: "Ετοιμάζουμε τη διεύθυνση…",
  askFailed: "Δεν μπορέσαμε να ετοιμάσουμε αυτή τη διεύθυνση",
  address: "διεύθυνση",
  back: "Νέα αναζήτηση",
  nothingHere: "Δεν βρέθηκε τίποτα για αυτή τη διεύθυνση",
  perMonth: "/μήνα",
  upfront: "αρχικό κόστος",
  priceFrom: "από",
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
  creditsLink: "Πηγές",
  creditsHome: "Αρχική",
  creditsTitle: "Πηγές και άδειες",
  creditsIntro:
    "Ο χάρτης δεν είναι δικός μας. Είναι φτιαγμένος από δεδομένα που δημοσιεύουν άλλοι, " +
    "και ο καθένας τους ζητά να αναφέρεται. Εδώ αναφέρονται.",
  creditsData: "Τα δεδομένα",
  creditsTools: "Τα εργαλεία",
  creditsCode: "Ο κώδικας",
  creditsTerms:
    "Ο κώδικας του site είναι MIT. Τα δεδομένα όμως κρατούν τις δικές τους άδειες: " +
    "οι μετρήσεις της Ookla είναι μη εμπορικές, και το μητρώο της ΓΓΤΤ επιτρέπει μόνο " +
    "προσωπική, μη εμπορική χρήση.",
  provides: {
    osm: "Γεωμετρία δρόμων και ο χάρτης από κάτω",
    overture: "Τα κτίρια",
    ookla: "Μετρημένες ταχύτητες ανά τετράγωνο 600 μέτρων",
    eett: "Ποιος δηλώνει κάλυψη πού, σε ποια τεχνολογία",
  },
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
  views: { coverage: "Coverage", measured: "Measured", mobile: "Mobile" },
  anyOperator: "Anyone",
  legend: { coverage: "Street speed", measured: "Measured speed", mobile: "Mobile coverage" },
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
  untested: "not tested",
  unreached: "no line reaches",
  regions: "By municipality",
  regionsHint: "A summary per municipality, while the map is far out",
  over: "over",
  streetHead: "On this street",
  notIndexed: "Sorry, that street is not indexed yet",
  notIndexedWhy: "No operator has filed coverage here.",
  street: "street",
  askThem: "ask",
  asking: "Preparing the address…",
  askFailed: "We could not prepare that address",
  address: "address",
  back: "New search",
  nothingHere: "Nothing found for this address",
  perMonth: "/month",
  upfront: "up front",
  priceFrom: "from",
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
  creditsLink: "Sources",
  creditsHome: "Home",
  creditsTitle: "Sources and licences",
  creditsIntro:
    "The map is not ours. It is built out of data other people publish, and each of them " +
    "asks to be named. Here they are.",
  creditsData: "The data",
  creditsTools: "The tools",
  creditsCode: "The code",
  creditsTerms:
    "The site's code is MIT. The data keeps its own licences: the Ookla measurements are " +
    "non-commercial, and the register allows personal, non-commercial use only.",
  provides: {
    osm: "Street geometry and the basemap underneath",
    overture: "The buildings",
    ookla: "Measured speeds, per 600 m tile",
    eett: "Who files coverage where, and on which technology",
  },
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
