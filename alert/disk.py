"""Disk space on the Pi. A full disk stops Postgres writing and nothing looks wrong."""

from __future__ import annotations

import shutil
from pathlib import Path

# missing ones are skipped, a desktop has no /srv/speedmap
WATCHED = (Path("/"), Path("/var/lib/postgresql"), Path("/srv/speedmap"), Path("/var/backups/speedmap"))

LEAST_SHARE = 0.10
LEAST_GB = 5


def short(paths: tuple[Path, ...] = WATCHED) -> list[str]:
    found, seen = [], set()
    for path in paths:
        if not path.exists():
            continue
        u = shutil.disk_usage(path)
        # same disk twice, report it once
        if (u.total, u.free) in seen:
            continue
        seen.add((u.total, u.free))
        gb = u.free / 1e9
        if u.free < u.total * LEAST_SHARE or gb < LEAST_GB:
            found.append(f"{path}: {gb:.1f} GB free of {u.total / 1e9:.0f} GB")
    return found
