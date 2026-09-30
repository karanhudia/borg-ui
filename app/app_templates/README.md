# App templates

One JSON file per app. Quick Start and the Backup Plans wizard list every file
here; no code change is needed to add an app.

To add an app:

1. Copy `immich.json` to `<app>.json`. `detect.image_prefix` matches the app's
   container image; `detect.mount_destination` is the path inside the
   container of the folder to back up.
2. Add the app's official logo as an SVG next to it and name it in `logo`.
   Take it from the app's own repository or press kit, unmodified.
3. Describe each top-level folder under `folders`, in words a user
   understands, with a `role`: `data` (always backed up), `database` (backed
   up; its newest file shows how fresh the app's dump is, flagged after
   `stale_after_hours`) or `rebuildable` (skipped by default). Mark a folder
   rebuildable only when the app's own docs say it rebuilds it.
4. If the app needs a check or dump before the backup, add a script file and
   point `pre_backup_script.file` at it. `__APP_ROOT__` is replaced with the
   app's folder, shell-quoted. It runs on the Borg UI server.
5. Set `verified` to the app version you tested against, and link the app's
   backup docs in `docs_url`.
6. Run `pytest tests/unit/test_app_templates.py`.
