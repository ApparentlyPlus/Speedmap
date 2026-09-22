/** Each operator's own mark and colour. */

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
   * What to call them on screen. The register's code is a join key. Nobody shops for OTE,
   * and nobody has heard of the holding company behind most of the rest either.
   */
  readonly name: string;
};

/** Anyone still without a mark of their own: their initial, in no colour in particular. */
const UNBRANDED = { mark: null, colour: "#a1a1aa" } as const;

export const BRANDS: Record<string, Brand> = {
  TELEKOM: { mark: telekom, colour: "#e20074", name: "Telekom" },
  VODAFONE: { mark: vodafone, colour: "#e60000", name: "Vodafone" },
  NOVA: { mark: nova, colour: "#0057ff", name: "Nova" },
  DEI: { mark: dei, colour: "#00a3e0", name: "ΔΕΗ Fiber" },
  STARLINK: { mark: starlink, colour: "#64748b", name: "Starlink" },
  INALAN: { mark: inalan, colour: "#e4002b", name: "Inalan" },
  HCN: { mark: hcn, colour: "#0091d2", name: "HCN" },
  // The networks with no shop. No mark of their own, so they take the unbranded grey.
  METADOSIS: { ...UNBRANDED, mark: metadosis, colour: "#34b44a", name: "Metadosis" },
  FIBERGRID: { ...UNBRANDED, name: "Fibergrid" },
  UNITEDFIBER: { ...UNBRANDED, name: "United Fiber" },
  FIBER2ALL: { ...UNBRANDED, name: "Fiber2All" },
  NETFIBER: { ...UNBRANDED, name: "Netfiber" },
};

export function brandOf(provider: string): Brand {
  // A code we have never seen is still a code somebody filed, so it gets shown as itself
  // rather than dropped.
  return BRANDS[provider] ?? { ...UNBRANDED, name: provider };
}
