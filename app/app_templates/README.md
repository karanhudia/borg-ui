# App templates

One JSON file per app. Quick Start and the Backup Plans wizard list every file
here; no code change is needed to add an app.

To add an app:

1. Copy `immich.json` to `<app>.json`. `detect.images` lists every image the
   app is published under, without tag (`vaultwarden/server` also matches
   `docker.io/vaultwarden/server:1.37.3`); `detect.mount_destinations` is the
   path inside the container of the folder to back up. If some images nest
   the app's folder deeper inside that mount, map them in
   `detect.root_subpaths` (see `plex.json`: hotio mounts Plex's folder at
   /config, the official and linuxserver images put it under
   `Library/Application Support/Plex Media Server`).
2. Add the app's official logo as an SVG next to it and name it in `logo`.
   Take it from the app's own repository or press kit, unmodified.
3. Describe each folder under `folders` (relative to the app's folder; nested
   paths like `Library/Application Support/...` are fine; listed folders must
   not overlap, since their sizes are added up), in words a user
   understands, with a `role`: `data` (always backed up), `database` (backed
   up; its newest file shows how fresh the app's dump is, flagged after
   `stale_after_hours`) or `rebuildable` (skipped by default). Mark a folder
   rebuildable only when the app's own docs say it rebuilds it.
4. If the app needs a check or dump before the backup, add a script file and
   point `pre_backup_script.file` at it. `__APP_ROOT__` is replaced with the
   app's folder and `__CONTAINER__` with the detected container's name, both
   shell-quoted; the container is empty when the user picked the folder by
   hand. Scripts that need the app to write its own dump use `docker exec`
   when there is a container, then check the dump is fresh either way (see
   `vaultwarden-db-backup.sh`). It runs where the app runs.
5. Set `verified` to the app version you tested against, and link the app's
   backup docs in `docs_url`.
6. Run `pytest tests/unit/test_app_templates.py`.
