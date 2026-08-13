"""Generated from schema/tiles.yaml. Do not edit; edit the schema and regenerate."""

from __future__ import annotations

from typing import Final

VERSION: Final = 1

# One feature per street, carrying the best each operator reaches on it. Painted by
# best_mbps and filtered by the per-operator fields, which is why both exist: a filter over
# a single best paints a street in one operator's colour while claiming another's.
STREETS_LAYER: Final = "streets"
STREETS_FIELDS: Final = (
    "id",
    "best_mbps",
    "nprov",
    "far",
    "p_ote",
    "p_vodafone",
    "p_nova",
    "p_dei",
    "p_inalan",
    "p_hcn",
    "p_metadosis",
)

# The operator each per-operator field belongs to. The builder pivots the
# provider table through this, so an operator with no field here is not
# written rather than written under a guessed name.
STREETS_BY_PROVIDER: Final[dict[str, str]] = {
    "OTE": "p_ote",
    "VODAFONE": "p_vodafone",
    "NOVA": "p_nova",
    "DEI": "p_dei",
    "INALAN": "p_inalan",
    "HCN": "p_hcn",
    "METADOSIS": "p_metadosis",
}

STREETS_NULLABLE: Final = (
    "best_mbps",
    "p_ote",
    "p_vodafone",
    "p_nova",
    "p_dei",
    "p_inalan",
    "p_hcn",
    "p_metadosis",
)

# One feature per municipality, for the zooms where a street is a fraction of a pixel. A map
# with no basemap and nothing drawn at low zoom is a black rectangle telling the reader to
# zoom in, somewhere, with no clue where — so the country has to have a shape before it has
# streets. Fibre rather than the fastest anything: the fastest anything is 5G, which reaches
# nearly every address, and a map of it is one colour.
REGIONS_LAYER: Final = "regions"
REGIONS_FIELDS: Final = (
    "id",
    "name",
    "addresses",
    "fibre",
    "fibre_share",
    "best_mbps",
)

REGIONS_NULLABLE: Final = (
    "best_mbps",
)

# One feature per Ookla tile that has ever been tested, drawn as the square that was
# measured rather than the centroid they publish. About 600 m across, and only a few per
# cent of the country has any at all, so an empty view is the normal case and must never be
# rendered as a failure.
CELLS_LAYER: Final = "cells"
CELLS_FIELDS: Final = (
    "quadkey",
    "family",
    "down_mbps",
    "up_mbps",
    "tests",
)

CELLS_NULLABLE: Final = (
)

LAYERS: Final = (
    "streets",
    "regions",
    "cells",
)
