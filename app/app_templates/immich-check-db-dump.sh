#!/usr/bin/env bash
# Immich writes its own database dumps to UPLOAD_LOCATION/backups (daily, 02:00).
# Fail the backup when none is newer than 26h, so an archive never silently
# holds photos without the database that indexes them.
set -euo pipefail
APP_ROOT=__APP_ROOT__
DUMP_DIR="$APP_ROOT/backups"
RECENT="$(find "$DUMP_DIR" -maxdepth 1 -name 'immich-db-backup-*' -mmin -1560 -print -quit 2>/dev/null || true)"
if [ -z "$RECENT" ]; then
  echo "No Immich database dump from the last 26 hours in $DUMP_DIR." >&2
  echo "Turn on Administration > Settings > Backup in Immich." >&2
  exit 1
fi
