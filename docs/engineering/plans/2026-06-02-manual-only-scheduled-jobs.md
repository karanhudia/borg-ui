# Manual-Only Scheduled Jobs Implementation Plan

## Goal

Allow legacy backup schedules to be saved as manual-only jobs with no cron expression while preserving existing scheduled cron behavior.

## Design

- Treat `ScheduledJob.cron_expression` as the existing persistence signal: a non-empty cron means scheduled, an empty string means manual-only.
- Keep `enabled` as the job availability toggle. Manual-only enabled jobs can be run with Run now but never receive `next_run`.
- Return `schedule_enabled`, nullable `cron_expression`, nullable `timezone`, and `next_run=null` in API responses for manual-only jobs.
- Add a manual-only switch to the existing schedule wizard step. The shared `SchedulePicker` remains the only cron/timezone UI and is rendered only when scheduling is enabled.

## Tasks

- [x] Add failing backend route tests for create, list, update, duplicate, and toggle behavior.
- [x] Add failing frontend tests for the schedule step and manual-only job card state.
- [x] Update `app/api/schedule.py` request models, cron normalization, serialization, create/update/toggle/duplicate paths, and scheduler dispatch safeguards.
- [x] Update legacy schedule wizard state, payload mapping, review UI, schedule config UI, cards, and TypeScript types.
- [x] Update locale files and Storybook coverage for the new manual-only state.
- [x] Run targeted backend/frontend tests, required validation gates, and runtime walkthrough evidence.
