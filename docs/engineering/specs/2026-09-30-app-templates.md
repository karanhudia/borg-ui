# App templates

Status: implemented 2026-09-30.

## Problem

Most new users install Borg UI to back up one well-known self-hosted app
(Immich, Vaultwarden, Paperless-ngx, Home Assistant, Nextcloud). They have to
work out the data folder, the database, and what is safe to skip.

## Design

- **Data, not code.** `app/app_templates/<id>.json` plus an optional
  pre-backup script. Loaded and validated by `app.app_templates`.
- **Detection.** `POST /api/source-discovery/apps/detect` reuses the container
  scan without size probes and returns only containers whose image matches a
  template, with the matched mount's path as Borg UI reads it and whether it
  is readable. It is free on every plan: unlike the full container scan
  (`container_backups`, Pro) it reveals nothing but known apps.
  `GET /api/source-discovery/apps` lists templates.
- **Quick Start.** New first step `app`. Picking an app sets default excludes
  and the app's cron. The folders step shows `AppTemplateFolderPanel`: found
  (fills the folder once), found but unreadable (compose line
  `- <host>:/local<host>:ro`), not found (manual hint). A `create_script`
  action creates the pre-backup check before the plan.
- **Backup Plans wizard.** An **Apps** tab in the source chooser
  (`AppSourcePanel`). Each app is a source location with an `app` selection:
  template id and version, its folder (`root`), the plan excludes it added,
  and its check as a source-level pre-backup script (run on the SSH machine for
  remote sources, like database scripts). On Apply the dialog swaps the old
  apps' excludes for the new ones, so removing an app removes its excludes.
- **Access.** Detect and inspect need the operator or admin role; operators
  inspecting local folders stay inside `LOCAL_MOUNT_POINTS`.

## Limits

- Quick Start still attaches the check as a plan-level script, so there it
  is only added for apps on this server.
- One folder per app (`detect.mount_destination`). Apps with data in several
  mounts need a `sources` list.
- Agents cannot be scanned; the user types the folder.

## Immich

Verified against Immich v3.2.4 docs and compose file: backs up
`UPLOAD_LOCATION` (mounted at `/data`), which includes Immich's own nightly DB
dumps in `backups/`; skips `thumbs/` and `encoded-video/`; runs at 03:00; the
check fails the backup when no `immich-db-backup-*` dump is newer than 26h.
Restore test on a real install is still open (`restore_tested: false`).
