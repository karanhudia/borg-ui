import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Typography, Chip, Tooltip, Stack } from '@mui/material'
import {
  Eye,
  Download,
  Trash2,
  Lock,
  Play,
  AlertCircle,
  Clock,
  Calendar,
  User,
  FolderOpen,
  RotateCcw,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import DataTable, { Column, ActionButton } from './DataTable'
import StatusBadge from './StatusBadge'
import RepositoryCell from './RepositoryCell'
import { formatDate, formatDateTimeFull, formatTimeRange } from '../utils/dateUtils'
import { Job, Repository } from '../types/jobs'
import ErrorDetailsDialog from './ErrorDetailsDialog'
import LogViewerDialog from './LogViewerDialog'
import CancelJobDialog from './CancelJobDialog'
import DeleteJobDialog from './DeleteJobDialog'
import RetryJobDialog from './RetryJobDialog'
import LockErrorDialog from './LockErrorDialog'
import { activityAPI, repositoriesAPI } from '../services/api'
import { buildDownloadUrl } from '@/utils/downloadUrl'
import { downloadArchiveFile } from '../utils/downloadArchiveFile'
import ArchiveContentsDialog from './ArchiveContentsDialog'
import type { Repository as FullRepository, Archive } from '../types'

interface EmptyState {
  icon?: React.ReactNode
  title?: string
  description?: string
}

type CanBreakLocks<T extends Job> = boolean | ((job: T) => boolean)

interface BackupJobsTableProps<T extends Job = Job> {
  // Data
  jobs: T[]

  // Display options
  showTypeColumn?: boolean
  showTriggerColumn?: boolean
  repositories?: Repository[]

  // State
  loading?: boolean
  emptyState?: EmptyState

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

  // Table styling
  headerBgColor?: string
  enableHover?: boolean
  getRowKey?: (job: T) => string | number

  // Pagination
  tableId?: string // Unique identifier for localStorage persistence
}

const getTypeLabel = (type: string, t: (key: string) => string): string => {
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
    default:
      return type
  }
}

const getTypeColor = (
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
    default:
      return 'default'
  }
}

const getTransportLabel = (
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

const RETRYABLE_BACKUP_JOB_STATUSES = new Set(['failed', 'cancelled'])
const DESTRUCTIVE_JOB_TYPES = new Set([
  'delete_archive',
  'archive_delete',
  'repository_wipe',
  'wipe',
  'prune',
])

const isManualBackupRetrySource = (job: Job): boolean => {
  const jobType = job.type || 'backup'
  if (jobType !== 'backup') return false
  if (job.backup_plan_id || job.backup_plan_run_id) return false
  if (job.scheduled_job_id || job.schedule_id) return false
  if (job.triggered_by === 'backup_plan' || job.triggered_by === 'schedule') return false
  return true
}

const hasBackupRetryRepositoryContext = (job: Job): boolean =>
  Boolean(job.repository_id || job.repository || job.repository_path)

const shouldShowRetryAction = (job: Job): boolean => {
  if (!RETRYABLE_BACKUP_JOB_STATUSES.has(job.status)) return false
  return isManualBackupRetrySource(job) || Boolean(job.type)
}

const getBackupJobRetryDisabledReason = (
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

export const BackupJobsTable = <T extends Job = Job>({
  jobs,
  showTypeColumn = false,
  showTriggerColumn = false,
  repositories = [],
  loading = false,
  emptyState,
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
  headerBgColor = 'background.default',
  enableHover = true,
  getRowKey,
  tableId,
}: BackupJobsTableProps<T>) => {
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

  const handleConfirmDelete = async () => {
    if (!deleteJob) return

    const jobToDelete = deleteJob
    const jobType = jobToDelete.type || 'backup'

    // Close dialog immediately for better UX
    setDeleteJob(null)

    // Store previous data for rollback on error
    const queryKeys = [
      ['backup-status-manual'],
      ['backup-status-scheduled'],
      ['backup-status'],
      ['activity'],
      ['recent-backup-jobs'],
    ]

    // Optimistically update all query caches by removing the deleted job
    const previousData = queryKeys.map((queryKey) => {
      const previous = queryClient.getQueryData(queryKey)
      if (previous) {
        queryClient.setQueryData(queryKey, (old: unknown) => {
          if (!old) return old
          // Handle different data structures
          if (Array.isArray(old)) {
            return old.filter((job) => (job as T).id !== jobToDelete.id)
          }
          if (typeof old === 'object' && old !== null && 'jobs' in old) {
            const oldData = old as { jobs: T[] }
            if (Array.isArray(oldData.jobs)) {
              return { ...oldData, jobs: oldData.jobs.filter((job) => job.id !== jobToDelete.id) }
            }
          }
          return old
        })
      }
      return { queryKey, data: previous }
    })

    try {
      // Call delete API
      await activityAPI.deleteJob(jobType, jobToDelete.id)

      // Success - show toast after item is already removed from UI
      toast.success(t('backupJobsTable.toasts.deleteSuccess'))
    } catch (error) {
      // Rollback optimistic updates on error
      previousData.forEach(({ queryKey, data }) => {
        if (data !== undefined) {
          queryClient.setQueryData(queryKey, data)
        }
      })

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

  // Build columns array based on options
  const columns: Column<T>[] = [
    {
      id: 'id',
      label: t('backupJobsTable.columns.jobId'),
      align: 'left',
      width: '80px',
      render: (job: T) => (
        <Typography variant="body2" fontWeight={600} color="primary">
          #{job.id}
        </Typography>
      ),
    },
    {
      id: 'repository',
      label: t('backupJobsTable.columns.repository'),
      align: 'left',
      width: '250px',
      mobileFullWidth: true,
      render: (job: T) => {
        // Handle Activity items with different repository field names
        if (job.type && job.type === 'script_execution') {
          const displayName = job.package_name || job.archive_name || '-'
          return <Typography variant="body2">{displayName}</Typography>
        }

        if (job.type && job.type === 'package') {
          const displayName = job.archive_name || job.package_name || '-'
          return <Typography variant="body2">{displayName}</Typography>
        }

        // For backup/restore/check/compact in Activity tab
        if (job.repository_path) {
          return (
            <RepositoryCell
              repositoryName={job.repository || job.repository_path}
              repositoryPath={job.repository_path}
              withIcon={false}
            />
          )
        }

        // Standard backup job handling
        const repo = repositories?.find((r) => r.path === job.repository)
        return (
          <RepositoryCell
            repositoryName={repo?.name || job.repository}
            repositoryPath={job.repository}
            withIcon={false}
          />
        )
      },
    },
    // Type column - conditionally included
    ...(showTypeColumn
      ? [
          {
            id: 'type',
            label: t('backupJobsTable.columns.type'),
            align: 'left' as const,
            width: '120px',
            render: (job: T) => (
              <Chip
                label={getTypeLabel(job.type || '', t)}
                color={getTypeColor(job.type || '')}
                size="small"
                variant="outlined"
                sx={{
                  maxWidth: '100%',
                  '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis' },
                }}
              />
            ),
          },
        ]
      : []),
    // Trigger column - conditionally included
    ...(showTriggerColumn
      ? [
          {
            id: 'trigger',
            label: t('backupJobsTable.columns.trigger'),
            align: 'center' as const,
            width: '70px',
            render: (job: T) => {
              const isScheduled = job.triggered_by === 'schedule'
              const isBackupPlan = job.triggered_by === 'backup_plan' || Boolean(job.backup_plan_id)
              const title = isBackupPlan
                ? t('backupJobsTable.backupPlanByName', {
                    name: job.backup_plan_name || `#${job.backup_plan_id || 'N/A'}`,
                  })
                : isScheduled
                  ? t('backupJobsTable.scheduledById', { id: job.schedule_id || 'N/A' })
                  : t('backupJobsTable.manual')
              return (
                <Tooltip title={title} placement="top" arrow>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    {isBackupPlan ? (
                      <Play size={18} color="#059669" />
                    ) : isScheduled ? (
                      <Calendar size={18} color="#1976d2" />
                    ) : (
                      <User size={18} color="#666" />
                    )}
                  </Box>
                </Tooltip>
              )
            },
          },
        ]
      : []),
    {
      id: 'status',
      label: t('backupJobsTable.columns.status'),
      align: 'left',
      width: '180px',
      render: (job: T) => {
        const transportLabel = getTransportLabel(job.execution_mode, job.route_strategy, t)
        return (
          <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
            <StatusBadge status={job.status} />
            {transportLabel && <Chip size="small" variant="outlined" label={transportLabel} />}
          </Stack>
        )
      },
    },
    {
      id: 'started_at',
      label: t('backupJobsTable.columns.started'),
      align: 'left',
      width: '160px',
      render: (job: T) => (
        <Tooltip title={job.started_at ? formatDateTimeFull(job.started_at) : ''} arrow>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ cursor: job.started_at ? 'help' : 'default', display: 'inline-block' }}
          >
            {job.started_at ? formatDate(job.started_at) : '-'}
          </Typography>
        </Tooltip>
      ),
    },
    {
      id: 'duration',
      label: t('backupJobsTable.columns.duration'),
      align: 'left',
      width: '110px',
      render: (job: T) => (
        <Typography variant="body2" color="text.secondary">
          {formatTimeRange(job.started_at, job.completed_at, job.status)}
        </Typography>
      ),
    },
  ]

  // Build actions array
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
    actionButtons.push({
      icon: <FolderOpen size={18} />,
      label: t('backupJobsTable.actions.viewArchive'),
      onClick: (job) => {
        if (!job.archive_name) return
        // Find repository from available data
        const allRepos = repositoriesData?.data?.repositories || repositories || []
        const repoPath = job.repository_path || job.repository
        const repo = allRepos.find(
          (r: FullRepository) => r.path === repoPath || r.name === repoPath
        ) as FullRepository | undefined
        if (!repo) {
          toast.error(t('backupJobsTable.toasts.repositoryNotFound'))
          return
        }
        setArchiveView({
          archive: {
            id: job.archive_name,
            archive: job.archive_name,
            name: job.archive_name,
            start: job.started_at || '',
            time: job.started_at || '',
          },
          repository: repo,
        })
      },
      color: 'success',
      tooltip: t('backupJobsTable.actions.viewArchive'),
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
      show: (job) => job.status !== 'running',
    })
  }

  if (actions.delete !== false && canDeleteJobs) {
    actionButtons.push({
      icon: <Trash2 size={18} />,
      label: t('backupJobsTable.actions.delete'),
      onClick: handleDeleteClick,
      color: 'error',
      tooltip: t('backupJobsTable.actions.delete'),
      show: (job) => job.status !== 'running', // Allow deleting pending jobs (useful for stuck jobs)
    })
  }

  // Build default emptyState
  const defaultEmptyState: EmptyState = {
    icon: (
      <Box sx={{ color: 'text.disabled' }}>
        <Clock size={48} />
      </Box>
    ),
    title: t('backupJobsTable.empty'),
    description: t('backupJobsTable.empty'),
  }

  const finalEmptyState: { icon: React.ReactNode; title: string; description?: string } = emptyState
    ? {
        icon: emptyState.icon || defaultEmptyState.icon!,
        title: emptyState.title || defaultEmptyState.title!,
        description: emptyState.description || defaultEmptyState.description,
      }
    : {
        icon: defaultEmptyState.icon!,
        title: defaultEmptyState.title!,
        description: defaultEmptyState.description,
      }

  return (
    <>
      <DataTable
        data={jobs}
        columns={columns}
        actions={actionButtons}
        actionColumnWidth={
          actionButtons.length > 0 ? `${Math.max(130, actionButtons.length * 34)}px` : undefined
        }
        getRowKey={getRowKey || ((job: T) => String((job as Job).id))}
        loading={loading}
        headerBgColor={headerBgColor}
        enableHover={enableHover}
        enablePointer={false}
        emptyState={finalEmptyState}
        defaultRowsPerPage={10}
        rowsPerPageOptions={[5, 10, 25, 50, 100]}
        tableId={tableId}
      />

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
          return downloadArchiveFile(archiveView.repository, archiveName, filePath, {
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
}

export default BackupJobsTable
