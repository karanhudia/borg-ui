---
title: Source-Aware Database Scan
nav_order: 16
description: "Engineering spec for scanning databases on local or remote SSH targets with user-supplied paths"
---

# Source-Aware Database Scan

This document defines the contract for the source-aware database discovery flow
in Borg UI. The goal is to let a user point the database scanner at any
filesystem location — local to the Borg UI server or on a remote SSH-reachable
machine — instead of only the four hardcoded local data directories the
current `_detect_template` checks.

## Status

Draft. Frontend implementation lands before backend; the new endpoint may return
404 until the backend is implemented. Frontend handles that gracefully with a
clear error state and a working fallback to the templates list.

## Motivation

`app/api/source_discovery.py` currently exposes `GET /api/source-discovery/databases`.
That endpoint scans four fixed local paths (`/var/lib/{postgresql,mysql,mongodb,redis}`)
and runs `which()` against four fixed CLI commands. This is too narrow:

- Many users install databases in non-default locations (`/data`, `/opt/<engine>`,
  custom Docker volumes).
- The detection always targets the Borg UI server itself, but Borg UI is a control
  plane — a user may want to back up a database living on a remote SSH host they
  have already configured as an `SSHConnection`.
- The UI today labels the action "Scan a database" but the scanning is implicit,
  unparameterised, and not re-triggerable except by reopening the dialog.

The new flow gives the user explicit control over **what to scan** and **where to
scan it**, mirroring the local/remote split that the files-and-folders flow
already uses.

## Goals

- Let the user pick a scan target: this Borg UI server, or any configured
  `SSHConnection`.
- Let the user override the paths to scan; default to the well-known
  per-engine locations.
- Let the user re-trigger a scan on demand (so a freshly-installed database is
  detectable without reopening the dialog).
- Keep the existing template catalogue available as a manual fallback when the
  scan finds nothing.

## Non-Goals

- No new database engines in this spec. The catalogue (PostgreSQL, MySQL /
  MariaDB, MongoDB, Redis) is unchanged.
- No process-table or systemd inspection in this iteration. Detection is
  purely filesystem-existence + CLI-on-PATH, applied to the user-supplied paths
  and any remote target's PATH.
- No persisted "saved scan profiles" yet. Each open of the dialog starts from
  the defaults.

---

## API

### Existing (unchanged)

`GET /api/source-discovery/databases`

Returns the existing `DatabaseDiscoveryResponse` (source types + local-only
detections + full templates list). Kept for backwards compatibility with any
existing caller; the frontend stops calling it when the new endpoint exists.

### New endpoint

`POST /api/source-discovery/databases/scan`

Request body — `DatabaseScanRequest`:

```json
{
  "source_type": "local",
  "source_ssh_connection_id": null,
  "paths": [
    "/var/lib/postgresql",
    "/var/lib/mysql",
    "/var/lib/mongodb",
    "/var/lib/redis"
  ]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `source_type` | `"local" \| "remote"` | yes | "local" scans the Borg UI server; "remote" scans via SSH. |
| `source_ssh_connection_id` | `int \| null` | only when `source_type=remote` | Must reference an existing `SSHConnection` row the calling user has access to. Reject with 400 otherwise. |
| `paths` | `string[]` | yes | At least one path. Each path is an absolute POSIX path on the target. Empty list → 400. Paths longer than 4 KB → 400. |

Response — `DatabaseScanResponse`:

```json
{
  "scan_target": {
    "source_type": "local",
    "source_ssh_connection_id": null,
    "label": "This Borg UI server"
  },
  "scanned_paths": ["/var/lib/postgresql", "/var/lib/mysql", "/var/lib/mongodb", "/var/lib/redis"],
  "detections": [
    {
      "id": "postgresql",
      "engine": "PostgreSQL",
      "display_name": "PostgreSQL database",
      "backup_strategy": "logical_dump",
      "source_directories": ["/var/tmp/borg-ui/database-dumps/postgresql"],
      "client_commands": ["pg_dump"],
      "documentation_url": "https://www.postgresql.org/docs/17/app-pgdump.html",
      "detected": true,
      "detection_source": "/var/lib/postgresql",
      "notes": ["..."],
      "script_drafts": { "pre_backup": { "..." }, "post_backup": { "..." } }
    }
  ],
  "templates": [/* same shape as detections, with detected=false */],
  "warnings": []
}
```

| Field | Type | Notes |
|---|---|---|
| `scan_target.label` | string | Human-readable: `"This Borg UI server"` for local, `"user@host"` for SSH. |
| `scanned_paths` | string[] | Echo of the request paths. Useful in the UI's "Scanned: …" caption. |
| `detections` | `DatabaseCandidate[]` | Same shape as `_templates()` rows, with `detected=true` and a `detection_source` string identifying which path or command produced the hit. |
| `templates` | `DatabaseCandidate[]` | Full catalogue with `detected=false`. Used by the UI as a fallback when nothing was detected. |
| `warnings` | `ScanWarning[]` | Optional, see below. |

`ScanWarning`:

```json
{
  "code": "SSH_HOST_UNREACHABLE",
  "message": "Could not connect to user@host: connection refused",
  "path": null
}
```

Suggested codes: `SSH_HOST_UNREACHABLE`, `SSH_AUTH_FAILED`, `PATH_PERMISSION_DENIED`,
`PATH_NOT_ABSOLUTE`, `SCAN_TIMEOUT`. Path-scoped warnings carry the offending
path in `path`; connection-scoped warnings carry `null`.

### Status codes

- `200` — successful scan. `detections` may be empty; that is not an error.
- `400` — malformed request (empty `paths`, missing `source_ssh_connection_id`
  when `source_type=remote`, path too long, non-absolute path, etc.). Returns
  `{detail: "..."}` per FastAPI convention.
- `403` — caller does not have access to the referenced `SSHConnection`.
- `404` / `405` — the endpoint or route is not deployed. The frontend treats
  both as "scanning unavailable" and falls back to the legacy templates list
  (see Frontend contract). Do not return 404 for a missing `SSHConnection`
  resource; return 400 with a descriptive `detail` instead.
- `502` — SSH dial failed in a way that is the connection's fault, not the
  caller's (e.g. the host is down). Surface a `warnings` array in the body if
  partial info is available.
- `504` — scan exceeded `SCAN_TIMEOUT_SECONDS` (suggested default: 15s).

---

## Detection logic

For each candidate engine in the existing template catalogue:

1. **Path probe.** For every path in `request.paths`, check existence on the
   target. If the path exists *and* the per-engine signature matches that
   path (see signature rules), record a detection and set
   `detection_source = <path>`.
2. **Command probe.** If `which(<client_command>)` succeeds on the target *and*
   no path-probe detection has been recorded for that engine yet, record a
   command-based detection with `detection_source = "<command> available on PATH"`.

An engine is detected if either probe succeeds. The result is a deduplicated
list of engines; do not emit two detections for the same engine.

### Signature rules

Path signatures are intentionally simple in v1. An engine matches a path if any
of these are true:

| Engine | Signature |
|---|---|
| PostgreSQL | path basename matches `postgresql`, `pgsql`, `postgres`, or path contains `PG_VERSION` file at top level |
| MySQL / MariaDB | path basename matches `mysql`, `mariadb`, or path contains `mysql/` subdirectory |
| MongoDB | path basename matches `mongodb`, `mongo`, or path contains `WiredTiger` file |
| Redis | path basename matches `redis`, or path contains `dump.rdb` |

This keeps v1 honest: we are not parsing config files, we are only checking
that the user-supplied path *looks like* a candidate. If we wrongly attribute
a path to an engine, the user can still pick a template manually.

### Local execution

For `source_type=local`, run the probes in the FastAPI worker process using
`pathlib.Path.exists()` and `shutil.which()`. No subprocess needed. Wrap the
entire request in a `SCAN_TIMEOUT_SECONDS` budget; on overrun, return 504.

### Remote execution

For `source_type=remote`, open an SSH session to the referenced
`SSHConnection` using the existing SSH key material from `SSHKey` (the same
machinery `SourceLocation` uses to browse remote paths today). Within the
session:

- Use `test -e <path>` / `test -d <path>` for path probes. Quote paths
  defensively; reject any path containing characters in `[;&|`$()<>]`.
- Use `command -v <bin>` for command probes (more portable than `which`).
- Concatenate probes per engine into a single `sh -c '...'` command per
  connection so we do one round trip per scan instead of one per path.

The SSH session must not be held open across requests; open, probe, close.
Apply `SCAN_TIMEOUT_SECONDS` to the whole round trip including connect time.

### Failure semantics

- Path-level failures (one path is permission-denied) surface as a `warnings[]`
  entry; the rest of the scan proceeds.
- Connection-level failures (SSH dial fails) return 502 with `warnings[]`
  populated; the response still includes the `templates` list so the UI can
  fall back to manual configuration.

---

## Backend implementation notes

- The existing `_detect_template(template: DatabaseCandidate)` in
  `app/api/source_discovery.py:301` is the local-only ancestor of the new
  probe. Factor its `known_paths` table out into a per-engine signature
  function so the new endpoint and the legacy GET can both call it.
- The remote SSH plumbing already exists for the file-browser endpoint
  (`/api/source-discovery/browse` or similar — confirm during implementation).
  Reuse the same connection helper.
- Cache nothing on the server. Each scan is a fresh probe. The state lives in
  the UI request.
- Add `SCAN_TIMEOUT_SECONDS` to `app/core/config.py` or equivalent, default
  `15`.

---

## Tests

Suggested coverage in `tests/unit/test_source_discovery.py` (existing file):

- `POST /databases/scan` with `source_type=local` and an empty paths list →
  400.
- `POST /databases/scan` with `source_type=remote` and missing
  `source_ssh_connection_id` → 400.
- `POST /databases/scan` with a valid local request and a path that exists →
  detection emitted, `detection_source` is the path.
- Same request with a path that does not exist but the engine's CLI is on
  PATH → detection emitted via command probe.
- Both probes negative for every engine → 200 with empty `detections` and the
  full `templates` list.
- Non-absolute path → 400 with `PATH_NOT_ABSOLUTE`.
- Path with shell metacharacters → 400.
- Mocked SSH layer: connection refused → 502, `warnings[]` populated.
- Mocked SSH layer: scan succeeds, returns mixed detected/not-detected output
  → response matches expected `detections`.

---

## Frontend contract

The frontend ships ahead of the backend. While the backend is unimplemented:

- The new `POST /api/source-discovery/databases/scan` call returns `404` (route
  missing) or `405` (route exists for a different verb). Either is treated as
  `ENDPOINT_MISSING` and the UI shows an info-severity banner explaining that
  scanning isn't available yet.
- The frontend also calls the existing `GET /api/source-discovery/databases`
  on dialog open as a parallel best-effort request. Its `templates` field
  becomes the fallback grid so the user can still pick a template manually
  and complete the backup plan when scanning is unavailable.

Result states the UI distinguishes (all of which the backend must support
returning, even if some only occur in error paths):

| State | Trigger | UI severity |
|---|---|---|
| `LOADING` | request in flight | spinner inline with "Scanning…" |
| `ENDPOINT_MISSING` | 404 or 405 | info — "Database scanning isn't available on this server yet." |
| `SCAN_FAILED` | 500 / 502 / 504 / network error | warning — "Couldn't scan {target}. Check the connection or try again." Includes inline Re-scan action. |
| `NOTHING_FOUND` | 200 with empty `detections` | info — "No databases found on {target}. Add another path above, or pick a template below." |
| `DETECTED` | 200 with `detections.length > 0` | tiles render in a "Detected" section above templates. |

The backend may also surface per-path issues via the `warnings[]` field even
on a 200 response; the UI renders these in a separate warning banner without
suppressing detections that *did* succeed.

Frontend wire shape (matches the response above):

```ts
type DatabaseScanRequest = {
  source_type: 'local' | 'remote'
  source_ssh_connection_id: number | null
  paths: string[]
}

type ScanWarning = {
  code: string
  message: string
  path: string | null
}

type DatabaseScanResponse = {
  scan_target: {
    source_type: 'local' | 'remote'
    source_ssh_connection_id: number | null
    label: string
  }
  scanned_paths: string[]
  detections: SourceDiscoveryDatabase[]
  templates: SourceDiscoveryDatabase[]
  warnings: ScanWarning[]
}
```

The UI auto-scans on dialog open and on any change to scan-target or paths
(debounced). A manual "Re-scan" button re-runs with current params.
