# Recent Feature Umami Events Spec

## Problem

Recent Borg UI work added several user-facing features without matching Umami event coverage. The main gaps are the newly added cloud storage/remotes page, managed agents page, and backup plans page. Older repositories, archives, schedules, settings, authentication, scripts, packages, and monitoring flows already use the shared analytics hook.

## Desired Outcome

Add privacy-preserving Umami events for the recent feature surfaces at stable workflow boundaries so adoption and usage can be understood without changing user behavior or introducing new tracking infrastructure.

## In Scope

- Cloud storage remotes:
  - refresh, search, sort, group, add dialog view, create, edit dialog view, update, delete request, delete confirm, test, browse, browser navigation, OAuth start, and OAuth credential save.
- Managed agents:
  - page refresh, tab changes, add dialog view, enrollment token create/revoke, agent revoke/delete, reinstall command view, setup/help command copy, agent/job log view, and job cancellation.
- Backup plans:
  - create dialog view, create, edit dialog view, update, delete, run, cancel run, toggle enabled state, view history, view logs, linked repository navigation, repository filter clear, search, sort, and group.

## Out of Scope

- New UI, copy, layout, navigation, or Storybook rendering changes.
- Backend analytics plumbing.
- Retrofitting analytics into already covered older flows unless needed to keep the new event map coherent.

## Event Design

Use the existing `useAnalytics` hook and existing categories/actions:

- Cloud storage events use `EventCategory.SYSTEM` with `section: 'cloud_storage'`.
- Managed agent events use `EventCategory.SYSTEM` with `section: 'managed_agents'`.
- Backup plan events use `EventCategory.BACKUP` with `entity: 'backup_plan'` or `entity: 'backup_plan_run'`.
- Event payloads use stable metadata such as operation, provider, status, source, tab, sort/group value, and boolean state. They must not include raw remote names, token values, paths, hostnames, or copied commands.

## Acceptance Criteria

- The three recent feature surfaces have Umami events at the workflow boundaries listed above.
- Analytics calls reuse `useAnalytics` and existing category/action constants.
- Existing behavior remains unchanged apart from best-effort event emission.
- Targeted tests prove the newly instrumented workflows emit the expected event category, action, and non-sensitive metadata.

## Validation

- `cd frontend && npm run test -- --run src/pages/__tests__/CloudStorage.test.tsx src/pages/__tests__/ManagedAgents.test.tsx src/pages/__tests__/BackupPlans.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
