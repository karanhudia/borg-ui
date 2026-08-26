# Automatic remote-direct execution

## Problem

Backup plans automatically select remote-direct execution when their remote SSH
source and SSH repository use the same connection. The resulting backup still
fails unless the connection was separately marked `is_backup_source`, a state
that the plan workflow neither explains nor can set.

## User outcome

Users choose a source and a repository. Borg UI selects the direct route when
those choices make it applicable and explains that Borg will run on the source
machine. Users do not configure `is_backup_source`.

## Scope

- Remove `is_backup_source` as a runtime prerequisite for remote-direct jobs.
- Preserve the automatic route selection already performed by the route planner.
- Show a concise, informational direct-execution notice in the plan review.
- Cover the review notice in Storybook and the removed backend guard in unit
  tests.

## Non-goals

- Do not remove the legacy API or database fields in this change.
- Do not add a user-facing execution-mode control.
- Do not implement an SSHFS fallback when Borg is absent on the direct source;
  that requires an explicit, verified route fallback design.

## Error handling

Remote-direct still requires Borg on the source host. This change removes the
hidden backup-source eligibility flag; a later change can preflight the Borg
dependency and offer a route fallback before the plan is run.
