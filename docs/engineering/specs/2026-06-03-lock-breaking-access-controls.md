# Lock Breaking Access Controls Spec

## Problem

Manual repository lock breaking is currently available without a global disable control. The backend route already uses repository-scoped access checks, but frontend affordances are still driven by global repository management flags in several places, so repository-scoped operators do not consistently see the action.

The original request also asks for deployments to disable manual lock breaking entirely because other services may normally touch the same Borg repositories and create transient locks.

## Desired Outcome

Manual lock breaking remains available by default for existing deployments, but administrators can turn it off globally. When enabled, the action is available to users who can perform repository maintenance on the affected repository. In Borg UI's current RBAC model, that means admin or repository `operator` access, which maps to the ticket's "editor access" intent.

## Scope

- Add a persistent `SystemSettings.lock_breaking_enabled` boolean, defaulting to `true`.
- Expose the setting through existing system settings GET/PUT contracts.
- Enforce the setting in `POST /api/repositories/{repo_id}/break-lock` before Borg execution.
- Keep existing repository access enforcement at `operator` level.
- Update lock-breaking UI states to combine the global setting with repository maintenance permission.
- Update copy so disabled states reference repository maintenance access instead of admin-only access.

## Out Of Scope

- Adding a new repository role named `editor`.
- Changing the existing `operator` repository role semantics.
- Changing Borg lock behavior for automatic maintenance cleanup paths outside the user-initiated break-lock endpoint.

## Validation

- Backend red/green tests for disabled global lock breaking and repository-operator lock breaking.
- Frontend red/green tests for disabled dialog state and per-job lock-break gating.
- Storybook coverage for the changed settings and lock-error table states.
- Required backend and frontend project checks before handoff.
