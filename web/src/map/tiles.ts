/** Generated from schema/tiles.yaml. Do not edit; edit the schema and regenerate. */

import type { Mbps } from "../tokens";

export const VERSION = 1 as const;

/**
 * One feature per street, carrying the best each operator reaches on it. Painted by
 * best_mbps and filtered by the per-operator fields, which is why both exist: a filter over
 * a single best paints a street in one operator's colour while claiming another's.
 */
export type Street = {
  /** the street row this was built from */
  readonly id: number;
  /** the fastest anyone reaches here; null is not filed, never zero */
  readonly best_mbps: Mbps | null;
  /** how many operators reach this street at all, filed speed or not */
  readonly nprov: number;
  readonly p_telekom: Mbps | null;
  readonly p_vodafone: Mbps | null;
  readonly p_nova: Mbps | null;
  readonly p_dei: Mbps | null;
  readonly p_inalan: Mbps | null;
  readonly p_hcn: Mbps | null;
  readonly p_metadosis: Mbps | null;
  readonly p_fibergrid: Mbps | null;
  readonly p_unitedfiber: Mbps | null;
  readonly p_fiber2all: Mbps | null;
  readonly p_netfiber: Mbps | null;
};

export const STREETS_LAYER = "streets" as const;
export const STREETS_FIELDS = [
  "id",
  "best_mbps",
  "nprov",
  "p_telekom",
  "p_vodafone",
  "p_nova",
  "p_dei",
  "p_inalan",
  "p_hcn",
  "p_metadosis",
  "p_fibergrid",
  "p_unitedfiber",
  "p_fiber2all",
  "p_netfiber",
] as const;

/** The field each operator's speed is written under, for the filter. */
export const STREETS_BY_PROVIDER: Readonly<
  Record<string, keyof Street>
> = {
  TELEKOM: "p_telekom",
  VODAFONE: "p_vodafone",
  NOVA: "p_nova",
  DEI: "p_dei",
  INALAN: "p_inalan",
  HCN: "p_hcn",
  METADOSIS: "p_metadosis",
  FIBERGRID: "p_fibergrid",
  UNITEDFIBER: "p_unitedfiber",
  FIBER2ALL: "p_fiber2all",
  NETFIBER: "p_netfiber",
};

/**
 * The operators here who retail nothing to a household: wholesale builders,
 * and anyone who files services and publishes no tariff. Drawn like the rest
 * and listed apart, because they are not a supplier anyone can choose.
 */
export const STREETS_INFRASTRUCTURE: readonly string[] = [
  "METADOSIS",
  "FIBERGRID",
  "UNITEDFIBER",
  "FIBER2ALL",
  "NETFIBER",
];

/**
 * One feature per municipality, for the zooms where a street is a fraction of a pixel. A
 * map with no basemap and nothing drawn at low zoom is a black rectangle telling the reader
 * to zoom in, somewhere, with no clue where — so the country has to have a shape before it
 * has streets. Fiber rather than the fastest anything: the fastest anything is 5G, which
 * reaches nearly every address, and a map of it is one colour.
 */
export type Region = {
  /** the municipality row this was built from */
  readonly id: number;
  readonly name: string;
  /** filed addresses in it, which is the denominator of the share */
  readonly addresses: number;
  /** how many of them fiber reaches */
  readonly fiber: number;
  /** nought to one; what the Filed view is painted by */
  readonly fiber_share: number;
  /** the band's assured speed, held to what the technology can carry */
  readonly best_mbps: Mbps | null;
  /** fixed-line speed tests here; null is untested, which is most of Greece */
  readonly measured_mbps: Mbps | null;
  /** how many tests that rests on, drawn as opacity rather than as deletion */
  readonly measured_tests: number | null;
  /** the same for mobile, kept apart because the two measure different things */
  readonly mobile_mbps: Mbps | null;
  readonly mobile_tests: number | null;
};

export const REGIONS_LAYER = "regions" as const;
export const REGIONS_FIELDS = [
  "id",
  "name",
  "addresses",
  "fiber",
  "fiber_share",
  "best_mbps",
  "measured_mbps",
  "measured_tests",
  "mobile_mbps",
  "mobile_tests",
] as const;

/**
 * One feature per Ookla tile that has ever been tested, drawn as the square that was
 * measured rather than the centroid they publish. About 600 m across, and only a few per
 * cent of the country has any at all, so an empty view is the normal case and must never be
 * rendered as a failure.
 */
export type Cell = {
  /** the zoom 16 tile key, which is also its identity upstream */
  readonly quadkey: string;
  /** fixed or mobile; the two measure differently and never mix */
  readonly family: string;
  readonly down_mbps: Mbps;
  readonly up_mbps: Mbps;
  /** measurements behind the figure; drawn as opacity, never as deletion */
  readonly tests: number;
};

export const CELLS_LAYER = "cells" as const;
export const CELLS_FIELDS = [
  "quadkey",
  "family",
  "down_mbps",
  "up_mbps",
  "tests",
] as const;
