# App templates

One JSON file per app. Quick Start and the Backup Plans wizard list every file
here; no code change is needed to add an app.

To add an app:

1. Copy `immich.json` to `<app>.json`. `detect.image_prefix` matches the app's
   container image; `detect.mount_destination` is the path inside the
   container of the folder to back up.
2. List under `excludes` only folders the app's own docs say it rebuilds.
   Paths are relative to that folder.
3. If the app needs a check or dump before the backup, add a script file and
   point `pre_backup_script.file` at it. `__APP_ROOT__` is replaced with the
   app's folder, shell-quoted. It runs on the Borg UI server.
4. Set `verified` to the app version you tested against, and link the app's
   backup docs in `docs_url`.
5. Run `pytest tests/unit/test_app_templates.py`.
