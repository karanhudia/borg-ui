# Prune Maintenance Enhancements

## Goal

Resolve the still-actionable parts of GitHub issue #200 for prune maintenance: actual prune runs should start as background jobs, and the retention preview should reflect current form values.

## Scope

- Keep compact classified as already complete because manual compact already starts a background maintenance job.
- Keep dry-run prune synchronous so users still receive an immediate deletion preview before confirming.
- Start actual manual prune as a `PruneJob` for Borg 1 and Borg 2 repositories.
- Update the prune dialog preview text from a static sentence to a state-driven summary.
- Add Storybook coverage and a snapshot for the changed prune dialog state.
- Leave destructive repository wipe behavior out of this change; it needs a separate security/product specification.

## Validation Plan

- Backend route unit tests for legacy and Borg 2 prune dispatch.
- Existing integration prune contract updates to poll the prune job for actual prune.
- Frontend unit coverage for dynamic retention preview text.
- Frontend locale parity, typecheck, lint, build, and Storybook snapshots.
