#!/usr/bin/env bash
# Jellyfin's docs: stop the server before copying its database, or the copy
# may not restore. Stop it only for the copy, start it again whatever happens,
# then store the copy in its folder. The container writes it: Borg UI usually
# has the folder read-only.
set -euo pipefail
APP_ROOT=__APP_ROOT__
CONTAINER=__CONTAINER__
DUMP_DIR="$APP_ROOT/borg-ui-db-backup"
if [ -n "$CONTAINER" ]; then
  TMP="$(mktemp -d)"
  trap 'docker start "$CONTAINER" >/dev/null 2>&1 || true; rm -rf "$TMP"' EXIT
  docker stop --time 60 "$CONTAINER" >/dev/null
  docker cp "$CONTAINER:/config/data/jellyfin.db" "$TMP/jellyfin.db"
  # A clean stop folds the write-ahead log into jellyfin.db. If one is left
  # with data in it, the copy alone would be missing those writes.
  if docker cp "$CONTAINER:/config/data/jellyfin.db-wal" "$TMP/wal" 2>/dev/null && [ -s "$TMP/wal" ]; then
    echo "Jellyfin did not shut down cleanly (jellyfin.db-wal is not empty); not taking a copy." >&2
    exit 1
  fi
  docker start "$CONTAINER" >/dev/null
  NAME="jellyfin-$(date +%Y%m%d-%H%M%S).db"
  docker exec -i "$CONTAINER" sh -c '
    set -e
    mkdir -p /config/borg-ui-db-backup
    cd /config/borg-ui-db-backup
    cat > "$1.part" && mv "$1.part" "$1"
    ls -1t jellyfin-*.db | tail -n +4 | xargs -r rm -f --
  ' sh "$NAME" < "$TMP/jellyfin.db"
fi
RECENT="$(find "$DUMP_DIR" -maxdepth 1 -name 'jellyfin-*.db' -mmin -60 -print -quit 2>/dev/null || true)"
if [ -z "$RECENT" ]; then
  echo "No Jellyfin database copy from the last hour in $DUMP_DIR." >&2
  exit 1
fi
