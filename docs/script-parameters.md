# Script Parameters

Script parameters let one script be reused across repositories without hard-coding every value.

Borg UI detects Bash-style placeholders:

```bash
${PARAM}
${PARAM:-default}
```

Parameter names must be uppercase snake case:

```text
DB_HOST
DB_PASSWORD
API_TOKEN
BACKUP_DIR
```

## Required vs Optional

Required:

```bash
pg_dump -h "${DB_HOST}" -U "${DB_USER}" "${DB_NAME}"
```

Optional with default:

```bash
BACKUP_DIR="${BACKUP_DIR:-/tmp/borg-ui-dumps}"
```

If a default exists, Borg UI treats the parameter as optional.

## Secret Detection

Parameters with these suffixes are treated as password fields:

- `_PASSWORD`
- `_TOKEN`
- `_SECRET`
- `_KEY`
- `_API_KEY`
- `_PASSPHRASE`
- `_APIKEY`
- `_AUTH`
- `_CREDENTIAL`
- `_CREDENTIALS`

Example:

```bash
curl -H "Authorization: Bearer ${API_TOKEN}" "${ENDPOINT_URL}"
```

`API_TOKEN` is shown as a secret field.

## Reserved Variables

Variables starting with `BORG_UI_` are reserved and injected by Borg UI at runtime.

Do not define parameters with this prefix.

Injected variables include:

| Variable | Meaning |
| --- | --- |
| `BORG_UI_HOOK_TYPE` | `pre-backup` or `post-backup` |
| `BORG_UI_BACKUP_STATUS` | post-backup result |
| `BORG_UI_REPOSITORY_ID` | repository ID |
| `BORG_UI_REPOSITORY_NAME` | repository name |
| `BORG_UI_REPOSITORY_PATH` | repository path |
| `BORG_UI_JOB_ID` | backup job ID |
| `BORG_UI_SOURCE_HOST` | remote source host, when available |
| `BORG_UI_SOURCE_PORT` | remote source SSH port |
| `BORG_UI_SOURCE_USERNAME` | remote source username |

## Example

```bash
#!/usr/bin/env bash
set -euo pipefail

dump_dir="${DUMP_DIR:-/local/db-dumps}"
mkdir -p "$dump_dir"

mysqldump \
  -h "${DB_HOST}" \
  -P "${DB_PORT:-3306}" \
  -u "${DB_USER}" \
  -p"${DB_PASSWORD}" \
  "${DB_NAME}" > "$dump_dir/${DB_NAME}.sql"
```

Detected parameters:

| Parameter | Required | Type |
| --- | --- | --- |
| `DB_HOST` | yes | text |
| `DB_PORT` | no | text |
| `DB_USER` | yes | text |
| `DB_PASSWORD` | yes | password |
| `DB_NAME` | yes | text |
| `DUMP_DIR` | no | text |

## Safety

Parameter values are passed as environment variables to the script process. They are not interpolated into a shell command by Borg UI.

Your script is still responsible for quoting variables correctly:

```bash
"${DB_NAME}"
```

not:

```bash
$DB_NAME
```

## Related

- [Docker Hooks](docker-hooks)
