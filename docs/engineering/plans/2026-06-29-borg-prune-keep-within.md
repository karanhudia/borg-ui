# Borg Prune Keep-Within Implementation Plan

## Goal

Add optional Borg prune keep-within support across manual prune, scheduled
maintenance, backup plan maintenance, agent execution, and borgmatic
import/export.

## Architecture

Treat keep-within as an optional string. Normalize user input by trimming
whitespace and converting empty strings to null/undefined at API and payload
boundaries. Thread the value through existing prune call chains and append
`--keep-within=<value>` near the other retention flags only when present.

## Tasks

- [x] Backend red tests
  - Add tests that expect Borg v1/v2/router/agent prune commands to include
    `--keep-within=1d` when set and omit it when blank.
  - Add API/persistence tests for backup plan create/copy/execute and borgmatic
    export/import carrying `prune_keep_within`.
  - Run the focused pytest paths and confirm the new tests fail for missing
    fields/arguments.

- [x] Backend implementation
  - Add migration `125_add_prune_keep_within.py`.
  - Add `prune_keep_within` to `ScheduledJob` and `BackupPlan` models.
  - Extend schedule and backup plan Pydantic payloads, create/update/list/copy
    serializers, backup plan run context, legacy schedule execution, and manual
    repository prune request parsing.
  - Extend `BorgRouter.prune`, v1/v2 prune services, `app.core.borg`,
    `app.core.borg2`, repository executor payloads, and agent command building.
  - Extend borgmatic retention export/import with `keep_within`.

- [x] Frontend red tests
  - Add `PruneSettingsInput` tests for rendering, editing, and disabling the
    keep-within text field.
  - Add manual `PruneRepositoryDialog` tests for initial values, submission
    payloads, and preview copy including keep-within.
  - Add backup plan payload/state/review tests for `pruneKeepWithin`.
  - Run focused Vitest commands and confirm the new tests fail before UI code.

- [x] Frontend implementation
  - Add `keepWithin` to `PruneSettings`, schedule wizard state/types,
    backup-plan payload state/types, API client `PruneOptions`, and response
    types.
  - Add localized labels/helper copy in all locale files and update tests/stories
    that use local translation maps.
  - Add the text field to `PruneSettingsInput` and manual
    `PruneRepositoryDialog`, preserving stable layout and compact controls.
  - Include the interval in retention summaries/review pills/schedule cards when
    configured.
  - Update Storybook stories for `PruneRepositoryDialog` and backup-plan
    `ScheduleStep`.

- [x] Validation and handoff
  - Run targeted backend/frontend tests.
  - Run required backend and frontend checks for touched code.
  - Run an app walkthrough or smoke proof for the prune retention UI path.
  - Commit, push, open/update PR with the Borg UI template, attach it to Linear,
    ensure the `symphony` label, sweep feedback/checks, and move to Human Review
    only when green.
