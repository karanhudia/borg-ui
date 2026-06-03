# Executable Jobs Schedules Spec

## Problem

GitHub issue #559 asks whether repository schedules are going away because the
reporter relies on a multi-repository scheduled workflow: wake a backup server,
run backup/prune/compact across repositories, then power off only after the last
repository finishes.

Backup Plans can run pre/post scripts and maintenance, but multi-repository
Backup Plans are plan-tier gated. The current product answer is that this
legacy repository schedule capability is not going away, but the Schedule
surface is confusing because it mixes plan schedules, repository schedules,
checks, restore checks, activity, and legacy backup schedules under one
"Schedule" label.

PR #608 tried to solve the ticket with documentation only. Owner feedback
rejected that approach and requested product/UI rework: move "Legacy Schedule"
out of the Schedule tab and use a clearer concept such as crons or batch jobs,
showing executable legacy repositories and Backup Plans while hiding newer
repositories that do not have repository-owned sources.

## Desired Outcome

The scheduling area should read as an executable jobs surface rather than a
deprecated schedule migration page. Users should understand that:

- legacy repository jobs remain supported;
- Backup Plans are the normal scheduled backup surface when they fit;
- legacy repository jobs are for repositories that still own executable source
  paths;
- newer repositories without repository-owned sources are not valid legacy job
  targets.

The GitHub issue reply can then point to the product direction accurately:
the capability remains, but the UI is being renamed/reframed around executable
jobs.

## Design

Use **Jobs** as the primary visible navigation label. It is shorter and less
cron-specific than "Crons", while still matching the existing product language
for backup/check/history work. Keep the existing `/schedule` route for
compatibility and tab enablement, but make visible labels say "Jobs" and make
the first tab "Executable Jobs".

The first tab keeps the existing plan-oriented cards and legacy scheduled job
table in one operational view:

- Backup Plans appear first because they are the preferred new scheduled backup
  workflow.
- Legacy Repository Jobs appear as a separate section and remain visible even
  when empty, so users can see that legacy repository jobs are still supported.
- The Create legacy job button opens the existing schedule wizard, but the
  repository list is filtered to executable legacy repositories only.

An executable legacy repository is a full-mode repository with repository-owned
sources:

- `source_directories` has at least one path; or
- `source_locations` has at least one path; or
- `source_locations` has a database selection with at least one `backup_paths`
  entry.

Repositories in observe mode, repositories without sources, and plan-owned
source repositories are excluded from legacy job creation. Backup Plans remain
selectable through the Backup Plans section.

## Scope

In scope:

- Rename visible navigation/page/tab/copy from Schedule/Schedules to Jobs where
  it refers to the overall executable work surface.
- Rename legacy backup schedule copy to Legacy Repository Jobs.
- Filter the legacy schedule wizard's repository choices to executable legacy
  repositories.
- Add frontend tests for navigation naming and executable repository filtering.
- Add or update Storybook coverage for the changed scheduled jobs table state.
- Update user docs for the navigation change.

Out of scope:

- Backend schedule model changes.
- New schedule record types.
- Combining Backup Plan and legacy repository jobs into one backend API.
- Removing `/schedule` compatibility routes.
- Changing plan-tier gating for multi-repository Backup Plans.

## Acceptance Criteria Mapping

- Legacy repository schedules are no longer presented as the main "Schedule"
  tab; the visible surface is Jobs with an Executable Jobs tab.
- Backup Plans and Legacy Repository Jobs are shown together in the executable
  jobs view.
- Legacy job creation only receives repositories with repository-owned source
  settings.
- Docs explain the Jobs navigation and when to use Backup Plans versus legacy
  repository jobs.
- GitHub issue #559 receives a final answer grounded in the implementation.

## Validation

- Failing-first Vitest coverage for executable repository filtering.
- Failing-first Vitest coverage for sidebar Jobs navigation naming.
- Targeted component tests for changed scheduled jobs table copy.
- Required frontend gate: `npm run check:locales`, `npm run typecheck`,
  `npm run lint`, and `npm run build`.
- Local app walkthrough of the Jobs page and legacy job creation path.
