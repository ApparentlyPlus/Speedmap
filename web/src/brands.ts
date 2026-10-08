/** Each operator's mark and colour. */

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
  /**
   * Name shown on screen, from the [operators] table in strings.toml. The register's code is a join key: nobody shops for OTE, and
   * nobody's heard of the holding companies behind most of the others.
   */
  readonly name: string;
};

/** Anyone without a mark: their initial, in neutral grey. */
const UNBRANDED = { mark: null, colour: "#a1a1aa" } as const;

/** The name the site shows for an operator, or its register code when the file has none. */
function shown(code: string): string {
  return OPERATOR_NAMES[code] ?? code;
}

export const BRANDS: Record<string, Brand> = {
  TELEKOM: { mark: telekom, colour: "#e20074", name: shown("TELEKOM") },
  VODAFONE: { mark: vodafone, colour: "#e60000", name: shown("VODAFONE") },
  NOVA: { mark: nova, colour: "#0057ff", name: shown("NOVA") },
  DEI: { mark: dei, colour: "#00a3e0", name: shown("DEI") },
  STARLINK: { mark: starlink, colour: "#64748b", name: shown("STARLINK") },
  INALAN: { mark: inalan, colour: "#e4002b", name: shown("INALAN") },
  HCN: { mark: hcn, colour: "#0091d2", name: shown("HCN") },
  // the networks with no shop, in unbranded grey
  METADOSIS: { ...UNBRANDED, mark: metadosis, colour: "#34b44a", name: shown("METADOSIS") },
  FIBERGRID: { ...UNBRANDED, name: shown("FIBERGRID") },
  UNITEDFIBER: { ...UNBRANDED, name: shown("UNITEDFIBER") },
  FIBER2ALL: { ...UNBRANDED, name: shown("FIBER2ALL") },
  NETFIBER: { ...UNBRANDED, name: shown("NETFIBER") },
};

export function brandOf(provider: string): Brand {
  // an unknown code is still something someone filed, so show it as-is
  return BRANDS[provider] ?? { ...UNBRANDED, name: shown(provider) };
}
