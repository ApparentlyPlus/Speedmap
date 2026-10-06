/** Each operator's mark and colour. */

import dei from "./assets/dei.svg";
import hcn from "./assets/hcn.svg";
import inalan from "./assets/inalan.svg";
import metadosis from "./assets/metadosis.svg";
import nova from "./assets/nova.svg";
import starlink from "./assets/starlink.svg";
import telekom from "./assets/telekom.svg";
import vodafone from "./assets/vodafone.svg";

export type Brand = {
  readonly mark: string | null;
  readonly colour: string;
  /**
   * Name shown on screen. The register's code is a join key: nobody shops for OTE, and
   * nobody's heard of the holding companies behind most of the others.
   */
  readonly name: string;
};

/** Anyone without a mark: their initial, in neutral grey. */
const UNBRANDED = { mark: null, colour: "#a1a1aa" } as const;

export const BRANDS: Record<string, Brand> = {
  TELEKOM: { mark: telekom, colour: "#e20074", name: "Telekom" },
  VODAFONE: { mark: vodafone, colour: "#e60000", name: "Vodafone" },
  NOVA: { mark: nova, colour: "#0057ff", name: "Nova" },
  DEI: { mark: dei, colour: "#00a3e0", name: "ΔΕΗ Fiber" },
  STARLINK: { mark: starlink, colour: "#64748b", name: "Starlink" },
  INALAN: { mark: inalan, colour: "#e4002b", name: "Inalan" },
  HCN: { mark: hcn, colour: "#0091d2", name: "HCN" },
  // the networks with no shop, in unbranded grey
  METADOSIS: { ...UNBRANDED, mark: metadosis, colour: "#34b44a", name: "Metadosis" },
  FIBERGRID: { ...UNBRANDED, name: "Fibergrid" },
  UNITEDFIBER: { ...UNBRANDED, name: "United Fiber" },
  FIBER2ALL: { ...UNBRANDED, name: "Fiber2All" },
  NETFIBER: { ...UNBRANDED, name: "Netfiber" },
};

export function brandOf(provider: string): Brand {
  // an unknown code is still something someone filed, so show it as-is
  return BRANDS[provider] ?? { ...UNBRANDED, name: provider };
}
