import { type BackupPlanRunLogJob } from '../../../components/BackupPlanRunsPanel'
import type { BackupPlanRun } from '../../../types'

export function findFirstLogJobForRun(run: BackupPlanRun): BackupPlanRunLogJob | null {
  const scriptExecution = run.script_executions?.find(
    (exec) => exec.status !== 'pending' && (exec.has_logs || exec.status === 'running')
  )
  if (scriptExecution) {
    return {
      id: scriptExecution.id,
      status: scriptExecution.status,
      type: 'script_execution',
      has_logs: scriptExecution.has_logs,
    }
  }

  const repositoryRun = run.repositories.find(
    (candidate) =>
      candidate.backup_job &&
      candidate.backup_job.status !== 'pending' &&
      (candidate.backup_job.has_logs || candidate.backup_job.status === 'running')
  )
  return repositoryRun?.backup_job ?? null
}
