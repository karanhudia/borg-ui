import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  LinearProgress,
  Stack,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import {
  Activity,
  AlertTriangle,
  Archive,
  CheckCircle2,
  Clock,
  Database,
  Eye,
  FileText,
  HardDrive,
  Square,
  XCircle,
  Zap,
} from 'lucide-react'
import type { BackupJob, BackupPlan, BackupPlanRun, BackupPlanRunRepository } from '../types'
import { formatBytes, formatDurationSeconds, formatTimeRange } from '../utils/dateUtils'
import { PlanRunScriptsSection, type BackupPlanRunLogJob } from './PlanRunScripts'
import { canViewBackupJobLogs as canViewLogs } from './planRunScriptLogs'

// Brand emerald is reserved for the live pulse dot (the only brand touch on
// this otherwise neutral card). Everything else uses text.primary tints.
const LIVE_DOT = '#059669'

export type ActivePlanRunLogJob = BackupPlanRunLogJob

interface ActiveBackupPlanRunCardProps {
  run: BackupPlanRun
  plan?: BackupPlan | null
  cancelling?: boolean
  onCancel: (runId: number) => void
  onViewLogs: (job: ActivePlanRunLogJob) => void
}

function isActive(status?: string): boolean {
  return status === 'pending' || status === 'running'
}

function getRepositoryLabel(runRepository: BackupPlanRunRepository): string {
  return runRepository.repository?.name || runRepository.backup_job?.repository || 'Repository'
}

function aggregateStats(run: BackupPlanRun) {
  // Per-source stats (files, original, compressed) reflect the actively running
  // repo only — summing them would double-count when a plan writes the same
  // source to multiple targets. Speed/ETA stay aggregated because they describe
  // the plan-wide rhythm (parallel throughput; longest remaining run).
  let totalSpeed = 0
  let speedSamples = 0
  let maxEta = 0
  let anyEta = false

  for (const repoRun of run.repositories) {
    const details = repoRun.backup_job?.progress_details
    if (!details) continue
    if (repoRun.backup_job?.status === 'running' && typeof details.backup_speed === 'number') {
      totalSpeed += details.backup_speed
      speedSamples += 1
    }
    if (
      typeof details.estimated_time_remaining === 'number' &&
      details.estimated_time_remaining > 0
    ) {
      anyEta = true
      maxEta = Math.max(maxEta, details.estimated_time_remaining)
    }
  }

  // Prefer the currently-running repo; fall back to the latest repo that has
  // emitted progress (so finished plans still show the last known size).
  const activeRepo =
    run.repositories.find(
      (r) => r.backup_job?.status === 'running' && r.backup_job?.progress_details
    ) ?? [...run.repositories].reverse().find((r) => r.backup_job?.progress_details)
  const activeDetails = activeRepo?.backup_job?.progress_details
  const nfiles = typeof activeDetails?.nfiles === 'number' ? activeDetails.nfiles : 0
  const originalSize =
    typeof activeDetails?.original_size === 'number' ? activeDetails.original_size : 0
  const compressedSize =
    typeof activeDetails?.compressed_size === 'number' ? activeDetails.compressed_size : 0

  return {
    nfiles,
    originalSize,
    compressedSize,
    speed: speedSamples > 0 ? totalSpeed : 0,
    hasSpeed: speedSamples > 0,
    eta: anyEta ? maxEta : 0,
    hasEta: anyEta,
  }
}

function aggregateProgress(run: BackupPlanRun): { processed: number; total: number; pct: number } {
  let processed = 0
  let total = 0
  for (const repoRun of run.repositories) {
    const details = repoRun.backup_job?.progress_details
    if (!details) continue
    if (typeof details.original_size === 'number') processed += details.original_size
    if (typeof details.total_expected_size === 'number' && details.total_expected_size > 0) {
      total += details.total_expected_size
    }
  }
  const pct = total > 0 ? Math.min(100, (processed / total) * 100) : 0
  return { processed, total, pct }
}

function getCurrentFile(run: BackupPlanRun): string | null {
  return (
    run.repositories.find((repoRun) => repoRun.backup_job?.progress_details?.current_file)
      ?.backup_job?.progress_details?.current_file ?? null
  )
}

function getPreferredViewableJob(run: BackupPlanRun): BackupJob | null {
  const runningJob = run.repositories.find(
    (repoRun) => repoRun.backup_job?.status === 'running' && canViewLogs(repoRun.backup_job)
  )
  if (runningJob?.backup_job) return runningJob.backup_job

  const activeRepositoryJob = run.repositories.find(
    (repoRun) => isActive(repoRun.status) && canViewLogs(repoRun.backup_job)
  )
  if (activeRepositoryJob?.backup_job) return activeRepositoryJob.backup_job

  const firstViewableJob = run.repositories.find((repoRun) => canViewLogs(repoRun.backup_job))
  return firstViewableJob?.backup_job ?? null
}

const STAT_ICONS = [
  <FileText key="files" size={11} />,
  <HardDrive key="size" size={11} />,
  <Zap key="speed" size={11} />,
  <Clock key="eta" size={11} />,
  <Archive key="comp" size={11} />,
  <Database key="db" size={11} />,
  <Activity key="act" size={11} />,
]

const ActiveBackupPlanRunCard: React.FC<ActiveBackupPlanRunCardProps> = ({
  run,
  plan,
  cancelling,
  onCancel,
  onViewLogs,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const planName =
    plan?.name ||
    (run.backup_plan_id
      ? t('backupPlans.runsPanel.planFallback', { id: run.backup_plan_id })
      : t('backupPlans.runsPanel.unknownPlan'))

  const stats = aggregateStats(run)
  const progress = aggregateProgress(run)
  const currentFile = getCurrentFile(run)
  const firstLogJob = getPreferredViewableJob(run)

  const visibleStats: { key: string; label: string; value: string; valueColor?: string }[] = []
  visibleStats.push({
    key: 'files',
    label: t('backup.runningJobs.progress.filesProcessed'),
    value: stats.nfiles.toLocaleString(),
  })
  visibleStats.push({
    key: 'original',
    label: t('backup.runningJobs.progress.originalSize'),
    value: stats.originalSize > 0 ? formatBytes(stats.originalSize) : '-',
  })
  visibleStats.push({
    key: 'speed',
    label: t('backup.runningJobs.progress.speed'),
    value: stats.hasSpeed ? `${stats.speed.toFixed(2)} MB/s` : 'N/A',
    valueColor: undefined,
  })
  visibleStats.push({
    key: 'eta',
    label: t('backup.runningJobs.progress.eta'),
    value: stats.hasEta ? formatDurationSeconds(stats.eta) : 'N/A',
    valueColor: undefined,
  })

  const statIconColor = theme.palette.text.secondary

  return (
    <Box
      sx={{
        position: 'relative',
        borderRadius: 2,
        bgcolor: 'background.paper',
        overflow: 'hidden',
        // Real border + elevation so the active card sits above neighboring
        // plan cards instead of merging with the page. A faint emerald-tinted
        // border serves as the second brand touch (the pulse dot being the
        // first); the surface itself stays neutral.
        border: '1px solid',
        borderColor: alpha(LIVE_DOT, isDark ? 0.32 : 0.22),
        boxShadow: isDark
          ? '0 8px 24px rgba(0, 0, 0, 0.45), 0 2px 6px rgba(0, 0, 0, 0.25)'
          : '0 8px 24px rgba(15, 23, 42, 0.07), 0 2px 6px rgba(15, 23, 42, 0.05)',
      }}
    >
      <Box sx={{ position: 'relative', px: { xs: 1.75, sm: 2.25 }, pt: 2, pb: 2 }}>
        {/* Header */}
        <Box
          sx={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'flex-start',
            gap: 2,
            mb: 2,
            flexWrap: { xs: 'wrap', sm: 'nowrap' },
          }}
        >
          {/* Left: plan identity + stage */}
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Stack
              direction="row"
              spacing={0.75}
              alignItems="center"
              sx={{ mb: 0.5, flexWrap: 'wrap', gap: 0.5 }}
            >
              <Box
                sx={{
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  bgcolor: LIVE_DOT,
                  flexShrink: 0,
                  animation: 'planRunLiveDot 2s ease-in-out infinite',
                  '@keyframes planRunLiveDot': {
                    '0%, 100%': { opacity: 1, transform: 'scale(1)' },
                    '50%': { opacity: 0.45, transform: 'scale(0.82)' },
                  },
                  '@media (prefers-reduced-motion: reduce)': {
                    animation: 'none',
                  },
                }}
              />
              <Typography variant="body1" fontWeight={700} noWrap sx={{ lineHeight: 1.3 }}>
                {planName}
              </Typography>
              <Typography
                variant="caption"
                sx={{
                  fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                  fontWeight: 600,
                  color: 'text.disabled',
                  bgcolor: alpha('#000', 0.05),
                  px: 0.75,
                  py: 0.15,
                  borderRadius: 0.75,
                  flexShrink: 0,
                  lineHeight: 1.4,
                }}
                aria-label={t('backupPlans.runsDialog.runNumber', { id: run.id })}
              >
                #{run.id}
              </Typography>
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
              {t('backupPlans.runsPanel.repositoryProgress', {
                completed: run.repositories.filter((r) => !isActive(r.status)).length,
                total: run.repositories.length,
              })}
              {plan?.repository_run_mode ? ` · ${plan.repository_run_mode}` : ''}
              {run.trigger ? ` · ${run.trigger}` : ''}
            </Typography>
          </Box>

          {/* Right: actions */}
          <Stack direction="row" spacing={0.75} alignItems="center" flexShrink={0}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: { xs: 'none', sm: 'block' }, mr: 0.5 }}
            >
              {formatTimeRange(run.started_at, run.completed_at, run.status)}
            </Typography>
            {firstLogJob && (
              <Button
                variant="outlined"
                size="small"
                color="inherit"
                startIcon={<Eye size={13} />}
                onClick={() => onViewLogs(firstLogJob)}
                sx={{ height: 28, fontSize: '0.75rem', px: 1.25 }}
              >
                {t('backupPlans.runsDialog.viewLogs')}
              </Button>
            )}
            <Button
              variant="outlined"
              size="small"
              color="error"
              startIcon={
                cancelling ? <CircularProgress size={13} color="inherit" /> : <Square size={13} />
              }
              disabled={cancelling}
              onClick={() => onCancel(run.id)}
              sx={{ height: 28, fontSize: '0.75rem', px: 1.25 }}
              aria-label={t('backupPlans.runsPanel.cancelRun')}
            >
              {t('backupPlans.runsPanel.cancelRun')}
            </Button>
          </Stack>
        </Box>

        {/* Progress bar — only when total source size is known */}
        {progress.total > 0 && (
          <Box sx={{ mb: 1.5 }}>
            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mb: 0.5 }}
            >
              <Typography
                sx={{
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  color: 'text.primary',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {progress.pct.toFixed(1)}%
              </Typography>
              <Typography sx={{ fontSize: '0.65rem', color: 'text.disabled' }}>
                {t('backup.runningJobs.progress.totalSourceSize')}
              </Typography>
            </Stack>
            <LinearProgress
              variant="determinate"
              value={progress.pct}
              sx={{
                height: 6,
                borderRadius: 3,
                bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.06),
                '& .MuiLinearProgress-bar': {
                  borderRadius: 3,
                  bgcolor: alpha(theme.palette.text.primary, 0.75),
                },
              }}
            />
          </Box>
        )}

        {/* Stats Band */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: {
              xs: 'repeat(2, 1fr)',
              sm: 'repeat(4, 1fr)',
            },
            borderRadius: 1.5,
            overflow: 'hidden',
            mb: 1.5,
            bgcolor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            gap: '1px',
          }}
        >
          {visibleStats.map((stat, i) => {
            return (
              <Box
                key={stat.key}
                sx={{
                  px: 1.5,
                  py: 1.1,
                  bgcolor: 'background.paper',
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.35 }}>
                  <Box
                    sx={{
                      color: statIconColor,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    {STAT_ICONS[i]}
                  </Box>
                  <Typography
                    sx={{
                      fontSize: '0.75rem',
                      fontWeight: 600,
                      color: 'text.secondary',
                      lineHeight: 1,
                    }}
                  >
                    {stat.label}
                  </Typography>
                </Box>
                <Typography
                  variant="body2"
                  fontWeight={600}
                  noWrap
                  sx={{
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '0.875rem',
                    color: stat.valueColor || 'text.primary',
                  }}
                >
                  {stat.value}
                </Typography>
              </Box>
            )
          })}
        </Box>

        {/* Per-repository strip */}
        {run.repositories.length > 0 && (
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: '1fr',
                sm: `repeat(${Math.min(run.repositories.length, 3)}, 1fr)`,
              },
              gap: 1,
              mb: currentFile ? 1.5 : 0,
            }}
          >
            {run.repositories.map((repoRun) => {
              const repoActive = isActive(repoRun.status)
              const repoDone = repoRun.status === 'completed'
              const repoDoneWithWarnings = repoRun.status === 'completed_with_warnings'
              const repoFailed = repoRun.status === 'failed' || repoRun.status === 'cancelled'

              // Done uses brand emerald LIVE_DOT (a stronger, on-brand green
              // than MUI's default success teal). Done-with-warnings borrows
              // amber so the warning hint is unmistakable while the repo still
              // reads as "this finished, no action needed urgently".
              const successColor = LIVE_DOT
              const warningColor = theme.palette.warning.main
              const errorColor = theme.palette.error.main
              // Running repo is communicated by a pulsing emerald LIVE_DOT (the
              // sole brand touch) plus a neutral darker border and text. Color
              // does not carry the "running" signal alone; the animation does.
              const runningBorderColor = alpha(theme.palette.text.primary, isDark ? 0.32 : 0.28)
              const runningBgColor = alpha(theme.palette.text.primary, isDark ? 0.05 : 0.03)

              let stateBorderColor: string
              let stateBgColor: string
              let icon: React.ReactNode
              let statusTextColor: string

              if (repoFailed) {
                stateBorderColor = alpha(errorColor, isDark ? 0.5 : 0.45)
                stateBgColor = alpha(errorColor, isDark ? 0.08 : 0.04)
                statusTextColor = errorColor
                icon = (
                  <Box sx={{ color: errorColor, display: 'flex', flexShrink: 0 }}>
                    <XCircle size={13} />
                  </Box>
                )
              } else if (repoDone) {
                stateBorderColor = alpha(successColor, isDark ? 0.5 : 0.4)
                stateBgColor = alpha(successColor, isDark ? 0.08 : 0.05)
                statusTextColor = successColor
                icon = (
                  <Box sx={{ color: successColor, display: 'flex', flexShrink: 0 }}>
                    <CheckCircle2 size={13} />
                  </Box>
                )
              } else if (repoDoneWithWarnings) {
                stateBorderColor = alpha(warningColor, isDark ? 0.55 : 0.4)
                stateBgColor = alpha(warningColor, isDark ? 0.08 : 0.05)
                statusTextColor = warningColor
                icon = (
                  <Box sx={{ color: warningColor, display: 'flex', flexShrink: 0 }}>
                    <AlertTriangle size={13} />
                  </Box>
                )
              } else if (repoActive) {
                stateBorderColor = runningBorderColor
                stateBgColor = runningBgColor
                statusTextColor = 'text.primary'
                icon = (
                  <Box
                    sx={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      bgcolor: LIVE_DOT,
                      flexShrink: 0,
                      boxShadow: `0 0 0 3px ${alpha(LIVE_DOT, 0.2)}`,
                      animation: 'planRunLiveDot 1.4s ease-in-out infinite',
                      '@media (prefers-reduced-motion: reduce)': {
                        animation: 'none',
                      },
                    }}
                  />
                )
              } else {
                stateBorderColor = isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08)
                stateBgColor = 'background.paper'
                statusTextColor = 'text.disabled'
                icon = (
                  <Box sx={{ color: 'text.disabled', display: 'flex', flexShrink: 0 }}>
                    <Clock size={11} />
                  </Box>
                )
              }

              return (
                <Box
                  key={repoRun.id}
                  sx={{
                    px: 1.25,
                    py: 0.75,
                    borderRadius: 1,
                    border: '1px solid',
                    borderColor: stateBorderColor,
                    bgcolor: stateBgColor,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.75,
                    minWidth: 0,
                    opacity:
                      !repoActive && !repoDone && !repoDoneWithWarnings && !repoFailed ? 0.7 : 1,
                  }}
                >
                  {icon}
                  <Typography
                    variant="caption"
                    fontWeight={600}
                    noWrap
                    sx={{ flex: 1, minWidth: 0 }}
                  >
                    {getRepositoryLabel(repoRun)}
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      fontSize: '0.65rem',
                      flexShrink: 0,
                      fontWeight: 700,
                      color: statusTextColor,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {t(`backupPlans.statuses.${repoRun.status}`, { defaultValue: repoRun.status })}
                  </Typography>
                </Box>
              )
            })}
          </Box>
        )}

        {/* Current file terminal box */}
        {currentFile && (
          <Box
            sx={{
              px: 1.5,
              py: 0.875,
              borderRadius: 1,
              bgcolor: isDark ? alpha('#000', 0.3) : alpha('#000', 0.03),
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              overflow: 'hidden',
            }}
          >
            <Box sx={{ color: 'text.secondary', display: 'flex', flexShrink: 0 }}>
              <FileText size={13} />
            </Box>
            <Typography
              sx={{
                fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                fontSize: '0.72rem',
                color: 'text.secondary',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
                minWidth: 0,
              }}
            >
              {currentFile}
            </Typography>
          </Box>
        )}

        {run.script_executions && run.script_executions.length > 0 && (
          <Box sx={{ mt: 1.5 }}>
            <PlanRunScriptsSection run={run} onViewLogs={onViewLogs} />
          </Box>
        )}

        {run.error_message && (
          <Alert severity={run.status === 'cancelled' ? 'warning' : 'error'} sx={{ mt: 1.5 }}>
            {run.error_message}
          </Alert>
        )}
      </Box>
    </Box>
  )
}

export default ActiveBackupPlanRunCard
