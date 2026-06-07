# Guided Repository Recovery Actions

## Problem

BOR-127 gave users copyable recovery commands when Borg UI cannot load repository info for a broken or uninitialized repository. The remaining product question is whether any of those commands should be runnable from Borg UI instead of only copied into a shell.

Running every command in-app would collapse very different risk levels into one surface. A diagnosis check is non-destructive when run without repair flags and already maps to Borg UI's `CheckJob` maintenance flow. Repair and reinitialization can modify repository contents, require stronger confirmation, and need failure recovery semantics that are closer to repository wipe than a normal maintenance run.

## Decision

Implement only the guided diagnosis/check action in-app.

Keep repair and reinitialization as copyable command templates until Borg UI has a dedicated destructive recovery workflow with typed confirmation, backend admission checks, operator access enforcement, progress/log visibility, terminal failure details, and clear unavailable states for repository configurations that cannot be safely modified by the server.

## Action Evaluation

### Diagnosis/check

- Supported as a guided in-app action.
- Opens the existing Check confirmation dialog instead of running immediately.
- Uses the existing backend `POST /api/repositories/{id}/check` route through `BorgApiClient.checkRepository`.
- Keeps backend operator access checks, repository job admission, Borg 1/2 routing, agent dispatch, job progress, logs, and terminal job feedback.
- Leaves the copyable `borg check` template visible as the fallback path.

### Repair

- Not supported as an in-app action in this change.
- `borg check --repair` can rewrite repository data and can make corruption worse if used incorrectly.
- The recovery panel keeps the copyable command, but the UI does not start a repair job.
- A future in-app repair flow must require explicit destructive confirmation copy, operator access, admission checks that block concurrent repository work, progress feedback, logs, terminal failure details, and configuration-aware availability rules.

### Reinitialization

- Not supported as an in-app action in this change.
- `borg init` / Borg 2 `rcreate` can create or replace repository state and can conflict with existing repository contents, passphrase/keyfile handling, remote path behavior, and agent execution.
- The recovery panel keeps the copyable command, but the UI does not start an init/rcreate job.
- A future in-app reinitialization flow must use a repository-init backend job, typed confirmation, backend permission checks, progress/log details, failure details, and a product decision about existing-data handling.

## UX Design

When repository info fails to load, the failed-state recovery panel gets a primary guided action for the safe diagnosis path: "Run guided check". The button is only active when the Repositories page can confirm the current user has maintenance permission; otherwise command templates remain the usable fallback.

Clicking the guided action opens the existing Check warning dialog. Users still confirm the job options before Borg UI queues work, so this is not a one-click destructive maintenance action. The Check dialog and existing running-job UI provide progress and job feedback after the backend starts the `CheckJob`.

The command template list remains visible for check, repair, and reinitialization. This preserves the BOR-127 fallback path for unsupported, unsafe, or unavailable actions.

## Safety Requirements

- Permission checks: the Repositories page gates the guided check action with `permissions.canDo(repo.id, 'maintenance')`, and the backend continues to enforce operator access.
- Confirmation: guided check opens `CheckWarningDialog`; repair and init have no in-app execution button.
- Progress feedback: guided check uses the existing check job flow and running-job polling.
- Logs: guided check uses existing `CheckJob` log/status endpoints.
- Failure details: guided check uses existing check terminal feedback and job error messages.
- Fallbacks: all recovery commands remain copyable.

## Acceptance Criteria

- Diagnosis/check, repair, and reinitialization are evaluated separately in this spec.
- The failed repository info recovery panel exposes a guided diagnosis/check action when a handler is available.
- The guided diagnosis/check action opens the existing check confirmation flow, then uses the existing backend check maintenance job path after confirmation.
- Repair and reinitialization remain copy-command only.
- The copyable command templates remain visible in all failed info recovery states.
- Frontend tests cover available and unavailable guided-check states.
- Backend tests document the existing check route/job path used by guided recovery.
- Storybook demonstrates the new failed info recovery action state.

## Validation

- Add failing frontend tests before changing the dialog/page code.
- Add backend coverage for the check route job path used by the guided recovery action.
- Run targeted frontend tests for `RepositoryInfoDialog` and `Repositories`.
- Run targeted backend tests for the repository check route dispatch path.
- Run `ruff check app tests`.
- Run `ruff format --check app tests`.
- Run `cd frontend && npm run check:locales`.
- Run `cd frontend && npm run typecheck`.
- Run `cd frontend && npm run lint`.
- Run `cd frontend && npm run build`.
- Run a local UI/runtime validation path for the repository info failed state and guided check action.
