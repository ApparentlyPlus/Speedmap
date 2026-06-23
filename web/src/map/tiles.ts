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
  readonly p_ote: Mbps | null;
  readonly p_vodafone: Mbps | null;
  readonly p_nova: Mbps | null;
  readonly p_dei: Mbps | null;
  readonly p_inalan: Mbps | null;
  readonly p_hcn: Mbps | null;
  readonly p_metadosis: Mbps | null;
};

export const STREETS_LAYER = "streets" as const;
export const STREETS_FIELDS = [
  "id",
  "best_mbps",
  "nprov",
  "p_ote",
  "p_vodafone",
  "p_nova",
  "p_dei",
  "p_inalan",
  "p_hcn",
  "p_metadosis",
] as const;

/** The field each operator's speed is written under, for the filter. */
export const STREETS_BY_PROVIDER: Readonly<
  Record<string, keyof Street>
> = {
  OTE: "p_ote",
  VODAFONE: "p_vodafone",
  NOVA: "p_nova",
  DEI: "p_dei",
  INALAN: "p_inalan",
  HCN: "p_hcn",
  METADOSIS: "p_metadosis",
};

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
