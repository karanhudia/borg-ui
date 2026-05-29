# Direct rclone Mount Support Decision

## Status

Decision: not approved for Borg UI support at this time.

Direct `rclone mount` must not be added as a repository location, cloud mirror
mode, or hidden runtime fallback. Borg UI should continue using normal
filesystem repositories as the primary Borg command target and use rclone only
for explicit mirror or hydrate operations.

## Context

BOR-67 moved Borg UI cloud storage away from a primary rclone repository
location and toward cloud mirrors:

- Local-primary repositories sync the primary server path to an rclone remote.
- SSH-primary repositories use a server-owned SSHFS mount only as the source for
  a bounded `rclone sync`, then unmount in a `finally` path.
- Managed-agent-primary repositories delegate the rclone sync to the selected
  agent and avoid client-provided cache or staging paths.

That model keeps Borg commands on storage that Borg UI owns directly. A direct
`rclone mount` workflow would invert the contract by making Borg read and write
its repository through an rclone VFS/FUSE layer backed by a remote provider.

Rclone's mount documentation describes useful file-system presentation, but it
also calls out important constraints for write compatibility, retries, attribute
caching, VFS cache ownership, and backend-specific directory behavior:

- https://rclone.org/commands/rclone_mount/
- https://rclone.org/commands/rclone_sync/

Borg's repository format depends on transaction markers, segment/index/hints
files, and repository locks:

- https://borgbackup.readthedocs.io/en/stable/internals/data-structures.html
- https://borgbackup.readthedocs.io/en/stable/usage/general.html

## Decision

Direct `rclone mount` is rejected as a supported Borg UI workflow until a future
decision proves a narrow provider and configuration set is safe enough for Borg
repositories.

This means:

- Do not add UI controls for selecting `rclone mount` as a repository location.
- Do not run Borg create, check, compact, prune, list, extract, break-lock, or
  restore commands against an rclone-mounted repository path.
- Do not reuse the SSHFS cloud mirror mount lifecycle as a template for direct
  rclone-mounted Borg repositories. SSHFS is only a bounded transfer source for
  rclone sync in the current mirror strategy.
- Keep cloud storage behavior based on repository mirror sync and hydrate.

If this is reconsidered later, it must be treated as a new experimental storage
backend decision, not as a small extension of cloud mirrors.

## Operational Risks

### Consistency

Borg repositories are transaction-oriented stores. A command may write segment
data, commit markers, index files, hints files, and integrity files. Borg can
discard uncommitted transactions and rebuild some derived files, but that
assumes the repository view is coherent enough for Borg to identify the last
committed transaction and replay segments correctly.

`rclone mount` adds a VFS layer between Borg and the durable remote. Without
disk VFS caching, rclone cannot support all normal write patterns. With disk VFS
caching, file close and writeback timing become part of the repository
consistency model. A Borg command can return after local filesystem operations
while rclone still has pending writeback, failed uploads, stale directory
entries, or provider-specific metadata behavior.

This is a poor default for backup storage. The current mirror strategy has a
clearer boundary: Borg completes against local or explicitly mounted primary
storage first, then rclone sync produces a separate off-site copy with a visible
sync status.

### Locking

Borg uses repository locks under the repository directory. Lock acquisition
depends on filesystem operations such as creating temporary lock state and
renaming it into place. Borg also exposes `--bypass-lock`, but Borg's own docs
warn that bypassing locks is only safe when no other writer can mutate the
repository.

An rclone-mounted path cannot guarantee Borg UI is the only writer unless Borg
UI also owns the remote path, the mount process, the VFS cache, and all other
clients that can write to the same remote. Multi-host mounts, user-run rclone
processes, provider consoles, lifecycle rules, or another Borg UI instance can
all create split-brain repository state outside Borg UI's lock awareness.

The current mirror model avoids using rclone for Borg locks. It treats the
rclone remote as a copy target and records sync status rather than relying on
remote-mounted lock semantics.

### Performance

Borg commands are not simple sequential uploads. `check`, `compact`, archive
listing, restore browsing, and prune/compact workflows can read many small
repository files, rewrite derived files, and scan segments. Over an rclone mount
this work is sensitive to:

- provider latency and rate limits;
- directory listing and attribute cache behavior;
- VFS cache mode and cache disk size;
- backend support for modification times, hashes, sparse files, and empty
  directories;
- writeback delay and retry behavior;
- API throttling during compaction or check workloads.

The safe cache modes that make rclone mount more filesystem-compatible also
require local disk capacity and cache lifecycle management. At that point the
operator is already managing a local working copy, which is what the Borg UI
mirror architecture makes explicit.

### Recovery

Failure recovery is ambiguous for direct mounts:

- If the Borg process exits successfully but rclone writeback later fails, Borg
  UI would have to detect that delayed failure and mark the repository unsafe.
- If rclone dies while files are open, writeback may resume only when rclone is
  restarted with compatible flags and the same VFS cache.
- If unmount fails because the mount is busy, Borg UI must decide whether Borg
  commands may continue, whether the mount path is stale, and whether a force
  unmount risks losing pending writes.
- If provider state is partially updated, recovery requires Borg checks plus
  rclone cache inspection, not just a retry of one Borg command.

The current mirror and hydrate flows give Borg UI clearer recovery states:
`pending`, `syncing`, `hydrating`, `current`, and `failed`. The primary
repository remains separate from the remote copy until a sync or hydrate
operation completes.

### Security

Direct mounts expand the trusted computing base:

- Borg UI would need FUSE access in more deployments, usually including
  container capabilities and `/dev/fuse` exposure.
- rclone configuration and provider credentials would need to be available to a
  long-running mount process, not just short bounded sync commands.
- Mount permissions, path ownership, and shared mount propagation can expose
  repository contents or lock files to unexpected local processes.
- A writable mounted repository path is easier for non-Borg tools to modify
  accidentally.
- Per-provider encryption, crypt remotes, token refresh, and rclone RC/control
  surfaces would need a separate hardening review.

For encrypted Borg repositories, the remote provider still sees Borg repository
metadata and traffic patterns. For unencrypted repositories or misconfigured
mount permissions, the mounted view can expose repository contents or keys to
the host/container boundary.

## Required Proof Before Reconsideration

A future proposal may only approve direct mount support if it defines a narrow
support matrix and passes a repeatable smoke suite. The implementation plan must
separate mount lifecycle from repository mirror sync.

### Architecture Gate

- Model direct mount as a separate experimental backend, not as `cloud_mirror`.
- Own the mount lifecycle in a dedicated service with explicit states such as
  `starting`, `ready`, `busy`, `failed`, `unmounting`, and `stale`.
- Keep mirror sync and hydrate services independent. They must not assume the
  direct mount is present, healthy, or safe to use.
- Derive mount paths server-side. The UI/API must not accept arbitrary mount,
  cache, or staging paths.
- Pin and validate required rclone flags per provider. At minimum this would
  include `--vfs-cache-mode full` or a proven equivalent, an isolated
  `--cache-dir`, bounded cache sizing, explicit writeback behavior, and
  provider-specific directory marker decisions.
- Block multi-writer use. Borg UI must reject any configuration where another
  Borg UI instance or external writer can mutate the same remote path.

### Smoke Proof Matrix

The proof suite must run against an rclone local remote first, then against each
provider allowed by the support matrix.

| Area | Required proof |
| --- | --- |
| Mount startup | Start the mount through Borg UI, wait until the mountpoint is ready, verify Borg can initialize or open a repository, and verify the status endpoint reports the mount as ready. |
| Mount teardown | Stop the mount after idle Borg commands, verify the process exits, verify the mountpoint is no longer mounted, and verify no open VFS cache entries remain. |
| Busy teardown | Hold an open file under the mount, request unmount, verify Borg UI reports busy/stale state without deleting the VFS cache, then release the file and verify teardown completes. |
| Startup failure | Use an invalid remote or denied credential, verify startup fails without creating a repository record or leaving a mounted path. |
| Runtime failure | Kill the rclone process during a Borg write, verify Borg UI marks the mount and repository unsafe, preserves diagnostics, and blocks further Borg commands until recovery. |
| Writeback failure | Force remote write failure after Borg writes close, verify Borg UI detects the delayed failure and requires `borg check` plus cache inspection before returning to ready state. |
| Repository create | Run `borg init`, create at least one archive, list archives, and run `borg check` through the mounted path. |
| Repository command behavior | Run list, create, extract, prune, compact, check, and break-lock behavior tests through the mount with lock-wait behavior enabled and no `--bypass-lock` default. |
| Lock contention | Run concurrent Borg commands and verify repository locks behave exactly as local filesystem locks do, including timeout and cleanup behavior. |
| Crash recovery | Crash Borg UI, restart with the same VFS cache, verify pending writeback state is detected, and require a successful Borg check before scheduling new writes. |
| Permission isolation | Verify the mounted path is not writable by unrelated local users/processes and that rclone config/credential files are not exposed through UI logs or command output. |

## Consequences

The current Borg UI implementation should remain focused on cloud mirror sync
and hydrate:

- Local mirrors use `primary_to_remote`.
- SSH mirrors use `sshfs_mount_to_remote` only for bounded transfer source
  access.
- Managed-agent mirrors use `agent_to_remote`.
- Legacy direct rclone repository compatibility, where present, should not be
  expanded into rclone-mounted Borg command execution.

This decision avoids adding a UI path whose correctness would depend on remote
provider semantics, local FUSE behavior, long-running credentialed mount
processes, and delayed writeback recovery.

## Validation For This Decision

- Review existing rclone storage, cloud mirror, SSH mirror, managed-agent
  mirror, FUSE, and repository command docs.
- Confirm no direct `rclone mount` UI or runtime support is added by this
  change.
- Confirm this document contains the required risk sections and proof matrix.
