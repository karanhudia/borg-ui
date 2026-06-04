# Broken Repository Check Recovery UI

## Problem

Broken or uninitialized Borg repositories can leave users with ambiguous maintenance feedback. A manual Check run starts a background job, the card spinner stops when the running job disappears, and the page currently only invalidates repository data and records analytics. It does not announce the terminal check status or any stored `error_message`, so a failed check can look like it simply stopped. The Info dialog also has a generic failed state without a recovery path or copyable commands.

## Desired Outcome

Manual repository checks should always end with visible success or failure feedback. When repository info cannot load, users should see a compact recovery panel with copyable command templates for checking, repairing, and recreating the repository using the saved repository settings. The UI should guide recovery without introducing a risky server-side reinitialization action.

## Approach

Use the existing job-history API rather than adding backend endpoints. `GET /repositories/{id}/check-jobs?limit=1` already returns the latest job with `status`, `completed_at`, and `error_message`. When `RepositoryCard` reports a tracked manual check has completed, `Repositories.tsx` will fetch that latest job and show a toast:

- success for `completed`;
- warning for `completed_with_warnings`;
- error with translated/raw `error_message` for failures or other unexpected terminal states.

For the Info dialog failure state, add an inline recovery section that uses saved repository data to generate copyable commands:

- normal check command;
- repair check command;
- reinitialization command via the existing `generateBorgInitCommand` utility.

This keeps the recovery UX reversible and inspectable. A future backend-backed reinitialize action can still be added if product requirements call for it.

## UI Notes

The recovery panel should be dense and operational, matching the existing MUI dialog style. Use balanced outlines, background tinting, icon buttons, and monospaced command blocks. Avoid heavy left accent borders and avoid expanding the Info dialog into a wizard.

## Acceptance Criteria

- Manual repository Check jobs surface an explicit completion toast.
- Failed manual Check jobs display the stored job error details when present.
- The Info dialog failed state includes copyable check, repair, and initialization command templates.
- Recovery commands use the repository path, Borg version, encryption, and remote path from saved repository settings.
- Existing healthy repository Info and Check flows continue to work.
- Storybook demonstrates the failed Info recovery state.

## Validation

- Add a failing frontend test that proves a completed manual Check job currently produces no terminal feedback.
- Add tests for failed Check job error feedback and Info recovery command copy buttons.
- Run targeted frontend tests for the touched components/page.
- Run `cd frontend && npm run check:locales`.
- Run `cd frontend && npm run typecheck`.
- Run `cd frontend && npm run lint`.
- Run `cd frontend && npm run build`.
- Run local app/runtime validation for the repository Info/Check path when feasible in the current environment.
