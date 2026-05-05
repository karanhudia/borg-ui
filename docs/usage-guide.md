---
title: Usage Guide
nav_order: 4
description: "Create repositories, run backups, browse archives, and restore files"
---

# Usage Guide

This guide covers the normal path after installation.

## First Login

Open Borg UI:

```text
http://localhost:8081
```

Default credentials:

```text
admin / admin123
```

Change the password in Settings > Account.

## Understand Container Paths

Borg UI sees paths inside the container, not host paths.

If Docker maps:

```yaml
- /mnt/usb-drive:/local:rw
```

then this host path:

```text
/mnt/usb-drive/borg-backups/laptop
```

is this Borg UI path:

```text
/local/borg-backups/laptop
```

Use the container path in repositories, sources, and restore destinations.

## Create a Local Repository

1. Go to Repositories.
2. Choose Create Repository.
3. Select a local or mounted path.
4. Enter a path under a mounted location, for example:

```text
/local/borg-backups/laptop
```

5. Choose encryption settings.
6. Save.

Keep repository passphrases and keyfiles safe. Borg UI can help manage repositories, but Borg encryption recovery still depends on your secrets.

## Add Backup Sources

Use paths that exist inside the container.

Examples:

```text
/local/Documents
/local/photos
/local/projects
```

If you need multiple host locations, mount them explicitly:

```yaml
volumes:
  - /home/user/Documents:/documents:ro
  - /mnt/photos:/photos:ro
  - /mnt/backups:/backups:rw
environment:
  - LOCAL_MOUNT_POINTS=/documents,/photos,/backups
```

Then use `/documents`, `/photos`, and `/backups` in the UI.

## Run a Backup

1. Open the repository.
2. Go to Backup.
3. Confirm the source paths.
4. Start the backup.

The job page shows live progress, logs, and final status.

## Browse Archives

1. Go to Archives.
2. Select a repository.
3. Pick an archive.
4. Browse folders and files.

Redis is used to speed up repeated archive browsing. The first browse of a large archive can still take time because Borg has to list archive contents.

## Restore Files

1. Go to Archives.
2. Open an archive.
3. Select files or folders.
4. Choose Restore.
5. Pick a destination path that exists inside the container.

Example destination:

```text
/local/restore-test
```

If `/local` maps to `/mnt/usb-drive`, restored files appear under:

```text
/mnt/usb-drive/restore-test
```

## Remote Machines

Use Remote Machines for SSH-based sources and destinations.

Typical flow:

1. Go to Remote Machines.
2. Generate or import the system SSH key.
3. Add a remote machine with host, port, username, and optional default path.
4. Deploy the public key or copy it into the remote user's `authorized_keys`.
5. Test the connection.
6. Use that remote machine when creating repositories or backup sources.

The old `/ssh-keys` route redirects to Remote Machines.

## Schedules

Schedules run backups automatically.

1. Go to Schedules.
2. Create a schedule.
3. Pick one or more repositories.
4. Set the cron expression and timezone.
5. Save.

Use notifications for scheduled backup failures so failures do not go unnoticed.

## Maintenance

Repository maintenance actions include:

- check
- prune
- compact
- break lock, when you are certain no Borg process is running

Use check and restore verification regularly. A backup that cannot be restored is not useful.

See [Disaster Recovery](disaster-recovery) for restore-check modes and recovery drills.

## Notifications

Configure notifications in Settings > Notifications.

Recommended minimum:

- backup failure
- backup warning
- restore failure
- schedule failure
- check failure

See [Notifications](notifications).

## Job Logs

Activity and job views show backup, restore, check, prune, compact, and archive-delete history.

Admins can delete job entries and associated log files. This removes UI history; it does not delete Borg archives unless the job was an archive-delete operation.

## Troubleshooting

### Permission denied

Set `PUID` and `PGID` to match the host user that owns the mounted files.

### Path not found

Check the Docker volume mapping and use the container path, not the host path.

### Repository locked

Do not break locks blindly. First confirm no backup, restore, check, prune, compact, mount, or external Borg process is using the repository.

### Slow archive browsing

The first browse of a large archive can be slow. Make sure Redis is running and see [Cache](cache).
