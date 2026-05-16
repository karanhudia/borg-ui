# Multiple Backup Source Locations

## Goal

Allow repository and backup-plan configurations to define more than one source
location. A source location owns its source type, optional SSH connection, and
paths, so users can combine local paths with paths from one or more SSH
connections in a single backup definition.

## Current Signal

The existing backup-plan payload has one `source_type`, one
`source_ssh_connection_id`, and one shared `source_directories` list. Repository
payloads follow the same single-location shape with `source_connection_id`.
That makes mixed local/remote sources impossible to represent.

## Compatibility Model

- Add nullable `source_locations` JSON columns to `repositories` and
  `backup_plans`.
- Keep existing single-source fields for older configs and API clients.
- Serialize `source_locations` for all records. When the new field is empty,
  derive one location from the legacy fields.
- When a new payload includes `source_locations`, validate and store it, then
  mirror a legacy summary into the existing fields for backward compatibility.
- Runtime backup execution should prefer `source_locations` when present and
  fall back to the legacy fields.

## Implementation Steps

1. Add shared source-location normalization helpers and database migration.
2. Update repository and backup-plan APIs to accept, validate, store, and
   serialize source locations.
3. Update backup execution to resolve local and per-connection remote source
   groups through the existing SSHFS mount flow.
4. Update frontend types, payload builders, repository wizard, backup-plan
   wizard, review views, and source browsing state.
5. Add focused backend and frontend tests for mixed local/remote source
   locations and legacy compatibility.
6. Run required backend/frontend validation and a local app walkthrough.
