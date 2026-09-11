import React from 'react'
import { useTranslation } from 'react-i18next'
import { Box, Typography, Chip, Tooltip, Stack } from '@mui/material'
import { Play, Clock, Calendar, User } from 'lucide-react'
import DataTable, { Column } from './DataTable'
import StatusBadge from './StatusBadge'
import RepositoryCell from './RepositoryCell'
import { formatDate, formatDateTimeFull, formatTimeRange } from '../utils/dateUtils'
import { Job } from '../types/jobs'
import RunChainRow, { type RunChainOperation } from './activity/RunChainRow'
import { useJobActions, type JobActionsOptions } from './jobs/useJobActions'
import { getSkipReasonLabel, getTransportLabel, getTypeColor, getTypeLabel } from './jobs/jobLabels'

function jobToRunChainOperation(job: Job): RunChainOperation {
  return {
    id: job.id,
    kind: job.kind ?? job.type ?? '',
    type: job.type,
    hook_type: job.hook_type,
    name: job.package_name,
    status: job.status,
    trigger: job.trigger,
    depends_on_id: job.depends_on_id,
    started_at: job.started_at,
    completed_at: job.completed_at,
    progress_current: job.progress_current,
    progress_total: job.progress_total,
    followups: (job.followups ?? []).map(jobToRunChainOperation),
  }
}

interface EmptyState {
  icon?: React.ReactNode
  title?: string
  description?: string
}

interface BackupJobsTableProps<T extends Job = Job> extends JobActionsOptions<T> {
  // Data
  jobs: T[]

  // Display options
  showTypeColumn?: boolean
  showTriggerColumn?: boolean

  // State
  loading?: boolean
  emptyState?: EmptyState

  // Table styling
  headerBgColor?: string
  enableHover?: boolean
  getRowKey?: (job: T) => string | number

  // Pagination
  tableId?: string // Unique identifier for localStorage persistence
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
  const { t } = useTranslation()
  const { actionButtons, dialogs } = useJobActions<T>({
    repositories,
    actions,
    onViewLogs,
    onDownloadLogs,
    onErrorDetails,
    onCancelJob,
    onBreakLock,
    onRunNow,
    onDeleteJob,
    onRetryJob,
    canBreakLocks,
    lockBreakingEnabled,
    canDeleteJobs,
    canRetryJob,
    retryingJobId,
  })

  // Build columns array based on options
  const columns: Column<T>[] = [
    {
      id: 'id',
      label: t('backupJobsTable.columns.jobId'),
      align: 'left',
      width: '80px',
      render: (job: T) => (
        <Typography
          variant="body2"
          color="primary"
          sx={{
            fontWeight: 600,
          }}
        >
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

        if (job.type === 'availability_check') {
          return <Typography variant="body2">{job.repository || '-'}</Typography>
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
        const skipReasonLabel = getSkipReasonLabel(job, t)
        return (
          <Stack
            direction="row"
            spacing={0.75}
            useFlexGap
            sx={{
              alignItems: 'center',
              flexWrap: 'wrap',
            }}
          >
            <StatusBadge status={job.status} tooltip={skipReasonLabel || undefined} />
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
            sx={{
              color: 'text.secondary',
              cursor: job.started_at ? 'help' : 'default',
              display: 'inline-block',
            }}
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
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
          }}
        >
          {formatTimeRange(job.started_at, job.completed_at, job.status)}
        </Typography>
      ),
    },
  ]

  // Build actions array
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
        subRowIndent={1}
        renderSubRow={(job) => {
          const followups = (job as Job).followups
          if (!followups || followups.length === 0) return null
          return <RunChainRow operation={jobToRunChainOperation(job as Job)} />
        }}
        loading={loading}
        headerBgColor={headerBgColor}
        enableHover={enableHover}
        enablePointer={false}
        emptyState={finalEmptyState}
        defaultRowsPerPage={10}
        rowsPerPageOptions={[5, 10, 25, 50, 100]}
        tableId={tableId}
      />
      {dialogs}
    </>
  )
}

export default BackupJobsTable
