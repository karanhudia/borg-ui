# Direct Borg 2 Rclone Repository Spec

## Context

BOR-66 added rclone remotes and server-owned rclone-backed repositories that use
a local Borg cache. BOR-67 moved cloud storage out of the primary repository
location flow and into an optional Cloud Mirror step for normal repositories.
BOR-74 adds a different capability: Borg 2 can talk to an rclone backend
directly, so Borg UI should support `rclone:` repository URLs without making
them look like cloud mirrors or cached rclone repositories.

The current API rejects `storage_backend: "rclone"` with Borg 2 before command
routing. That protects existing cache-backed behavior, but blocks the Borg 2
direct repository use case.

## Scope

- Add an explicit advanced repository mode for direct Borg 2 rclone URLs.
- Keep the default primary-location flow as Borg UI Server, SSH Server, or
  Managed Agent plus optional Cloud Mirror.
- Preserve existing cached rclone repository compatibility for
  `storage_backend: "rclone"`.
- Use a new request/response storage backend value, `rclone_direct`, for direct
  Borg 2 rclone repositories.
- Do not create `RepositoryStorage` rows, local cache directories, rclone sync
  jobs, or cloud mirror status for direct rclone repositories.
- Store the direct `rclone:remote:path` URL as the repository path and route
  Borg operations through the Borg 2 services.

## UX

The direct mode is exposed from the Location step as an advanced option, not as
one of the normal location cards. The normal path remains:

1. Choose Borg UI Server, SSH Server, or Managed Agent.
2. Optionally enable Cloud Mirror in the separate Cloud Mirror step.
3. Continue through Security, Advanced, and Review.

When the advanced direct rclone option is enabled:

- Borg version is set to 2 and the mode is disabled unless Borg 2 is selected.
- The repository path field is labeled as a direct rclone repository URL, with
  examples such as `rclone:remote-name:path/to/repository`.
- File browsing is disabled because the URL is not a local or SSH filesystem
  path.
- The Cloud Mirror step is skipped and mirror fields are cleared.
- Review calls out that Borg writes directly through rclone, with no Borg UI
  cache, no mirror sync status, and rclone/Borg failures surfacing during Borg
  operations.

The UI follows the existing flat MUI wizard pattern with progressive disclosure,
subtle full outlines or background tinting, and no heavy left accent borders.

## Backend Behavior

- `storage_backend: "rclone_direct"` is valid only for Borg 2 create/import
  payloads.
- Direct rclone payloads must not include SSH repository connection fields,
  managed-agent execution, cloud mirror enablement, cached rclone remote fields,
  sync policies, extra rclone flags, or client-provided cache paths.
- Direct rclone paths must use Borg's non-empty `rclone:remote:path` syntax.
- Borg 2 feature/license gating still applies.
- Create initializes the repository with Borg 2 against the direct rclone URL and
  stores a normal `Repository` row with `repository_type="rclone"`,
  `borg_version=2`, and no storage row.
- Import verifies the existing repository with Borg 2 against the direct rclone
  URL and stores the same repository shape with no storage row.
- Update allows ordinary editable repository settings and path changes for an
  existing direct rclone repository after direct URL validation. It rejects
  switching normal repositories into direct mode through update, enabling cloud
  mirrors on direct repositories, or mutating cached/mirror rclone fields.
- List/detail serialization reports `storage_backend: "rclone_direct"` for a
  Borg 2 rclone repository without an rclone storage row.

## Command Routing

Direct rclone repositories must use the existing Borg 2 routing surface:

- create: `BorgRouter.initialize_repository` or equivalent Borg 2 repository
  service path
- import: `BorgRouter.verify_repository` with `borg_version=2`
- backup: Borg 2 `create` commands with `-r <rclone-url>`
- info/list/maintenance operations: existing BorgRouter version dispatch

Borg 2 local-path validation must skip rclone URLs the same way it skips SSH
URLs, because the path is a repository URL and not a local directory.

## Validation

- Backend tests cover create/import success for direct Borg 2 rclone payloads,
  Borg 1 rejection, incompatible mirror/cache field rejection, update path
  validation, and normal mirror behavior preservation.
- Command routing tests cover Borg 2 backup command construction for an rclone
  URL and local-access validation skipping direct rclone URLs.
- Frontend tests cover advanced-mode gating, Cloud Mirror step omission, payload
  shape, edit population, and Review tradeoff copy.
- Storybook stories and snapshots cover the Location/Review direct rclone state.
- Runtime walkthrough covers the default primary-location plus optional mirror
  flow and the advanced direct rclone selection/validation path.
