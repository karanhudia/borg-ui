# Schedule-Aware Upload Limits Spec

## Problem

BOR-166 added one constant `--upload-ratelimit` value for a backup run. That
works for repository defaults, backup-plan values, and linked-repository
overrides, but it cannot express a common throttling policy such as a low
daytime cap and an unrestricted overnight window.

## Desired Outcome

Backup plans can define upload-limit time windows. At backup execution time,
Borg UI resolves the existing constant upload limit and then applies the first
matching time-window policy for the plan's timezone. The Borg 1 and Borg 2
command builders still receive a single resolved create-time
`upload_ratelimit_kib` value, preserving Borg's native constant cap behavior.

## Scope

- Add backup-plan level scheduled upload-limit policies.
- Store policies in backup-plan create/edit payloads and responses.
- Let a policy value be a positive KiB/s cap or `null` for unlimited.
- Treat policy start/end times as `HH:MM` wall-clock times in the backup plan
  timezone.
- Support overnight windows by allowing `start_time` later than `end_time`.
- Apply active policies to manual and scheduled backup plan executions.
- Keep repository default, plan constant, and linked-repository override behavior
  unchanged when no policy matches.

## Precedence

1. Resolve the existing constant cap for each repository run:
   linked-repository override, then backup-plan constant, then repository
   default, then unlimited.
2. If the backup plan has scheduled policies, evaluate them in payload order
   against the plan run timestamp in the plan timezone.
3. The first matching policy overrides the constant cap for that repository run.
   A policy value of `null` means unlimited and intentionally clears any
   repository default, plan constant, or linked-repository override while that
   window is active.
4. If no policy matches, use the constant cap from step 1.

## Validation Rules

- `upload_ratelimit_schedule_policies` is optional and defaults to an empty
  list.
- A policy requires a non-empty `label`, `start_time`, and `end_time`.
- Times must be valid `HH:MM` values.
- `start_time` and `end_time` cannot be equal because that would be ambiguous.
- `upload_ratelimit_kib` must be `null` or a positive integer.
- API responses normalize labels by trimming whitespace and preserve policy
  order.

## Frontend UX

The backup-plan settings step keeps the existing constant upload speed field and
adds a compact policy editor directly beneath it. Each row has a label, start
time, end time, and MB/s cap. Leaving the cap blank means unlimited. The control
uses ordinary MUI form controls in the existing backup-plan wizard layout, with
small composed components and no new page-level visual system.

The review step shows a concise summary of configured windows so users can see
when the upload limit differs from the constant fallback before creating or
editing the plan.

## Acceptance Criteria

- Users can configure at least one time-window upload-limit policy for backups,
  including a low daytime cap and a higher or unlimited overnight window.
- Borg 1 and Borg 2 backup execution paths receive the expected resolved upload
  cap.
- Existing constant upload-limit settings from BOR-166 continue to work
  unchanged outside active windows and when no policies are configured.
- Scope and precedence are explicit in code, tests, and UI copy.
- Create/edit API payloads, persistence, frontend hydration, and command
  generation remain consistent.

## Validation

- Backend tests cover policy persistence and serialization.
- Backend resolver tests cover daytime, overnight, no-match, unlimited, invalid,
  and precedence cases.
- Backup plan execution tests cover scheduled policy resolution before command
  generation.
- Borg 1 and Borg 2 command tests cover the resolved cap and unlimited behavior.
- Frontend tests cover policy row editing, create/edit payload conversion, and
  hydration.
- Storybook covers the scheduled upload-limit control with day/night policies.
- Local validation runs the required backend and frontend gates plus a runtime
  walkthrough.
