# Borg Check Flag Conflict Guidance Spec

## Goal

Prevent users and API callers from starting Borg check commands that combine a
partial repository-only duration with advanced flags that require a full
archive-aware check.

## Context

Borg UI adds `--repository-only --max-duration <seconds>` whenever a check job
has a positive max duration. Advanced `check_extra_flags` can also add
`--verify-data`, `--repair`, or `--archives-only`. Those flags need a full check
and conflict with the repository-only mode implied by positive `max_duration`.

Scheduled checks have an additional issue: the UI currently hints at a minimum
duration of 60 seconds, and the scheduler uses `repo.check_max_duration or 3600`,
which turns a persisted unlimited value of `0` back into a one-hour partial
check.

## Design

Add one shared backend validator for check extra flags and max duration. The
validator parses the flag string with `shlex.split`, detects full-check flags,
and rejects positive durations when any detected flag requires a full check. API
routes return a 422 response with a translatable error key and the conflicting
flags. Invalid shell-like quoting keeps the existing execution behavior and is
not expanded into broader flag validation for this ticket.

Apply the guard to manual repository checks, Borg 2 manual checks, repository
check schedule updates, and backup plan create/update. Preserve valid
`max_duration: 0` configurations and fix scheduled dispatch so `0` reaches the
`CheckJob` instead of falling back to `3600`.

On the frontend, add a shared check-flag conflict helper. Manual check,
scheduled check, and backup plan maintenance forms show an inline warning when
positive max duration is combined with `--verify-data`, `--repair`, or
`--archives-only`. The warning uses existing MUI alert styling, no heavy accent
borders, and keeps the relevant submit/next action disabled until the duration
is set to `0` or the conflicting flags are removed.

## Acceptance Criteria

- Scheduled check UI accepts and explains `max_duration: 0` as unlimited/full
  check mode.
- Manual check, scheduled check, and backup-plan maintenance surfaces warn when
  full-check flags are combined with positive max duration.
- API routes reject new conflicting combinations and allow
  `check_extra_flags: "--verify-data"` with `max_duration: 0`.
- Scheduled dispatch preserves `max_duration: 0` when copying repository
  settings into a `CheckJob`.
- Targeted backend and frontend tests cover one rejected conflicting path and
  one valid `--verify-data` plus `max_duration: 0` path.
- Updated Storybook stories and generated snapshots cover the changed warning
  state.

## Validation

- Backend: targeted repository schedule/manual check, scheduler, backup plan,
  and Borg 2 route tests.
- Frontend: targeted tests for `CheckWarningDialog`, `ScheduledChecksSection`,
  and backup plan schedule/maintenance controls.
- Storybook: `cd frontend && npm run snapshots`.
- Required gates: backend ruff checks and relevant pytest; frontend locales,
  typecheck, lint, build.
