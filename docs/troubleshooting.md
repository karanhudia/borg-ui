---
title: Troubleshooting
nav_order: 8
description: "Common Borg UI troubleshooting checks"
---

# Troubleshooting

Use this page for issues that cross installation, Docker, cache, paths, and
repository operations. Feature-specific pages still keep focused
troubleshooting sections for that feature.

## Docker and Backup Performance

### Remote source backups still use SSHFS

Remote source backups use SSHFS pull mode unless the source SSH connection and
the SSH repository connection are the same. Different SSH source/repository
pairs still run on the Borg UI server and may see warnings when active files
change during backup.

Pull mode mounts the remote filesystem inside the container and therefore
needs FUSE access (`/dev/fuse`, `SYS_ADMIN`, AppArmor exception). A job that
fails at once with `failedPrepareSourcePaths` and `fuse: device not found` is
missing that - see
[Remote Machines](ssh-keys#sshfs-mount-fails-with-fuse-device-not-found).

### Slow first backup after a pull or restart

`docker compose pull` and container recreates do not remove Docker volumes or
bind mounts by themselves. A backup that is slow only for the first run after a
container update usually means Borg could not fully reuse its files cache for
that run.

Keep the two cache layers separate when troubleshooting:

- Borg UI archive cache: Redis or the in-memory fallback used by archive
  browsing.
- Borg files cache: Borg's own cache under the default `BORG_CACHE_DIR`
  (`/home/borg/.cache/borg`), used by
  `borg create` to avoid reprocessing unchanged files during backups.

Redis does not make backup creation faster. If Redis restarted, archive
browsing cache is cold, but that should not by itself slow `borg create`
backup jobs.

Check these items:

- Keep `/home/borg/.cache/borg` mounted to persistent storage. A named volume
  such as `borg_cache:/home/borg/.cache/borg` or a stable host bind mount such
  as `./cache:/home/borg/.cache/borg` is fine.
- Keep source directories mounted at the same container paths. Borg's files
  cache uses absolute filenames, so changing `/local/photos` to `/photos`, or
  moving the same host path between container paths, can make a later backup
  behave like a first scan.
- Make sure the cache is writable by the configured `PUID` and `PGID`.
  Permission problems can prevent Borg from updating or reading cache state.
- If the source path is an SSHFS, FUSE, network, or removable-drive mount with
  unstable inode numbers, Borg's default files-cache mode can treat unchanged
  files as modified. In that case, set repository custom Borg flags to a mode
  that ignores inode numbers, for example `--files-cache=mtime,size`. Use this
  only when you understand the reduced change-detection safety for that
  filesystem.
- After an image update that changes the bundled Borg version, the first backup
  may need extra cache validation or rebuild work. Later runs should speed up
  again if the cache volume and source mount paths stay stable.

Useful checks from the Docker host:

```bash
docker exec borg-web-ui sh -lc 'id borg && echo "BORG_CACHE_DIR=${BORG_CACHE_DIR:-/home/borg/.cache/borg}" && ls -ld "${BORG_CACHE_DIR:-/home/borg/.cache/borg}"'
docker exec borg-web-ui sh -lc 'find "${BORG_CACHE_DIR:-/home/borg/.cache/borg}" -maxdepth 2 -type f | head'
docker compose ps redis
```

## Archive sync lock failures

Background archive sync waits and retries when a server-side Borg listing
reports temporary lock contention (modern exit codes 70, 71, or 73), using
the operations runner's bounded backoff. The existing archive list stays
intact while the sync waits; dependent index work waits too. A sync that stays
blocked after 20 deferrals ends with a visible failure. You can cancel a
waiting sync from the operations queue.

The operation log includes a `Lock diagnostics` entry on each server listing
contention. For a lock under the configured local Borg cache, this records up
to five owner filenames, the current hostname, any configured `BORG_HOST_ID`,
and up to ten running operations on that repository. The final failure keeps
the latest diagnostic context if retries are exhausted. Owner filenames encode
Borg's host identity and PID; their presence does **not** prove the owner is
alive or dead. Remote/repository lock directories are not inspected, and these
diagnostics never remove locks.

A cache lock can survive a container replacement while Borg's host identity
changes. Check the owner entry against the old container and current Borg
processes, including other processes sharing that cache. A lock at
`/home/borg/.cache/borg/<repository-id>/lock.exclusive` is a local cache lock,
even when the repository itself is remote. `--bypass-lock` does not bypass
Borg 1's cache security checks, so it does not solve that case. Confirm the
owner has stopped before an administrator performs lock recovery; see
[Repository Locks](security#repository-locks).

Permission denial while creating a lock (exit code 72) is a filesystem access
problem and fails immediately rather than retrying. Check repository mount
permissions and the container's `PUID`, `PGID`, and supplementary groups as
below. Borg 2's `Our lock was killed by another borg` is also terminal: it is
not treated as contention that waiting can fix.

## Database migration recovery

Stop Borg UI before restoring or moving database files. Preserve the current
`DATA_DIR` and any existing `borg_bak.db` rollback; for SQLite, retain the
associated `-wal` and `-shm` files with the database. Prefer a consistent SQLite
backup or copy the files after all writers have stopped.

A legacy SQLite upgrade keeps the original database and builds both a catch-up
snapshot and a new database beside it. Allow space for those two additional
databases, SQLite journal/WAL growth, and migration/index overhead; the exact
amount depends on the database. Check free space, inodes and quotas on that
volume before retrying a `database or disk is full` failure. Failed snapshots
are disposable and are removed when possible. If cleanup itself fails, resolve
the storage/permission issue first; the next upgrade recreates its catch-up
snapshot. Do not remove the original database or its rollback to make room.

An `Incomplete Alembic initialization` error means Alembic bookkeeping exists
without a recorded revision, alongside existing application tables. This can
follow an interrupted first schema build; older releases may instead report
`table agent_machines already exists`. Startup refuses to guess which schema
changes or data transforms completed and leaves durable tables untouched.
Restore a verified pre-upgrade backup after preserving the failed database, or
contact support with the migration logs for schema recovery. Do not stamp a
revision, delete tables, or treat a populated durable database as disposable
staging. If no verified backup exists, keep the failed database for recovery.

Legacy transfers tolerate foreign keys pointing to a missing source table.
The target schema determines the policy: nullable references are cleared;
rows with required missing parents and their required dependents are omitted.
The upgrade report lists these changes, and the original database remains the
rollback. This does not reconstruct missing users or their credentials.

## Storage failures and repeated archive-sync failures

An input/output error means the operating system could not read or write the
affected storage. Check the disk, filesystem, remote storage and mount health
before retrying. The error alone does not identify a failed disk or prove that
the repository is corrupt.

If the database or disk is full, check free space, inodes and quotas on the
volume containing `DATA_DIR` (normally `/data`) and the Borg repository/cache
volumes. Restore capacity before submitting more operations. Check the actual
run status after a failed cancellation: a failed database write does not prove
that the backup process stopped. Borg UI does not delete data automatically to
recover from these failures.

Repeated failed background archive listings slow down from the configured
refresh interval to twice and then four times that interval, capped at six
hours. An interval already longer than six hours is preserved. The failed
operation remains visible in Activity. After fixing the cause, use the
repository's manual refresh to retry immediately. A successful listing resets
the cooldown; backup follow-up listings and manual refreshes are not delayed by
it. Lock contention uses the operations runner's separate bounded retry policy.

## Paths and Permissions

### Permission denied

Set `PUID` and `PGID` to match the host user that should own restored files and
write backup repositories. Also confirm the host path is mounted read/write
when Borg UI needs to write to it.

For rootless Podman, if a source bind mount such as `/local` appears as
`root:nogroup` and the default non-root `borg` user cannot read it, set
`PUID=0` and `PGID=0`. In rootless Podman, container root maps to the host user
running `podman`, not to host root. If SELinux is enforcing, add `:Z` to private
bind mounts or `:z` to shared bind mounts.

Borg UI does not chown source bind mounts such as `/local`. Changing ownership
from inside the container can modify user data on the host and can fail for
read-only mounts. Fix access with host permissions, runtime UID/GID mapping, or
the rootless Podman `PUID=0` / `PGID=0` mode above.

### Group-readable source paths in Docker

`PUID` and `PGID` set the Borg UI container process's primary user and group;
they do not grant it access to every supplementary group on the host. This can
matter when a mounted source directory is readable by a group other than the
configured `PGID` (for example, a directory owned by `otheruser:photos` with
mode `2770`).

Add the host group's **numeric GID** to the Borg UI service with `group_add`:

```yaml
services:
  app:
    environment:
      - PUID=1008
      - PGID=1008
    group_add:
      - "3001" # Host group with read access to the mounted source
```

Recreate the container after changing Compose. To confirm the running Borg UI
process has the expected supplementary group, run:

```bash
docker exec borg-web-ui sh -c "cat /proc/1/status | grep -E 'Uid|Gid|Groups'"
```

Use the GID of the group that owns or can read the source directory, not a Borg
UI web-login user. Prefer granting access only to the mounted data Borg UI
needs rather than running the container as root.

### Path not found

Check the Docker volume mapping and use the container path, not the host path.
For example, if `/mnt/usb-drive` is mounted as `/local`, use `/local/...`
inside Borg UI.

If you mount a different container path, include it in `LOCAL_MOUNT_POINTS` so
the file browser exposes the path.

## Repository Operations

### Repository locked

Do not break locks blindly. First confirm no backup, restore, check, prune,
compact, mount, or external Borg process is using the repository.

Break the lock only when you are certain the previous Borg process is gone.

### Borg 2 repository unreadable after an upgrade

Borg operations on an existing Borg 2 repository fail with:

| Message | Exit code | Meaning |
| --- | --- | --- |
| `... is not a valid repository. Check the repository config.` | 15 | Borg 2.0.0b25 is reading a repository written by an earlier Borg 2 beta. |

Borg 2 changes its repository format between betas, the last time in
2.0.0b25 (repository version 5), without a conversion. With this
error, right after an upgrade, the storage, the passphrase and the key are
fine; the format alone is the problem. To keep using the repository, go back
to the image you upgraded from. To move on, move the repository aside and let
a fresh one be created, and delete the old one only once the new one holds
backups you have verified. Borg 1 repositories are not affected.

The message is also what Borg prints for a directory that is not a
repository at all, so check that the path is the one you mean.

A repository that became inaccessible after an image pull but reports a
different error is an ordinary access problem: check the job log for the
actual message and start from storage, network and credentials.

### Borg 2.0.0b25: other messages after the upgrade

| Message | Cause | What to do |
| --- | --- | --- |
| `rest:// repository URLs were removed in Borg 2.0.0b25 ...` | The repository path still starts with `rest://`. Borg would read it as a local directory, so Borg UI does not run it. | Change the path to `ssh://`, keeping the rest of the URL, and create the repository anew. |
| `This endpoint's Borg 2 is ..., older than this server's ...` | A managed agent's Borg 2 is older than the one the server ships. Borg UI runs no Borg 2 job on it; the agent list marks it with "Borg 2 too old". | Run the agent installer on the endpoint with `--reinstall --borg-version both --borg-source server` (`2` instead of `both` where it has no Borg 1), or replace its Borg 2 yourself and restart the agent. If the installer says the `borg2` it would link "exists and is not a symlink", that file is an older Borg 2 installed by hand: rename or remove it and run the installer again. |
| `Borg 2 has no unencrypted repositories since 2.0.0b25 ...` | A repository was to be created with encryption `none`. | Choose an encrypted mode. |
| A new `ssh://` repository appears under the login directory of the remote user | Borg 2 reads `ssh://host/path` as relative to the login directory. | Write an absolute path with a second slash: `ssh://host//srv/backups/repo`. |
| `Borg 2 does not restore into a directory that already holds files ...` | An exact Borg 2 restore into a directory that is not empty. Borg 2.0.0b25 refuses it (`Extraction directory ... is not empty`, exit code 33), and Borg UI says so before Borg runs. | Restore into an empty directory, or choose "Restore into existing files" in the restore dialog (Borg's `--continue`: a file with the archived type, mode, size and modification time is skipped, so a file damaged in place is not replaced). |
| `The agent of this repository is too old to restore into existing files ...` | A restore into existing files on a managed agent before 0.1.17, which does not read the choice. | Upgrade the agent, or restore into an empty directory. |
| `Cannot acquire a passphrase ...` (exit code 50) on break-lock, check or repository deletion | These commands need the repository key now. | Store the repository's passphrase in Borg UI. |
| `No key found in repository ...` (exit code 44) | A `keyfile` repository whose key file is not on this machine. | Restore the key file from your key export. |
| `unrecognized arguments: --remote-path` | A Borg UI or agent older than this release with Borg 2.0.0b25. | Upgrade Borg UI and the agent. |

### Slow archive browsing

The first browse of a large archive can be slow because Borg has to list archive
contents. Make sure Redis is running for repeated browsing and see
[Cache](cache).

### Archive browsing fails with "Line limit exceeded"

When an archive contains more entries than Borg UI's safety limit, logs can show
messages such as `Line limit exceeded, terminating command`,
`Archive too large for safe browsing`, or an HTTP `413` response from an
archive browse endpoint.

An administrator can raise the limit in
Settings > System > Archive Browsing Limits, or by opening `/settings/system`
directly and updating `Max Files to Load`. If the archive also needs more memory
to build the file tree, increase `Max Memory (MB)` there as well.

Increase these values gradually. Very large archives can require substantial
RAM, and setting the limits too high can cause the Borg UI server to run out of
memory. For more detail, see [Configuration](configuration#archive-browsing-limits).

## More Troubleshooting

- [Authentication and SSO](authentication#troubleshooting)
- [Cache](cache#troubleshooting)
- [Docker Hooks](docker-hooks#troubleshooting)
- [Metrics](METRICS#troubleshooting)
- [Mounting Archives](mounting#troubleshooting)
- [Notifications](notifications#troubleshooting)
- [Remote Machines](ssh-keys#troubleshooting)
