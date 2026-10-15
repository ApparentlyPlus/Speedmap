#!/usr/bin/env bash
# only what can't be rebuilt: answers, dated tariffs, reports and attempts, a few hundred MB
# of the 11 GB
set -euo pipefail

DSN="${SPEEDMAP_DSN:-postgresql:///speedmap}"
INTO="${SPEEDMAP_BACKUPS:-/var/backups/speedmap}"
KEEP="${SPEEDMAP_BACKUP_KEEP:-30}"

mkdir -p "$INTO"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="$INTO/speedmap-$stamp.dump"

# temp name then rename, so a half written dump never passes for a finished one
pg_dump "$DSN" --format=custom --compress=9 \
    --table=availability \
    --table=probe_attempt \
    --table=plan \
    --table=plan_price \
    --table=report \
    --file="$out.partial"
mv "$out.partial" "$out"

# a month, the register has moved on by then anyway
find "$INTO" -name 'speedmap-*.dump' -type f -printf '%T@ %p\n' \
    | sort -rn | tail -n +$((KEEP + 1)) | cut -d' ' -f2- | xargs -r rm --
