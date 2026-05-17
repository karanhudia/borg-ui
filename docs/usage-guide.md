---
title: Usage Guide
nav_order: 4
description: "Create repositories, build backup plans, browse archives, and restore files"
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

## Create a Remote Repository

Remote repositories use a Remote Machine connection.

1. Go to Remote Machines.
2. Add and test the remote machine.
3. Go to Repositories.
4. Choose Create Repository.
5. Select a remote or SSH location.
6. Pick the remote machine and enter the repository path, for example:

```text
/backups/laptop
```

7. Choose encryption settings.
8. Save.

Use remote repositories when the Borg archive should live on another server or off-site storage.

## Import an Existing Repository

Use Import Existing when a Borg repository already exists and you want Borg UI to manage or monitor it.

1. Go to Repositories.
2. Choose Import Existing.
3. Select the repository location.
4. Enter the passphrase or upload the keyfile if the repository needs one.
5. Save, then verify archives can be listed.

Full mode lets Borg UI run backups for the repository. Observability-only mode is for repositories backed up by something else; Borg UI can browse archives, restore files, run checks, and show health, but it will not run backups or scheduled backups for that repository.

## Repository vs Backup Plan

A repository is the storage target. Use it to inspect repository-level information such as path, archive count, total size, last backup, last check, archives, restores, and maintenance actions.

A Backup Plan is the backup workflow. It defines what to back up, which repository or repositories to use, when the backup should run, and which scripts or maintenance actions should run around it.

Community plans can use one repository. Pro plans can use multiple repositories, such as one local target and one off-site target, and can run them one after another or in parallel.

## Choose Backup Sources

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

For remote sources, choose a Remote Machine in the Backup Plan and select paths from that machine.

## Create a Backup Plan

Create a Backup Plan after the repository exists.

If the repository already has source paths, you can start from the repository:

1. Go to Repositories.
2. Find the local or remote repository.
3. Choose Create Backup Plan.
4. Name the plan.
5. Choose whether to move the repository source settings into the plan.
6. If the repository already has a schedule, choose whether to copy it to the plan and pause the old repository schedule.
7. Save, then review the plan from Backup Plans.

For a new setup, start from Backup Plans:

1. Go to Backup Plans.
2. Choose Create Backup Plan.
3. Choose local paths or a remote source.
4. Select one or more repositories as storage targets.
5. Configure archive settings, scripts, and maintenance options.
6. Configure the schedule, or leave it disabled for manual runs.
7. Review and save.

For a local repository, the plan can back up local container paths such as `/local/Documents` into `/local/borg-backups/laptop`.

For a remote repository, the plan can back up local or remote sources into the SSH repository. If you want both a local copy and an off-site copy, add both repositories to the plan when your license allows multiple repositories.

## Run a Backup Plan

1. Go to Backup Plans.
2. Find the plan.
3. Choose Run.

The job page shows live progress, logs, and final status for each repository in the plan.

If an older repository still has legacy source settings, its repository card can also show Legacy Backup. Use Backup Plans for new backup workflows.

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
6. Use that remote machine when creating remote repositories or remote backup sources.

The old `/ssh-keys` route redirects to Remote Machines.

Remote source backups and SSH restore destinations use SSHFS. The container needs FUSE access for those flows; see [Installation](installation#optional-fuse-access).

## Backup Plan Schedules

Backup Plan schedules run backups automatically.

1. Go to Backup Plans.
2. Create or edit a plan.
3. Open the Schedule step.
4. Set the cron expression and timezone.
5. Turn the schedule on or off.
6. Save.

Plans can also run prune, compact, and check after successful repository backups.

The Schedules area still shows scheduled repository work. New backup schedules should usually live on Backup Plans.

Use notifications for scheduled backup failures so failures do not go unnoticed.

## Maintenance

Repository maintenance actions include:

- check
- prune
- compact
- break lock, when you are certain no Borg process is running

Use check and restore verification regularly. A backup that cannot be restored is not useful.

Scheduled repository checks and restore checks are managed from Schedule.

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

Activity and job views show backup, restore, restore-check, check, prune, compact, and package-install history.

Admins can delete supported job entries and associated log files. This removes UI history; it does not delete Borg archives. Archive deletion is a separate archive operation.

## Troubleshooting

### Permission denied

Set `PUID` and `PGID` to match the host user that owns the mounted files.

### Path not found

Check the Docker volume mapping and use the container path, not the host path.

### Repository locked

Do not break locks blindly. First confirm no backup, restore, check, prune, compact, mount, or external Borg process is using the repository.

### Slow archive browsing

The first browse of a large archive can be slow. Make sure Redis is running and see [Cache](cache).
