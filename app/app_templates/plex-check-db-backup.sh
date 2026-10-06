#!/usr/bin/env bash
# Plex copies its database every three days (Scheduled Tasks, keeps three).
# The live file can change while Borg reads it, so fail the backup when no
# copy is newer than 100h: the archive would hold no safe database.
set -euo pipefail
APP_ROOT=__APP_ROOT__
DUMP_DIR="$APP_ROOT/Plug-in Support/Databases"
RECENT="$(find "$DUMP_DIR" -maxdepth 1 -name 'com.plexapp.plugins.library.db-[0-9]*' -mmin -6000 -print -quit 2>/dev/null || true)"
if [ -z "$RECENT" ]; then
  echo "No Plex database backup from the last 100 hours in $DUMP_DIR." >&2
  echo "Turn on Settings > Scheduled Tasks > Backup database every three days in Plex." >&2
  exit 1
fi
