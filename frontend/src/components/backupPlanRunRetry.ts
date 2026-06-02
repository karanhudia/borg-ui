import type { BackupPlanRun } from '../types'

type RetryTranslate = (key: string, options?: Record<string, unknown>) => string

export function backupPlanRunHasFailedRepositories(run: BackupPlanRun): boolean {
  return run.repositories.some(
    (runRepository) =>
      Boolean(runRepository.repository_id) &&
      (runRepository.status === 'failed' || runRepository.backup_job?.status === 'failed')
  )
}

export function shouldShowBackupPlanRunRetryAction(run: BackupPlanRun): boolean {
  return run.status === 'failed' || run.status === 'cancelled'
}

export function getBackupPlanRunRetryDisabledReason(
  run: BackupPlanRun,
  t: RetryTranslate,
  options: {
    canRetry: boolean
    hasActiveRunForPlan: boolean
  }
): string | null {
  if (run.status !== 'failed') {
    return t('backupPlans.runsPanel.retryTooltips.onlyFailed')
  }
  if (!run.backup_plan_id) {
    return t('backupPlans.runsPanel.retryTooltips.missingPlan')
  }
  if (options.hasActiveRunForPlan) {
    return t('backupPlans.runsPanel.retryTooltips.activeRun')
  }
  if (!backupPlanRunHasFailedRepositories(run)) {
    return t('backupPlans.runsPanel.retryTooltips.noFailedRepositories')
  }
  if (!options.canRetry) {
    return t('backupPlans.runsPanel.retryTooltips.requiresPermission')
  }
  return null
}
