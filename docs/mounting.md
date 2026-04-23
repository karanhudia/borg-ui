---
layout: default
title: Mounting Archives
nav_order: 7
description: "Mount Borg archives as a read-only filesystem for browsing"
permalink: /mounting/
---

# Mounting Borg Archives

Borg Web UI exposes Borg's `borg mount` and `borg umount` so you can mount a repository or a specific archive as a read-only filesystem inside the container. This lets you browse backup contents as normal directories and copy files out without using the in-app archive browser.

---

## What You Get

- **Borg mount in the UI:** Choose an archive and mount it; the filesystem appears under `/data/mounts/` inside the container.
- **Read-only:** Mounted archives are always read-only; you cannot modify backup contents.
- **Manage mounts:** List active mounts and unmount from **Settings → Management → Mounts**. Mounts are cleared when the container restarts.

---

## How to Use

### Mounting an Archive

1. Go to **Archives** and select the repository.
2. Click **Mount** on the archive you want.
3. Optionally enter a **Mount Name** (e.g. `my-backup`). If omitted, the archive name is used.
4. Click **Mount**. When it succeeds, the UI shows the path and a `docker exec` command you can use to access it.

The archive is mounted at a path like `/data/mounts/my-backup` inside the container.

### Managing Mounts

- **Settings → Management → Mounts** shows all active Borg archive mounts.
- Use **Unmount** to unmount when done. **Force unmount** is available if the mount is busy.

{: .note }
> Mounts do not survive container restarts. Unmount before restarting if you need a clean shutdown, or they will be cleared on next start.

---

## Docker Requirements (FUSE)

Borg mount uses **FUSE** (Filesystem in Userspace). The container must have:

- Access to the FUSE device: `devices: /dev/fuse`
- Capability to mount: `cap_add: SYS_ADMIN`

For Docker Compose, the minimum Linux setup looks like:

```yaml
services:
  app:
    cap_add:
      - SYS_ADMIN
    devices:
      - /dev/fuse:/dev/fuse
    security_opt:
      - apparmor:unconfined
    environment:
      - BORG_FUSE_IMPL=pyfuse3
```

If you want mounted archives to be visible on the host, also bind `/data/mounts`
with `bind.propagation: shared` as shown below.

### Development Compose

There is a Linux-only development override in
[`docker-compose.dev.mount.yml`](/Users/karanhudia/Documents/Projects/borg-ui/docker-compose.dev.mount.yml).
To test archive mounting in development:

1. Start the normal dev stack. It now goes through the same
   [`entrypoint.sh`](/Users/karanhudia/Documents/Projects/borg-ui/entrypoint.sh)
   runtime setup as the regular compose path, while still enabling code reload.
2. On a **native Linux Docker host**, add the FUSE override:
   `docker compose -f docker-compose.dev.yml -f docker-compose.dev.mount.yml up`
3. Verify the FUSE device exists:
   `docker exec borg-web-ui-dev ls -l /dev/fuse`
4. Verify Borg sees the selected backend:
   `docker exec borg-web-ui-dev borg --version`
5. Mount an archive from the UI, then inspect it inside the container:
   `docker exec borg-web-ui-dev ls /data/mounts`

If mount still fails, check:

- the container has `/dev/fuse`
- the host kernel supports FUSE
- AppArmor/seccomp is not blocking the mount
- `pyfuse3` is importable inside the container

### Docker Desktop Caveat

On Docker Desktop for macOS or Windows, these Compose settings may still not be
enough. Docker Desktop runs containers inside a Linux VM, and in practice Borg
archive mounts often remain unavailable there because a usable FUSE device is
not exposed to the container the same way it is on a native Linux host.

Inference from Docker's container isolation model: even privileged containers
on Docker Desktop gain privileges inside the Linux VM, not on the host itself.
If you need reliable mount testing, use a Linux machine or Linux VM with Docker
Engine rather than Docker Desktop.

---

## Accessing Mounted Files

### Option 1: Inside the Container (`docker exec`)

After mounting, use the path shown in the UI:

```bash
docker exec -it borg-ui ls /data/mounts/my-backup
```

Replace `borg-ui` with your container name and `my-backup` with your mount name.

### Option 2: On the Host (Without `docker exec`)

You can make FUSE mounts created inside the container visible on the host by bind-mounting a host directory to `/data/mounts` with **shared propagation**. Then any archive you mount in the UI appears under that host path.

**Minimal Docker Compose example:**

```yaml
services:
  borg-ui:
    image: ainullcode/borg-ui:latest
    container_name: borg-ui
    cap_add:
      - SYS_ADMIN   # Needed to mount borg archives and browse them
    devices:
      - /dev/fuse   # Needed to mount borg archives and browse them
    volumes:
      # FUSE mounts inside the container appear on the host here
      - type: bind
        source: /path/to/host/mountpoint
        target: /data/mounts
        bind:
          propagation: shared
    ports:
      - 8081:8081
```

Replace `/path/to/host/mountpoint` with a directory on your host (e.g. `/mnt/borg-mounts`). After you mount an archive in the UI, it will appear under that path on the host.

**Important:** the host-side source mount must also allow shared propagation. The Compose snippet alone is not always enough.

Check the host path propagation mode:

```bash
findmnt -o TARGET,PROPAGATION /path/to/host/mountpoint
```

If it is not `shared` or `rshared`, update it on the host:

```bash
sudo mount --make-rshared /path/to/host/mountpoint
```

If the host path lives under another mount with restrictive propagation, you may need to make the parent mount `rshared` as well.

If the archive is visible inside the container at `/data/mounts/...` but not on the host, this is almost always a host mount propagation issue rather than a Borg UI mount failure.

---

## Timeouts for Large Repositories

Large repositories can take a long time to mount. The default **Mount Timeout** is 2 minutes. If mounts fail with timeout errors or you see "Process still running" / "Mount timeout" in the logs, increase the timeout.

- **Settings → System → System → Operation Timeouts:** set **Mount Timeout** (e.g. 600 seconds for 10 minutes).

See the [Configuration Guide](configuration#operation-timeouts-for-very-large-repositories) for all timeout options and recommended values for very large repos.

---

## Security

- Mounted archives are **read-only**; backup data cannot be modified via the mount.
- Using `cap_add: SYS_ADMIN` and `devices: /dev/fuse` increases container privileges. Prefer the minimal FUSE setup (as in the Installation Guide) over privileged mode. See the [Security Guide](security) for best practices.
