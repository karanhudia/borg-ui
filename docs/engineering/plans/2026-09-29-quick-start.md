# Quick Start implementation plan

**Spec:** `docs/engineering/specs/2026-09-29-quick-start.md`
**Delivery:** stacked PRs, one per phase, each based on the previous branch.

## Progress

| Phase | Branch | Scope | Status |
| --- | --- | --- | --- |
| 1 | `feat/quick-start-1-spec` | spec and this plan | done |
| 2 | `feat/quick-start-2-core` | dialog, state, actions, runner, local to local end to end | not started |
| 3 | `feat/quick-start-3-entry` | sidebar button, first-run auto-open, empty-state actions, user docs | not started |
| 4 | `feat/quick-start-4-ssh` | SSH destination and SSH pull source with inline key deploy | not started |
| 5 | `feat/quick-start-5-agent` | managed agent source (Pro) | not started |

Each phase: TDD for the pure modules, stories for every new component, all
four locales (en, de, es, it) for every new key, `npm run lint`,
`npm run typecheck`, `npm run check:locales`, `npx vitest run` for touched
areas, Storybook screenshots light and dark, local CodeRabbit loop until
clean, then push and PR.

## Phase 2: core (local to local)

1. `components/quick-start/quickStartState.ts`
   - `QuickStartAnswers`: `sourceKind: 'server' | 'ssh' | 'agent'`,
     `sourceConnection`, `sourceAgentId`, `sourcePaths`,
     `destinationKind: 'server' | 'ssh' | 'agent'`, `destinationConnection`,
     `destinationPath`, `name`, `passphrase`, `passphraseConfirm`,
     `passphraseSaved`, `schedulePreset`, `cronExpression`, `timezone`, and
     `customize` (encryption, compression, keep counts, prune, compact,
     check, scheduleEnabled, borgVersion).
   - `visibleSteps(answers)` and `isStepValid(step, answers)`.
   - Tests first.
2. `components/quick-start/quickStartActions.ts`
   - `buildQuickStartActions(answers, done)` returns the ordered actions.
     Phase 2 only emits `create_repository` and `create_plan`.
   - `buildRepositoryPayload(answers)` and `buildPlanPayload(answers, repositoryId)`
     (the second via `buildBackupPlanPayload({...createInitialState(), ...})`).
   - `schedulePresetCron(preset)`.
   - Tests first.
3. `components/quick-start/useQuickStartRunner.ts`: executes actions,
   stores results, `retry()` resumes. Tests with mocked API modules.
4. Step components (each small, each with a story): `QuickStartSourceStep`,
   `QuickStartFoldersStep`, `QuickStartDestinationStep`,
   `QuickStartProtectStep`, `QuickStartScheduleStep`,
   `QuickStartReviewStep` (with `QuickStartCustomize`),
   `QuickStartProgress`.
5. `QuickStartDialog.tsx` wires them into `WizardDialog`, handles Back/Next,
   blocks close while running, offers Run first backup / Open plan on
   success. Component test for local to local.
6. Temporary entry for review: none. Phase 3 adds entry points; the dialog
   is exercised through Storybook and tests in this PR.

## Phase 3: entry points and docs

1. Sidebar **New backup** button in `AppSidebar` for users with
   `repositories.manage_all` (the permission the Repositories page already
   uses for its create button); opens `QuickStartDialog` via a small context
   (`QuickStartProvider` with `openQuickStart()`), mounted in `Layout`.
2. First-run auto-open on the dashboard: the user has
   `repositories.manage_all`, there are zero repositories and zero plans, and
   it was not dismissed in localStorage. Dismissal written on close.
3. Quick start action on the Backup Plans and Repositories empty states.
4. User docs: new `docs/quick-start.md`, `docs/navigation.md` mention, and
   index link.
5. Stories: sidebar with the button, empty states with the action.

## Phase 4: SSH

1. State: `sourceKind: 'ssh'` and `destinationKind: 'ssh'` choices enabled;
   `QuickStartSshConnect` sub-form (existing connection via
   `SshConnectionSelect`, or new host/user/port/password).
2. Actions: `ensure_key` (generate when `/ssh-keys/system-key` says it does
   not exist) and `deploy_key` per new connection; deploy `success: false`
   is a failure. Repository payload for SSH (`storage_backend: 'ssh'`,
   `connection_id`, `execution_target: 'ssh'`); plan source location
   `remote` with `source_ssh_connection_id`.
3. Folder and destination browsing on the SSH connection.
4. Tests for new branches; stories for the connect sub-form.

## Phase 5: agent (Pro)

1. `sourceKind: 'agent'` behind `managed_agents` with `PlanGate`.
2. `QuickStartAgentConnect`: `ManagedAgentSelect` plus "Add a new computer"
   opening `AddAgentDialog`; select the agent once it connects.
3. Destination fixed to a disk on that agent (`storage_backend:
   'agent_local'`, `executor_type: 'agent'`, `agent_machine_id`); plan
   source location `agent`.
4. Tests and stories.
