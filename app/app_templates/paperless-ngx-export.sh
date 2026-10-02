#!/usr/bin/env bash
# Paperless keeps documents in one volume and the database in another (or in
# PostgreSQL/MariaDB). Its document exporter writes both into the export folder
# as one consistent set, which is what this backup reads.
set -euo pipefail
APP_ROOT=__APP_ROOT__
CONTAINER=__CONTAINER__
if [ -n "$CONTAINER" ]; then
  docker exec "$CONTAINER" document_exporter /usr/src/paperless/export --use-folder-prefix --delete || {
    echo "Could not run document_exporter in container $CONTAINER." >&2
    exit 1
  }
fi
# The exporter rewrites manifest.json on every run.
RECENT="$(find "$APP_ROOT" -maxdepth 1 -name 'manifest.json' -mmin -120 -print -quit 2>/dev/null || true)"
if [ -z "$RECENT" ]; then
  echo "No Paperless export (manifest.json) from the last 2 hours in $APP_ROOT." >&2
  exit 1
fi
