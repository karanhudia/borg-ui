# Automated Configuration Export Spec

## Problem

Borg UI can export repository configuration from the web UI, but disaster
recovery routines need an unattended export path. A pre-backup script should be
able to capture the same borgmatic-compatible configuration data without a
browser session or manual download.

The current disaster recovery guidance still correctly says that `/data` is the
full recovery boundary. The automated export is an additional migration and
audit artifact, not a replacement for backing up `/data`, `.secret_key`, SSH
material, logs, and the database.

## Desired Outcome

Operators can run a supported command from the Borg UI runtime environment to
write the current export/import configuration artifact to a file or stdout. The
artifact uses the same repository export service and YAML/ZIP shape as the web
UI export endpoint.

## Scope

- Add a script module callable as:

  ```bash
  python3 -m app.scripts.export_config --output /path/to/borg-ui-config.export
  ```

- Support exporting all repositories by default.
- Support selecting repositories with repeated `--repository-id` flags.
- Support excluding schedule-derived retention data with `--no-schedules`.
- Support `--output -` for stdout so shell pipelines can redirect the artifact.
- Keep single-repository exports as YAML and multi-repository exports as ZIP,
  matching the UI endpoint behavior.
- Refactor shared artifact generation out of the FastAPI route so the route and
  script cannot drift.
- Document the command in export/import and disaster recovery docs, including
  a pre-backup script example.

## Out of Scope

- Importing full Borg UI `/data` state from this export.
- Exporting users, auth tokens, logs, encrypted SSH key material, rclone config,
  or runtime-generated secrets.
- Adding a new frontend UI flow.
- Scheduling Borg UI's own `/data` backup automatically.

## Design

The backend already has `BorgmaticExportService.export_all_repositories()` for
the web export flow. Add a small immutable artifact value object and a
`build_borgmatic_export_artifact()` helper near that service. The helper takes
the exported `(repository_name, config)` tuples and returns bytes, media type,
and default filename.

`app/routers/config.py` will call the helper and translate it into a FastAPI
`Response`. `app/scripts/export_config.py` will open a `SessionLocal`, call the
same service/helper pair, and write the bytes to a filesystem path or
`stdout.buffer`.

The script will return a non-zero exit code when no repositories match the
requested selection or when the output path cannot be written. It will not
perform authentication because it is intended to run locally inside the trusted
Borg UI process/container context against the configured database.

## Validation

- Add service tests proving YAML/ZIP artifact generation is stable and shared.
- Add script tests proving the CLI writes YAML for one repository, ZIP for
  multiple repositories, honors `--repository-id`, and fails clearly when no
  repositories are exportable.
- Run targeted pytest for the service/API/script tests.
- Run backend lint and format checks.
- Run a local smoke command against a temporary SQLite database to prove the
  documented module invocation writes an export file.

## Notes

- Upstream request: https://github.com/karanhudia/borg-ui/issues/538
- Existing UI export endpoint: `POST /api/config/export/borgmatic`
- Existing user docs: `docs/export-import.md`, `docs/disaster-recovery.md`
