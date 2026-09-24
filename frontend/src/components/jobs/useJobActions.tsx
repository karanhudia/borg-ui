import React, { useCallback, useState, useSyncExternalStore } from 'react'
import { useTranslation } from 'react-i18next'
import { Eye, Download, Trash2, Lock, Play, AlertCircle, FolderOpen, RotateCcw } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import type { ActionButton } from '../RowActions'
import { Job, Repository } from '../../types/jobs'
import ErrorDetailsDialog from '../ErrorDetailsDialog'
import LogViewerDialog from '../LogViewerDialog'
import CancelJobDialog from '../CancelJobDialog'
import DeleteJobDialog from '../DeleteJobDialog'
import RetryJobDialog from '../RetryJobDialog'
import LockErrorDialog from '../LockErrorDialog'
import { activityAPI, repositoriesAPI } from '../../services/api'
import { buildDownloadUrl } from '@/utils/downloadUrl'
import { downloadArchiveFile } from '../../utils/downloadArchiveFile'
import { isV2Repo } from '../../utils/repoCapabilities'
import ArchiveContentsDialog from '../ArchiveContentsDialog'
import type { Repository as FullRepository, Archive } from '../../types'
import { getBackupJobRetryDisabledReason, shouldShowRetryAction } from './jobLabels'
import { deleteJobFromLists, jobKey, pendingDeletes, subscribeToPendingDeletes } from './jobCache'

type CanBreakLocks<T extends Job> = boolean | ((job: T) => boolean)

export interface JobActionsOptions<T extends Job = Job> {
  repositories?: Repository[]

  // Actions configuration
  actions?: {
    viewLogs?: boolean
    viewArchive?: boolean
    downloadLogs?: boolean
    cancel?: boolean
    errorInfo?: boolean
    breakLock?: boolean
    runNow?: boolean
    delete?: boolean
    retry?: boolean
  }

  // Callbacks
  onViewLogs?: (job: T) => void
  onDownloadLogs?: (job: T) => void
  onErrorDetails?: (job: T) => void
  onCancelJob?: (job: T) => void | Promise<void>
  onBreakLock?: (job: T) => void | Promise<void>
  onRunNow?: (job: T) => void
  onDeleteJob?: (job: T) => void | Promise<void>
  onRetryJob?: (job: T) => void | Promise<void>

  // User permissions
  canBreakLocks?: CanBreakLocks<T>
  lockBreakingEnabled?: boolean
  canDeleteJobs?: boolean
  canRetryJob?: (job: T) => boolean
  retryingJobId?: string | number | null
}

// The actions a listed job offers (logs, archive, cancel, delete, retry,
// break lock) and the dialogs they open. Extracted from BackupJobsTable so
// the Activity timeline offers exactly the same set; render `dialogs` once
// next to whatever lists the jobs.
export function useJobActions<T extends Job = Job>({
  repositories = [],
  actions = {},
  onViewLogs,
  onDownloadLogs,
  onErrorDetails,
  onCancelJob,
  onBreakLock,
  onRunNow,
  onDeleteJob,
  onRetryJob,
  canBreakLocks = false,
  lockBreakingEnabled = true,
  canDeleteJobs = false,
  canRetryJob = () => false,
  retryingJobId = null,
}: JobActionsOptions<T>): { actionButtons: ActionButton<T>[]; dialogs: React.ReactNode } {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  // Fetch repositories (needed for break lock and view archive)
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.list,
    enabled: actions.breakLock !== false || actions.viewArchive !== false,
  })

  // Internal state for dialogs
  const [errorJob, setErrorJob] = useState<T | null>(null)
  const [logJob, setLogJob] = useState<T | null>(null)
  const [cancelJob, setCancelJob] = useState<T | null>(null)
  const [deleteJob, setDeleteJob] = useState<T | null>(null)
  const [retryJob, setRetryJob] = useState<T | null>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
    borgVersion?: 1 | 2
    canBreakLock: boolean
    lockBreakingEnabled: boolean
  } | null>(null)
  const [archiveView, setArchiveView] = useState<{
    archive: Archive
    repository: FullRepository
  } | null>(null)

  // Internal error handler (can be overridden by onErrorDetails prop)
  const handleErrorClick = (job: T) => {
    if (onErrorDetails) {
      onErrorDetails(job)
    } else {
      setErrorJob(job)
    }
  }

  const handleCloseError = () => {
    setErrorJob(null)
  }

  // Internal log viewer handler (can be overridden by onViewLogs prop)
  const handleViewLogsClick = (job: T) => {
    if (onViewLogs) {
      onViewLogs(job)
    } else {
      setLogJob(job)
    }
  }

  const handleCloseLogs = () => {
    setLogJob(null)
  }

  // Internal download logs handler (can be overridden by onDownloadLogs prop)
  const handleDownloadLogsClick = (job: T) => {
    if (onDownloadLogs) {
      onDownloadLogs(job)
    } else {
      // Default implementation: use activity API endpoint
      const jobType = job.type || 'backup'
      const url = buildDownloadUrl(`/activity/${jobType}/${job.id}/logs/download`)
      const a = document.createElement('a')
      a.href = url
      a.download = `${jobType}-${job.id}-logs.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      toast.success(t('backupJobsTable.toasts.downloadingLogs'))
    }
  }

  // Internal cancel handler (can be overridden by onCancelJob prop)
  const handleCancelClick = (job: T) => {
    if (onCancelJob) {
      onCancelJob(job)
    } else {
      setCancelJob(job)
    }
  }

  const handleConfirmCancel = async () => {
    if (!cancelJob) return

    try {
      // Call cancel API
      const jobType = cancelJob.type || 'backup'
      await activityAPI.cancelJob(jobType, cancelJob.id)

      toast.success(t('backupJobsTable.toasts.cancelSuccess'))
      setCancelJob(null)
      // The Activity, Backup and Schedule tables each cache their own list;
      // refresh them so the row stops offering Cancel before the next poll.
      queryClient.invalidateQueries({ queryKey: ['activity'] })
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
      queryClient.invalidateQueries({ queryKey: ['backup-jobs-all'] })
    } catch (error) {
      toast.error(t('backupJobsTable.toasts.failedToCancel'))
      console.error(error)
    }
  }

  const handleCloseCancelDialog = () => {
    setCancelJob(null)
  }

  // Internal delete handler (can be overridden by onDeleteJob prop)
  const handleDeleteClick = (job: T) => {
    if (onDeleteJob) {
      onDeleteJob(job)
    } else {
      setDeleteJob(job)
    }
  }

  // Deletes still waiting for the server, shared by every table on this
  // query client. A row that comes back while its delete is out (a poll, an
  // operation event) keeps its Delete disabled.
  const deletingKeys = useSyncExternalStore(
    useCallback((listener) => subscribeToPendingDeletes(queryClient, listener), [queryClient]),
    () => pendingDeletes(queryClient)
  )
  const isDeleting = (job: T) => deletingKeys.has(jobKey(job))

  const handleConfirmDelete = async () => {
    if (!deleteJob) return

    const jobToDelete = deleteJob
    const jobType = jobToDelete.type || 'backup'

    // Close dialog immediately for better UX
    setDeleteJob(null)

    try {
      const deleted = await deleteJobFromLists(
        queryClient,
        { id: jobToDelete.id, type: jobType },
        () => activityAPI.deleteJob(jobType, jobToDelete.id)
      )
      // Success - show toast after item is already removed from UI
      if (deleted) toast.success(t('backupJobsTable.toasts.deleteSuccess'))
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t('backupJobsTable.toasts.failedToDelete')
      )
      console.error(error)
    }
  }

  const handleCloseDeleteDialog = () => {
    setDeleteJob(null)
  }

  const resolveCanBreakLocks = (job: T): boolean => {
    return typeof canBreakLocks === 'function' ? canBreakLocks(job) : canBreakLocks
  }

  const handleRetryClick = (job: T) => {
    const disabledReason = getBackupJobRetryDisabledReason(job, canRetryJob(job), t)
    if (disabledReason) return
    setRetryJob(job)
  }

  const handleConfirmRetry = async () => {
    if (!retryJob) return

    const jobToRetry = retryJob
    setRetryJob(null)
    await onRetryJob?.(jobToRetry)
  }

  const handleCloseRetryDialog = () => {
    setRetryJob(null)
  }

  // Internal break lock handler (can be overridden by onBreakLock prop)
  const handleBreakLockClick = async (job: T) => {
    if (onBreakLock) {
      onBreakLock(job)
    } else {
      // Default implementation: extract repo path from error message and show dialog
      const repoPath = job.error_message?.match(/LOCK_ERROR::(.+)/)?.[1].split('\n')[0]
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const repo = repositoriesData?.data?.repositories?.find((r: any) => r.path === repoPath)
      if (!repo) {
        toast.error(t('backupJobsTable.toasts.repositoryNotFound'))
        return
      }

      // Show LockErrorDialog
      setLockError({
        repositoryId: repo.id,
        repositoryName: repo.name,
        borgVersion: repo.borg_version as 1 | 2 | undefined,
        canBreakLock: resolveCanBreakLocks(job),
        lockBreakingEnabled,
      })
    }
  }

  const actionButtons: ActionButton<T>[] = []

  if (actions.viewLogs !== false) {
    actionButtons.push({
      icon: <Eye size={18} />,
      label: t('backupJobsTable.actions.viewLogs'),
      onClick: handleViewLogsClick,
      color: 'primary',
      tooltip: t('backupJobsTable.actions.viewLogs'),
      show: (job) => {
        // Show logs button for running and completed jobs (when logs exist)
        // Check has_logs flag or log_file_path, exclude only pending status
        return (
          (job.has_logs === true || !!job.log_file_path || job.status === 'running') &&
          job.status !== 'pending'
        )
      },
    })
  }

  if (actions.viewArchive !== false) {
    const findArchiveRepo = (job: T) => {
      const allRepos = repositoriesData?.data?.repositories || repositories || []
      const repoPath = job.repository_path || job.repository
      return allRepos.find((r: FullRepository) => r.path === repoPath || r.name === repoPath) as
        FullRepository | undefined
    }
    // A Borg 2 archive is addressed by id (a series repeats names) and the id
    // comes from the stored archive row, which the sync writes moments after
    // the backup. Until then the shortcut has nothing valid to open.
    const awaitingArchiveId = (job: T) => {
      const repo = findArchiveRepo(job)
      return !!repo && isV2Repo(repo) && !job.archive_borg_id
    }
    actionButtons.push({
      icon: <FolderOpen size={18} />,
      label: t('backupJobsTable.actions.viewArchive'),
      onClick: (job) => {
        if (!job.archive_name || awaitingArchiveId(job)) return
        const repo = findArchiveRepo(job)
        if (!repo) {
          toast.error(t('backupJobsTable.toasts.repositoryNotFound'))
          return
        }
        setArchiveView({
          archive: {
            // The borg id, not the name: the client selects by `aid:<id>`.
            // Empty only for Borg 1, where the client uses the unique name.
            id: job.archive_borg_id ?? '',
            archive: job.archive_name,
            name: job.archive_name,
            start: job.started_at || '',
            time: job.started_at || '',
          },
          repository: repo,
        })
      },
      color: 'success',
      // the row outlives its archive: the button stays, greyed out, and says why
      disabled: (job) => !!job.archive_pruned_at || awaitingArchiveId(job),
      tooltip: (job) =>
        job.archive_pruned_at
          ? t('backupJobsTable.actions.viewArchivePruned')
          : awaitingArchiveId(job)
            ? t('backupJobsTable.actions.viewArchiveUnindexed')
            : t('backupJobsTable.actions.viewArchive'),
      show: (job) =>
        !!job.archive_name &&
        (job.type === 'backup' || !job.type) &&
        (job.status === 'completed' || job.status === 'completed_with_warnings'),
    })
  }

  if (actions.downloadLogs !== false) {
    actionButtons.push({
      icon: <Download size={18} />,
      label: t('backupJobsTable.actions.downloadLogs'),
      onClick: handleDownloadLogsClick,
      color: 'info',
      tooltip: t('backupJobsTable.actions.downloadLogs'),
      show: (job) => {
        // Show download button for running and completed jobs (when logs exist)
        // Check has_logs flag or log_file_path, exclude only pending status
        return (
          (job.has_logs === true || !!job.log_file_path || job.status === 'running') &&
          job.status !== 'pending'
        )
      },
    })
  }

  if (actions.errorInfo !== false) {
    actionButtons.push({
      icon: <AlertCircle size={18} />,
      label: t('backupJobsTable.actions.errorDetails'),
      onClick: handleErrorClick,
      color: 'error',
      tooltip: t('backupJobsTable.actions.errorDetails'),
      show: (job) => job.status === 'failed' && !!job.error_message,
    })
  }

  if (actions.retry === true && onRetryJob) {
    actionButtons.push({
      icon: <RotateCcw size={18} />,
      label: t('backupJobsTable.actions.retry'),
      onClick: handleRetryClick,
      color: 'info',
      tooltip: (job) => {
        if (retryingJobId !== null && String(retryingJobId) === String(job.id)) {
          return t('backupJobsTable.retryTooltips.retrying')
        }
        return (
          getBackupJobRetryDisabledReason(job, canRetryJob(job), t) ||
          t('backupJobsTable.retryTooltips.ready')
        )
      },
      disabled: (job) =>
        (retryingJobId !== null && String(retryingJobId) === String(job.id)) ||
        Boolean(getBackupJobRetryDisabledReason(job, canRetryJob(job), t)),
      show: shouldShowRetryAction,
    })
  }

  if (actions.cancel !== false) {
    actionButtons.push({
      icon: <Trash2 size={18} />,
      label: t('backupJobsTable.actions.cancel'),
      onClick: handleCancelClick,
      color: 'warning',
      tooltip: t('backupJobsTable.actions.cancelJob'),
      show: (job) => job.status === 'running',
    })
  }

  if (actions.breakLock !== false) {
    actionButtons.push({
      icon: <Lock size={18} />,
      label: t('backupJobsTable.actions.breakLock'),
      onClick: handleBreakLockClick,
      color: 'warning',
      tooltip: t('backupJobsTable.actions.breakLock'),
      show: (job) =>
        lockBreakingEnabled &&
        resolveCanBreakLocks(job) &&
        job.status === 'failed' &&
        !!job.error_message?.includes('LOCK_ERROR::'),
    })
  }

  if (actions.runNow !== false && onRunNow) {
    actionButtons.push({
      icon: <Play size={18} />,
      label: t('backupJobsTable.actions.runNow'),
      onClick: onRunNow,
      color: 'success',
      tooltip: t('backupJobsTable.actions.runNow'),
      show: (job) => job.status !== 'running' && job.type !== 'availability_check',
    })
  }

  if (actions.delete !== false && canDeleteJobs) {
    actionButtons.push({
      icon: <Trash2 size={18} />,
      label: t('backupJobsTable.actions.delete'),
      onClick: handleDeleteClick,
      color: 'error',
      disabled: isDeleting,
      tooltip: (job) =>
        isDeleting(job)
          ? t('backupJobsTable.actions.deleting')
          : t('backupJobsTable.actions.delete'),
      show: (job) => job.status !== 'running' && job.type !== 'availability_check', // Availability decisions are immutable history, not jobs.
    })
  }

  const dialogs = (
    <>
      {/* Error Details Dialog */}
      <ErrorDetailsDialog
        job={errorJob}
        open={Boolean(errorJob)}
        onClose={handleCloseError}
        onViewLogs={onViewLogs || handleViewLogsClick}
      />

      {/* Log Viewer Dialog */}
      <LogViewerDialog job={logJob} open={Boolean(logJob)} onClose={handleCloseLogs} />

      {/* Cancel Confirmation Dialog */}
      <CancelJobDialog
        open={Boolean(cancelJob)}
        onClose={handleCloseCancelDialog}
        onConfirm={handleConfirmCancel}
        jobId={cancelJob?.id}
      />

      {/* Delete Confirmation Dialog */}
      <DeleteJobDialog
        open={Boolean(deleteJob)}
        onClose={handleCloseDeleteDialog}
        onConfirm={handleConfirmDelete}
        jobId={deleteJob?.id}
        jobType={deleteJob?.type}
      />

      <RetryJobDialog
        open={Boolean(retryJob)}
        title={retryJob ? t('backupJobsTable.confirmations.retryJob', { id: retryJob.id }) : ''}
        confirmLabel={t('backupJobsTable.actions.retry')}
        onClose={handleCloseRetryDialog}
        onConfirm={handleConfirmRetry}
      />

      {/* Archive Contents Dialog */}
      <ArchiveContentsDialog
        open={!!archiveView}
        archive={archiveView?.archive ?? null}
        repository={archiveView?.repository ?? null}
        onClose={() => setArchiveView(null)}
        onDownloadFile={(archiveName, filePath, size) => {
          if (!archiveView?.repository) return
          // Same rule as the Archives page: a Borg 2 archive is addressed by
          // id (the backend wraps it as aid:<hex>); Borg 1 names are unique.
          const archiveRef =
            isV2Repo(archiveView.repository) && archiveView.archive.id
              ? archiveView.archive.id
              : archiveName
          return downloadArchiveFile(archiveView.repository, archiveRef, filePath, {
            totalSize: size ?? undefined,
          })
        }}
      />

      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          borgVersion={lockError.borgVersion}
          canBreakLock={lockError.canBreakLock}
          lockBreakingEnabled={lockError.lockBreakingEnabled}
          onLockBroken={() => {
            setLockError(null)
            queryClient.invalidateQueries({ queryKey: ['activity'] })
            queryClient.invalidateQueries({ queryKey: ['backup-status'] })
            queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
            queryClient.invalidateQueries({ queryKey: ['backup-status-scheduled'] })
          }}
        />
      )}
    </>
  )

  return { actionButtons, dialogs }
}
