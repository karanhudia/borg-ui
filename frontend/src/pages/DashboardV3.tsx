/**
 * DashboardV3: operations dashboard for repository health, recent activity,
 * upcoming work, system resources, and storage.
 *
 * Numerics use a monospace stack so columns of digits align. Layout is a
 * 2-column bento on md+, single column below. Padding comes from Layout's
 * outer Container; this component adds none.
 */

import React from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Alert, Box, Button, Stack, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Activity, ArrowRight, Cpu, HardDrive } from 'lucide-react'
import { differenceInDays, formatDistanceToNow } from 'date-fns'
import { useTheme } from '../context/ThemeContext'
import { useAnalytics } from '../hooks/useAnalytics'
import { dashboardAPI } from '../services/api'
import { ActivityTimeline } from './dashboard-v3/ActivityTimeline'
import { ArcGauge, StorageDonut, SuccessDonut } from './dashboard-v3/charts'
import { DashboardSkeleton } from './dashboard-v3/DashboardSkeleton'
import { PulseDot } from './dashboard-v3/health'
import { UpcomingBackupsPanel } from './dashboard-v3/UpcomingBackupsPanel'
import { RepositoryHealthPanel } from './dashboard-v3/RepositoryHealthPanel'
import { ResourceGaugeGrid } from './dashboard-v3/ResourceGaugeGrid'
import { makeT, STATUS, TokenContext } from './dashboard-v3/tokens'
import type { DashboardOverview } from './dashboard-v3/types'
import { gaugeColor, toCompactGB } from './dashboard-v3/utils'

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

  const surface = {
    bgcolor: T.bgCard,
    border: `1px solid ${T.border}`,
    borderRadius: T.radius,
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
      {/* No outer bgcolor / padding — Layout's Container already provides this.
          overflowX: 'clip' prevents any internal min-content overflow from
          becoming a horizontal page scrollbar on mobile. */}
      <Box sx={{ color: T.textPrimary, minWidth: 0, overflowX: 'clip', width: '100%' }}>
        {/* Health banner */}
        <Box
          sx={{
            ...surface,
            mb: 2.5,
            px: { xs: 2, sm: 2.5 },
            py: { xs: 1.5, sm: 1.75 },
            display: 'flex',
            // Stack vertically on mobile so the health label, the 2x2 stats
            // grid, and the refresh button each get their own clean row
            // instead of awkward flex wrapping. Horizontal flow returns at
            // md+ where the row fits in one line.
            flexDirection: { xs: 'column', md: 'row' },
            alignItems: { xs: 'stretch', md: 'center' },
            justifyContent: 'space-between',
            flexWrap: { md: 'wrap' },
            gap: { xs: 1.75, md: 2 },
            borderColor: alpha(sc.color, 0.33),
          }}
        >
          <Stack direction="row" spacing={2} alignItems="center">
            <PulseDot color={sc.color} />
            <Box>
              <Typography
                sx={{
                  fontSize: '0.75rem',
                  fontWeight: 500,
                  color: T.textMuted,
                  mb: 0.25,
                }}
              >
                {t('dashboard.banner.systemStatus')}
              </Typography>
              <Typography
                sx={{
                  fontFamily: T.mono,
                  fontSize: '0.95rem',
                  fontWeight: 700,
                  lineHeight: 1.3,
                  color: sc.color,
                }}
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

          {/* Quick stats: 2x2 grid on xs (so labels do not get cramped or
              orphaned by flex wrap), natural row-with-gaps on sm+ where the
              4-up layout fits comfortably. */}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: 'repeat(2, minmax(0, 1fr))',
                sm: 'repeat(4, auto)',
              },
              columnGap: { xs: 2, sm: 3 },
              rowGap: { xs: 1.25, sm: 0 },
              alignItems: 'start',
              width: { xs: '100%', md: 'auto' },
            }}
          >
            {(
              [
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
                  cta:
                    totalAutomationCount === 0
                      ? {
                          label: t('dashboard.banner.stats.automationsCta'),
                          onClick: () => {
                            trackNavigation(EventAction.VIEW, {
                              section: 'dashboard',
                              destination: 'schedule',
                              source: 'automations_cta',
                            })
                            navigate('/schedule')
                          },
                        }
                      : undefined,
                },
                {
                  label: t('dashboard.banner.stats.storage'),
                  value: storage.total_size,
                  color: T.textPrimary,
                },
              ] as Array<{
                label: string
                value: React.ReactNode
                color: string
                cta?: { label: string; onClick: () => void }
              }>
            ).map(({ label, value, color, cta }) => (
              <Box key={label}>
                <Typography
                  sx={{
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    color: T.textMuted,
                  }}
                >
                  {label}
                </Typography>
                {cta ? (
                  // Render as the same <p>-based Typography as the non-CTA
                  // variant so font metrics match byte-for-byte. <button>
                  // brings user-agent font + line-box defaults that no amount
                  // of sx reset can fully neutralise; using role + tabIndex +
                  // keyboard handlers gets full button accessibility on a
                  // baseline-identical element.
                  <Typography
                    role="button"
                    tabIndex={0}
                    onClick={cta.onClick}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        cta.onClick()
                      }
                    }}
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      fontSize: '0.95rem',
                      lineHeight: 1.3,
                      color: T.blue,
                      cursor: 'pointer',
                      width: 'fit-content',
                      '&:hover': { textDecoration: 'underline' },
                      '&:focus-visible': {
                        outline: `2px solid ${T.blue}`,
                        outlineOffset: '2px',
                        borderRadius: '2px',
                      },
                    }}
                  >
                    {cta.label}
                  </Typography>
                ) : (
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
                )}
              </Box>
            ))}
          </Box>

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
              fontSize: '0.8125rem',
              minWidth: 0,
              // Right-align the refresh row on mobile (since it sits on its
              // own row under the stats grid) so it does not look orphaned.
              alignSelf: { xs: 'flex-end', md: 'auto' },
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
            // minmax(0, ...) on both tracks overrides the implicit min-content
            // floor that 1fr/auto would otherwise inherit. Without this, a
            // single child wider than its share of the row (e.g. a long repo
            // name) forces the column to grow and the grid to overflow.
            gridTemplateColumns: { xs: 'minmax(0, 1fr)', md: '200px minmax(0, 1fr)' },
            gap: 2.5,
            alignItems: 'start',
          }}
        >
          {/* Left: donut + resources */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            <Box sx={{ ...surface, p: 2 }}>
              {/* Header carries the label and the headline value side by side.
                  The donut below is a glanceable shape, not the focal point. */}
              <Stack
                direction="row"
                alignItems="baseline"
                justifyContent="space-between"
                sx={{ mb: 1.75 }}
              >
                <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
                  {t('dashboard.successDonut.label')}
                </Typography>
                <Typography
                  sx={{
                    fontFamily: T.mono,
                    fontSize: '0.95rem',
                    fontWeight: 700,
                    color:
                      summary.success_rate_30d >= 90
                        ? T.green
                        : summary.success_rate_30d >= 70
                          ? T.amber
                          : T.red,
                    lineHeight: 1,
                  }}
                >
                  {summary.success_rate_30d.toFixed(0)}%
                </Typography>
              </Stack>
              <SuccessDonut
                rate={summary.success_rate_30d}
                good={summary.successful_jobs_30d}
                total={summary.total_jobs_30d}
              />
              <Stack direction="row" justifyContent="space-between" sx={{ mt: 1.75, px: 0.5 }}>
                <Stack direction="row" alignItems="baseline" spacing={0.75}>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      color: T.green,
                      fontSize: '0.875rem',
                      lineHeight: 1,
                    }}
                  >
                    {summary.successful_jobs_30d}
                  </Typography>
                  <Typography sx={{ fontSize: '0.75rem', color: T.textMuted }}>
                    {t('dashboard.successDonut.passed')}
                  </Typography>
                </Stack>
                <Stack direction="row" alignItems="baseline" spacing={0.75}>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      color: summary.failed_jobs_30d > 0 ? T.red : T.textMuted,
                      fontSize: '0.875rem',
                      lineHeight: 1,
                    }}
                  >
                    {summary.failed_jobs_30d}
                  </Typography>
                  <Typography sx={{ fontSize: '0.75rem', color: T.textMuted }}>
                    {t('dashboard.successDonut.failed')}
                  </Typography>
                </Stack>
              </Stack>
            </Box>

            <Box sx={{ ...surface, p: 2 }}>
              <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 2 }}>
                <Cpu size={14} color={T.textMuted} />
                <Typography
                  sx={{
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    color: T.textPrimary,
                  }}
                >
                  {t('dashboard.resources')}
                </Typography>
              </Stack>
              <ResourceGaugeGrid>
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
                  sub={`${toCompactGB(sys.memory_total - sys.memory_available)}/${toCompactGB(sys.memory_total)}G`}
                />
                <ArcGauge
                  value={sys.disk_usage}
                  color={gaugeColor(sys.disk_usage, T)}
                  label={t('dashboard.diskAbbr')}
                  sub={`${toCompactGB(sys.disk_total - sys.disk_free)}/${toCompactGB(sys.disk_total)}G`}
                />
              </ResourceGaugeGrid>
            </Box>

            <UpcomingBackupsPanel tasks={ov.upcoming_tasks} />

            {/* Storage donut */}
            <Box sx={{ ...surface, p: 2 }}>
              {/* Total size moves into the header so it reads as data, not a
                  centered hero number. */}
              <Stack
                direction="row"
                alignItems="baseline"
                justifyContent="space-between"
                sx={{ mb: 1.75 }}
              >
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <HardDrive size={14} color={T.textMuted} />
                  <Typography sx={{ fontSize: '0.8125rem', fontWeight: 600, color: T.textPrimary }}>
                    {t('dashboard.banner.stats.storage')}
                  </Typography>
                </Stack>
                <Typography
                  sx={{
                    fontFamily: T.mono,
                    fontSize: '0.875rem',
                    fontWeight: 700,
                    color: T.textPrimary,
                    lineHeight: 1,
                  }}
                >
                  {storage.total_size}
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
                  <Typography sx={{ fontSize: '0.75rem', color: T.textMuted }}>
                    {t('dashboard.storageDonut.dedupRatio')}
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontSize: '0.8125rem',
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
              surface={surface}
              repos={repos}
              criticalCount={criticalCount}
              warningCount={warningCount}
              healthyCount={healthyCount}
              nowMs={nowMs}
              currentFailures={currentFailures}
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
            <Box sx={{ ...surface, p: 2.5 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1.75 }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Activity size={14} color={T.textMuted} />
                  <Typography
                    sx={{
                      fontSize: '0.8125rem',
                      fontWeight: 600,
                      color: T.textPrimary,
                    }}
                  >
                    {t('dashboard.recentActivity.last14Days')}
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={1.5} alignItems="center">
                  {/* Failed-marker legend lives in the header next to the
                      Full Log button so it does not claim its own row under
                      the chart. The ringed circle here visually matches the
                      ring drawn around failed dots in the SVG. */}
                  <Stack direction="row" spacing={0.65} alignItems="center">
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        border: `1.5px solid ${T.red}`,
                        flexShrink: 0,
                      }}
                    />
                    <Typography
                      sx={{ fontFamily: T.mono, fontSize: '0.75rem', color: T.textMuted }}
                    >
                      {t('dashboard.activityTimeline.legendFailed')}
                    </Typography>
                  </Stack>
                  <Button
                    size="small"
                    variant="text"
                    endIcon={<ArrowRight size={14} />}
                    onClick={() => {
                      trackNavigation(EventAction.VIEW, {
                        section: 'dashboard',
                        destination: 'activity',
                        source: 'recent_activity',
                      })
                      navigate('/activity')
                    }}
                    sx={{
                      fontSize: '0.8125rem',
                      color: T.textMuted,
                      '&:hover': { color: T.textPrimary, bgcolor: T.hoverBg },
                    }}
                  >
                    {t('dashboard.recentActivity.fullLog')}
                  </Button>
                </Stack>
              </Stack>

              {ov.activity_feed.length === 0 ? (
                <Typography
                  sx={{ color: T.textMuted, textAlign: 'center', py: 3, fontSize: '0.875rem' }}
                >
                  {t('dashboard.recentActivity.emptyRecorded')}
                </Typography>
              ) : (
                <ActivityTimeline activities={ov.activity_feed} />
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </TokenContext.Provider>
  )
}
