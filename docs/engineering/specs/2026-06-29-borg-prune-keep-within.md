# Borg Prune Keep-Within Support

## Problem

Borg UI prune settings only support count-based retention rules such as hourly,
daily, weekly, monthly, quarterly, and yearly. Users running frequent backups,
for example every five minutes, cannot keep every recent archive for a time
window before older archives are thinned. Borg supports this directly with
`--keep-within=<interval>`.

## Desired Outcome

Manual repository prune, scheduled post-backup prune, backup plan maintenance,
agent-executed prune jobs, and borgmatic import/export all understand an
optional keep-within interval. When present, Borg UI passes it through to Borg as
`--keep-within=<interval>` without changing existing count-based retention
defaults.

## UX

The existing prune retention UI keeps its count-based controls and adds a text
field for the recent archive window. The field accepts Borg interval strings
such as `12H`, `1d`, `2w`, `1m`, and `1y`. Empty means disabled. The helper text
explains that archives inside the interval are kept before the count rules apply.

The shared `PruneSettingsInput` covers scheduled jobs and backup plans. The
manual `PruneRepositoryDialog` keeps its compact row layout and adds a matching
first row for keep-within. Review/status summaries include the interval when it
is set.

## Data Model

Add nullable string columns:

- `scheduled_jobs.prune_keep_within`
- `backup_plans.prune_keep_within`

Manual prune requests do not persist repository defaults; they carry the
optional interval in the request body. Existing rows remain valid because null
and empty strings both mean disabled.

## Acceptance Criteria

- Manual prune dry-run and execution include `--keep-within=<interval>` when the
  dialog submits a non-empty interval.
- Scheduled jobs and backup plans persist `prune_keep_within`, return it in API
  responses, duplicate/copy it, and pass it into post-backup prune execution.
- Borg v1, Borg v2, and agent prune command builders include the flag when set
  and omit it when blank.
- Existing count-based retention defaults and behavior are unchanged when
  keep-within is blank.
- Storybook coverage demonstrates the new manual prune field and backup plan
  schedule state.
- Focused backend and frontend tests cover payload plumbing and command
  generation.

## Validation

- Backend-targeted tests:
  `pytest tests/unit/test_borg_router.py tests/unit/test_v2_prune_service.py tests/unit/test_agent_runtime.py tests/unit/test_api_backup_plans.py tests/unit/test_borgmatic_service.py`
- Frontend-targeted tests:
  `cd frontend && npm run test -- PruneSettingsInput PruneRepositoryDialog ScheduleStep ReviewStep borgApi/client backupPlanPayload`
- Required backend checks:
  `ruff check app tests`, `ruff format --check app tests`
- Required frontend checks:
  `cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build`
- Runtime/UI proof: launch or smoke-test Borg UI enough to open the prune
  retention path and verify the new interval field is visible and usable.

## Notes

- Borg docs define `--keep-within INTERVAL` as keeping all archives within the
  interval, and those archives do not count toward other retention totals.
- Borg interval examples from the docs use `<int><char>` with chars such as
  `H`, `d`, `w`, `m`, and `y`.
