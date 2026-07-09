import type { BackupJob, BackupPlanScriptExecution } from '../types'

// A log target opened from a plan run: either a repository backup job or one of
// the plan's script (hook) executions. Shared source of truth for the type and
// the log-eligibility rule used by every plan-run script surface.
export type BackupPlanRunLogJob =
  | BackupJob
  | {
      id: number
      status: string
      type: 'script_execution'
      has_logs?: boolean
    }

// A script execution's logs are viewable once it has actually run (not pending)
// and either the server flagged output or it is still running (live). Single
// definition so the row button and first-log selection can't drift apart.
export function canViewScriptLogs(execution: BackupPlanScriptExecution): boolean {
  return (
    execution.status !== 'pending' && Boolean(execution.has_logs || execution.status === 'running')
  )
}

// The same eligibility rule for a repository backup job. Shared so the run
// panels, the active-run card and first-log selection stay aligned.
export function canViewBackupJobLogs(job?: BackupJob | null): job is BackupJob {
  return Boolean(job && job.status !== 'pending' && (job.has_logs || job.status === 'running'))
}
