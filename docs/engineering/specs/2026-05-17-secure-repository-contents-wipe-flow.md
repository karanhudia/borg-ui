# Secure Repository Contents Wipe Flow

## Goal

Define a secure Borg UI flow for deleting every archive in a configured
repository while preserving the Borg UI repository record, schedules, scripts,
connection settings, and future backup capability.

This is a product and security design only. It does not implement the wipe
runtime.

## Context

GitHub issue #200 asked for a secure way to delete all contents of a repository
without deleting the repository itself. BOR-26 handled prune backgrounding and
retention-preview behavior, and deliberately left this broader destructive flow
out of that implementation.

Current Borg UI behavior has these relevant pieces:

- single-archive deletion uses `DeleteArchiveJob`;
- manual prune and compact use repository maintenance jobs;
- repository deletion removes the Borg UI record and related references;
- repository stats are refreshed by version-aware `BorgRouter.update_stats`;
- access control already distinguishes global admin permissions from
  repository-scoped viewer/operator roles.

This flow should not be implemented by setting all prune retention values to
zero. Prune has retention semantics, version-specific edge cases, and in Borg 2
it is a soft-delete operation. A contents wipe needs explicit archive deletion,
its own preview, and its own audit trail.

## References

- Borg 1.4 `delete` documents archive deletion, `--dry-run --list`, archive
  glob filters, and the need to run `borg compact` to reclaim repository space:
  https://borgbackup.readthedocs.io/en/stable/usage/delete.html
- Borg 1.4 `compact` documents that compact frees repository space after
  archive deletion and supports progress/threshold behavior:
  https://borgbackup.readthedocs.io/en/stable/usage/compact.html
- Borg 2 `delete` documents archive soft-deletion, `--dry-run --list`,
  `--match-archives`, and `borg undelete` only before compaction:
  https://borgbackup.readthedocs.io/en/latest/usage/delete.html
- Borg 2 `compact` documents that unused chunks from delete/prune are removed
  by compact and encrypted repositories need the Borg key:
  https://borgbackup.readthedocs.io/en/2.0.0b10/usage/compact.html
- Borg 2 `tag` documents the special `@PROT` tag that protects archives from
  delete/prune:
  https://borgbackup.readthedocs.io/en/latest/usage/tag.html

## UX Direction

Use Borg UI's existing MUI language for maintenance dialogs: compact layout,
clear hierarchy, icon plus text for destructive warnings, and accessible
validation. The `ui-ux-pro-max` pass for this issue recommends a flat,
dashboard-oriented SaaS surface with high contrast, controlled form inputs,
visible validation states, and confirmation before irreversible actions.

For this flow specifically:

- do not rely on a browser `window.confirm`;
- do not use heavy left accent borders;
- use a balanced warning panel with an icon, full outline, and background tint;
- use text plus icon, not color alone, for blocked/destructive states;
- use controlled React inputs with inline validation and `role="alert"` or
  equivalent ARIA announcement for validation errors.

## Entry Point

Add a "Wipe contents" action on repository management surfaces where an admin
already starts destructive repository actions:

- repository card overflow/menu;
- repository details/settings actions area if present in the future.

The action is hidden or disabled with an explanatory tooltip unless the current
user has the required wipe permission. It must not appear as a normal archive
list bulk action, because the scope is the entire repository.

## User Flow

1. Admin selects "Wipe contents" for a repository.
2. Borg UI opens a responsive wipe dialog with repository name, repository path,
   Borg version, current archive count, last backup timestamp, and current
   total-size estimate.
3. The primary action is "Generate wipe preview". Execution is unavailable until
   a fresh preview exists.
4. Preview runs a backend dry-run job and returns:
   - archive count that would be deleted;
   - first and last archive timestamps;
   - a scrollable table of archive names or Borg 2 archive IDs;
   - compact choice and expected cleanup semantics;
   - dry-run command output or parsed summary;
   - a preview fingerprint for the archive set.
5. If archive count is zero, the dialog shows "No archives to wipe" and no
   execute action.
6. If preview finds protected or unsupported archives, execution is blocked and
   the blocking reason is shown.
7. To execute, the user must complete a double confirmation:
   - check "I understand this removes every archive and restore point in this
     repository";
   - type the exact phrase `WIPE <repository name>`.
8. The final destructive button reads "Wipe all archives" and remains disabled
   until the preview is fresh, the checkbox is checked, the typed phrase
   exactly matches, and no blocking validation errors remain.
9. After execution starts, the dialog switches to job progress and links to the
   job log. Closing the dialog does not cancel the job.
10. On completion, Borg UI refreshes archive lists, repository stats, dashboard
    state, and MQTT state. The repository remains configured and can receive
    new backups.

## Required UI Copy

Dialog title:

```text
Wipe repository contents
```

Scope summary:

```text
This will delete every archive in this repository. The repository configuration
will remain, but existing restore points will be gone.
```

Warning panel:

```text
This is not repository deletion. Borg UI will keep the repository record,
schedules, scripts, connection settings, and future backup capability. The
archive data selected in this preview cannot be restored through Borg UI after
the wipe completes.
```

Preview button:

```text
Generate wipe preview
```

Preview empty state:

```text
No archives were found in this repository. There is nothing to wipe.
```

Preview stale state:

```text
The archive list changed after this preview was generated. Generate a new
preview before wiping contents.
```

Typed confirmation label:

```text
Type WIPE {{repositoryName}} to confirm
```

Typed confirmation helper when invalid:

```text
The confirmation phrase must match exactly.
```

Compact option:

```text
Run compact after deleting archives to reclaim repository space
```

Compact helper:

```text
Without compact, archive entries are removed but repository disk usage may not
shrink yet. Borg 2 soft-deleted archives may be recoverable with Borg CLI until
compact runs.
```

Final button:

```text
Wipe all archives
```

Success toast:

```text
Repository contents wiped. Repository configuration is still available.
```

Compact failure toast:

```text
Archives were deleted, but compact failed. Run compact later to reclaim space.
```

## Authorization

Execution must require a global admin-level capability, not only
repository-scoped operator access.

Recommended permission rule:

- preview and execute require `repositories.manage_all`;
- the backend also verifies repository access with at least `operator` role as a
  defense-in-depth check;
- API tokens must need the same permission;
- unauthenticated, viewer, and repository-only operator users receive `403`.

Reasoning: wiping all restore points is closer to repository deletion than to
routine maintenance. Existing repository roles do not include a repository-local
admin role, so allowing every repository operator to wipe all contents would be
too broad.

Future enterprise work can add a narrower `repositories.wipe_contents`
capability, but this design should start with the existing admin boundary.

## Backend Contract

Add a version-aware repository wipe service behind `BorgRouter`.

Suggested API:

- `POST /api/repositories/{repo_id}/wipe-preview`
- `POST /api/repositories/{repo_id}/wipe`
- `GET /api/repositories/{repo_id}/wipe-jobs/{job_id}`

Suggested request shape for execution:

```json
{
  "preview_id": 123,
  "preview_fingerprint": "sha256:...",
  "confirmation_phrase": "WIPE Primary Repository",
  "understood": true,
  "run_compact": true
}
```

Suggested persisted model: `RepositoryWipeJob`.

Minimum fields:

- `id`;
- `repository_id`;
- `repository_path`;
- `repository_name`;
- `borg_version`;
- `status`;
- `phase`;
- `archive_count`;
- `archive_fingerprint`;
- `archive_manifest_json`;
- `dry_run_output`;
- `run_compact`;
- `requested_by_user_id`;
- `confirmed_by_user_id`;
- `started_at`;
- `confirmed_at`;
- `completed_at`;
- `progress`;
- `progress_message`;
- `error_message`;
- `log_file_path`;
- `has_logs`.

Statuses should distinguish at least:

- `previewed`;
- `pending`;
- `running`;
- `completed`;
- `completed_compaction_failed`;
- `completed_with_warnings`;
- `failed`;
- `failed_partial`;
- `cancelled`.

The job record is part of the audit trail and must not be deleted during normal
log cleanup.

## Preview Behavior

Preview is a required dry-run, not just a frontend archive count.

Preview must:

1. acquire the repository command lock;
2. reject the request if backup, restore, check, prune, compact, delete-archive,
   or another wipe job is running for the repository;
3. list current archives with the same version-aware repository environment used
   for backup and maintenance operations;
4. compute a stable fingerprint over the archive identity set;
5. run Borg's dry-run delete with list output;
6. store the archive manifest and dry-run output in `RepositoryWipeJob`;
7. return a preview payload suitable for the confirmation UI.

The archive manifest should use stable identities:

- Borg 1: archive names are unique and may be used as identities.
- Borg 2: archive IDs are unique; store full IDs and display names/timestamps
  separately.

If preview cannot confidently identify the archive set, execution must be
blocked.

## Execution Behavior

Execution must:

1. load the preview job;
2. verify the same user or another currently authorized admin is confirming;
3. verify `understood` and the exact confirmation phrase;
4. reacquire the repository command lock;
5. reject if another repository operation is running;
6. re-list the repository archives and compare the current fingerprint with the
   preview fingerprint;
7. abort with `409` if the archive set changed;
8. run the version-aware delete command;
9. run compact when requested;
10. refresh repository stats and archive caches;
11. publish MQTT/state updates;
12. persist logs and final status.

The service must never call Borg repository-delete commands (`borg delete REPO`
without archive selection or Borg 2 `repo-delete`/`rdelete`) for this feature.
The configured repository must remain in Borg UI.

## Borg 1 Behavior

Use Borg 1 archive deletion, not prune.

Preview command shape:

```bash
borg delete --list --dry-run --glob-archives '*' <repo>
```

Execution command shape:

```bash
borg delete --list --stats --glob-archives '*' <repo>
```

When the repository has `remote_path`, include `--remote-path <remote_path>` in
the same position used by the existing Borg 1 services. Use the existing
passphrase and SSH environment builder. Do not pass secret values in logs.

After delete, run compact by default unless the user explicitly opted out:

```bash
borg compact --progress --verbose <repo>
```

If compact is skipped or fails, Borg UI must say that archives were deleted but
space may not be reclaimed yet. A later manual compact should remain available.

## Borg 2 Behavior

Use Borg 2 archive deletion, not repository deletion.

Preview command shape:

```bash
borg2 -r <repo> delete --list --dry-run -a 'sh:*'
```

Execution command shape:

```bash
borg2 -r <repo> delete --list -a 'sh:*'
```

Compaction command shape:

```bash
borg2 -r <repo> compact
```

Use the configured Borg 2 binary, passphrase, remote path, and SSH environment
from the existing Borg 2 wrapper.

Borg 2 archive deletion is soft deletion until compact runs. This creates two
important UX requirements:

- if `run_compact` is enabled, the UI must explain that Borg CLI undelete is no
  longer expected after compaction;
- if `run_compact` is disabled or fails, the UI must explain that disk space is
  not reclaimed and Borg CLI undelete may still be possible until a future
  compact.

If any archive has the special `@PROT` tag, preview must block execution and
list the protected archives. Borg UI should not auto-remove protection tags in
this flow.

## Compaction Semantics

Default `run_compact` to enabled because users expect a wipe to reclaim space.
Allow advanced users to disable it only after acknowledging that repository disk
usage may not shrink.

Compaction is part of the wipe job, not a separate user-facing compact job, so
the audit trail shows one destructive operation. Internally the service may
reuse compact helpers, but the final job state must distinguish:

- delete failed before compact;
- delete succeeded and compact succeeded;
- delete succeeded and compact failed;
- delete succeeded and compact was skipped.

When compact is skipped or fails, repository stats refresh should still run so
`archive_count` becomes zero while `total_size` may remain non-zero.

## Audit Trail

Every preview and execution must record structured audit data:

- actor user id and username;
- repository id, name, path, and Borg version;
- preview id and archive fingerprint;
- archive count;
- whether compact was requested;
- command phase transitions;
- final status and error summary;
- timestamps for preview, confirmation, delete start, compact start, and finish.

Logs must redact passphrases, key material, environment secrets, and token
values. Repository paths and archive names may be logged because they are
already visible to authorized admins, but the UI should not expose logs to users
without the same admin permission.

## Error and Recovery Behavior

No automatic rollback is promised.

Expected states:

- Preview failure: no repository changes. Show the Borg error and keep execute
  disabled.
- Confirmation mismatch: no backend execution. Keep the final button disabled.
- Archive set changed after preview: backend returns `409`, marks the preview
  stale, and requires a new preview.
- Delete command failure before deleting archives: mark `failed`, keep logs, and
  refresh stats.
- Delete command failure after partial progress: mark `failed_partial`, show
  that some archives may already be gone, keep logs, and refresh stats.
- Compact failure after successful delete: mark `completed_compaction_failed`;
  show manual compact guidance.
- Cancellation before process start: mark `cancelled`.
- Cancellation during delete or compact: mark `cancelled` only if Borg exits
  cleanly with no partial delete signal; otherwise mark `failed_partial` or
  `completed_compaction_failed` as appropriate.

Recovery expectations:

- Borg UI does not provide a one-click restore/undelete for wiped contents.
- Users who need recoverability must restore from an external backup or replica.
- Borg 2 may allow CLI `borg undelete` before compaction, but Borg UI should
  present that as best-effort external recovery, not a supported product
  guarantee.
- Once compact succeeds, Borg UI should treat the wipe as irreversible.

## Post-Wipe Cleanup

On any terminal execution state, run best-effort cleanup:

- invalidate archive browse/list caches for the repository;
- clear selected-archive UI state if the user is on the Archives page;
- refresh repository stats through `BorgRouter.update_stats`;
- update dashboard health/status surfaces;
- sync MQTT state;
- leave backup schedules, backup plans, scripts, SSH connections, repository
  passphrase/keyfile configuration, and repository notification settings intact.

The repository should remain selectable for future backups. The next successful
backup should repopulate archive lists and stats normally.

## Non-Goals

- Do not securely erase storage media or promise cryptographic erasure.
- Do not delete the Borg UI repository record.
- Do not delete schedules, backup plans, scripts, SSH keys, connections, logs,
  or historical backup job records.
- Do not build bulk file-level removal from existing archives.
- Do not add a Borg 2 protected-tag management flow.
- Do not make prune-with-zero-values a supported wipe path.

## Implementation Outline

Backend:

- add `RepositoryWipeJob` model and migration;
- add repository wipe preview/execute/status routes;
- add version-aware `BorgRouter.wipe_preview` and `BorgRouter.wipe_execute`;
- add Borg 1 and Borg 2 service helpers for list/dry-run/delete/compact;
- add repository operation conflict checks covering all maintenance and archive
  deletion jobs;
- add structured audit logging and log file persistence;
- refresh stats/cache/MQTT state after terminal states.

Frontend:

- add a repository contents wipe dialog;
- gate the entry point on `repositories.manage_all`;
- add preview loading, stale preview, zero archives, protected archives,
  confirmation mismatch, running, success, partial failure, and compact failure
  states;
- add locale keys in every supported locale;
- add Storybook coverage and snapshots for the destructive confirmation states.

Tests:

- backend route authorization tests;
- backend preview/execution command construction for Borg 1 and Borg 2;
- backend archive-set fingerprint mismatch test;
- backend protected Borg 2 archive blocking test;
- backend compact success/failure tests;
- frontend dialog validation and disabled-state tests;
- Storybook story plus snapshot for the dialog states.

## Validation Plan

Dry-run/preview proof:

1. Create a disposable Borg 1 repository with two archives.
2. Generate wipe preview.
3. Verify preview lists both archives and the final action is disabled until
   typed confirmation is valid.
4. Run `borg list <repo>` after preview and verify both archives still exist.
5. Repeat with a disposable Borg 2 repository.
6. For Borg 2, include a protected `@PROT` archive proof and verify preview
   blocks execution.

Successful wipe proof:

1. Create a disposable Borg 1 repository with two archives.
2. Generate preview, confirm, execute with compact enabled.
3. Verify `borg list <repo>` returns zero archives.
4. Verify Borg UI repository record remains and `archive_count` refreshes to
   zero.
5. Verify a new backup can be created into the same repository.
6. Repeat with a disposable Borg 2 repository and `borg2 repo-list`.

Automated validation for the implementation:

- `ruff check app tests`;
- `ruff format --check app tests`;
- focused backend tests for wipe routes/services/router;
- `cd frontend && npm run check:locales`;
- `cd frontend && npm run typecheck`;
- `cd frontend && npm run lint`;
- focused Vitest tests for the wipe dialog and API client;
- `cd frontend && npm run build`;
- `cd frontend && npm run snapshots` after adding the Storybook story.

Docs validation for this design-only change:

- `git diff --check`;
- placeholder scan for incomplete sections;
- self-review against the BOR-31 acceptance criteria.
