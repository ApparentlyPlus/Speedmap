"""Whether the Pi is running out of room.

The database is about 18 GB, a backup lands every night and the tiles are recut every week, on
a disk nobody looks at. Full, Postgres stops taking writes and the site keeps serving whatever
it had, so nothing looks wrong until someone wonders why answers stopped changing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Where the Pi keeps what grows. Missing ones are skipped: a desktop has no /srv/speedmap.
WATCHED = (Path("/"), Path("/var/lib/postgresql"), Path("/srv/speedmap"), Path("/var/backups/speedmap"))

# Short of either, it's time to look. A tenth of a small card can be under a gigabyte.
LEAST_SHARE = 0.10
LEAST_GB = 5


def short(paths: tuple[Path, ...] = WATCHED) -> list[str]:
    """One line per disk under the floor, naming the path and what's left."""
    found, seen = [], set()
    for path in paths:
        if not path.exists():
            continue
        usage = shutil.disk_usage(path)
        # two watched paths on one disk are one problem, said once
        disk = (usage.total, usage.free)
        if disk in seen:
            continue
        seen.add(disk)
        free_gb = usage.free / 1e9
        if usage.free < usage.total * LEAST_SHARE or free_gb < LEAST_GB:
            found.append(f"{path}: {free_gb:.1f} GB free of {usage.total / 1e9:.0f} GB")
    return found
