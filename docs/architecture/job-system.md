# Job System

Borg UI runs long operations as background jobs. Jobs keep the UI responsive while Borg commands run inside the container.

## Job Lifecycle

Most jobs follow the same lifecycle:

```text
pending -> running -> completed
pending -> running -> failed
pending -> running -> cancelled
```

Job records store status, timestamps, progress, errors, and log file references.

## Main Job Types

| Job type | Purpose |
| --- | --- |
| Backup | Run Borg create for a repository |
| Restore | Extract files from an archive |
| Check | Verify repository/archive integrity |
| Compact | Free unused repository space |
| Prune | Apply retention policy |
| Archive delete | Delete an archive |
| Restore check | Verify that selected paths can be restored |

Schedules are configuration records. When a schedule fires, it creates backup/check/restore-check jobs.

## Backup Jobs

Backup jobs can be started manually or by schedule.

Typical flow:

1. create job record
2. run pre-backup scripts
3. run Borg backup
4. update progress and logs
5. run configured prune/compact work
6. run post-backup scripts
7. send notifications
8. update final status

## Restore Jobs

Restore jobs extract archive contents to a destination path visible inside the container.

Restores can target:

- local mounted paths
- remote destinations supported by the restore flow

Notifications can be sent for restore success or failure.

## Check, Prune, and Compact

Maintenance jobs run Borg maintenance commands and record job history.

Use them carefully:

- checks can be expensive on large repositories
- prune changes retention state
- compact reclaims space after prune

Do not interrupt maintenance unless necessary.

## Logs

Job logs are written to disk and referenced from the database.

System settings control:

- log retention days
- log save policy
- total log size cap
- cleanup on startup

## Concurrency

System settings control concurrent work:

- max concurrent manual backups
- max concurrent scheduled backups
- max concurrent scheduled checks

Avoid running multiple write operations against the same repository at the same time.

## Notifications

Job-related notifications are handled by the notification service.

Current notification event groups include:

- backup start/success/warning/failure
- restore success/failure
- check success/failure
- schedule failure

See [Notifications](../notifications).
