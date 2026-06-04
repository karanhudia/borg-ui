# Rclone Repository Edit Updates Spec

## Problem

Repository wizard edit mode treats existing cached rclone repositories as ordinary
local repositories with cloud mirror enabled. Those repositories have
`repository_type="rclone"` and a `RepositoryStorage` row with `backend="rclone"`.
When submitted from the wizard, the payload includes `storage_backend: "local"`
and `cloud_mirror_enabled: true`. The repository update endpoint interprets that
as an unsupported attempt to change the primary rclone storage mode and returns
`backend.errors.rclone.updateUnsupported`.

## Desired Outcome

Editing an existing cached rclone repository through the repository wizard keeps
the repository in cached rclone mode and updates supported rclone storage fields:
remote, remote path, sync policy, schedule, and extra flags. Unsupported primary
storage conversions stay rejected with an actionable message and database
rollback semantics.

## Supported And Unsupported Paths

Supported repository edit paths:

- Local, SSH, and managed-agent primary repositories can enable, update, or
  disable cloud mirrors.
- Existing cached rclone primary repositories can update their rclone remote,
  remote path, schedule, and extra flags while remaining cached rclone
  repositories.
- Direct Borg 2 rclone repositories can edit ordinary repository metadata and
  path, but cannot add cached rclone or cloud mirror fields.

Unsupported repository edit paths:

- Switching a normal repository directly to `storage_backend: "rclone"` or
  `storage_backend: "rclone_direct"` from the edit endpoint.
- Switching an existing cached rclone primary repository to local, SSH, managed
  agent, direct rclone, or cloud mirror mode in the same edit endpoint.
- Supplying server-owned rclone cache path fields from the UI/API.

## Requirements

- The wizard must submit cached rclone repository edits with
  `storage_backend: "rclone"` and the selected rclone fields.
- The backend must preserve rollback behavior when an unsupported cached rclone
  mode conversion is attempted after ordinary repository fields are present in
  the request.
- The unsupported update message must tell users what can be edited and what
  path is required for unsupported storage-mode changes.
- Automated coverage must include the current wizard payload regression and a
  backend no-partial-state assertion.

## Validation

- `pytest tests/unit/test_api_rclone.py::<new rollback test> -q`
- `cd frontend && npm run test -- src/components/__tests__/RepositoryWizard.test.tsx -t "<new cached rclone edit test>" --run`
- Required backend and frontend checks listed in the Linear issue after the fix.
