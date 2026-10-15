/** Generated from schema/tiles.yaml. Edit the schema and regenerate, never this file. */

import type { Mbps } from "../tokens";

export const VERSION = 1 as const;

/**
 * One feature per street. Painted by best_mbps, filtered by the per-operator fields.
 */
export type Street = {
  /** street row id, absent below zoom 10 where identical streets get merged */
  readonly id: number | null;
  /** fastest anyone reaches here, null if nothing's filed */
  readonly best_mbps: Mbps | null;
  /** operators reaching it at all, absent below zoom 10 */
  readonly nprov: number | null;
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

/** operator code -> field, for the filter */
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

// drawn but listed apart, nobody can buy from them directly
export const STREETS_INFRASTRUCTURE: readonly string[] = [
  "METADOSIS",
  "FIBERGRID",
  "UNITEDFIBER",
  "FIBER2ALL",
  "NETFIBER",
];

/**
 * One feature per municipality, for the low zooms. Painted by fiber share, since 5G reaches
 * nearly everywhere and would make it one colour.
 */
export type Region = {
  /** municipality row id */
  readonly id: number;
  readonly name: string;
  /** filed addresses, the share's denominator */
  readonly addresses: number;
  /** addresses fiber reaches */
  readonly fiber: number;
  /** 0 to 1, paints the Filed view */
  readonly fiber_share: number;
  /** assured speed of the band, capped at what the technology carries */
  readonly best_mbps: Mbps | null;
  /** fixed line speed tests, null if untested (most of Greece) */
  readonly measured_mbps: Mbps | null;
  /** tests behind it, drawn as opacity */
  readonly measured_tests: number | null;
  /** same for mobile */
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
 * One square per tested Ookla tile, ~600 m across. Most of the country has none, so an
 * empty view is normal.
 */
export type Cell = {
  /** zoom 16 tile key */
  readonly quadkey: string;
  /** fixed or mobile, never mixed */
  readonly family: string;
  readonly down_mbps: Mbps;
  readonly up_mbps: Mbps;
  /** tests behind the figure, drawn as opacity */
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

// archive -> layer -> fields the style reads, for tools/slim_basemap.py
export const BASEMAP: Readonly<
  Record<string, Readonly<Record<string, readonly string[]>>>
> = {
  "greece.pmtiles": {
    landcover: [],
    park: [],
    water: [],
    transportation: ["class"],
    transportation_name: ["name", "name:el"],
    place: ["class", "name", "name:el"],
  },
  "buildings.pmtiles": {
    building: ["height", "num_floors", "min_height"],
  },
};
