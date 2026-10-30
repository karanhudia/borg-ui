# Operator Path Confinement

## Approved behavior

Constrain paths newly selected by non-admin users while preserving stored backup plans. Apply the supplied operator-path patch on main `59fe26261c2ad714b8a7e3f96051fa4e7fa3225e`; keep administrator behavior except SSHFS staging escapes. No frontend changes, version bump, agent allowed-root model, runtime revalidation, or automatic migration.

New server-local sources in `source_directories` and `source_locations` must be absolute, have no `..` segment, resolve inside `LOCAL_MOUNT_POINTS`, and neither contain nor be inside `/app` or `DATA_DIR`. Apply the same checks to new `R`/`r` roots in plan `custom_flags` and link `custom_flags_override`, including disabled links. New agent sources and agent pattern roots require an administrator.

New database `dump_path`, container `export_path`, and btrfs `staging_path` metadata must be absolute, contain no `..`, and avoid the reserved application/data directories; mount-point membership is not required. Existing stored sources, pattern roots, and metadata can be retained or removed. A plan without repositories has no trusted stored paths. Invalid stored source data counts as no stored paths for non-admin validation.

Agent repository restores require an administrator and return HTTP 403 with `backend.errors.auth.notEnoughPermissions` before operation/job dispatch. Preserve server destination errors and agent restore-check temporary targets, previews, downloads, and SSH destinations.

Non-admin Borg mount targets and occupied-target siblings must resolve strictly below `DATA_DIR/mounts`, with denial before directory creation. SSHFS staging paths for all users must stay below their temporary root, normalize `..`, reject symlink escapes before mkdir/mount, and preserve spelling for paths without `..`.

## Compatibility and limits

Stored plans keep running manually and on schedule without path migration. Administrators must audit source directories/locations, plan and link pattern roots, metadata staging, and existing agent paths. Checks run when paths are selected, so later symlink replacement remains possible. Pattern-file contents, ZFS settings, and database `backup_paths` do not gain these checks. New metadata path strings from remote SSH locations, including database `dump_path` and container `export_path`, receive server-side reserved-path checks. Database and container metadata scripts with `script_execution_target=source` continue to execute on the SSH host; these checks do not confine that host's filesystem or symlinks. Document these limits without claiming full confinement.

## Acceptance evidence

Run supplied tests before product changes, then both new modules and neighboring backup-plan, restore, mount and local-path tests. Add a focused role-denial error-key assertion and prove RED/GREEN. Run scoped ruff lint/format and `git diff --check`. The landing controller owns the full combined Linux suite and disposable runtime validation. Retain Benjamin Stein author attribution and Codex coauthor credit.
