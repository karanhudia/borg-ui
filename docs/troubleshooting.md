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
