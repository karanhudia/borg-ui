---
title: Mounting Archives
nav_order: 7
description: "Mount Borg archives as read-only filesystems"
permalink: /mounting/
---

# Mounting Archives

Borg UI can call `borg mount` so an archive appears as a read-only filesystem inside the container.

Use archive mounting when you need filesystem access to archive contents. For normal file restore, the Archives page is usually simpler.

## Requirements

Archive mounting requires FUSE support from the Docker host.

The same Docker FUSE access is also needed for SSHFS-based remote source backups and SSH restore destinations.

Add this to the Borg UI service:

```yaml
cap_add:
  - SYS_ADMIN
devices:
  - /dev/fuse:/dev/fuse
security_opt:
  - apparmor:unconfined
environment:
  - BORG_FUSE_IMPL=pyfuse3
```

## Mount an Archive

1. Open Archives.
2. Select a repository and archive.
3. Choose Mount.
4. Pick a mount name.

Mounted archives appear under:

```text
/data/mounts/<mount-name>
```

Mounts are read-only.

## Inspect from the Container

```bash
docker exec -it borg-web-ui ls /data/mounts
docker exec -it borg-web-ui ls /data/mounts/my-backup
```

Replace `borg-web-ui` with your container name if you changed it.

## Make Mounts Visible on the Host

If you need host access to mounted archives, bind `/data/mounts` with shared propagation:

```yaml
volumes:
  - type: bind
    source: /mnt/borg-ui-mounts
    target: /data/mounts
    bind:
      propagation: shared
```

Your Docker host and filesystem must support shared mount propagation.

## Unmount

Use Settings > Management > Mounts to unmount.

Force unmount is available when a mount is busy. Use it only after closing processes that may be reading from the mount.

Mounts do not survive container restarts.

## Troubleshooting

### Operation not permitted

FUSE is not available to the container. Check `/dev/fuse`, `SYS_ADMIN`, and AppArmor settings.

### fusermount3: mount failed: Permission denied

On Ubuntu 25.04 and newer, the host's own AppArmor profile for `fusermount3`
restricts where FUSE filesystems may be mounted, and the container's
`apparmor:unconfined` does not lift it. Confirm with
`apparmor="DENIED" ... info="failed mntpnt match"` in `dmesg`, and see
[Optional FUSE Access](installation#optional-fuse-access) for the host-side
drop-in.

### Mount is busy

Close shells, file browsers, or processes using the mounted path, then unmount again.

### Mount takes too long

Increase the mount timeout in Settings > System > Operation Timeouts.
