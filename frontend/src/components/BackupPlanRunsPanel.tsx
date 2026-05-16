import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { Activity, Clock, Eye, FileText, ListChecks, RefreshCw, Square } from 'lucide-react'
import ActiveBackupPlanRunCard from './ActiveBackupPlanRunCard'
import DataTable, { type ActionButton, type Column } from './DataTable'
import RepositoryCell from './RepositoryCell'
import StatusBadge from './StatusBadge'
import type {
  BackupJob,
  BackupPlan,
  BackupPlanRun,
  BackupPlanRunRepository,
  BackupPlanScriptExecution,
} from '../types'
import {
  formatBytes as formatBytesUtil,
  formatDate,
  formatDateTimeFull,
  formatTimeRange,
} from '../utils/dateUtils'

function isActiveRun(status?: string): boolean {
  return status === 'pending' || status === 'running'
}

function runStatusColor(status?: string): 'default' | 'primary' | 'success' | 'warning' | 'error' {
  if (status === 'completed') return 'success'
  if (status === 'completed_with_warnings' || status === 'partial' || status === 'skipped')
    return 'warning'
  if (status === 'failed' || status === 'cancelled') return 'error'
  if (isActiveRun(status)) return 'primary'
  return 'default'
}

function formatRunStatus(status?: string): string {
  if (!status) return 'Unknown'
  return status.replace(/_/g, ' ')
}

function isFinishedRepositoryRun(runRepository: BackupPlanRunRepository): boolean {
  return !isActiveRun(runRepository.status)
}

function canViewLogs(job?: BackupJob | null): job is BackupJob {
  return Boolean(job && job.status !== 'pending' && (job.has_logs || job.status === 'running'))
}

export type BackupPlanRunLogJob =
  | BackupJob
  | {
      id: number
      status: string
      type: 'script_execution'
      has_logs?: boolean
    }

function canViewScriptLogs(execution: BackupPlanScriptExecution): boolean {
  return (
    execution.status !== 'pending' && Boolean(execution.has_logs || execution.status === 'running')
  )
}

function getRepositoryLabel(runRepository: BackupPlanRunRepository): string {
  return runRepository.repository?.name || runRepository.backup_job?.repository || 'Repository'
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

function getPrimaryRepositoryName(run: BackupPlanRun): string {
  const firstRepository = run.repositories[0]
  if (!firstRepository) return '-'
  return getRepositoryLabel(firstRepository)
}

function getPrimaryRepositoryPath(run: BackupPlanRun): string {
  const firstRepository = run.repositories[0]
  if (!firstRepository) return ''
  return getRepositoryPath(firstRepository)
}

function getCurrentFile(run: BackupPlanRun): string | null {
  return (
    run.repositories.find(
      (runRepository) => runRepository.backup_job?.progress_details?.current_file
    )?.backup_job?.progress_details?.current_file ?? null
  )
}

function RepositoryRunRow({
  runRepository,
  onViewLogs,
}: {
  runRepository: BackupPlanRunRepository
  onViewLogs: (job: BackupPlanRunLogJob) => void
}) {
  const { t } = useTranslation()
  const job = runRepository.backup_job
  const progress = job?.progress ?? 0
  const progressDetails = job?.progress_details
  const maintenanceStatus = job?.maintenance_status
  const statusLabel = t(`backupPlans.statuses.${runRepository.status}`, {
    defaultValue: formatRunStatus(runRepository.status),
  })

  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        p: 1.5,
        bgcolor: 'background.paper',
      }}
    >
      <Stack spacing={1.25}>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          justifyContent="space-between"
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2">{getRepositoryLabel(runRepository)}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap component="div">
              {getRepositoryPath(runRepository)}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Chip size="small" label={statusLabel} color={runStatusColor(runRepository.status)} />
            {job && (
              <Typography variant="caption" color="text.secondary">
                {t('backupPlans.runsDialog.jobNumber', { id: job.id })}
              </Typography>
            )}
            {maintenanceStatus && (
              <Chip
                size="small"
                variant="outlined"
                color={maintenanceStatus.includes('failed') ? 'warning' : 'default'}
                label={t('backupPlans.runsDialog.maintenanceStatus', {
                  status: t(`backupPlans.statuses.${maintenanceStatus}`, {
                    defaultValue: formatRunStatus(maintenanceStatus),
                  }),
                })}
              />
            )}
          </Stack>
        </Stack>

        {job?.status === 'running' && (
          <LinearProgress
            variant={progress > 0 ? 'determinate' : 'indeterminate'}
            value={progress}
          />
        )}

        <Stack
          direction={{ xs: 'column', md: 'row' }}
          spacing={1}
          alignItems={{ xs: 'flex-start', md: 'center' }}
          justifyContent="space-between"
        >
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
            {progressDetails?.nfiles !== undefined && (
              <InlineMetric
                icon={<FileText size={13} />}
                label={t('backup.runningJobs.progress.filesProcessed')}
                value={progressDetails.nfiles.toLocaleString()}
              />
            )}
            {progressDetails?.original_size !== undefined && (
              <InlineMetric
                icon={<Activity size={13} />}
                label={t('backup.runningJobs.progress.originalSize')}
                value={formatBytesUtil(progressDetails.original_size)}
              />
            )}
            {job?.status === 'running' && progressDetails?.backup_speed !== undefined && (
              <InlineMetric
                icon={<RefreshCw size={13} />}
                label={t('backup.runningJobs.progress.speed')}
                value={`${progressDetails.backup_speed.toFixed(2)} MB/s`}
              />
            )}
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="caption" color="text.secondary">
              {job?.archive_name
                ? t('backupPlans.runsDialog.archiveName', { name: job.archive_name })
                : t('backupPlans.runsDialog.archivePending')}
            </Typography>
            {canViewLogs(job) && (
              <Button
                size="small"
                variant="text"
                startIcon={<Eye size={14} />}
                onClick={() => onViewLogs(job)}
              >
                {t('backupPlans.runsDialog.viewLogs')}
              </Button>
            )}
          </Stack>
        </Stack>

        {progressDetails?.current_file && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              display: 'block',
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {progressDetails.current_file}
          </Typography>
        )}

        {(runRepository.error_message || job?.error_message) && (
          <Typography variant="caption" color="error">
            {runRepository.error_message || job?.error_message}
          </Typography>
        )}
      </Stack>
    </Box>
  )
}

function ScriptExecutionRow({
  execution,
  onViewLogs,
}: {
  execution: BackupPlanScriptExecution
  onViewLogs: (job: BackupPlanRunLogJob) => void
}) {
  const { t } = useTranslation()
  const hookLabel =
    execution.hook_type === 'pre-backup'
      ? t('backupPlans.runsDialog.prePlanScript')
      : execution.hook_type === 'post-backup'
        ? t('backupPlans.runsDialog.postPlanScript')
        : execution.hook_type || t('backupPlans.runsDialog.planScript')
  const statusLabel = t(`backupPlans.statuses.${execution.status}`, {
    defaultValue: formatRunStatus(execution.status),
  })

  return (
    <Box
      sx={{
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        p: 1.5,
        bgcolor: 'background.paper',
      }}
    >
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={1}
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        justifyContent="space-between"
      >
        <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
          <Box sx={{ color: 'text.secondary', display: 'flex', flexShrink: 0 }}>
            <FileText size={16} />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle2" noWrap>
              {hookLabel}: {execution.script_name}
            </Typography>
            <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap>
              {execution.exit_code !== null && execution.exit_code !== undefined && (
                <Typography variant="caption" color="text.secondary">
                  {t('backupPlans.runsDialog.exitCode', { code: execution.exit_code })}
                </Typography>
              )}
              {execution.execution_time !== null && execution.execution_time !== undefined && (
                <Typography variant="caption" color="text.secondary">
                  {t('backupPlans.runsDialog.scriptDuration', {
                    seconds: execution.execution_time.toFixed(2),
                  })}
                </Typography>
              )}
            </Stack>
          </Box>
        </Stack>
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" label={statusLabel} color={runStatusColor(execution.status)} />
          {canViewScriptLogs(execution) && (
            <Button
              size="small"
              variant="text"
              startIcon={<Eye size={14} />}
              onClick={() =>
                onViewLogs({
                  id: execution.id,
                  status: execution.status,
                  type: 'script_execution',
                  has_logs: execution.has_logs,
                })
              }
            >
              {t('backupPlans.runsDialog.viewLogs')}
            </Button>
          )}
        </Stack>
      </Stack>
      {execution.error_message && (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: 'block' }}>
          {execution.error_message}
        </Typography>
      )}
    </Box>
  )
}

function InlineMetric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
}) {
  return (
    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ minWidth: 0 }}>
      <Box sx={{ color: 'text.secondary', display: 'flex', flexShrink: 0 }}>{icon}</Box>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="caption" fontWeight={600}>
        {value}
      </Typography>
    </Stack>
  )
}

function SummaryPill({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Box
      sx={{
        minWidth: 0,
        flex: 1,
        border: 1,
        borderColor: 'divider',
        borderRadius: 1,
        px: 1.5,
        py: 1,
      }}
    >
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600} noWrap>
        {value}
      </Typography>
    </Box>
  )
}

export function BackupPlanRunCard({
  run,
  plan,
  cancelling,
  onCancel,
  onViewLogs,
}: {
  run: BackupPlanRun
  plan?: BackupPlan | null
  cancelling?: boolean
  onCancel: (runId: number) => void
  onViewLogs: (job: BackupPlanRunLogJob) => void
}) {
  const { t } = useTranslation()
  const active = isActiveRun(run.status)
  const progress = getRunProgress(run)
  const statusLabel = t(`backupPlans.statuses.${run.status}`, {
    defaultValue: formatRunStatus(run.status),
  })
  const planName =
    plan?.name ||
    (run.backup_plan_id
      ? t('backupPlans.runsPanel.planFallback', { id: run.backup_plan_id })
      : t('backupPlans.runsPanel.unknownPlan'))

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2.5}>
          <Stack
            direction={{ xs: 'column', sm: 'row' }}
            spacing={1.5}
            alignItems={{ xs: 'flex-start', sm: 'center' }}
            justifyContent="space-between"
          >
            <Box sx={{ minWidth: 0 }}>
              <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                {active && <RefreshCw size={16} className="animate-spin" />}
                <Typography variant="subtitle1" fontWeight={700} noWrap>
                  {planName}
                </Typography>
                <Chip size="small" label={t('backupPlans.runsDialog.runNumber', { id: run.id })} />
                <Chip size="small" label={statusLabel} color={runStatusColor(run.status)} />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                {t('backupPlans.runsPanel.repositoryProgress', {
                  completed: getFinishedCount(run),
                  total: run.repositories.length,
                })}
              </Typography>
            </Box>
            {active && (
              <Button
                color="warning"
                size="small"
                variant="outlined"
                disabled={cancelling}
                onClick={() => onCancel(run.id)}
                startIcon={
                  cancelling ? <CircularProgress size={14} color="inherit" /> : <Square size={14} />
                }
              >
                {t('backupPlans.runsPanel.cancelRun')}
              </Button>
            )}
          </Stack>

          <LinearProgress
            variant={active && progress === 0 ? 'indeterminate' : 'determinate'}
            value={progress}
          />

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <SummaryPill label={t('backupPlans.runsDialog.trigger')} value={run.trigger} />
            <SummaryPill
              label={t('backupPlans.runsDialog.started')}
              value={run.started_at ? new Date(run.started_at).toLocaleString() : '-'}
            />
            <SummaryPill
              label={t('backupPlans.runsPanel.duration')}
              value={formatTimeRange(run.started_at, run.completed_at, run.status)}
            />
          </Stack>

          {run.error_message && (
            <Alert severity={run.status === 'cancelled' ? 'warning' : 'error'}>
              {run.error_message}
            </Alert>
          )}

          {run.script_executions && run.script_executions.length > 0 && (
            <Stack spacing={1.25}>
              <Typography variant="subtitle2" fontWeight={700}>
                {t('backupPlans.runsDialog.planScripts')}
              </Typography>
              {run.script_executions.map((execution) => (
                <ScriptExecutionRow
                  key={execution.id}
                  execution={execution}
                  onViewLogs={onViewLogs}
                />
              ))}
            </Stack>
          )}

          {run.repositories.length === 0 ? (
            <Alert severity="info">{t('backupPlans.runsPanel.noRepositories')}</Alert>
          ) : (
            <Stack spacing={1.25}>
              {run.repositories.map((runRepository) => (
                <RepositoryRunRow
                  key={runRepository.id}
                  runRepository={runRepository}
                  onViewLogs={onViewLogs}
                />
              ))}
            </Stack>
          )}
        </Stack>
      </CardContent>
    </Card>
  )
}

export default function BackupPlanRunsPanel({
  runs,
  plans,
  loading,
  cancellingRunId,
  onCancel,
  onViewLogs,
}: {
  runs: BackupPlanRun[]
  plans: BackupPlan[]
  loading?: boolean
  cancellingRunId?: number | null
  onCancel: (runId: number) => void
  onViewLogs: (job: BackupPlanRunLogJob) => void
}) {
  const { t } = useTranslation()
  const activeRuns = useMemo(() => runs.filter((run) => isActiveRun(run.status)), [runs])
  const recentRuns = useMemo(
    () => runs.filter((run) => !isActiveRun(run.status)).slice(0, 4),
    [runs]
  )
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
          <Typography variant="body2" fontWeight={700} color="primary">
            #{run.id}
          </Typography>
          <Typography variant="caption" color="text.secondary" noWrap component="div">
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
          <Typography variant="body2" fontWeight={700} noWrap>
            {getPlanName(run)}
          </Typography>
          <RepositoryCell
            repositoryName={getPrimaryRepositoryName(run)}
            repositoryPath={getPrimaryRepositoryPath(run)}
            withIcon={false}
          />
          <Typography variant="caption" color="text.secondary" component="div">
            {t('backupPlans.runsPanel.repositoryProgress', {
              completed: getFinishedCount(run),
              total: run.repositories.length,
            })}
          </Typography>
          {getCurrentFile(run) && (
            <Typography
              variant="caption"
              color="text.secondary"
              component="div"
              sx={{
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
          <StatusBadge status={run.status} />
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
            color="text.secondary"
            sx={{ cursor: getStartedAt(run) ? 'help' : 'default', display: 'inline-block' }}
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
        <Typography variant="body2" color="text.secondary" noWrap>
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
          alignItems="center"
          sx={{ mb: 1, color: 'text.secondary' }}
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
          <Typography id={sectionId} variant="h6" fontWeight={600}>
            {title}
          </Typography>
          {countChip}
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
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
        <Card
          component="section"
          aria-labelledby="backup-plan-active-runs-heading"
          sx={{ overflow: 'visible' }}
        >
          <CardContent>
            <Stack
              direction="row"
              spacing={1.5}
              alignItems="center"
              sx={{ mb: 1, color: 'text.secondary' }}
            >
              <Box sx={{ display: 'flex', color: 'success.main' }}>
                <RefreshCw size={20} className="animate-spin" />
              </Box>
              <Typography id="backup-plan-active-runs-heading" variant="h6" fontWeight={600}>
                {t('backupPlans.runsPanel.activeTitle')}
              </Typography>
              <Chip
                size="small"
                color="primary"
                label={t('backupPlans.runsPanel.activeCount', { count: activeRuns.length })}
              />
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
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
          </CardContent>
        </Card>
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
    </Stack>
  )
}
