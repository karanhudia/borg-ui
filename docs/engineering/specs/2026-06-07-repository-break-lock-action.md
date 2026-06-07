# Repository Break-Lock Action Spec

## Problem

Repository lock breaking already exists in the API and in lock-error recovery flows, but the Repositories page does not expose a direct action beside the existing repository wipe action. Users with repository maintenance/editor-level access must wait for another workflow to surface a lock error before they can clear a stale lock from the repository management surface.

## Desired outcome

Add a `Break lock` action to each eligible repository card. The action should live in the same action cluster as destructive repository actions, use the existing lock-break confirmation dialog and backend endpoint, and remain unavailable when global lock breaking is disabled or the current user lacks repository maintenance access.

## Existing contract

This work builds on `docs/engineering/specs/2026-06-03-lock-breaking-access-controls.md`:

- Borg UI's current repository RBAC model has `viewer` and `operator` roles, not a separate `editor` role.
- The previous lock-breaking access-control spec maps the rough "editor access" intent to repository `operator` / `maintenance` access.
- `POST /api/repositories/{repo_id}/break-lock` is already guarded by operator access and the `lock_breaking_enabled` system setting.
- Frontend lock-break availability should be derived from `lock_breaking_enabled && canDo(repoId, 'maintenance')`.

## Acceptance criteria

- Repository cards show a `Break lock` icon action for repositories where `canBreakLock({ repository_id })` is true.
- The new action appears in the separated repository action cluster immediately before `Wipe contents` for users who can also wipe.
- Users without repository maintenance access, or deployments with manual lock breaking disabled, do not see the repo-card break-lock action.
- Clicking the action opens the existing `LockErrorDialog` for the selected repository and uses `repositoriesAPI.breakLock` through that dialog.
- Existing wipe, delete, and lock-error recovery flows keep their current behavior.
- `RepositoryCard` Storybook coverage includes the break-lock action state.

## Validation

- Red/green Vitest coverage for `RepositoryCard` rendering, hiding, and click handling of the break-lock action.
- Red/green Vitest coverage for `Repositories` wiring the repo-card action to `LockErrorDialog`.
- Existing backend break-lock tests remain valid; no backend code change is expected.
- Required frontend validation from `frontend/`: `npm run check:locales`, `npm run typecheck`, `npm run lint`, and `npm run build`.
- Runtime walkthrough: open the Repositories page with lock breaking enabled, confirm an eligible repo card shows `Break lock`, click it, confirm the lock dialog opens, and confirm a non-eligible permission state does not show the button.

## Notes

Original request:

> Probably right next to wipe repo button, and Only for rbac with edit repo access.
