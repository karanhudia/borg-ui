# Feature request: Use sudo for remote SSH backups

## Summary

Add a per-connection option to prefix the borg binary with `sudo` when running backups
over a remote SSH connection. This allows backing up files owned by root or other system
users (e.g. database data directories, TLS certificate stores, application secrets) when
the SSH user does not itself have read access to those paths.

## Use case

When borg-ui performs a remote backup via SSH, it connects as a restricted service
account (e.g. `backup-agent`) that has SSH access but limited filesystem permissions.
Files like database WAL files, TLS private keys, or configuration secrets owned by
`root` are inaccessible to that account, causing `Permission denied` errors.

Passwordless `sudo` (scoped via `/etc/sudoers` to the borg binary and/or the
sftp-server binary) is a common, auditable pattern for granting this elevated access
without giving the SSH user a full root shell.

## Proposed behaviour

### SSH connection settings

Add a boolean field `use_sudo` (default: `false`) to the SSH connection model.
Expose it as a checkbox in the Edit Connection dialog:

> **Use sudo for backups**
> Prefix borg with `sudo` on the remote host. Requires passwordless sudo for the SSH
> user. Only applies to remote SSH backup mode.

### Remote SSH (push) mode

When `use_sudo=True`, prepend `sudo` as a separate token before the borg binary in the
command constructed by `remote_backup_service`:

```python
if use_sudo:
    cmd_parts.append("sudo")
cmd_parts.append(shlex.quote(borg_binary_path))
```

`sudo` must be a separate, unquoted token — it cannot be embedded inside a quoted
borg path string.

### SSHFS (pull) mode

SSHFS connects via SFTP, so `sudo` cannot be applied to the borg binary directly.
Instead, instruct SSHFS to spawn the remote SFTP server under sudo:

```
-o sftp_server=sudo /path/to/sftp-server
```

This causes all filesystem operations through the SSHFS mount to run as root on the
remote side, giving borg (running locally) read access to all files on the mount.

The sftp-server binary path differs by distribution:
- Debian/Ubuntu: `/usr/lib/openssh/sftp-server`
- RHEL/AlmaLinux/Fedora: `/usr/libexec/openssh/sftp-server`
- Alpine: `/usr/lib/misc/sftp-server`

The path should be detected dynamically by running a short probe command over SSH
before mounting, then falling back to a sensible default if detection fails.

## Required sudoers configuration

For remote SSH mode:
```
backup-agent ALL=(root) NOPASSWD: /usr/bin/borg
```

For SSHFS mode:
```
backup-agent ALL=(root) NOPASSWD: /usr/lib/openssh/sftp-server
# or /usr/libexec/openssh/sftp-server on RHEL-based systems
```

## Database migration

```sql
ALTER TABLE ssh_connections ADD COLUMN use_sudo BOOLEAN NOT NULL DEFAULT 0;
```

## Affected files

- `app/database/models.py` — add `use_sudo` column to `SSHConnection`
- `app/database/migrations/` — new migration file
- `app/api/ssh_keys.py` — expose field in GET response and accept in PUT request
- `app/services/remote_backup_service.py` — inject `sudo` into borg command
- `app/services/mount_service.py` — pass `sftp_server=sudo …` option to SSHFS
- `frontend/src/pages/SSHConnectionsSingleKey.tsx` — add checkbox to Edit dialog

---

## Working implementation

This feature is fully implemented and running in a fork. You can pull and test it
immediately without building anything:

```bash
docker run -d \
  --name borg-ui-test \
  -p 8082:8081 \
  -e SECRET_KEY=changeme \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=admin \
  ghcr.io/djlongy/borg-ui:latest
```

Or clone and build yourself:

```bash
git clone https://github.com/djlongy/borg-ui.git
cd borg-ui
# Native build (arm64 / Apple Silicon)
docker build -f Dockerfile.dev -t borg-ui-dev .
# Cross-compile for amd64
docker buildx build --platform linux/amd64 -f Dockerfile.dev -t borg-ui-dev:amd64 .
```

Once running, go to **SSH Keys → Edit Connection** — the "Use sudo for backups"
checkbox is at the bottom of the form.

**Relevant commit**: [`c8f5e74`](https://github.com/djlongy/borg-ui/commit/c8f5e74)
`feat(sudo): add use_sudo option for remote SSH backups + fix log viewer`

**Fork**: https://github.com/djlongy/borg-ui
