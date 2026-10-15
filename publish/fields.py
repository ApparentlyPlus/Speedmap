"""Generated from schema/tiles.yaml. Edit the schema and regenerate, never this file."""

from __future__ import annotations

from typing import Final

VERSION: Final = 1

# One feature per street. Painted by best_mbps, filtered by the per-operator fields.
STREETS_LAYER: Final = "streets"
STREETS_FIELDS: Final = (
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
)

# operator code -> field, an operator missing here isn't written
STREETS_BY_PROVIDER: Final[dict[str, str]] = {
    "TELEKOM": "p_telekom",
    "VODAFONE": "p_vodafone",
    "NOVA": "p_nova",
    "DEI": "p_dei",
    "INALAN": "p_inalan",
    "HCN": "p_hcn",
    "METADOSIS": "p_metadosis",
    "FIBERGRID": "p_fibergrid",
    "UNITEDFIBER": "p_unitedfiber",
    "FIBER2ALL": "p_fiber2all",
    "NETFIBER": "p_netfiber",
}

# drawn but listed apart, nobody can buy from them directly
STREETS_INFRASTRUCTURE: Final[tuple[str, ...]] = (
    "METADOSIS",
    "FIBERGRID",
    "UNITEDFIBER",
    "FIBER2ALL",
    "NETFIBER",
)

STREETS_NULLABLE: Final = (
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
)

# One feature per municipality, for the low zooms. Painted by fiber share, since 5G reaches
# nearly everywhere and would make it one colour.
REGIONS_LAYER: Final = "regions"
REGIONS_FIELDS: Final = (
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
)

REGIONS_NULLABLE: Final = (
    "best_mbps",
    "measured_mbps",
    "measured_tests",
    "mobile_mbps",
    "mobile_tests",
)

# One square per tested Ookla tile, ~600 m across. Most of the country has none, so an empty
# view is normal.
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

# archive -> layer -> fields the style reads, for tools/slim_basemap.py
BASEMAP: Final[dict[str, dict[str, tuple[str, ...]]]] = {
    "greece.pmtiles": {
        "landcover": (),
        "park": (),
        "water": (),
        "transportation": ("class",),
        "transportation_name": ("name", "name:el"),
        "place": ("class", "name", "name:el"),
    },
    "buildings.pmtiles": {
        "building": ("height", "num_floors", "min_height"),
    },
}
