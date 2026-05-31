# Linked Backup Plans From Repositories Spec

## Problem

Backup plan cards can send users to the Repositories page with a backup-plan filter applied, but repository cards do not offer the inverse workflow. Users who start from a repository must manually inspect Backup Plans to find plans that target that repository.

## Desired Outcome

Repository cards expose a linked backup plans action. Activating it opens Backup Plans with a repository-scoped filter applied, and the page clearly indicates which repository is filtering the list.

## Acceptance Criteria

- Repository cards include a clear linked-plan action using the existing compact action style and icon system.
- The repository action navigates to `/backup-plans?repositoryId=<id>`.
- Backup Plans reads `repositoryId` from the URL and requests only plans linked to that repository.
- The filtered Backup Plans page shows the repository filter context and lets users clear it.
- Invalid or absent repository filters fall back to the normal unfiltered list.
- The existing Backup Plans -> Repositories `backupPlanId` flow continues unchanged.

## Validation

- Add red/green tests for repository card action behavior.
- Add red/green tests for backup-plan repository filtering.
- Run targeted frontend and backend tests for the changed surfaces.
- Run locale parity, typecheck, lint, build, and Storybook snapshots.
- Walk through the app from Repositories to filtered Backup Plans.
