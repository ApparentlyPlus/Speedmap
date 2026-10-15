// each operator's mark and colour

import dei from "./assets/dei.svg";
import hcn from "./assets/hcn.svg";
import inalan from "./assets/inalan.svg";
import metadosis from "./assets/metadosis.svg";
import nova from "./assets/nova.svg";
import starlink from "./assets/starlink.svg";
import telekom from "./assets/telekom.svg";
import vodafone from "./assets/vodafone.svg";
import { OPERATOR_NAMES } from "./strings";

export type Brand = {
  readonly mark: string | null;
  readonly colour: string;
  // from [operators] in strings.toml, nobody shops for OTE
  readonly name: string;
  // null for wholesalers
  readonly site: string | null;
};

// no mark: their initial in grey
const UNBRANDED = { mark: null, colour: "#a1a1aa", site: null } as const;

function shown(code: string): string {
  return OPERATOR_NAMES[code] ?? code;
}

export const BRANDS: Record<string, Brand> = {
  TELEKOM: { mark: telekom, colour: "#e20074", name: shown("TELEKOM"), site: "https://www.telekom.gr/" },
  VODAFONE: { mark: vodafone, colour: "#e60000", name: shown("VODAFONE"), site: "https://www.vodafone.gr/" },
  NOVA: { mark: nova, colour: "#0057ff", name: shown("NOVA"), site: "https://nova.gr/" },
  DEI: { mark: dei, colour: "#00a3e0", name: shown("DEI"), site: "https://www.dei.gr/el/gia-to-spiti/dei-fiber" },
  STARLINK: { mark: starlink, colour: "#64748b", name: shown("STARLINK"), site: "https://starlink.com/gr" },
  INALAN: { mark: inalan, colour: "#e4002b", name: shown("INALAN"), site: "https://inalan.gr/" },
  HCN: { mark: hcn, colour: "#0091d2", name: shown("HCN"), site: "https://www.hcn.gr/el/" },
  METADOSIS: { ...UNBRANDED, mark: metadosis, colour: "#34b44a", name: shown("METADOSIS") },
  FIBERGRID: { ...UNBRANDED, name: shown("FIBERGRID") },
  UNITEDFIBER: { ...UNBRANDED, name: shown("UNITEDFIBER") },
  // Vodafone's own fiber network, people know the Vodafone name
  FIBER2ALL: { ...UNBRANDED, mark: vodafone, colour: "#e60000", name: shown("FIBER2ALL") },
  NETFIBER: { ...UNBRANDED, name: shown("NETFIBER") },
};

export function brandOf(provider: string): Brand {
  // still something someone filed, show it as is
  return BRANDS[provider] ?? { ...UNBRANDED, name: shown(provider) };
}

// telekom.gr, not https://www.telekom.gr/
export function hostOf(site: string): string {
  return new URL(site).hostname.replace(/^www\./, "");
}
