---
title: API
nav_order: 13
description: "Authenticated API examples for developer and automation clients"
---

# API

Borg UI exposes authenticated API routes under `/api`. This page focuses on the
manual backup flow that automation clients commonly need: get an access token,
start an existing repository backup, then poll status and logs.

The examples use `X-Borg-Authorization` because Borg UI gives that header
precedence when both headers are present. The legacy `Authorization: Bearer
TOKEN` header is still accepted for compatibility.

## Create an access token

For local username/password auth, create a short-lived bearer token with the
login endpoint:

```bash
BASE_URL="https://backups.example.com"

TOKEN="$(
  curl -sS -X POST "$BASE_URL/api/auth/login" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "username=admin" \
    --data-urlencode "password=change-this-password" |
    jq -r .access_token
)"
```

SSO, TOTP, and passkey deployments may require their normal interactive login
flow to produce an accepted bearer token. Generated tokens from
`Settings > Account` are shown once and can be revoked there, but manual API
requests still require the bearer token from a normal login. Do not use
generated `borgui_...` account tokens as standalone credentials for manual
backup endpoints yet.

The token inherits the signed-in user's permissions:

- starting or cancelling a backup requires operator access to the repository
- polling status, streaming logs, or downloading logs requires viewer access to
  the repository
- admins have access to every repository

## Start a manual backup

Start an existing repository backup with `POST /api/backup/start`:

```bash
REPOSITORY="/backups/server1"

START_RESPONSE="$(
  curl -sS -X POST "$BASE_URL/api/backup/start" \
    -H "X-Borg-Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"repository\":\"$REPOSITORY\"}"
)"

JOB_ID="$(printf '%s\n' "$START_RESPONSE" | jq -r .job_id)"
printf '%s\n' "$START_RESPONSE"
```

Successful responses use this shape:

```json
{
  "job_id": 123,
  "status": "pending",
  "message": "Backup job started"
}
```

The JSON body uses the `repository` string accepted by Borg UI's manual backup
flow. For the current `/api/backup/start` and `/api/backup/run` endpoints, pass
the repository path shown in Borg UI. Older clients may still submit requests
without a registered repository path. For compatibility, those requests can be
accepted, but unknown paths fail to authorize or route. Automation should send a
registered repository path so permissions, routing, and logs resolve against the
intended repository.

## Compatibility alias

`POST /api/backup/run` is a compatibility alias for clients that use `run`
instead of `start`. It accepts the same request body and returns the same
response shape:

```bash
curl -sS -X POST "$BASE_URL/api/backup/run" \
  -H "X-Borg-Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"repository\":\"$REPOSITORY\"}"
```

## Poll job status

After receiving `job_id`, poll `/api/backup/status/{job_id}` until the job
reaches a terminal status:

```bash
curl -sS "$BASE_URL/api/backup/status/$JOB_ID" \
  -H "X-Borg-Authorization: Bearer $TOKEN"
```

The status payload includes the repository, current status, timestamps, progress,
error details, logs summary, and progress details:

```json
{
  "id": 123,
  "repository": "/backups/server1",
  "status": "running",
  "started_at": "2026-06-04T17:30:00+00:00",
  "completed_at": null,
  "progress": 42.0,
  "error_message": null,
  "logs": null,
  "progress_details": {
    "progress_percent": 42.0,
    "current_file": "/srv/app.db"
  }
}
```

Common statuses include `pending`, `running`, `completed`,
`completed_with_warnings`, `failed`, and `cancelled`.

## Poll job logs

Use `/api/backup/logs/{job_id}/stream` for incremental log polling. Start with
`offset=0`; for later calls, use the previous `total_lines` value as the next
offset.

```bash
curl -sS "$BASE_URL/api/backup/logs/$JOB_ID/stream?offset=0" \
  -H "X-Borg-Authorization: Bearer $TOKEN"
```

The log stream response is line-oriented:

```json
{
  "job_id": 123,
  "status": "running",
  "lines": [
    {
      "line_number": 1,
      "content": "Starting backup"
    }
  ],
  "total_lines": 1,
  "has_more": false
}
```

For completed non-running jobs with stored logs, you can also download a text
file:

```bash
curl -sS "$BASE_URL/api/backup/logs/$JOB_ID/download" \
  -H "X-Borg-Authorization: Bearer $TOKEN" \
  -o "backup_job_${JOB_ID}_logs.txt"
```
