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

### Slow first backup after a pull or restart

`docker compose pull` and container recreates do not remove Docker volumes or
bind mounts by themselves. A backup that is slow only for the first run after a
container update usually means Borg could not fully reuse its files cache for
that run.

Keep the two cache layers separate when troubleshooting:

- Borg UI archive cache: Redis or the in-memory fallback used by archive
  browsing.
- Borg files cache: Borg's own cache under `/home/borg/.cache/borg`, used by
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
docker exec borg-web-ui sh -lc 'id borg && ls -ld /home/borg/.cache/borg'
docker exec borg-web-ui sh -lc 'find /home/borg/.cache/borg -maxdepth 2 -type f | head'
docker compose ps redis
```

## Paths and Permissions

### Permission denied

Set `PUID` and `PGID` to match the host user that should own restored files and
write backup repositories. Also confirm the host path is mounted read/write
when Borg UI needs to write to it.

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

## More Troubleshooting

- [Authentication and SSO](authentication#troubleshooting)
- [Cache](cache#troubleshooting)
- [Docker Hooks](docker-hooks#troubleshooting)
- [Metrics](METRICS#troubleshooting)
- [Mounting Archives](mounting#troubleshooting)
- [Notifications](notifications#troubleshooting)
- [Remote Machines](ssh-keys#troubleshooting)
