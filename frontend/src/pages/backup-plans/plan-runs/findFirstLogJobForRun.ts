import {
  canViewBackupJobLogs,
  canViewScriptLogs,
  type BackupPlanRunLogJob,
} from '../../../components/planRunScriptLogs'
import type { BackupPlanRun } from '../../../types'

export function findFirstLogJobForRun(run: BackupPlanRun): BackupPlanRunLogJob | null {
  // The run-level eye opens the primary artifact: the borg backup job. Script
  // (hook) executions have their own per-row "View Logs" affordance, so prefer
  // the backup job here and only fall back to a script when borg never produced
  // a viewable log (e.g. the run failed during a pre-backup hook).
  const repositoryRun = run.repositories.find((candidate) =>
    canViewBackupJobLogs(candidate.backup_job)
  )
  if (repositoryRun?.backup_job) {
    return repositoryRun.backup_job
  }

  const scriptExecution = run.script_executions?.find(canViewScriptLogs)
  if (scriptExecution) {
    return {
      id: scriptExecution.id,
      status: scriptExecution.status,
      type: 'script_execution',
      has_logs: scriptExecution.has_logs,
    }
  }

  return null
}
