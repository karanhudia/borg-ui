# Managed Agent Log Viewer Alignment Spec

## Problem

Managed Agents uses terminal icons for log actions and raw MUI `Dialog`
instances with `<pre>` blocks for agent/job logs. The rest of Borg UI uses an
eye icon for "view logs" actions and the reusable log viewer dialog backed by
`TerminalLogViewer`.

## Desired Outcome

Managed Agents should present log viewing the same way other Borg UI surfaces
do. Agent and job log actions use the eye/view icon, and logs open in the
generic log viewer dialog. The reusable log viewer source should live under
`frontend/src/components/shared/` so future features can import it directly.

## Design

Move `LogViewerDialog` and `TerminalLogViewer` into shared components and keep
thin compatibility re-exports at their previous paths. Extend
`LogViewerDialog` with an optional custom log fetcher so non-activity log
sources, including managed-agent job and session logs, can reuse the same
viewer chrome without going through the activity logs API.

Managed Agents converts backend agent/job log entries into the viewer's
`line_number`/`content` shape. Agent logs use the agent id as the viewer job id
and show a title of `Agent Logs - <agent label>`. Agent job logs use the job id
and show `Agent Job Logs - Job #<id>`. Online agents and running jobs keep the
viewer in running mode so it polls for fresh log lines.

The UI remains operational and quiet: no new accent-border patterns, no new
dialog vocabulary, and no new icon family. The icon change is limited to log
actions; the setup-command affordance can keep a terminal icon because it
represents a shell command rather than viewing logs.

## Acceptance Criteria

- Managed Agents agent-card log actions use the eye/view icon.
- Managed Agents job-row log actions use the eye/view icon.
- Managed-agent session logs open in the shared log viewer dialog.
- Managed-agent job logs open in the shared log viewer dialog.
- `LogViewerDialog` and `TerminalLogViewer` are importable from
  `frontend/src/components/shared/`.
- Existing imports from the previous component paths continue to work.
- Managed Agents Storybook coverage demonstrates the updated log viewer state.

## Validation

- Red/green Vitest coverage for the Managed Agents icon and log-dialog behavior.
- Shared log viewer tests cover custom log fetchers.
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run snapshots`
- Runtime walkthrough of Managed Agents log actions.

## Notes

Reproduction before implementation: `frontend/src/pages/ManagedAgents.tsx`
imports `Terminal`, renders terminal icons for the agent-card and job-row log
actions, and renders both log dialogs as raw `Dialog` plus `<pre>` blocks.
