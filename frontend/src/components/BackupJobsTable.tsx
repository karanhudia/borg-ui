import React, { useState } from 'react'
import { Box, Typography, Chip, Tooltip } from '@mui/material'
import { Eye, Download, Trash2, Lock, Play, AlertCircle, Clock, Calendar, User } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useQueryClient } from '@tanstack/react-query'
import DataTable, { Column, ActionButton } from './DataTable'
import StatusBadge from './StatusBadge'
import RepositoryCell from './RepositoryCell'
import { formatDate, formatTimeRange } from '../utils/dateUtils'
import { Job, Repository } from '../types/jobs'
import ErrorDetailsDialog from './ErrorDetailsDialog'
import LogViewerDialog from './LogViewerDialog'
import CancelJobDialog from './CancelJobDialog'
import DeleteJobDialog from './DeleteJobDialog'

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
  isAdmin?: boolean

  // Table styling
  headerBgColor?: string
  enableHover?: boolean
  getRowKey?: (job: T) => string | number
}

const getTypeLabel = (type: string): string => {
  switch (type) {
    case 'backup':
      return 'Backup'
    case 'restore':
      return 'Restore'
    case 'check':
      return 'Repository Check'
    case 'compact':
      return 'Compact'
    case 'prune':
      return 'Prune'
    case 'package':
      return 'Package Install'
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
  isAdmin = false,
  headerBgColor = 'background.default',
  enableHover = true,
  getRowKey,
}: BackupJobsTableProps<T>) => {
  const queryClient = useQueryClient()

  // Internal state for dialogs
  const [errorJob, setErrorJob] = useState<T | null>(null)
  const [logJob, setLogJob] = useState<T | null>(null)
  const [cancelJob, setCancelJob] = useState<T | null>(null)
  const [deleteJob, setDeleteJob] = useState<T | null>(null)

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
      const token = localStorage.getItem('access_token')
      if (!token) {
        toast.error('Authentication required')
        return
      }

      const url = `/api/activity/${jobType}/${job.id}/logs/download?token=${token}`
      const a = document.createElement('a')
      a.href = url
      a.download = `${jobType}-${job.id}-logs.txt`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      toast.success('Downloading logs...')
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
      const response = await fetch(`/api/activity/${jobType}/${cancelJob.id}/cancel`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
      })

      if (!response.ok) {
        throw new Error('Failed to cancel job')
      }

      toast.success('Job cancelled successfully')
      setCancelJob(null)
    } catch (error) {
      toast.error('Failed to cancel job')
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
        queryClient.setQueryData(queryKey, (old: any) => {
          if (!old) return old
          // Handle different data structures
          if (Array.isArray(old)) {
            return old.filter((job: any) => job.id !== jobToDelete.id)
          }
          if (old.jobs && Array.isArray(old.jobs)) {
            return { ...old, jobs: old.jobs.filter((job: any) => job.id !== jobToDelete.id) }
          }
          return old
        })
      }
      return { queryKey, data: previous }
    })

    try {
      // Call delete API
      const response = await fetch(`/api/activity/${jobType}/${jobToDelete.id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
        },
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Failed to delete job' }))
        throw new Error(errorData.detail || 'Failed to delete job')
      }

      // Success - show toast after item is already removed from UI
      toast.success('Job deleted successfully')
    } catch (error) {
      // Rollback optimistic updates on error
      previousData.forEach(({ queryKey, data }) => {
        if (data !== undefined) {
          queryClient.setQueryData(queryKey, data)
        }
      })

      toast.error(error instanceof Error ? error.message : 'Failed to delete job')
      console.error(error)
    }
  }

  const handleCloseDeleteDialog = () => {
    setDeleteJob(null)
  }

  // Build columns array based on options
  const columns: Column<T>[] = [
    {
      id: 'id',
      label: 'Job ID',
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
      label: 'Repository',
      align: 'left',
      minWidth: '250px',
      width: '30%',
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
            label: 'Type',
            align: 'left' as const,
            width: '140px',
            render: (job: T) => (
              <Chip
                label={getTypeLabel(job.type || '')}
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
            label: 'Trigger',
            align: 'center' as const,
            width: '90px',
            render: (job: T) => {
              const isScheduled = job.triggered_by === 'schedule'
              return (
                <Tooltip
                  title={isScheduled ? `Scheduled (ID: ${job.schedule_id || 'N/A'})` : 'Manual'}
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
      label: 'Status',
      align: 'left',
      width: '100px',
      render: (job: T) => <StatusBadge status={job.status} />,
    },
    {
      id: 'started_at',
      label: 'Started',
      align: 'left',
      width: '180px',
      render: (job: T) => (
        <Typography variant="body2" color="text.secondary">
          {job.started_at ? formatDate(job.started_at) : '-'}
        </Typography>
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      align: 'left',
      width: '90px',
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
      label: 'View Logs',
      onClick: handleViewLogsClick,
      color: 'primary',
      tooltip: 'View Logs',
      show: (job) => {
        // Show logs button only when logs exist
        // Check has_logs flag or log_file_path, and status is not pending
        return (job.has_logs === true || !!job.log_file_path) && job.status !== 'pending'
      },
    })
  }

  if (actions.downloadLogs !== false) {
    actionButtons.push({
      icon: <Download size={18} />,
      label: 'Download Logs',
      onClick: handleDownloadLogsClick,
      color: 'info',
      tooltip: 'Download Logs',
      show: (job) => {
        // Show download button only when logs exist
        // Check has_logs flag or log_file_path, and status is not pending
        return (job.has_logs === true || !!job.log_file_path) && job.status !== 'pending'
      },
    })
  }

  if (actions.errorInfo !== false) {
    actionButtons.push({
      icon: <AlertCircle size={18} />,
      label: 'Error Details',
      onClick: handleErrorClick,
      color: 'error',
      tooltip: 'View Error',
      show: (job) => job.status === 'failed' && !!job.error_message,
    })
  }

  if (actions.cancel !== false) {
    actionButtons.push({
      icon: <Trash2 size={18} />,
      label: 'Cancel',
      onClick: handleCancelClick,
      color: 'warning',
      tooltip: 'Cancel Job',
      show: (job) => job.status === 'running',
    })
  }

  if (actions.breakLock !== false && onBreakLock) {
    actionButtons.push({
      icon: <Lock size={18} />,
      label: 'Break Lock',
      onClick: onBreakLock,
      color: 'warning',
      tooltip: 'Break Lock',
      show: (job) => job.status === 'running',
    })
  }

  if (actions.runNow !== false && onRunNow) {
    actionButtons.push({
      icon: <Play size={18} />,
      label: 'Run Now',
      onClick: onRunNow,
      color: 'success',
      tooltip: 'Run Now',
      show: (job) => job.status !== 'running',
    })
  }

  if (actions.delete !== false && isAdmin) {
    actionButtons.push({
      icon: <Trash2 size={18} />,
      label: 'Delete',
      onClick: handleDeleteClick,
      color: 'error',
      tooltip: 'Delete Job (Admin Only)',
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
    title: 'No jobs found',
    description: 'No backup jobs to display',
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
        pagination={true}
        defaultRowsPerPage={10}
        rowsPerPageOptions={[5, 10, 25, 50, 100]}
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
    </>
  )
}

export default BackupJobsTable
