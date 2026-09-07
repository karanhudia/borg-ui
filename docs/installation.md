---
title: Installation
nav_order: 2
description: "Install Borg UI with Docker, or directly on a Debian or Ubuntu host"
---

# Installation

There are two supported ways to install Borg UI:

- **[Docker](#option-1-no-redis-simple)** is the recommended path. It is the
  fastest to set up, and it is what most installs run.
- **[Directly on a Linux host](#install-without-docker)**, with no container
  layer, for bare metal, a VM (KVM, Proxmox, or any hypervisor), or an LXC
  container. Debian and Ubuntu only.

The rest of this page covers Docker first. Jump to
[Install without Docker](#install-without-docker) for the native installer.

## Docker

Use Docker Compose unless you only need a quick local test.

Pick one Compose workflow:

- [No Redis](#option-1-no-redis-simple): simplest setup. Uses in-memory archive cache.
- [With Redis](#option-2-with-redis-recommended): recommended for normal installs.
- [External Redis](#option-3-external-redis): use Redis from another host, stack, or managed service.

For Portainer or Unraid, use the same settings and see the platform notes below.

## Option 1: No Redis (Simple)

Use this for small installs or occasional archive browsing. Backups and restores work normally. Archive browsing cache is kept in memory and is lost when the app restarts.

Create `docker-compose.yml`:

```yaml
services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "${PORT:-8081}:${PORT:-8081}"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /etc/localtime:/etc/localtime:ro
      - ${LOCAL_STORAGE_PATH:-/home/youruser}:/local:rw
    environment:
      - PORT=${PORT:-8081}
      - PUID=${PUID:-1001}
      - PGID=${PGID:-1001}
      - TZ=${TZ:-UTC}
      - LOCAL_MOUNT_POINTS=${LOCAL_MOUNT_POINTS:-/local}
      - REDIS_HOST=disabled

volumes:
  borg_data:
  borg_cache:
```

## Option 2: With Redis (Recommended)

Use this for normal deployments. Redis makes repeated archive browsing faster and keeps cache across app container restarts.

Create `docker-compose.yml`:

```yaml
services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "${PORT:-8081}:${PORT:-8081}"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /etc/localtime:/etc/localtime:ro
      - ${LOCAL_STORAGE_PATH:-/home/youruser}:/local:rw
    environment:
      - PORT=${PORT:-8081}
      - PUID=${PUID:-1001}
      - PGID=${PGID:-1001}
      - TZ=${TZ:-UTC}
      - LOCAL_MOUNT_POINTS=${LOCAL_MOUNT_POINTS:-/local}
      - REDIS_HOST=redis
      - REDIS_PORT=6379
      - REDIS_DB=0
    depends_on:
      redis:
        condition: service_healthy

  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save ""
      --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3

volumes:
  borg_data:
  borg_cache:
```

## Option 3: External Redis

Use this when Redis already runs somewhere else.

Create `docker-compose.yml` on the Borg UI host:

```yaml
services:
  app:
    image: ainullcode/borg-ui:latest
    container_name: borg-web-ui
    restart: unless-stopped
    ports:
      - "${PORT:-8081}:${PORT:-8081}"
    volumes:
      - borg_data:/data
      - borg_cache:/home/borg/.cache/borg
      - /etc/localtime:/etc/localtime:ro
      - ${LOCAL_STORAGE_PATH:-/home/youruser}:/local:rw
    environment:
      - PORT=${PORT:-8081}
      - PUID=${PUID:-1001}
      - PGID=${PGID:-1001}
      - TZ=${TZ:-UTC}
      - LOCAL_MOUNT_POINTS=${LOCAL_MOUNT_POINTS:-/local}
      - REDIS_URL=redis://redis.example.com:6379/0
      - REDIS_HOST=disabled

volumes:
  borg_data:
  borg_cache:
```

Replace `redis.example.com` with your Redis host.

Examples:

```text
redis://redis.example.com:6379/0
redis://:password@redis.example.com:6379/0
rediss://:password@redis.example.com:6379/0
unix:///run/redis/redis.sock?db=0
unix:///run/redis/redis.sock?db=0&password=password
```

`REDIS_URL` takes precedence over `REDIS_HOST`. Keeping `REDIS_HOST=disabled` prevents Borg UI from trying `localhost:6379` if the external URL is unavailable.

For `unix://` Redis URLs, mount the Redis socket into the Borg UI container at the same path used in `REDIS_URL`.

If you need to create the external Redis instance too, run Redis on that host with a small Compose file:

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: borg-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save ""
      --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 3
```

Only expose Redis to trusted networks. If Redis is reachable across a network, use firewall rules, a private network, or Redis authentication.

## Start Borg UI

From the directory containing `docker-compose.yml`:

```bash
docker compose up -d
```

Open:

```text
http://localhost:8081
```

Default login:

```text
username: admin
password: admin123
```

Change the password immediately after first login. You can set a different first password with `INITIAL_ADMIN_PASSWORD`.

## Portainer

In Portainer, create a Stack and paste one of the Compose files above.

Use real host paths for volumes. Paths are evaluated on the Docker host, not on your laptop or browser session.

Recommended checks before deploying:

- keep `/data` persistent with `borg_data` or a host bind mount
- set `PUID` and `PGID` for the host user that should own restored files
- set `LOCAL_STORAGE_PATH` to the host path that contains repositories or backup sources
- keep `LOCAL_MOUNT_POINTS=/local` unless you change the container mount path
- use the Redis Compose option, external Redis, or `REDIS_HOST=disabled`

If you mount the Docker socket for hooks, remember that the container may still need the Docker CLI installed. See [Docker Hooks](docker-hooks).

## Unraid

On Unraid, use either the Docker Compose Manager plugin or the Docker web UI.

Recommended defaults:

```text
PUID=99
PGID=100
TZ=<your timezone>
```

Common path mapping:

```text
/mnt/user/appdata/borg-ui -> /data
/mnt/user/appdata/borg-ui/cache -> /home/borg/.cache/borg
/mnt/user/backups -> /local
```

Then use `/local/...` paths inside Borg UI.

Set `LOCAL_MOUNT_POINTS=/local` unless you use a different container path.

For Redis, use the Compose Redis option, an existing Redis container, an external Redis URL, or `REDIS_HOST=disabled`.

If you use the Docker web UI instead of Compose, add the same container paths and environment variables manually. Make sure `/data` points to persistent appdata storage.

## Pick the Right Host Path

The `LOCAL_STORAGE_PATH` host path is mounted into the container at `/local`.

Example:

```yaml
volumes:
  - /mnt/usb-drive:/local:rw
```

Then this host path:

```text
/mnt/usb-drive/borg-backups/laptop
```

is this container path in Borg UI:

```text
/local/borg-backups/laptop
```

Do not add the host prefix again inside the UI.

## Permissions

Set `PUID` and `PGID` to the host user that should own restored files and write backup repositories.

Find them with:

```bash
id -u
id -g
```

Example `.env`:

```bash
PORT=8081
PUID=1000
PGID=1000
LOCAL_STORAGE_PATH=/mnt/usb-drive
TZ=America/Chicago
```

### Rootless Podman

Rootless Podman maps container users differently from Docker. In a typical
rootless Podman container, UID 0 inside the container maps to the host user
running `podman`, while non-root container users map to a subordinate UID/GID
range. If a bind-mounted source such as `/local` appears as `root:nogroup` in
the container and the default `borg` user cannot read it, run Borg UI as
container root:

```bash
podman run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -e PUID=0 \
  -e PGID=0 \
  -e REDIS_HOST=disabled \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v "$HOME/ofl-w:/local:ro,Z" \
  -v "$HOME/bk:/backups:rw,Z" \
  ainullcode/borg-ui:latest
```

With rootless Podman, `PUID=0` and `PGID=0` mean container root, not host root.
That container root is mapped back to the user that started Podman, so it can
read that user's bind-mounted files without giving the container host-root
privileges.

Use `:Z` for private SELinux labels, or `:z` if the same host path is shared
with multiple containers. Omit the label option on hosts that do not use
SELinux.

Do not fix source path access by changing ownership of `/local` from inside
the container. Borg UI does not chown source bind mounts such as `/local`
because they are user data, may be read-only, and may be shared with other host
processes. It only adjusts ownership for app-managed paths such as `/data`,
`/backups`, `/home/borg`, and Borg's cache.

## Redis

Redis is used as an archive-browsing cache. It is not required for backups or restores.

The Compose example uses Redis without disk persistence:

```text
--save ""
--appendonly no
```

That means cached archive listings survive app container restarts while Redis keeps running, but they do not survive a Redis container restart. This is fine because Borg UI can rebuild the cache.

Set `REDIS_HOST=disabled` when you intentionally run without Redis. Otherwise the app tries the configured Redis host first and falls back to in-memory cache if it cannot connect.

## Optional Docker Socket

Only mount the Docker socket if you use script hooks to stop or start containers during backups:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

This grants powerful host access to the Borg UI container. You can avoid mounting the socket into the app container by running a Docker socket proxy and setting `DOCKER_HOST=tcp://docker-socket-proxy:2375` for Borg UI instead. See [Docker Hooks](docker-hooks).

## Optional FUSE Access

Archive mounting uses `borg mount` and requires FUSE access.

Remote source backups in SSHFS pull mode and SSH restore destinations also use
FUSE (through SSHFS); Remote Direct Backups do not.

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

Add this only if you need archive mounts, SSHFS remote source backups, or SSH
restore destinations. These three settings are the narrow replacement for
`privileged: true`: the repository's own `docker-compose.yml` runs the
container privileged for the same reason, which grants this access and a great
deal more. Use one or the other, not both. The host also needs FUSE itself: `/dev/fuse` must exist
there (`ls -l /dev/fuse`; if it is missing, `modprobe fuse`). Without it, and
without the lines above, SSHFS pull-mode backups fail with
`fuse: device not found` before they read a single file. `SYS_ADMIN` plus `apparmor:unconfined` widens the
container's privileges noticeably - Remote Direct Backups need neither. See
[Mounting Archives](mounting) and
[Remote Machines](ssh-keys#remote-source-backups).

## Docker Run

For a quick test:

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -e REDIS_HOST=disabled \
  -v borg_data:/data \
  -v borg_cache:/home/borg/.cache/borg \
  -v /home/youruser:/local:rw \
  ainullcode/borg-ui:latest
```

This does not include Redis. Use Compose for normal deployments.

## Install without Docker

Borg UI installs directly onto a Debian or Ubuntu host with no container layer.
Bare metal, a VM under KVM or Proxmox, and an LXC container are all the same
thing to the installer: a Linux host with systemd.

Docker remains the recommended path. Install natively when the host does not run
Docker, or when you want Borg UI to see the host's filesystem without bind
mounts.

### Requirements

- Debian 12 or newer, or Ubuntu 22.04 or newer
- systemd running as PID 1 (a system container or VM, not a chroot)
- x86_64 or aarch64
- Root access

### Install

```bash
curl -fsSLO https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh
curl -fsSL https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh.sha256 | sha256sum -c - \
  && sudo bash install.sh
```

That installs the latest release and starts it on port 8081. The installer
prints the URL when it finishes.

The installer is published as an asset of each release, alongside its SHA-256,
so those commands name a fixed artifact rather than a branch. `sha256sum -c`
prints `install.sh: OK` and exits non-zero on a mismatch, which is what stops
the third line from running something other than what was published. Reading
the script before running it as root is worth the minute it takes:

```bash
less install.sh
```

If you would rather not stop to verify, the one-liner is:

```bash
curl -fsSL https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh | sudo bash
```

To install a specific release instead of the newest, take the installer from
that release and pass the matching version. Every release's notes carry these
lines filled in:

```bash
curl -fsSLO https://github.com/karanhudia/borg-ui/releases/download/v2.3.0/install.sh
curl -fsSL https://github.com/karanhudia/borg-ui/releases/download/v2.3.0/install.sh.sha256 | sha256sum -c - \
  && sudo bash install.sh --version 2.3.0
```

The release archive the installer then downloads is verified against its own
published SHA-256 before anything is unpacked.

Options:

| Option | Default | What it does |
| --- | --- | --- |
| `--version <v>` | latest release | Install a specific release |
| `--port <n>` | `8081` | Port to serve on |
| `--data-dir <path>` | `/var/lib/borg-ui` | Where the database, keys and logs live |
| `--service-user <u>` | `root` | User the service runs as |
| `--skip-borg2` | off | Do not install Borg 2 |
| `--no-start` | off | Install and enable the service, but do not start it |

### What it installs

| Path | Contents |
| --- | --- |
| `/opt/borg-ui/current` | The running release (a symlink into `releases/<version>`) |
| `/opt/borg-ui/current/venv` | The application's Python environment, one per release |
| `/var/lib/borg-ui` | Database, SSH keys, Borg keyfiles, cache, logs |
| `/etc/borg-ui/borg-ui.env` | Configuration |
| `/etc/systemd/system/borg-ui.service` | The systemd unit |
| `/opt/borg-ui/bin` | The pinned `borg`, `borg2` and `rclone` this release runs |
| `/usr/local/bin/borg`, `/usr/local/bin/borg2` | Links to the above, so your shell finds them too |

Borg and rclone are pinned to exactly the versions the Docker image ships, and
every download is verified against a published SHA-256 checksum.

An existing `borg` on the host is left alone if it is not a symlink, and the
installer says so when that happens. The service is unaffected either way: its
unit puts `/opt/borg-ui/bin` first on `PATH`, so Borg UI always runs the Borg
this release was built against, whatever your shell resolves `borg` to.

### Service user

The service runs as `root` by default. A host backup tool has to read files it
does not own, such as `/etc`, other users' home directories, and database
directories, so an unprivileged default would silently skip most of the host.

Pass `--service-user borg` for a restricted install. Borg UI will then only be
able to back up what that user can read, which is the right trade when the host
only backs up one application's data.

### Configuration

Everything lives in `/etc/borg-ui/borg-ui.env`. Edit it and restart:

```bash
sudo systemctl restart borg-ui
```

Redis is optional and off by default, exactly as in
[Option 1](#option-1-no-redis-simple): the archive cache is kept in memory and
lost on restart. To use one, install `redis-server` and set `REDIS_HOST` and
`REDIS_PORT` in that file.

The installer never overwrites this file on an upgrade.

### Managing the service

```bash
sudo systemctl status borg-ui
sudo systemctl restart borg-ui
sudo journalctl -u borg-ui -f
```

### Upgrading

Re-run the installer. It unpacks the new release beside the current one and
builds that release's Python environment while the running one keeps serving,
then stops the service, moves the `current` symlink, and starts it again. The
data directory, database and configuration file are never touched.

Anything that fails before the switch leaves the old release running. If the new
one does not come up, the installer points `current` back at the previous
release and starts that instead, then reports the failure. The previous release
is kept for exactly this reason; older ones are removed.

```bash
curl -fsSLO https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh
curl -fsSL https://github.com/karanhudia/borg-ui/releases/latest/download/install.sh.sha256 | sha256sum -c - \
  && sudo bash install.sh
```

The Borg 2 repository-format warning under [Docker upgrade](#docker-upgrade)
applies here too.

### Borg 2 on older releases

Borg 2 is a beta with no distribution package. Where the host's glibc is new
enough, the installer uses the same static binary the image uses. Otherwise it
builds Borg 2 from source, which needs OpenSSL 3.2 or newer because 2.0.0b24
takes argon2 from OpenSSL.

Debian 12 (bookworm) ships OpenSSL 3.0, so Borg 2 cannot be installed there. The
installer says so and continues. Borg 1 repositories are unaffected, and Borg 1
is what almost every install uses. Debian 13 (trixie) and Ubuntu 25.04 or newer
carry a new enough OpenSSL.

### LXC notes

Borg UI runs in an LXC container, including on Proxmox, with two caveats.

**Mounting archives needs FUSE.** Browsing an archive's contents in the UI
mounts it over FUSE, which an unprivileged container cannot do unless the host
allows it. On Proxmox, add to `/etc/pve/lxc/<vmid>.conf`:

```
features: nesting=1,fuse=1
```

Then restart the container. Without this, backups, restores and pruning all work
normally; only in-place archive browsing fails.

**Backing up the host itself is not possible from inside a container.** An LXC
container sees its own filesystem. To back up the Proxmox host, either install
Borg UI on the host directly, or add the host as a remote machine over SSH.

### VM notes

A VM needs nothing special. Give it enough disk for the Borg cache, which grows
with the number of archives, and make sure the port you chose is reachable.

### Uninstalling

```bash
sudo systemctl disable --now borg-ui
sudo rm -f /etc/systemd/system/borg-ui.service
sudo systemctl daemon-reload

# Remove the borg, borg2 and rclone links, but only where they still point
# into the install; a link you put there yourself is left alone.
for cmd in borg borg2 rclone; do
  case "$(readlink -f "/usr/local/bin/$cmd" 2>/dev/null)" in
    /opt/borg-ui/*) sudo rm -f "/usr/local/bin/$cmd" ;;
  esac
done

sudo rm -rf /opt/borg-ui /etc/borg-ui
```

That leaves `/var/lib/borg-ui` in place, and with it the database and your SSH
and Borg keys. Delete it only when you are certain you no longer need them.
Removing Borg UI never touches your repositories.

## Docker upgrade

> **Borg 2 repositories written before 2.0.0b22 do not survive this upgrade.**
> 2.0.0b22 changed the repository format (packs) and cannot read a repository
> written by any earlier Borg 2 beta — opening one fails with
> `repository version 3 is not supported by this borg version`. There is no
> in-place conversion. 2.0.0b23 and 2.0.0b24 kept that format, so repositories
> created with 2.0.0b22 or later stay readable. Coming from a pre-b22 image:
>
> 1. Keep the image you are upgrading from available — it is the only thing
>    that can still read the old repositories.
> 2. Move the old Borg 2 repositories aside (rename the directory, or point
>    the repository at a fresh path) rather than deleting them.
> 3. After the new image is running, let Borg UI create new repositories —
>    the old image cannot create packs-format repositories — and delete the
>    old ones only once the new ones hold backups you have verified.
>
> Borg 1 repositories are unaffected. Borg 2 is a beta line with no stable
> release yet, and upstream reserves exactly this kind of break between betas.

Then pull and start the new image:

```bash
docker compose pull
docker compose up -d
```

Do not delete `borg_data` or `borg_cache` unless you intentionally want to remove application state or Borg cache data.

If the first backup after an image pull or container recreate is slower than later backups, see [Slow first backup after a pull or restart](troubleshooting#slow-first-backup-after-a-pull-or-restart).

## Next

- [Usage Guide](usage-guide)
- [Configuration](configuration)
- [Troubleshooting](troubleshooting)
- [Security](security)
