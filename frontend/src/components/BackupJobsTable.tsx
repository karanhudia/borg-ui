import React from 'react'
import { Box, Typography, Chip, Tooltip } from '@mui/material'
import { Eye, Download, Trash2, Lock, Play, AlertCircle, Clock, Calendar, User } from 'lucide-react'
import DataTable, { Column, ActionButton } from './DataTable'
import StatusBadge from './StatusBadge'
import RepositoryCell from './RepositoryCell'
import { formatDate, formatTimeRange } from '../utils/dateUtils'

interface BackupJobsTableProps {
  // Data
  jobs: any[]

  // Display options
  showTypeColumn?: boolean
  showTriggerColumn?: boolean
  repositories?: any[]

  // State
  loading?: boolean
  emptyState?: {
    icon?: React.ReactNode
    title?: string
    description?: string
  }

  // Actions configuration
  actions?: {
    viewLogs?: boolean
    downloadLogs?: boolean
    cancel?: boolean
    errorInfo?: boolean
    breakLock?: boolean
    runNow?: boolean
  }

  // Callbacks
  onViewLogs?: (job: any) => void
  onDownloadLogs?: (job: any) => void
  onErrorDetails?: (job: any) => void
  onCancelJob?: (job: any) => void
  onBreakLock?: (job: any) => void
  onRunNow?: (job: any) => void

  // Table styling
  headerBgColor?: string
  enableHover?: boolean
  getRowKey?: (job: any) => string
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

export const BackupJobsTable: React.FC<BackupJobsTableProps> = ({
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
  headerBgColor = 'background.default',
  enableHover = true,
  getRowKey,
}) => {
  // Build columns array based on options
  const columns: Column<any>[] = [
    {
      id: 'id',
      label: 'Job ID',
      align: 'left',
      width: '80px',
      render: (job: any) => (
        <Typography variant="body2" fontWeight={600} color="primary">
          #{job.id}
        </Typography>
      ),
    },
    {
      id: 'repository',
      label: 'Repository',
      align: 'left',
      minWidth: '200px',
      width: '25%',
      render: (job: any) => {
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
        const repo = repositories.find((r: any) => r.path === job.repository)
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
            render: (job: any) => (
              <Chip label={getTypeLabel(job.type)} color={getTypeColor(job.type)} size="small" />
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
            render: (job: any) => {
              const isScheduled = job.triggered_by === 'schedule'
              return (
                <Tooltip
                  title={
                    isScheduled
                      ? `Scheduled (ID: ${job.schedule_id || 'N/A'})`
                      : 'Manual'
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
      label: 'Status',
      align: 'left',
      width: '130px',
      render: (job: any) => <StatusBadge status={job.status} />,
    },
    {
      id: 'started_at',
      label: 'Started',
      align: 'left',
      width: '140px',
      render: (job: any) => (
        <Typography variant="body2" color="text.secondary">
          {job.started_at ? formatDate(job.started_at) : '-'}
        </Typography>
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      align: 'left',
      width: '110px',
      render: (job: any) => (
        <Typography variant="body2" color="text.secondary">
          {formatTimeRange(job.started_at, job.completed_at, job.status)}
        </Typography>
      ),
    },
  ]

  // Build actions array
  const actionButtons: ActionButton<any>[] = []

  if (actions.viewLogs !== false && onViewLogs) {
    actionButtons.push({
      icon: <Eye size={18} />,
      label: 'View Logs',
      onClick: onViewLogs,
      color: 'primary',
      tooltip: 'View Logs',
    })
  }

  if (actions.downloadLogs !== false && onDownloadLogs) {
    actionButtons.push({
      icon: <Download size={18} />,
      label: 'Download Logs',
      onClick: onDownloadLogs,
      color: 'info',
      tooltip: 'Download Logs',
      show: (job) => job.has_logs === true,
    })
  }

  if (actions.errorInfo !== false && onErrorDetails) {
    actionButtons.push({
      icon: <AlertCircle size={18} />,
      label: 'Error Details',
      onClick: onErrorDetails,
      color: 'error',
      tooltip: 'View Error',
      show: (job) => job.status === 'failed' && !!job.error_message,
    })
  }

  if (actions.cancel !== false && onCancelJob) {
    actionButtons.push({
      icon: <Trash2 size={18} />,
      label: 'Cancel',
      onClick: onCancelJob,
      color: 'warning',
      tooltip: 'Cancel Backup',
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

  // Build default emptyState
  const defaultEmptyState: any = {
    icon: (
      <Box sx={{ color: 'text.disabled' }}>
        <Clock size={48} />
      </Box>
    ),
    title: 'No jobs found',
    description: 'No backup jobs to display',
  }

  const finalEmptyState = emptyState
    ? {
        icon: emptyState.icon || defaultEmptyState.icon,
        title: emptyState.title || defaultEmptyState.title,
        description: emptyState.description || defaultEmptyState.description,
      }
    : defaultEmptyState

  return (
    <DataTable
      data={jobs}
      columns={columns}
      actions={actionButtons}
      getRowKey={getRowKey || ((job: any) => String(job.id))}
      loading={loading}
      headerBgColor={headerBgColor}
      enableHover={enableHover}
      enablePointer={false}
      emptyState={finalEmptyState}
    />
  )
}

export default BackupJobsTable
