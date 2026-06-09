#!/usr/bin/env bash
# Back up only what cannot be rebuilt.
#
# The database is eleven gigabytes and almost all of it is the register verbatim, which can
# be fetched again, and everything derived from it, which can be rebuilt in an hour. What
# cannot: answers operators gave us, tariffs on the day we read them, what people reported
# as wrong, and the record of who was asked and when. That is a few hundred megabytes.
set -euo pipefail

DSN="${SPEEDMAP_DSN:-postgresql:///speedmap}"
INTO="${SPEEDMAP_BACKUPS:-/var/backups/speedmap}"
KEEP="${SPEEDMAP_BACKUP_KEEP:-30}"

mkdir -p "$INTO"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$INTO/speedmap-$stamp.dump"

# Written to a temporary name and renamed once whole, so a backup that was interrupted is
# never mistaken for one that finished.
pg_dump "$DSN" --format=custom --compress=9 \
    --table=availability \
    --table=probe_attempt \
    --table=plan \
    --table=plan_price \
    --table=report \
    --file="$out.partial"
mv "$out.partial" "$out"

# Keep a month. Older than that and the register has moved on anyway.
find "$INTO" -name 'speedmap-*.dump' -type f -printf '%T@ %p\n' \
    | sort -rn | tail -n +$((KEEP + 1)) | cut -d' ' -f2- | xargs -r rm --
