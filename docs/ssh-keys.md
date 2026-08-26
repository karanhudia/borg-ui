---
title: Remote Machines
nav_order: 6
description: "Configure remote machines and the system SSH key"
---

# Remote Machines

Borg UI uses a system SSH key for remote machine access.

Use Remote Machines to:

- connect to NAS or Linux servers
- deploy the Borg UI public key
- test SSH access
- use remote paths in repositories and backup sources

The old `/ssh-keys` route redirects to Remote Machines.

## Key Model

Borg UI stores one system SSH key and uses it for remote connections.

Supported key types:

- ED25519, recommended
- RSA, for older systems
- ECDSA, for compatibility

Generate the key in the UI unless you have a reason to import an existing key.

## Add a Remote Machine

1. Go to Remote Machines.
2. Generate or import the system key.
3. Add a remote machine.
4. Enter host, port, username, and optional default path.
5. Deploy the public key or copy it manually.
6. Test the connection.

Example:

```text
Host: backup.example.com
Port: 22
Username: backup
Default path: /backups
```

## Setup Presets

The deploy dialog includes setup presets for Linux servers, BorgBase, Hetzner
Storage Box, and NAS targets such as Synology and Unraid. Presets prefill
provider-aware placeholders and editable defaults like port, deployment mode,
default path, SSH path prefix, and mount point. They do not fill passwords or
private account IDs. Review provider-specific path details in
[Provider Guides](provider-guides) before saving.

## Connection Options

Common options:

| Option | Use when |
| --- | --- |
| Default path | File browsing should start from a specific remote directory |
| SFTP deployment mode | Key deployment needs SFTP mode, for example Hetzner Storage Box |
| SSH path prefix | SSH commands need a prefix that SFTP browsing does not, for example some NAS paths |
| Logical mount point | You want a friendly name for the remote machine in path pickers |
| Use sudo | The SSH user's own permissions are not enough: SSHFS runs the remote SFTP server through sudo, and Remote Direct Backups run `borg create` through sudo (see below) |

SFTP deployment mode can break some older SSH servers or NAS devices. Disable it when key deployment fails on those systems.

Remote Machines can also refresh storage usage by running `df` on the remote host.

## Connection Diagnostics

Use the diagnostics action on a configured remote machine when a connection test
passes but backups or remote services still feel slow or unreliable.

Diagnostics report:

- SSH session health and elapsed time
- latency for a simple remote command
- optional TCP reachability from the remote machine to a host and port
- bounded SSH download throughput with clear units

The TCP target is optional and lives under **Advanced: test another service**.
Leave it blank for a basic SSH and speed check, or enter a service host and port
such as `postgres.internal:5432` to verify whether the remote machine can reach a
dependency from its own network. Optionally adjust the timeout in seconds to
control how long the remote TCP check waits before reporting a timeout.

## Manual Public Key Install

On the remote server:

```bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo "ssh-ed25519 AAAA... borg-ui" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Use a dedicated remote user where possible.

## Repository Paths

When creating or importing SSH repositories, use paths that Borg can access through the selected remote connection.

Examples:

```text
backup@example.com:/backups/laptop
ssh://backup@example.com:22/backups/laptop
```

For Hetzner Storage Box-style paths, keep the provider-specific path syntax:

```text
ssh://u123456@u123456.your-storagebox.de:23/./backup-repo
```

Use `/home` as the Remote Machine default path for Storage Box browsing and
key deployment. Keep `/./backup-repo` or `/./borg-repository` as the repository
path syntax when creating or importing the Borg repository.

For BorgBase, repository URLs commonly use `/./repo`:

```text
ssh://abcd@abcd.repo.borgbase.com/./repo
```

Use `/./repo` as the Remote Machine default path and repository path. Do not
shorten it to `/repo`. Add Borg UI's full public key in BorgBase SSH Keys and
grant that key access to the repository; BorgBase SFTP Access is not required
for Borg UI's Borg-over-SSH repository setup. See
[Provider Guides](provider-guides) for BorgBase, Hetzner Storage Box, Synology,
Unraid, and other hosted or NAS examples.

## Remote Source Backups

A backup plan can use a Remote Machine as its *source*. Borg UI runs that
backup in one of two ways:

- **SSHFS pull mode** (when Remote Direct Backup does not apply): the container mounts the remote
  filesystem with SSHFS and runs `borg create` itself. This needs FUSE access
  from the Docker host - `/dev/fuse`, the `SYS_ADMIN` capability and an
  AppArmor exception - which the Compose examples in
  [Installation](installation) do not grant. See
  [Optional FUSE Access](installation#optional-fuse-access) for the exact
  lines; `privileged: true`, as the repository's own `docker-compose.yml`
  uses, is the broader way to get the same access - use one or the other,
  not both. Without either the job fails before it reads a single file (see
  [Troubleshooting](#sshfs-mount-fails-with-fuse-device-not-found)).
- **Remote Direct Backup**: `borg create` runs on the remote machine itself,
  see below. It needs no FUSE access and no extra container privileges.

`SYS_ADMIN` plus `apparmor:unconfined` is a real widening of the container's
privileges, and `privileged: true` more so. If you would rather not grant
either, put source and repository on the same SSH connection and use Remote
Direct Backup mode instead.

## Remote Direct Backups

When a backup plan uses an SSH source and an SSH repository on the same SSH
connection, Borg UI runs `borg create` on that remote machine and sends data
directly to the repository. This avoids SSHFS pull mode and keeps high-I/O
source reads on the remote/source host where the data resides instead of the
Borg UI Docker host.

Use the connection's Borg binary path when the source host needs a wrapper
script, for example to pause Docker containers before Borg starts and resume
them after Borg exits. The repository `remote_path` setting is different: it is
passed to Borg as the repository-side remote Borg path.

With *Use sudo* enabled, Borg UI runs
`sudo -n --preserve-env=BORG_PASSPHRASE,... borg create ...` on the source
host, so the passphrase and the other `BORG_*` variables survive sudo's
`env_reset` (the default on Debian, Ubuntu and Raspberry Pi OS). The SSH user
needs passwordless sudo that also allows preserving those variables. Prefer a
rule scoped to the Borg binary with the `SETENV:` tag, for example
`backup ALL=(root) NOPASSWD: SETENV: /usr/bin/borg` - the path in the rule must
be the connection's configured Borg binary path, exactly as entered, wrapper
scripts included, because that is what runs after `sudo`.

::: warning The sudo target must not be writable by the SSH user
The configured Borg binary or wrapper - and every parent directory on its
path - must be owned by root and not writable by the SSH user. A file or
directory the SSH user can modify turns the sudo rule into root code
execution: the user replaces the target (or redirects a parent directory)
and sudo runs it as root.
:::

The unrestricted
`NOPASSWD: ALL` that many images grant their default user works as well, but
it lets the SSH user run any command as root - use it only where that is
intentional, and prefer the scoped `SETENV` rule otherwise.
Without either, sudo refuses the command or the environment and the backup
fails before it touches the repository.

## Synology and NAS Path Prefixes

Some NAS devices expose different paths over SFTP and SSH. Synology DSM is a
common example. For provider-level mapping notes, see
[Provider Guides](provider-guides#synology-unraid-and-other-nas-targets).

```text
SFTP path shown while browsing: /playbackup/borguitest
Path Borg needs over SSH:       /volume1/playbackup/borguitest
```

In this setup, configure the remote machine like this:

```text
Default path: /playbackup
SSH path prefix: /volume1
```

Then select or enter repository paths using the SFTP-visible path, such as
`/playbackup/borguitest`. Borg UI keeps SFTP browsing in that namespace and
prepends the SSH path prefix only when it builds SSH/Borg commands.

If repository initialization fails with an error like `The parent path of the
repo directory [...] does not exist`, compare the path shown by SFTP browsing
with the full path needed by Borg over SSH. Put only the missing leading
segment, such as `/volume1`, in SSH path prefix. Do not include that prefix
again in the repository path, or the generated SSH path may be wrong.

## Import an Existing Key

If you import from the host filesystem, mount the key read-only into the container first:

```bash
docker run -d \
  --name borg-web-ui \
  -p 8081:8081 \
  -e REDIS_HOST=disabled \
  -v borg_data:/data \
  -v ~/.ssh:/host-ssh:ro \
  ainullcode/borg-ui:latest
```

Then import from a path such as:

```text
/host-ssh/id_ed25519
```

Passphrase-protected keys are not suitable for unattended scheduled backups unless the UI flow explicitly supports your setup.

## Restrict Remote Access

For backup-only remote users, consider restricting the public key in `authorized_keys`:

```text
command="borg serve --restrict-to-path /backups",restrict ssh-ed25519 AAAA... borg-ui
```

Adjust the path for your server.

## Troubleshooting

### Connection test fails

- verify host and port
- verify the public key is installed for the correct user
- check remote file permissions on `~/.ssh` and `authorized_keys`
- check that the container can reach the host

### Permission denied during backup

The remote user needs read access to source paths and write access to repository paths.

### Host key changed

Verify the host change first. Then update known-hosts through the UI or by reconnecting as appropriate.

### SSHFS mount fails with `fuse: device not found`

A remote-source backup in SSHFS pull mode fails immediately with
`backend.errors.service.failedPrepareSourcePaths`, and the container log shows
`SSHFS mount failed: fuse: device not found, try 'modprobe fuse' first` or
`fusermount3: mount failed: Operation not permitted`.

The container has no FUSE access. Add `/dev/fuse`, `SYS_ADMIN` and the AppArmor
exception from [Optional FUSE Access](installation#optional-fuse-access) to the
Borg UI service (or run it with `privileged: true`, which includes all three),
make sure `/dev/fuse` exists on the host (`ls -l /dev/fuse`; if it is missing,
`modprobe fuse`), and recreate the container.
On Ubuntu the AppArmor line is the one that matters: the `docker-default`
profile denies `fusermount3` even when the device and capability are present.
If you would rather not widen the container's privileges, use
[Remote Direct Backup](#remote-direct-backups) mode, which needs none of this.
