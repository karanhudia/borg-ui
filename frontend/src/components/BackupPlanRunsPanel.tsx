import React, { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Box,
  Card,
  CardContent,
  Chip,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { Clock, Eye, ListChecks, RefreshCw, RotateCcw, Square } from 'lucide-react'
import ActiveBackupPlanRunCard from './ActiveBackupPlanRunCard'
import DataTable, { type ActionButton, type Column } from './DataTable'
import RepositoryCell from './RepositoryCell'
import RetryJobDialog from './RetryJobDialog'
import StatusBadge from './StatusBadge'
import type { BackupPlan, BackupPlanRun, BackupPlanRunRepository } from '../types'
import { formatDate, formatDateTimeFull, formatTimeRange } from '../utils/dateUtils'
import {
  getBackupPlanRunRetryDisabledReason,
  shouldShowBackupPlanRunRetryAction,
} from './backupPlanRunRetry'
import {
  canViewBackupJobLogs as canViewLogs,
  canViewScriptLogs,
  type BackupPlanRunLogJob,
} from './planRunScriptLogs'

export type { BackupPlanRunLogJob } from './planRunScriptLogs'

function isActiveRun(status?: string): boolean {
  return status === 'pending' || status === 'running'
}

function isFinishedRepositoryRun(runRepository: BackupPlanRunRepository): boolean {
  return !isActiveRun(runRepository.status)
}

function getTransportLabel(
  runRepository: BackupPlanRunRepository,
  t: (key: string) => string
): string | null {
  const executionMode = runRepository.backup_job?.execution_mode
  const routeStrategy = runRepository.backup_job?.route_strategy
  if (executionMode === 'agent' || runRepository.repository?.executor_type === 'agent') {
    return t('backupPlans.runsDialog.transport.agent')
  }
  if (
    executionMode === 'remote_ssh' ||
    executionMode === 'remote_direct' ||
    routeStrategy === 'remote_direct'
  ) {
    return t('backupPlans.runsDialog.transport.remoteSsh')
  }
  if (executionMode || runRepository.repository?.executor_type === 'server') {
    return t('backupPlans.runsDialog.transport.server')
  }
  return null
}

function getRepositoryLabel(runRepository: BackupPlanRunRepository, fallback: string): string {
  return runRepository.repository?.name || runRepository.backup_job?.repository || fallback
}

function getRepositoryPath(runRepository: BackupPlanRunRepository): string {
  return runRepository.repository?.path || runRepository.backup_job?.repository || '-'
}

function getFinishedCount(run: BackupPlanRun): number {
  return run.repositories.filter(isFinishedRepositoryRun).length
}

function getRunProgress(run: BackupPlanRun): number {
  if (run.repositories.length === 0) return isActiveRun(run.status) ? 0 : 100
  return Math.round((getFinishedCount(run) / run.repositories.length) * 100)
}

function findPlan(run: BackupPlanRun, plans: BackupPlan[]): BackupPlan | null {
  return plans.find((plan) => plan.id === run.backup_plan_id) || null
}

function findFirstLogJob(run: BackupPlanRun): BackupPlanRunLogJob | null {
  const scriptExecution = run.script_executions?.find(canViewScriptLogs)
  if (scriptExecution) {
    return {
      id: scriptExecution.id,
      status: scriptExecution.status,
      type: 'script_execution',
      has_logs: scriptExecution.has_logs,
    }
  }

  const repositoryRun = run.repositories.find((candidate) => canViewLogs(candidate.backup_job))
  return repositoryRun?.backup_job ?? null
}

function getStartedAt(run: BackupPlanRun): string | null {
  return run.started_at || run.created_at || null
}

function getPrimaryRepositoryName(run: BackupPlanRun, fallback: string): string {
  const firstRepository = run.repositories[0]
  if (!firstRepository) return '-'
  return getRepositoryLabel(firstRepository, fallback)
}

function getPrimaryRepositoryPath(run: BackupPlanRun): string {
  const firstRepository = run.repositories[0]
  if (!firstRepository) return ''
  return getRepositoryPath(firstRepository)
}

function getPrimaryTransportLabel(run: BackupPlanRun, t: (key: string) => string): string | null {
  const firstRepository = run.repositories[0]
  return firstRepository ? getTransportLabel(firstRepository, t) : null
}

function getCurrentFile(run: BackupPlanRun): string | null {
  return (
    run.repositories.find(
      (runRepository) => runRepository.backup_job?.progress_details?.current_file
    )?.backup_job?.progress_details?.current_file ?? null
  )
}

export default function BackupPlanRunsPanel({
  runs,
  plans,
  loading,
  cancellingRunId,
  retryingRunId = null,
  onCancel,
  onViewLogs,
  onRetry,
  canRetryRun = () => false,
}: {
  runs: BackupPlanRun[]
  plans: BackupPlan[]
  loading?: boolean
  cancellingRunId?: number | null
  retryingRunId?: number | null
  onCancel: (runId: number) => void
  onViewLogs: (job: BackupPlanRunLogJob) => void
  onRetry?: (runId: number) => void
  canRetryRun?: (run: BackupPlanRun) => boolean
}) {
  const { t } = useTranslation()
  const [retryRun, setRetryRun] = useState<BackupPlanRun | null>(null)
  const activeRuns = useMemo(() => runs.filter((run) => isActiveRun(run.status)), [runs])
  const recentRuns = useMemo(
    () => runs.filter((run) => !isActiveRun(run.status)).slice(0, 4),
    [runs]
  )
  const activePlanIds = useMemo(
    () =>
      new Set(
        activeRuns
          .map((run) => run.backup_plan_id)
          .filter((planId): planId is number => typeof planId === 'number')
      ),
    [activeRuns]
  )
  const hasActiveRunForPlan = (run: BackupPlanRun) =>
    Boolean(run.backup_plan_id && activePlanIds.has(run.backup_plan_id))
  const getRetryDisabledReason = (run: BackupPlanRun) =>
    getBackupPlanRunRetryDisabledReason(run, t, {
      canRetry: canRetryRun(run),
      hasActiveRunForPlan: hasActiveRunForPlan(run),
    })
  const getRetryTooltip = (run: BackupPlanRun) => {
    if (retryingRunId === run.id) return t('backupPlans.runsPanel.retryTooltips.retrying')
    return getRetryDisabledReason(run) || t('backupPlans.runsPanel.retryTooltips.ready')
  }
  const handleRetryRun = (run: BackupPlanRun) => {
    if (getRetryDisabledReason(run)) return
    setRetryRun(run)
  }
  const handleConfirmRetryRun = () => {
    if (!retryRun) return

    const runId = retryRun.id
    setRetryRun(null)
    onRetry?.(runId)
  }
  const handleCloseRetryDialog = () => {
    setRetryRun(null)
  }
  const getPlanName = (run: BackupPlanRun) => {
    const plan = findPlan(run, plans)
    return (
      plan?.name ||
      (run.backup_plan_id
        ? t('backupPlans.runsPanel.planFallback', { id: run.backup_plan_id })
        : t('backupPlans.runsPanel.unknownPlan'))
    )
  }
  const columns: Column<BackupPlanRun>[] = [
    {
      id: 'run',
      label: t('backupPlans.runsPanel.columns.run'),
      width: '90px',
      render: (run) => (
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="body2"
            color="primary"
            sx={{
              fontWeight: 700,
            }}
          >
            #{run.id}
          </Typography>
          <Typography
            variant="caption"
            noWrap
            component="div"
            sx={{
              color: 'text.secondary',
            }}
          >
            {run.trigger}
          </Typography>
        </Box>
      ),
    },
    {
      id: 'plan',
      label: t('backupPlans.runsPanel.columns.plan'),
      minWidth: '280px',
      mobileFullWidth: true,
      render: (run) => (
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="body2"
            noWrap
            sx={{
              fontWeight: 700,
            }}
          >
            {getPlanName(run)}
          </Typography>
          <RepositoryCell
            repositoryName={getPrimaryRepositoryName(
              run,
              t('backupPlans.status.repositoryFallback')
            )}
            repositoryPath={getPrimaryRepositoryPath(run)}
            withIcon={false}
          />
          {getPrimaryTransportLabel(run, t) && (
            <Chip
              size="small"
              variant="outlined"
              label={getPrimaryTransportLabel(run, t)}
              sx={{ mt: 0.5 }}
            />
          )}
          <Typography
            variant="caption"
            component="div"
            sx={{
              color: 'text.secondary',
            }}
          >
            {t('backupPlans.runsPanel.repositoryProgress', {
              completed: getFinishedCount(run),
              total: run.repositories.length,
            })}
          </Typography>
          {getCurrentFile(run) && (
            <Typography
              variant="caption"
              component="div"
              sx={{
                color: 'text.secondary',
                fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {getCurrentFile(run)}
            </Typography>
          )}
        </Box>
      ),
    },
    {
      id: 'status',
      label: t('backupPlans.runsPanel.columns.status'),
      width: '160px',
      render: (run) => (
        <Stack spacing={0.75}>
          <StatusBadge
            status={run.status}
            tooltip={
              run.skip_reason === 'minimum_interval_not_elapsed'
                ? t('availabilitySchedule.skipReasons.minimumIntervalNotElapsed')
                : run.skip_reason === 'source_unavailable'
                  ? t('availabilitySchedule.skipReasons.sourceUnavailable')
                  : undefined
            }
          />
          {isActiveRun(run.status) && (
            <LinearProgress
              variant={getRunProgress(run) === 0 ? 'indeterminate' : 'determinate'}
              value={getRunProgress(run)}
              sx={{ maxWidth: 112 }}
            />
          )}
        </Stack>
      ),
    },
    {
      id: 'started',
      label: t('backupPlans.runsPanel.columns.started'),
      width: '160px',
      render: (run) => (
        <Tooltip
          title={getStartedAt(run) ? formatDateTimeFull(getStartedAt(run) as string) : ''}
          arrow
        >
          <Typography
            variant="body2"
            sx={{
              color: 'text.secondary',
              cursor: getStartedAt(run) ? 'help' : 'default',
              display: 'inline-block',
            }}
          >
            {getStartedAt(run) ? formatDate(getStartedAt(run) as string) : '-'}
          </Typography>
        </Tooltip>
      ),
    },
    {
      id: 'duration',
      label: t('backupPlans.runsPanel.columns.duration'),
      width: '140px',
      render: (run) => (
        <Typography
          variant="body2"
          noWrap
          sx={{
            color: 'text.secondary',
          }}
        >
          {formatTimeRange(run.started_at, run.completed_at, run.status)}
        </Typography>
      ),
    },
  ]

  const actions: ActionButton<BackupPlanRun>[] = [
    {
      icon: <Eye size={16} />,
      label: t('backupPlans.runsDialog.viewLogs'),
      tooltip: t('backupPlans.runsDialog.viewLogs'),
      onClick: (run) => {
        const logJob = findFirstLogJob(run)
        if (logJob) onViewLogs(logJob)
      },
      show: (run) => Boolean(findFirstLogJob(run)),
    },
    ...(onRetry
      ? [
          {
            icon: <RotateCcw size={16} />,
            label: t('backupPlans.runsPanel.retryRun'),
            tooltip: getRetryTooltip,
            color: 'info' as const,
            onClick: handleRetryRun,
            disabled: (run: BackupPlanRun) =>
              retryingRunId === run.id || Boolean(getRetryDisabledReason(run)),
            show: shouldShowBackupPlanRunRetryAction,
          },
        ]
      : []),
    {
      icon: <Square size={16} />,
      label: t('backupPlans.runsPanel.cancelRun'),
      tooltip: t('backupPlans.runsPanel.cancelRun'),
      color: 'warning',
      onClick: (run) => onCancel(run.id),
      disabled: (run) => cancellingRunId === run.id,
      show: (run) => isActiveRun(run.status),
    },
  ]

  const renderRunSection = (
    title: string,
    subtitle: string,
    icon: React.ReactNode,
    tableRuns: BackupPlanRun[],
    tableId: string,
    sectionId: string,
    emptyTitle: string,
    countChip?: React.ReactNode
  ) => (
    <Card component="section" aria-labelledby={sectionId}>
      <CardContent>
        <Stack
          direction="row"
          spacing={1.5}
          sx={{
            alignItems: 'center',
            mb: 1,
            color: 'text.secondary',
          }}
        >
          <Box
            sx={{
              display: 'flex',
              color: tableRuns.some((run) => isActiveRun(run.status))
                ? 'success.main'
                : 'text.secondary',
            }}
          >
            {icon}
          </Box>
          <Typography
            id={sectionId}
            variant="h6"
            sx={{
              fontWeight: 600,
            }}
          >
            {title}
          </Typography>
          {countChip}
        </Stack>
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
            mb: 3,
          }}
        >
          {subtitle}
        </Typography>

        <DataTable
          data={tableRuns}
          columns={columns}
          actions={actions}
          loading={loading}
          getRowKey={(run) => run.id}
          tableId={tableId}
          defaultRowsPerPage={5}
          rowsPerPageOptions={[5, 10, 25]}
          actionColumnWidth="120px"
          borderRadius={2}
          headerBgColor="background.default"
          emptyState={{
            icon: (
              <Box sx={{ color: 'text.disabled' }}>
                <ListChecks size={48} />
              </Box>
            ),
            title: emptyTitle,
          }}
        />
      </CardContent>
    </Card>
  )

  return (
    <Stack spacing={3} sx={{ mb: 4 }}>
      {activeRuns.length > 0 && (
        <Box component="section" aria-labelledby="backup-plan-active-runs-heading">
          <Stack
            direction="row"
            spacing={1.5}
            sx={{
              alignItems: 'center',
              mb: 1,
              color: 'text.secondary',
            }}
          >
            <Box sx={{ display: 'flex', color: 'success.main' }}>
              <RefreshCw size={20} className="animate-spin" />
            </Box>
            <Typography
              id="backup-plan-active-runs-heading"
              variant="h6"
              sx={{
                fontWeight: 600,
              }}
            >
              {t('backupPlans.runsPanel.activeTitle')}
            </Typography>
            <Chip
              size="small"
              color="primary"
              label={t('backupPlans.runsPanel.activeCount', { count: activeRuns.length })}
            />
          </Stack>
          <Typography
            variant="body2"
            sx={{
              color: 'text.secondary',
              mb: 2.5,
            }}
          >
            {t('backupPlans.runsPanel.activeSubtitle')}
          </Typography>

          <Stack spacing={2}>
            {activeRuns.map((run) => (
              <ActiveBackupPlanRunCard
                key={run.id}
                run={run}
                plan={findPlan(run, plans)}
                cancelling={cancellingRunId === run.id}
                onCancel={onCancel}
                onViewLogs={onViewLogs}
              />
            ))}
          </Stack>
        </Box>
      )}

      {renderRunSection(
        t('backupPlans.runsPanel.recentTitle'),
        t('backupPlans.runsPanel.recentSubtitle'),
        <Clock size={20} />,
        recentRuns,
        'backup-plan-recent-runs',
        'backup-plan-recent-runs-heading',
        runs.length === 0
          ? t('backupPlans.runsPanel.empty')
          : t('backupPlans.runsPanel.emptyRecent')
      )}
      <RetryJobDialog
        open={Boolean(retryRun)}
        title={retryRun ? t('backupPlans.runsPanel.retryConfirm', { id: retryRun.id }) : ''}
        confirmLabel={t('backupPlans.runsPanel.retryRun')}
        onClose={handleCloseRetryDialog}
        onConfirm={handleConfirmRetryRun}
      />
    </Stack>
  )
}
