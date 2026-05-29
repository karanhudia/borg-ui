# Rclone Storage Integration Spec

## Goal

Add a first-class Borg UI design for rclone-backed repository storage so users
can use S3-compatible buckets, Backblaze B2, Google Drive, WebDAV, SFTP, and
other rclone providers as off-site backup targets without turning Borg UI into
a generic file-sync product.

## Current Signal

- GitHub issue
  [#211](https://github.com/karanhudia/borg-ui/issues/211) requests rclone as
  an optional backend and suggests selecting an existing rclone remote, a remote
  path, and extra flags.
- Repository setup currently models repository location as Borg UI server local
  storage or SSH remote storage. `WizardStepLocation` uses
  `repositoryLocation: "local" | "ssh"`, and the backend repository model stores
  `repository_type`, `connection_id`, `remote_path`, `executor_type`, and
  optional `agent_machine_id`.
- `docs/plan-content.json` already lists `rclone_support` as a coming-soon Pro
  feature, but the app has no rclone-specific model, API, service, UI path, or
  validation.
- Current SSH repository docs explain direct Borg-over-SSH and remote-direct
  backups, but not cloud/object storage destinations.

## Product Decision

The recommended default is not "Borg writes directly to the cloud bucket."
The first supported rclone mode should be a local Borg repository cache that
Borg UI mirrors to the rclone remote after Borg operations finish.

This means:

1. Borg always reads and writes a normal local filesystem repository under a
   persistent Borg UI cache root.
2. After successful Borg writes, Borg UI runs an rclone mirror job from that
   local repository directory to the configured rclone target.
3. For restore, browse, check, prune, and compact, Borg UI uses the local cache
   when it is present and marked current. If the cache is missing or stale, Borg
   UI hydrates it from the remote first.
4. The rclone remote is the durable off-site copy, while the local cache is the
   operational working copy.

This is the safest MVP because Borg repositories are filesystem-based,
transactional stores with locks, indexes, hints, and append-only segment files.
Rclone can mount remotes through FUSE, but rclone's own mount documentation says
write-heavy applications need VFS write/full caching for non-sequential writes.
Object storage providers also vary in directory semantics, latency, modtime
support, and consistency. A direct mount mode can be considered later as an
advanced experimental option for known-good providers, but it should not be the
default storage contract.

Official references:

- Rclone usage and remote path syntax:
  https://rclone.org/docs/
- Rclone `copy` and `sync` behavior:
  https://rclone.org/commands/rclone_copy/ and
  https://rclone.org/commands/rclone_sync/
- Rclone mount behavior and VFS cache constraints:
  https://rclone.org/commands/rclone_mount/
- Borg repository file structure and lock semantics:
  https://borgbackup.readthedocs.io/en/stable/internals/data-structures.html

## Scope

- Add an rclone storage target concept for repositories.
- Add rclone remote configuration discovery, test, browse, and health checks.
- Add a local-cache-plus-remote-mirror runtime path for create, import,
  backup, restore, archive browsing, check, prune, compact, and break-lock
  where those operations are supported today.
- Add a Cloud Storage page for reusable rclone remotes, plus repository setup UI
  for selecting an existing remote and configuring repository-owned remote path,
  local cache preview, sync policy, and advanced flags.
- Add status surfaces for cache state, last sync, pending sync, failed sync,
  hydration, and drift/conflict protection.
- Add docs and smoke tests that prove a repository can be created locally,
  mirrored to an rclone remote, hydrated into an empty cache, and read by Borg.

## Out Of Scope

- Making Borg UI a general-purpose rclone file manager.
- Bidirectional sync between local cache and remote after independent remote
  edits. The remote path is owned by Borg UI once configured.
- Direct rclone mount as the default repository backend.
- Provider-specific S3, B2, Google Drive, or WebDAV clients inside Borg UI.
  Borg UI should delegate provider protocol behavior to rclone.
- Multi-writer or active/active Borg UI instances sharing one rclone remote.
- Running rclone-backed repositories on managed agents in the first slice.
  Agent support should be a later extension after server-owned rclone is stable.

## Storage Model

Add explicit rclone storage records instead of overloading SSH fields:

- `rclone_remotes`
  - `id`
  - `name`
  - `provider`
  - `config_source`: `managed`, `imported`, or `external_file`
  - `config_path`
  - `redacted_config`
  - `last_tested_at`
  - `last_test_status`
  - `last_error`
- `repository_storage`
  - `repository_id`
  - `backend`: `local`, `ssh`, `agent_local`, or `rclone`
  - `rclone_remote_id`: selected `rclone_remotes.id`
  - `rclone_remote_path`: relative path inside the remote, without a
    `remote:` prefix
  - `cache_path`: server-derived path under `RCLONE_CACHE_ROOT`
  - `sync_policy`: `after_success`, `manual`, or `scheduled`
  - `sync_direction`: always `cache_to_remote` for normal operations
  - `sync_status`: `current`, `pending`, `syncing`, `failed`, `hydrating`
  - `last_synced_at`
  - `last_hydrated_at`
  - `last_remote_check_at`
  - `last_sync_error`
  - `extra_flags`

Keep `repositories.path` as the Borg path that existing Borg services use. For
rclone repositories, this should be the local cache path. The new storage row
describes where the repository is mirrored.

Canonical target shape:

- Persist `rclone_remote_id` as the configured remote identifier.
- Persist `rclone_remote_path` as a relative path such as
  `borg-ui/repositories/app`.
- Compose the full rclone target only inside backend command builders by
  resolving the remote name and joining `<remote_name>:<rclone_remote_path>`.
- API responses may include a derived, read-only `rclone_target` preview such
  as `prod-s3:borg-ui/repositories/app`, but clients must not submit that full
  URI back as `rclone_remote_path`.
- Derive `cache_path` server-side from `RCLONE_CACHE_ROOT` and repository
  identity. Clients must not submit a custom cache path in create or import
  requests.

## Runtime Flow

### Create New Rclone Repository

1. User selects "Cloud storage (rclone)" in the repository location step.
2. User picks an existing rclone remote or creates/imports one.
3. User enters a relative remote path such as `borg-ui/repositories/app`.
4. Borg UI derives a local cache path such as
   `/data/rclone-cache/repositories/<repository-id>`.
5. Borg UI runs `borg init` against the local cache path.
6. Borg UI writes a Borg UI ownership marker under the cache metadata area.
7. Borg UI runs a first mirror job from cache to remote.
8. Repository is marked `current` only after the mirror succeeds.

### Import Existing Rclone Repository

1. User selects an rclone remote and relative remote path.
2. Borg UI composes the full rclone target server-side and validates it by
   listing the Borg repository files (`README`, `config`, `data/`) through
   rclone.
3. Borg UI hydrates a local cache from the remote into a job-scoped temporary
   cache directory.
4. Borg UI runs `borg info` or `borg2 repo-info` on the hydrated cache using
   the provided passphrase/keyfile.
5. Borg UI atomically promotes the hydrated cache to the repository cache path
   and creates the repository record.

### Backup

1. Acquire the existing repository command lock.
2. Refuse to run if the repository is currently hydrating or syncing.
3. If cache state is missing or stale, hydrate from the remote first.
4. Run Borg against the local cache.
5. If Borg succeeds or exits with accepted warnings, run the mirror job.
6. Mark the backup result separately from mirror result:
   - Borg failed: job failed, no mirror.
   - Borg succeeded and mirror succeeded: job completed.
   - Borg succeeded and mirror failed: backup job completed with warnings,
     repository sync status `failed`, retry available.

### Read Operations

Archive list, archive browse, info, restore, check, prune, compact, delete
archive, and break-lock should use the local cache under the same command lock.
Operations that mutate the repository must trigger a remote mirror afterward.
Read-only operations can run without a mirror unless they hydrate or repair
cache state.

### Hydration

Hydration copies remote contents into a temporary local cache directory, verifies
with Borg, then promotes it. A failed hydration must leave the previous cache in
place. If no previous cache exists, the repository remains unavailable until a
successful hydration.

### Sync Command Choice

Use `rclone sync` for repository mirrors after a successful Borg transaction so
the composed rclone target exactly matches the local Borg repository tree. Use
`rclone copy` only for non-destructive diagnostics or future migration helpers.
Because sync can delete remote files that are absent locally, Borg UI must
require an empty or verified Borg-owned relative remote path before enabling
normal sync.

## Backend Design

- Add `app/services/rclone_service.py` for subprocess-safe rclone command
  execution. It should never use shell strings.
- Add `app/services/rclone_repository_service.py` for create/import/hydrate/sync
  orchestration and ownership-marker validation.
- Add a small command builder layer for:
  - `rclone version`
  - `rclone listremotes`
  - `rclone lsf` or `lsjson`
  - `rclone about`
  - `rclone sync`
  - `rclone check`
- Add database migrations for rclone remotes, repository storage metadata, and
  rclone sync jobs.
- Add API routes:
  - `GET /api/rclone/status`
  - `GET /api/rclone/remotes`
  - `POST /api/rclone/remotes`
  - `POST /api/rclone/remotes/{id}/test`
  - `GET /api/rclone/remotes/{id}/browse`
  - `POST /api/repositories/{id}/rclone/sync`
  - `POST /api/repositories/{id}/rclone/hydrate`
  - `GET /api/repositories/{id}/rclone/status`
- Update existing repository APIs so rclone-backed repositories serialize
  storage metadata and route mutation operations through mirror hooks.
- Update Docker/runtime packaging to include rclone or provide a clear
  unavailable state if the host image does not include it. The product path is
  much cleaner if the official runtime image includes rclone.
- Add settings for:
  - `RCLONE_CONFIG_ROOT` defaulting to `/data/rclone`
  - `RCLONE_CACHE_ROOT` defaulting to `/data/rclone-cache`
  - `RCLONE_SYNC_TIMEOUT`
  - `RCLONE_HYDRATE_TIMEOUT`
  - `RCLONE_DEFAULT_TRANSFERS`
  - `RCLONE_DEFAULT_CHECKERS`

## Secret Handling

- Treat rclone config as sensitive. Rclone's obfuscation is not a replacement
  for Borg UI secret handling.
- Store managed rclone remote sections in the server-owned
  `/data/rclone/rclone.conf` with restrictive file permissions.
- Redact tokens, keys, passwords, endpoints, and bucket names from logs unless
  the field is explicitly safe to display.
- Keep Borg passphrases/keyfiles in the existing Borg UI repository secret path.
- Never put rclone credentials into generated command previews.
- Add export/import handling so rclone metadata can be exported without raw
  credentials by default.

## Frontend Design

Use the existing operational dashboard style:

- Small, dense controls.
- MUI cards with balanced outlines and subtle background tint.
- Existing icon language from MUI/lucide.
- No heavy left accent borders.
- No decorative gradients or marketing-style hero sections.

### Repository Location Step

Cloud Storage remote management lives in the BACKUP sidebar as a reusable
rclone remote registry. It lists remotes, provider/config metadata, connection
test state, browse actions, and repository usage counts. It must not create
repositories or add a Backup Plan wizard step.

Repository setup keeps a single Location step with four destination cards:

- Borg UI server
- Remote machine (SSH)
- Managed agent
- Cloud Storage

When Cloud Storage is selected, the wizard shows repository-owned rclone
fields below the cards:

- Remote selector with test status.
- Provider badge and remote name.
- Relative remote path field with browse action.
- Server-derived, read-only local cache path preview.
- Sync policy selector:
  - Sync after successful Borg job (default)
  - Manual sync
  - Scheduled sync
- Advanced rclone flags in a collapsed section.
- Clear copy that Borg writes to the local cache first and Borg UI mirrors the
  repository to the rclone remote.

### Review Step

Show a route preview:

`Sources -> Borg UI server Borg process -> local cache -> rclone sync -> remote`

Review must call out:

- Local cache path.
- Relative remote path and derived full rclone target preview.
- Last remote test status.
- Whether sync is automatic or manual.
- Local disk requirement: cache should be sized for the full repository.
- Warning if the remote path is not empty or not verified as Borg-owned.

### Repository Card

Add storage chips and actions:

- `Rclone mirror`
- `Synced 12 minutes ago`
- `Sync pending`
- `Sync failed`
- `Hydrate cache`
- `Run sync now`

The card should keep existing repository action density and avoid turning sync
state into a large alert unless the repository is unavailable.

## UX Mockup

The HTML mockup for this spec is stored at:

`docs/engineering/mockups/2026-05-24-rclone-storage-integration.html`

It shows:

- Rclone as a repository location.
- Remote/provider configuration.
- Local cache and sync policy.
- Review route preview.
- Repository card sync status.

## Validation Plan For Implementation

- Backend unit tests for rclone command builders and redaction.
- Backend unit tests for remote path ownership checks and dangerous sync
  prevention.
- Backend unit tests for repository create/import/hydrate/sync state
  transitions.
- Backend API tests for remotes, browse, test, manual sync, and hydrate.
- Integration test with an rclone local filesystem remote:
  - create repository cache
  - mirror to remote
  - delete cache
  - hydrate from remote
  - list archives with Borg
- Frontend tests for location selection, payload shape, disabled/unavailable
  states, sync status rendering, and review route preview.
- Storybook stories for create, import, failed sync, hydration required, and
  unavailable rclone binary states.
- Storybook snapshots for all changed stories.
- Runtime walkthrough through create -> backup -> mirror -> cache delete ->
  hydrate -> archive list.

## Rollout

- Gate behind `rclone_storage_beta_enabled` and the existing Pro plan feature
  entry for `rclone_support`.
- Start with server-owned rclone repositories only.
- Add telemetry-safe counters for rclone repository count and sync failure
  categories, without provider credentials or paths.
- Mark direct mount as unsupported in UI copy. The follow-up decision record
  `docs/engineering/specs/2026-05-28-direct-rclone-mount-decision.md`
  rejects direct `rclone mount` support until a separate provider-specific
  proof matrix is satisfied.

## Self-Review

- Acceptance coverage: the spec answers direct-vs-sync architecture, backend
  scope, frontend scope, security, rollout, validation, and failure modes.
- Scope boundary: direct rclone mount, managed-agent rclone, and bidirectional
  sync are explicitly out of scope for the first implementation slice.
- UI consistency: design follows Borg UI's existing repository wizard, compact
  status chips, and balanced-outline surfaces rather than a new marketing
  visual language.
