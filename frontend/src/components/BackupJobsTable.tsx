import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Typography, Chip, Tooltip } from '@mui/material'
import { Eye, Download, Trash2, Lock, Play, AlertCircle, Clock, Calendar, User } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useQueryClient, useQuery } from '@tanstack/react-query'
import DataTable, { Column, ActionButton } from './DataTable'
import StatusBadge from './StatusBadge'
import RepositoryCell from './RepositoryCell'
import { formatDate, formatTimeRange } from '../utils/dateUtils'
import { Job, Repository } from '../types/jobs'
import ErrorDetailsDialog from './ErrorDetailsDialog'
import LogViewerDialog from './LogViewerDialog'
import CancelJobDialog from './CancelJobDialog'
import DeleteJobDialog from './DeleteJobDialog'
import LockErrorDialog from './LockErrorDialog'
import { repositoriesAPI } from '../services/api'
import { BASE_PATH } from '@/utils/basePath'
import { buildDownloadUrl } from '@/utils/downloadUrl'

interface EmptyState {
  icon?: React.ReactNode
  title?: string
  description?: string
}

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
    downloadLogs?: boolean
    cancel?: boolean
    errorInfo?: boolean
    breakLock?: boolean
    runNow?: boolean
    delete?: boolean
  }

  // Callbacks
  onViewLogs?: (job: T) => void
  onDownloadLogs?: (job: T) => void
  onErrorDetails?: (job: T) => void
  onCancelJob?: (job: T) => void | Promise<void>
  onBreakLock?: (job: T) => void | Promise<void>
  onRunNow?: (job: T) => void
  onDeleteJob?: (job: T) => void | Promise<void>

  // User permissions
  canBreakLocks?: boolean
  canDeleteJobs?: boolean

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
    case 'check':
      return t('backupJobsTable.types.check')
    case 'compact':
      return t('backupJobsTable.types.compact')
    case 'prune':
      return t('backupJobsTable.types.prune')
    case 'package':
      return t('backupJobsTable.types.package')
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
    case 'check':
      return 'info'
    case 'compact':
      return 'warning'
    case 'prune':
      return 'warning'
    case 'package':
      return 'success'
    default:
      return 'default'
  }
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
  canBreakLocks = false,
  canDeleteJobs = false,
  headerBgColor = 'background.default',
  enableHover = true,
  getRowKey,
  tableId,
}: BackupJobsTableProps<T>) => {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  // Fetch repositories (needed for break lock)
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.list,
    enabled: actions.breakLock !== false, // Only fetch if break lock action is enabled
  })

  // Internal state for dialogs
  const [errorJob, setErrorJob] = useState<T | null>(null)
  const [logJob, setLogJob] = useState<T | null>(null)
  const [cancelJob, setCancelJob] = useState<T | null>(null)
  const [deleteJob, setDeleteJob] = useState<T | null>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
    borgVersion?: 1 | 2
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
      const response = await fetch(`${BASE_PATH}/api/activity/${jobType}/${cancelJob.id}/cancel`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
      })

      if (!response.ok) {
        throw new Error(t('backupJobsTable.toasts.failedToCancel'))
      }

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
      const response = await fetch(`${BASE_PATH}/api/activity/${jobType}/${jobToDelete.id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
      })

      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ detail: t('backupJobsTable.toasts.failedToDelete') }))
        throw new Error(errorData.detail || t('backupJobsTable.toasts.failedToDelete'))
      }

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
      })
    }
  }

  // Build columns array based on options
  const columns: Column<T>[] = [
    {
      id: 'id',
      label: t('backupJobsTable.columns.jobId'),
      align: 'left',
      width: '60px',
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
      render: (job: T) => {
        // Handle Activity items with different repository field names
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
              return (
                <Tooltip
                  title={
                    isScheduled
                      ? t('backupJobsTable.scheduledById', { id: job.schedule_id || 'N/A' })
                      : t('backupJobsTable.manual')
                  }
                  placement="top"
                  arrow
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {isScheduled ? (
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
      render: (job: T) => <StatusBadge status={job.status} />,
    },
    {
      id: 'started_at',
      label: t('backupJobsTable.columns.started'),
      align: 'left',
      width: '160px',
      render: (job: T) => (
        <Typography variant="body2" color="text.secondary">
          {job.started_at ? formatDate(job.started_at) : '-'}
        </Typography>
      ),
    },
    {
      id: 'duration',
      label: t('backupJobsTable.columns.duration'),
      align: 'left',
      width: '80px',
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

  if (actions.breakLock !== false && canBreakLocks) {
    actionButtons.push({
      icon: <Lock size={18} />,
      label: t('backupJobsTable.actions.breakLock'),
      onClick: handleBreakLockClick,
      color: 'warning',
      tooltip: t('backupJobsTable.actions.breakLock'),
      show: (job) => job.status === 'failed' && !!job.error_message?.includes('LOCK_ERROR::'),
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

      {/* Lock Error Dialog */}
      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          borgVersion={lockError.borgVersion}
          canBreakLock={canBreakLocks}
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
