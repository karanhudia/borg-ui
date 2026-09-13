import type { Job } from '../../types/jobs'

/** The words for a status, wherever it is shown: a badge, a tooltip, or the
 *  accessible name of a status dot that shows no words of its own. */
export const statusLabel = (status: string, t: (key: string) => string): string => {
  switch (status.toLowerCase()) {
    case 'completed':
      return t('status.completed')
    case 'completed_with_warnings':
      return t('status.completedWithWarnings')
    case 'needs_backup':
      return t('status.needsBackup')
    case 'failed':
      return t('status.failed')
    case 'running':
    case 'in_progress':
      return t('status.running')
    case 'pending':
      return t('status.pending')
    case 'queued':
      return t('status.queued')
    case 'cancelled':
      return t('status.cancelled')
    case 'skipped':
      return t('status.skipped')
    default:
      return status.charAt(0).toUpperCase() + status.slice(1)
  }
}

/** Translate a backend operation type into its shared display label. */
export const getTypeLabel = (type: string, t: (key: string) => string): string => {
  switch (type) {
    case 'backup':
      return t('backupJobsTable.types.backup')
    case 'restore':
      return t('backupJobsTable.types.restore')
    case 'restore_check':
      return t('backupJobsTable.types.restoreCheck')
    case 'check':
      return t('backupJobsTable.types.check')
    case 'compact':
      return t('backupJobsTable.types.compact')
    case 'prune':
      return t('backupJobsTable.types.prune')
    case 'package':
      return t('backupJobsTable.types.package')
    case 'rclone_sync':
      return t('backupJobsTable.types.rcloneSync')
    case 'rclone_hydrate':
      return t('backupJobsTable.types.rcloneHydrate')
    case 'script_execution':
      return t('backupJobsTable.types.scriptExecution')
    case 'availability_check':
      return t('backupJobsTable.types.availabilityCheck')
    case 'backup_plan_run':
      return t('backupJobsTable.types.backupPlanRun')
    default:
      return type
  }
}

/** Map an operation type to the color used by its shared badge. */
export const getTypeColor = (
  type: string
): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
  switch (type) {
    case 'backup':
      return 'primary'
    case 'restore':
      return 'secondary'
    case 'restore_check':
      return 'info'
    case 'check':
      return 'info'
    case 'compact':
      return 'warning'
    case 'prune':
      return 'warning'
    case 'package':
      return 'success'
    case 'rclone_sync':
      return 'info'
    case 'rclone_hydrate':
      return 'primary'
    case 'script_execution':
      return 'secondary'
    case 'availability_check':
      return 'default'
    case 'backup_plan_run':
      return 'error'
    default:
      return 'default'
  }
}

export const getTransportLabel = (
  executionMode: string | null | undefined,
  routeStrategy: string | null | undefined,
  t: (key: string) => string
) => {
  if (executionMode === 'agent') return t('backupJobsTable.transport.agent')
  if (
    executionMode === 'remote_ssh' ||
    executionMode === 'remote_direct' ||
    routeStrategy === 'remote_direct'
  ) {
    return t('backupJobsTable.transport.remoteSsh')
  }
  if (!executionMode) return null
  return t('backupJobsTable.transport.server')
}

export const getSkipReasonLabel = (job: Job, t: (key: string) => string): string | null => {
  if (job.status !== 'skipped') return null
  if (job.skip_reason === 'minimum_interval_not_elapsed') {
    return t('availabilitySchedule.skipReasons.minimumIntervalNotElapsed')
  }
  if (job.skip_reason === 'source_unavailable') {
    return t('availabilitySchedule.skipReasons.sourceUnavailable')
  }
  return job.error_message || null
}

export const RETRYABLE_BACKUP_JOB_STATUSES = new Set(['failed', 'cancelled'])
export const DESTRUCTIVE_JOB_TYPES = new Set([
  'delete_archive',
  'archive_delete',
  'repository_wipe',
  'wipe',
  'prune',
])

export const isManualBackupRetrySource = (job: Job): boolean => {
  const jobType = job.type || 'backup'
  if (jobType !== 'backup') return false
  if (job.backup_plan_id || job.backup_plan_run_id) return false
  if (job.scheduled_job_id || job.schedule_id) return false
  if (job.triggered_by === 'backup_plan' || job.triggered_by === 'schedule') return false
  return true
}

export const hasBackupRetryRepositoryContext = (job: Job): boolean =>
  Boolean(job.repository_id || job.repository || job.repository_path)

export const shouldShowRetryAction = (job: Job): boolean => {
  if (!RETRYABLE_BACKUP_JOB_STATUSES.has(job.status)) return false
  return isManualBackupRetrySource(job) || Boolean(job.type)
}

export const getBackupJobRetryDisabledReason = (
  job: Job,
  canRetry: boolean,
  t: (key: string, options?: Record<string, unknown>) => string
): string | null => {
  if (!RETRYABLE_BACKUP_JOB_STATUSES.has(job.status)) {
    return t('backupJobsTable.retryTooltips.onlyTerminal')
  }

  if (!isManualBackupRetrySource(job)) {
    const typeLabel = getTypeLabel(job.type || 'backup', t)
    if (DESTRUCTIVE_JOB_TYPES.has(job.type || '')) {
      return t('backupJobsTable.retryTooltips.destructiveType', { type: typeLabel })
    }
    if (job.backup_plan_id || job.backup_plan_run_id || job.triggered_by === 'backup_plan') {
      return t('backupJobsTable.retryTooltips.backupPlanJob')
    }
    if (job.scheduled_job_id || job.schedule_id || job.triggered_by === 'schedule') {
      return t('backupJobsTable.retryTooltips.scheduledJob')
    }
    return t('backupJobsTable.retryTooltips.unsupportedType', { type: typeLabel })
  }

  if (!hasBackupRetryRepositoryContext(job)) {
    return t('backupJobsTable.retryTooltips.missingRepository')
  }

  if (!canRetry) {
    return t('backupJobsTable.retryTooltips.requiresPermission')
  }

  return null
}
