/**
 * Each operator's own mark and colour.
 *
 * A card takes the colour of whoever is selling, because on a list of eight offers the
 * provider is the first thing anyone looks for and a logo is recognised before it is read.
 * The colours are the operators' own, taken from their marks or their sites — not chosen
 * to look well together, which is why they are used as an edge and a wash rather than a
 * fill: five brands competing at full strength would be a fairground.
 */

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
};

/** Anyone still without a mark of their own: their initial, in no colour in particular. */
export const UNBRANDED: Brand = { mark: null, colour: "#a1a1aa" };

export const BRANDS: Record<string, Brand> = {
  OTE: { mark: telekom, colour: "#e20074" },
  VODAFONE: { mark: vodafone, colour: "#e60000" },
  NOVA: { mark: nova, colour: "#0057ff" },
  DEI: { mark: dei, colour: "#00a3e0" },
  STARLINK: { mark: starlink, colour: "#64748b" },
  INALAN: { mark: inalan, colour: "#e4002b" },
  HCN: { mark: hcn, colour: "#0091d2" },
  METADOSIS: { mark: metadosis, colour: "#34b44a" },
};

export function brandOf(provider: string): Brand {
  return BRANDS[provider] ?? UNBRANDED;
}
