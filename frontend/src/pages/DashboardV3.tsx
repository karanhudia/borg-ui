/**
 * DashboardV3 — "Void" ops command center
 *
 * Design system: Real-Time Monitoring × Modern Cinema (ui-ux-pro-max)
 * Palette:       Glass surface · Hairline border
 * Accent:        Indigo #6366f1 · Green #22c55e · Amber #f59e0b · Red #ef4444
 * Typography:    JetBrains Mono for all numeric / data values
 * Layout:        Bento grid (asymmetric) + full-width activity timeline SVG
 *
 * Padding note:  The Layout already provides Container maxWidth="xl" + p:3.
 *                This component adds NO extra outer padding or background.
 */

import React from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Alert, Box, Button, Stack, Tooltip, Typography } from '@mui/material'
import { Activity, ArrowRight, Cpu, HardDrive, XCircle } from 'lucide-react'
import { differenceInDays, formatDistanceToNow } from 'date-fns'
import { useTheme } from '../context/ThemeContext'
import { useAnalytics } from '../hooks/useAnalytics'
import { dashboardAPI } from '../services/api'
import { formatDateTimeFull } from '../utils/dateUtils'
import { ActivityTimeline } from './dashboard-v3/ActivityTimeline'
import { ArcGauge, StorageDonut, SuccessDonut } from './dashboard-v3/charts'
import { DashboardSkeleton } from './dashboard-v3/DashboardSkeleton'
import { PulseDot } from './dashboard-v3/health'
import { UpcomingBackupsPanel } from './dashboard-v3/UpcomingBackupsPanel'
import { RepositoryHealthPanel } from './dashboard-v3/RepositoryHealthPanel'
import { makeT, STATUS, TokenContext } from './dashboard-v3/tokens'
import type { DashboardOverview } from './dashboard-v3/types'
import { gaugeColor, toGB } from './dashboard-v3/utils'

const RESOLVING_ACTIVITY_STATUSES = new Set(['completed', 'completed_with_warnings'])

function getCurrentFailures(activityFeed: DashboardOverview['activity_feed']) {
  return activityFeed.filter((activity) => {
    if (activity.status !== 'failed') return false

    const failedAt = new Date(activity.timestamp).getTime()
    return !activityFeed.some(
      (candidate) =>
        candidate.type === activity.type &&
        candidate.repository === activity.repository &&
        RESOLVING_ACTIVITY_STATUSES.has(candidate.status) &&
        new Date(candidate.timestamp).getTime() > failedAt
    )
  })
}

export default function DashboardV3() {
  const navigate = useNavigate()
  const { effectiveMode } = useTheme()
  const { t } = useTranslation()
  const { trackNavigation, EventAction } = useAnalytics()
  const T = makeT(effectiveMode === 'dark')
  const [nowMs] = React.useState(() => Date.now())

  const glass = {
    bgcolor: T.bgCard,
    border: `1px solid ${T.border}`,
    borderRadius: T.radius,
    backdropFilter: 'blur(12px)',
    transition: 'border-color 0.2s',
    '&:hover': { borderColor: T.borderHover },
  } as const

  const {
    data: ov,
    isLoading,
    error,
    refetch,
  } = useQuery<DashboardOverview>({
    queryKey: ['dashboard-v3'],
    queryFn: () => dashboardAPI.getOverview().then((response) => response.data),
    refetchInterval: 30_000,
  })

  if (isLoading) return <DashboardSkeleton T={T} />
  if (error || !ov)
    return (
      <Alert
        severity="error"
        action={
          <Button
            size="small"
            onClick={() => {
              trackNavigation(EventAction.VIEW, {
                section: 'dashboard',
                operation: 'retry_refresh',
              })
              refetch()
            }}
          >
            {t('dashboard.error.retry')}
          </Button>
        }
      >
        {t('dashboard.error.unavailable')}
      </Alert>
    )

  const { summary, storage, repository_health: repos, system_metrics: sys } = ov
  const criticalCount = repos.filter((r) => r.health_status === 'critical').length
  const warningCount = repos.filter((r) => r.health_status === 'warning').length
  const healthyCount = repos.filter((r) => r.health_status === 'healthy').length
  const sysStatus = criticalCount > 0 ? 'critical' : warningCount > 0 ? 'warning' : 'healthy'
  const sc = STATUS[sysStatus]
  const activeAutomationCount =
    summary.active_automations ?? summary.active_schedules + (summary.active_backup_plans ?? 0)
  const totalAutomationCount =
    summary.total_automations ?? summary.total_schedules + (summary.total_backup_plans ?? 0)

  // Most recent backup across all repos
  const lastBackupDate = repos
    .map((r) => (r.last_backup ? new Date(r.last_backup) : null))
    .filter(Boolean)
    .sort((a, b) => b!.getTime() - a!.getTime())[0]
  const currentFailures = getCurrentFailures(ov.activity_feed)

  return (
    <TokenContext.Provider value={T}>
      {/* No outer bgcolor / padding — Layout's Container already provides this */}
      <Box sx={{ color: T.textPrimary }}>
        {/* ── Health banner ─────────────────────────────────────────────────── */}
        <Box
          sx={{
            ...glass,
            mb: 2.5,
            px: 2.5,
            py: 1.75,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 2,
            borderColor: sc.color + '35',
            boxShadow: `0 0 28px ${sc.glow}, inset 0 1px 0 ${T.insetLine}`,
          }}
        >
          <Stack direction="row" spacing={2} alignItems="center">
            <PulseDot color={sc.color} glow={sc.glow} />
            <Box>
              <Typography
                sx={{
                  fontSize: '0.62rem',
                  color: T.textMuted,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                  mb: 0.2,
                }}
              >
                {t('dashboard.banner.systemStatus')}
              </Typography>
              <Typography
                sx={{ fontFamily: T.mono, fontSize: '1rem', fontWeight: 700, color: sc.color }}
              >
                {sysStatus === 'healthy'
                  ? t('dashboard.banner.allNominal')
                  : sysStatus === 'warning'
                    ? t('dashboard.banner.warnings', {
                        count: warningCount,
                        s: warningCount > 1 ? 's' : '',
                      })
                    : t('dashboard.banner.critical', { count: criticalCount })}
              </Typography>
            </Box>
          </Stack>

          {/* Quick stats */}
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
            {[
              {
                label: t('dashboard.stats.repositories'),
                value: summary.total_repositories,
                color: T.blue,
              },
              {
                label: t('dashboard.banner.stats.lastBackup'),
                value: lastBackupDate
                  ? formatDistanceToNow(lastBackupDate, { addSuffix: true })
                  : t('common.never'),
                color:
                  lastBackupDate && differenceInDays(new Date(), lastBackupDate) > 1
                    ? T.amber
                    : T.green,
              },
              {
                label: t('dashboard.banner.stats.automations', { defaultValue: 'Automations' }),
                value: `${activeAutomationCount}/${totalAutomationCount}`,
                color: T.textMuted,
              },
              {
                label: t('dashboard.banner.stats.storage'),
                value: storage.total_size,
                color: T.textPrimary,
              },
            ].map(({ label, value, color }) => (
              <Box key={label}>
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: T.textMuted,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                  }}
                >
                  {label}
                </Typography>
                <Typography
                  sx={{
                    fontFamily: T.mono,
                    fontWeight: 700,
                    color,
                    fontSize: '0.95rem',
                    lineHeight: 1.3,
                  }}
                >
                  {value}
                </Typography>
              </Box>
            ))}
          </Stack>

          <Button
            size="small"
            variant="text"
            onClick={() => {
              trackNavigation(EventAction.VIEW, {
                section: 'dashboard',
                operation: 'refresh',
              })
              refetch()
            }}
            sx={{
              color: T.textMuted,
              fontSize: '0.68rem',
              minWidth: 0,
              px: 1.25,
              '&:hover': { color: T.textPrimary, bgcolor: T.hoverBg },
            }}
          >
            {t('common.buttons.refresh')}
          </Button>
        </Box>

        {/* ── Bento grid ────────────────────────────────────────────────────── */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '220px 1fr' },
            gap: 2.5,
            alignItems: 'start',
          }}
        >
          {/* Left: donut + resources */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            <Box sx={{ ...glass, p: 2.5, textAlign: 'center' }}>
              <Typography
                sx={{
                  fontSize: '0.58rem',
                  color: T.textMuted,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                  mb: 2,
                }}
              >
                {t('dashboard.successDonut.label')}
              </Typography>
              <SuccessDonut
                rate={summary.success_rate_30d}
                good={summary.successful_jobs_30d}
                total={summary.total_jobs_30d}
              />
              <Stack direction="row" justifyContent="center" spacing={2.5} sx={{ mt: 2 }}>
                <Box>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      color: T.green,
                      fontSize: '1.1rem',
                      lineHeight: 1,
                    }}
                  >
                    {summary.successful_jobs_30d}
                  </Typography>
                  <Typography sx={{ fontSize: '0.58rem', color: T.textMuted, mt: 0.25 }}>
                    {t('dashboard.successDonut.passed')}
                  </Typography>
                </Box>
                <Box sx={{ width: '1px', height: 28, bgcolor: T.border, flexShrink: 0 }} />
                <Box>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      color: summary.failed_jobs_30d > 0 ? T.red : T.textMuted,
                      fontSize: '1.1rem',
                      lineHeight: 1,
                    }}
                  >
                    {summary.failed_jobs_30d}
                  </Typography>
                  <Typography sx={{ fontSize: '0.58rem', color: T.textMuted, mt: 0.25 }}>
                    {t('dashboard.successDonut.failed')}
                  </Typography>
                </Box>
              </Stack>
            </Box>

            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 2 }}>
                <Cpu size={13} color={T.textMuted} />
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: T.textMuted,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {t('dashboard.resources')}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-around">
                <ArcGauge
                  value={sys.cpu_usage}
                  color={gaugeColor(sys.cpu_usage, T)}
                  label={t('dashboard.cpu')}
                  sub={`${sys.cpu_count}c`}
                />
                <ArcGauge
                  value={sys.memory_usage}
                  color={gaugeColor(sys.memory_usage, T)}
                  label={t('dashboard.memAbbr')}
                  sub={`${toGB(sys.memory_total - sys.memory_available)}/${toGB(sys.memory_total)}G`}
                />
                <ArcGauge
                  value={sys.disk_usage}
                  color={gaugeColor(sys.disk_usage, T)}
                  label={t('dashboard.diskAbbr')}
                  sub={`${toGB(sys.disk_total - sys.disk_free)}/${toGB(sys.disk_total)}G`}
                />
              </Stack>
            </Box>

            <UpcomingBackupsPanel tasks={ov.upcoming_tasks} />

            {/* Storage donut */}
            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 1.75 }}>
                <HardDrive size={13} color={T.textMuted} />
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: T.textMuted,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {t('dashboard.banner.stats.storage')}
                </Typography>
              </Stack>
              <StorageDonut
                breakdown={storage.breakdown}
                totalSize={storage.total_size}
                totalArchives={storage.total_archives}
              />
              {storage.average_dedup_ratio != null && (
                <Box
                  sx={{
                    mt: 1.5,
                    px: 1.25,
                    py: 0.6,
                    bgcolor: T.indigoDim,
                    border: `1px solid ${T.indigo}25`,
                    borderRadius: '8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <Typography sx={{ fontSize: '0.62rem', color: T.textMuted }}>
                    {t('dashboard.storageDonut.dedupRatio')}
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: T.indigo,
                    }}
                  >
                    {storage.average_dedup_ratio.toFixed(2)}×
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>

          {/* Right: repo mini-cards + activity */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            <RepositoryHealthPanel
              T={T}
              glass={glass}
              repos={repos}
              criticalCount={criticalCount}
              warningCount={warningCount}
              healthyCount={healthyCount}
              nowMs={nowMs}
              onOpenRepositories={() => {
                trackNavigation(EventAction.VIEW, {
                  section: 'dashboard',
                  destination: 'repositories',
                  source: 'repository_health',
                })
                navigate('/repositories')
              }}
            />

            {/* Activity timeline */}
            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1.75 }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Activity size={13} color={T.textMuted} />
                  <Typography
                    sx={{
                      fontSize: '0.58rem',
                      color: T.textMuted,
                      letterSpacing: 2,
                      textTransform: 'uppercase',
                    }}
                  >
                    {t('dashboard.recentActivity.last14Days')}
                  </Typography>
                </Stack>
                <Button
                  size="small"
                  variant="text"
                  endIcon={<ArrowRight size={12} />}
                  onClick={() => {
                    trackNavigation(EventAction.VIEW, {
                      section: 'dashboard',
                      destination: 'activity',
                      source: 'recent_activity',
                    })
                    navigate('/activity')
                  }}
                  sx={{
                    fontSize: '0.65rem',
                    color: T.textMuted,
                    '&:hover': { color: T.textPrimary, bgcolor: T.hoverBg },
                  }}
                >
                  {t('dashboard.recentActivity.fullLog')}
                </Button>
              </Stack>

              {ov.activity_feed.length === 0 ? (
                <Typography
                  sx={{ color: T.textMuted, textAlign: 'center', py: 3, fontSize: '0.8rem' }}
                >
                  {t('dashboard.recentActivity.emptyRecorded')}
                </Typography>
              ) : (
                <ActivityTimeline activities={ov.activity_feed} />
              )}

              {currentFailures.length > 0 && (
                <Box sx={{ mt: 2, borderTop: `1px solid ${T.border}`, pt: 1.5 }}>
                  <Typography
                    sx={{
                      fontSize: '0.58rem',
                      color: T.red,
                      letterSpacing: 1.5,
                      textTransform: 'uppercase',
                      mb: 1,
                    }}
                  >
                    {t('dashboard.recentFailures.title')}
                  </Typography>
                  <Stack spacing={0.6}>
                    {currentFailures.slice(0, 3).map((a) => (
                      <Box
                        key={`${a.type}-${a.id}`}
                        sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}
                      >
                        <XCircle size={13} color={T.red} style={{ marginTop: 2, flexShrink: 0 }} />
                        <Box sx={{ minWidth: 0 }}>
                          <Stack direction="row" spacing={1.5}>
                            <Typography
                              sx={{
                                fontFamily: T.mono,
                                fontSize: '0.68rem',
                                fontWeight: 600,
                                color: T.textPrimary,
                              }}
                            >
                              {a.repository}
                            </Typography>
                            <Tooltip title={formatDateTimeFull(a.timestamp)} arrow placement="top">
                              <Typography
                                sx={{
                                  cursor: 'help',
                                  fontFamily: T.mono,
                                  fontSize: '0.62rem',
                                  color: T.textMuted,
                                }}
                              >
                                {formatDistanceToNow(new Date(a.timestamp), { addSuffix: true })}
                              </Typography>
                            </Tooltip>
                          </Stack>
                          {a.error && (
                            <Typography
                              sx={{
                                fontFamily: T.mono,
                                fontSize: '0.6rem',
                                color: T.red + 'cc',
                                mt: 0.25,
                                wordBreak: 'break-all',
                              }}
                            >
                              {a.error}
                            </Typography>
                          )}
                        </Box>
                      </Box>
                    ))}
                  </Stack>
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </TokenContext.Provider>
  )
}
