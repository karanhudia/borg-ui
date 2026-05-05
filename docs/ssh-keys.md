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

## Connection Options

Common options:

| Option | Use when |
| --- | --- |
| Default path | File browsing should start from a specific remote directory |
| SFTP deployment mode | Key deployment needs SFTP mode, for example Hetzner Storage Box |
| SSH path prefix | SSH commands need a prefix that SFTP browsing does not, for example some NAS paths |
| Logical mount point | You want a friendly name for the remote machine in path pickers |
| Use sudo | SSHFS access needs the remote SFTP server to run through sudo |

SFTP deployment mode can break some older SSH servers or NAS devices. Disable it when key deployment fails on those systems.

Remote Machines can also refresh storage usage by running `df` on the remote host.

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
