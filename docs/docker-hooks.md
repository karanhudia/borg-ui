# Docker Hooks

Borg UI can run pre-backup and post-backup scripts. If the Docker socket is mounted, those scripts can stop, start, inspect, or restart containers.

Use this only when you need consistent backups of stateful containers.

## Enable Docker Access

Add the Docker socket to the Borg UI container:

```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock:rw
```

This gives the Borg UI container control over the host Docker daemon. Treat it as host-level access.

## Docker CLI

The socket exposes the Docker daemon, but scripts still need the `docker` command inside the Borg UI container.

If a hook fails with `docker: command not found`, install `docker.io` from:

```text
Settings > System > Packages
```

You can also use a custom image that includes the Docker CLI.

## Typical Flow

1. Create a script in the script library.
2. Attach it to a repository as a pre-backup or post-backup hook.
3. Set execution order if multiple scripts run.
4. Test the script before relying on a scheduled backup.

Common use:

- pre-backup: stop a database container
- backup: run Borg
- post-backup: start the database container

## Runtime Environment

Borg UI injects these variables when scripts run:

| Variable | Meaning |
| --- | --- |
| `BORG_UI_HOOK_TYPE` | `pre-backup` or `post-backup` |
| `BORG_UI_BACKUP_STATUS` | `success`, `failure`, or `warning` for post-backup hooks |
| `BORG_UI_REPOSITORY_ID` | Repository ID |
| `BORG_UI_REPOSITORY_NAME` | Repository name |
| `BORG_UI_REPOSITORY_PATH` | Repository path |
| `BORG_UI_JOB_ID` | Backup job ID, when available |
| `BORG_UI_REMOTE_HOST` | Remote source host for script library execution and script tests |
| `BORG_UI_REMOTE_PORT` | Remote source SSH port for script library execution and script tests |
| `BORG_UI_REMOTE_USERNAME` | Remote source username for script library execution and script tests |
| `BORG_UI_SOURCE_HOST` | Remote source host for legacy inline repository hooks |
| `BORG_UI_SOURCE_PORT` | Remote source SSH port for legacy inline repository hooks |
| `BORG_UI_SOURCE_USERNAME` | Remote source username for legacy inline repository hooks |

Variables starting with `BORG_UI_` are reserved by Borg UI and are not treated as script parameters.

## Example Pre-Backup Script

```bash
#!/usr/bin/env bash
set -euo pipefail

container="${CONTAINER_NAME:-postgres}"

if docker ps --format '{{.Names}}' | grep -qx "$container"; then
  docker stop "$container"
fi
```

## Example Post-Backup Script

```bash
#!/usr/bin/env bash
set -euo pipefail

container="${CONTAINER_NAME:-postgres}"

if docker ps -a --format '{{.Names}}' | grep -qx "$container"; then
  docker start "$container"
fi
```

Use a post-backup hook that runs on failure as well as success if the pre-backup hook stops a service.

## Safer Pattern

Prefer application-native dump commands when possible.

For databases, a pre-backup script that writes a dump file is often safer than stopping the live container:

```bash
#!/usr/bin/env bash
set -euo pipefail

mkdir -p /local/db-dumps
docker exec postgres pg_dumpall -U postgres > /local/db-dumps/postgres.sql
```

Then back up `/local/db-dumps`.

## Security Rules

- Do not mount the Docker socket unless hooks need it.
- Do not run unreviewed scripts.
- Use repository-specific parameters for container names.
- Keep scripts idempotent.
- Make post-backup cleanup run on failure.

## Related

- [Script Parameters](script-parameters)
- [Installation](installation)
- [Security](security)
