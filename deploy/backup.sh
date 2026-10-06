#!/usr/bin/env bash
# Back up only what can't be rebuilt.
#
# The database is eleven gigabytes, almost all of it the register verbatim (fetchable again)
# and things derived from it (rebuilt in an hour). What can't come back: operators' answers,
# tariffs on the day we read them, what people reported, and who was asked when. A few
# hundred megabytes.
set -euo pipefail

DSN="${SPEEDMAP_DSN:-postgresql:///speedmap}"
INTO="${SPEEDMAP_BACKUPS:-/var/backups/speedmap}"
KEEP="${SPEEDMAP_BACKUP_KEEP:-30}"

mkdir -p "$INTO"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$INTO/speedmap-$stamp.dump"

# written under a temp name and renamed once complete, so an interrupted backup never passes
# for a finished one
pg_dump "$DSN" --format=custom --compress=9 \
    --table=availability \
    --table=probe_attempt \
    --table=plan \
    --table=plan_price \
    --table=report \
    --file="$out.partial"
mv "$out.partial" "$out"

# keep a month, by then the register has moved on anyway
find "$INTO" -name 'speedmap-*.dump' -type f -printf '%T@ %p\n' \
    | sort -rn | tail -n +$((KEEP + 1)) | cut -d' ' -f2- | xargs -r rm --
