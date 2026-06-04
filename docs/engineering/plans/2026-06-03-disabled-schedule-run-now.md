# Disabled Schedule Run Now Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development while implementing this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep manual execution available for disabled legacy scheduled jobs.

**Architecture:** Treat a disabled scheduled job as the persisted manual-run workflow described in BOR-124 rework feedback. The backend `POST /api/schedule/{id}/run-now` already accepts disabled jobs, so the implementation stays in the schedule card action state: only permissions and a pending run should disable `Run now`. Existing schedule creation, cron validation, timezone controls, and scheduled dispatcher behavior remain unchanged.

**Tech Stack:** React, TypeScript, MUI, lucide-react, i18next, Vitest, Storybook.

---

## Files

- Modify: `frontend/src/components/ScheduleJobCard.tsx`
- Modify: `frontend/src/components/__tests__/ScheduleJobCard.test.tsx`
- Add: `frontend/src/components/ScheduleJobCard.stories.tsx`

## Implementation Tasks

- [x] Verify current `main` behavior with a failing Vitest case showing disabled scheduled jobs set `primaryAction.disabled=true`.
- [x] Change `ScheduleJobCard` so `Run now` is disabled only while `isRunNowPending` is true; `canManage` still controls whether the primary action exists.
- [x] Keep the pending-state test to prove the action still disables while a manual run is being submitted.
- [x] Add Storybook coverage for enabled scheduled, disabled manual-run, and pending disabled states.
- [x] Run focused Vitest for `ScheduleJobCard`.
- [x] Run frontend required gates: locales, typecheck, lint, build.
- [x] Run a runtime walkthrough that creates or uses a disabled scheduled job, confirms the card displays it as disabled, and triggers `Run now`.

## Self-Review

- This plan deliberately does not carry forward PR #610's no-cron API/UI changes because PR #610 was closed for Rework and the owner feedback identified disabled schedules as the intended manual-run mechanism.
- The plan does not add ad hoc cron or timezone UI; existing schedule wizard controls remain unchanged.
- The disabled status remains visually distinct through the existing switch/badge, while the manual action remains available as an explicit button.
