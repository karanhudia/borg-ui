# Stale Backup Running Check Spec

## Problem

GitHub discussion 590 reports backup task cards that remain visible as running even after progress stops. The screenshot shows backup cards at `FINALIZING...` with `RUNNING_CHECK`, and canceling one raises `Can only cancel running jobs`.

The frontend schedule flow treats any backup row with a `maintenance_status` containing `running` as an active card. The backend cancel endpoint only recognizes base backup `running`, `running_prune`, and `running_compact`, so `running_check` reaches the generic rejection path.

## Desired Outcome

Backup rows stuck in `running_check` can be canceled or reconciled from the same cancel affordance that appears on the active backup card. Startup orphan cleanup also normalizes stale `running_check` maintenance state so old rows stop appearing as running tasks.

## Acceptance Criteria

- `POST /api/backup/cancel/{job_id}` succeeds for a backup row with `maintenance_status="running_check"` and a running `CheckJob`.
- The same endpoint reconciles a stale `running_check` parent backup row when no running `CheckJob` exists.
- Startup orphan cleanup maps `running_check` to `check_failed`.
- Completed or warning backup rows keep their backup result when only the post-backup maintenance check is stale.
- Focused backend tests cover cancel and orphan cleanup behavior.

## Validation

- Run focused cancel and cleanup tests that fail before the code change and pass after it.
- Run `ruff check app tests`.
- Run `ruff format --check app tests`.

## Notes

- Keep this backend-only unless validation reveals the frontend needs a state-label adjustment.
- Do not introduce new UI patterns. The visible cancel button is already present for the affected card.
