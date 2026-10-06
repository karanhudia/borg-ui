#!/usr/bin/env bash
# Vaultwarden's database is a live SQLite file; copying it mid-write can give a
# broken copy. Its own `backup` command writes a consistent db_<date>.sqlite3
# next to it (VACUUM INTO). Keep the newest three, and fail when none is fresh.
set -euo pipefail
APP_ROOT=__APP_ROOT__
CONTAINER=__CONTAINER__
DUMP_GLOB='db_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9].sqlite3'
if [ -n "$CONTAINER" ]; then
  OUT="$(docker exec "$CONTAINER" /vaultwarden backup)" || {
    echo "$OUT" >&2
    echo "Could not run '/vaultwarden backup' in container $CONTAINER (needs Vaultwarden 1.32.1+ with SQLite)." >&2
    exit 1
  }
  echo "$OUT"
  # Prune inside the container: Borg UI usually mounts the folder read-only.
  # Only Vaultwarden's own db_YYYYMMDD_HHMMSS.sqlite3 copies, never a file the
  # user named db_something.sqlite3.
  docker exec "$CONTAINER" sh -c "cd /data && ls -1t $DUMP_GLOB 2>/dev/null | tail -n +4 | xargs -r rm -f --"
fi
RECENT="$(find "$APP_ROOT" -maxdepth 1 -name "$DUMP_GLOB" -mmin -60 -print -quit 2>/dev/null || true)"
if [ -z "$RECENT" ]; then
  echo "No Vaultwarden database copy (db_*.sqlite3) from the last hour in $APP_ROOT." >&2
  exit 1
fi
