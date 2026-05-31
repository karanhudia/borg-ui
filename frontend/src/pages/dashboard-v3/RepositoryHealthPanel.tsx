import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Server, XCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { formatDateTimeFull } from '../../utils/dateUtils'
import { translateBackendKey } from '../../utils/translateBackendKey'
import { DimStatusGrid, PulseDot, ScheduleBadge } from './health'
import { STATUS, TYPE_COLOR, type Tokens } from './tokens'
import type { DashboardOverview } from './types'

type RepositoryHealth = DashboardOverview['repository_health']
type RepoCardData = RepositoryHealth[number]
type ActivityFeed = DashboardOverview['activity_feed']

/**
 * Two small chips rendered identically on both the compact and full repo
 * card variants: the destination-type chip (colored by `TYPE_COLOR`) and an
 * optional "Observe Only" chip when the repo is in observe mode.
 */
function RepoTypeChips({ repo, T }: { repo: RepoCardData; T: Tokens }) {
  const { t } = useTranslation()
  const tColor = TYPE_COLOR[repo.type.toLowerCase()] ?? T.textMuted
  return (
    <>
      <Chip
        label={repo.type.toUpperCase()}
        size="small"
        sx={{
          height: 20,
          fontSize: '0.6875rem',
          bgcolor: alpha(tColor, 0.08),
          color: tColor,
          border: `1px solid ${alpha(tColor, 0.25)}`,
          fontFamily: T.mono,
          px: 0.5,
        }}
      />
      {repo.mode === 'observe' && (
        <Chip
          label={t('repositories.observeOnly')}
          size="small"
          sx={{
            height: 20,
            fontSize: '0.6875rem',
            bgcolor: T.indigoDim,
            color: T.indigo,
            border: `1px solid ${alpha(T.indigo, 0.19)}`,
            fontFamily: T.mono,
            px: 0.5,
          }}
        />
      )}
    </>
  )
}

export function RepositoryHealthPanel({
  T,
  surface,
  repos,
  criticalCount,
  warningCount,
  healthyCount,
  nowMs,
  currentFailures,
  onOpenRepositories,
}: {
  T: Tokens
  surface: Record<string, unknown>
  repos: RepositoryHealth
  criticalCount: number
  warningCount: number
  healthyCount: number
  nowMs: number
  currentFailures: ActivityFeed
  onOpenRepositories: () => void
}) {
  const { t } = useTranslation()

  return (
    <Box sx={{ ...surface, p: 2.5 }}>
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Server size={14} color={T.textMuted} />
          <Typography
            sx={{
              fontSize: '0.8125rem',
              fontWeight: 600,
              color: T.textPrimary,
            }}
          >
            {t('dashboard.repositoryHealth.title')}
          </Typography>
        </Stack>
        <Stack direction="row" spacing={0.75}>
          {criticalCount > 0 && (
            <Chip
              label={t('dashboard.banner.critical', { count: criticalCount })}
              size="small"
              sx={{
                height: 22,
                fontSize: '0.75rem',
                bgcolor: T.redDim,
                color: T.red,
                border: `1px solid ${alpha(T.red, 0.19)}`,
                fontFamily: T.mono,
              }}
            />
          )}
          {warningCount > 0 && (
            <Chip
              label={t('dashboard.banner.warnChip', { count: warningCount })}
              size="small"
              sx={{
                height: 22,
                fontSize: '0.75rem',
                bgcolor: T.amberDim,
                color: T.amber,
                border: `1px solid ${alpha(T.amber, 0.19)}`,
                fontFamily: T.mono,
              }}
            />
          )}
          {healthyCount > 0 && (
            <Chip
              label={t('dashboard.banner.okChip', { count: healthyCount })}
              size="small"
              sx={{
                height: 22,
                fontSize: '0.75rem',
                bgcolor: T.greenDim,
                color: T.green,
                border: `1px solid ${alpha(T.green, 0.19)}`,
                fontFamily: T.mono,
              }}
            />
          )}
        </Stack>
      </Stack>

      {currentFailures.length > 0 && (
        // Recent failures strip lives here, alongside the cards they reference,
        // instead of inside the Activity Timeline panel. Failure context is
        // operational and belongs next to the repos the user would act on.
        <Box
          sx={{
            mb: 2,
            border: `1px solid ${alpha(T.red, 0.2)}`,
            borderRadius: '10px',
            bgcolor: alpha(T.red, 0.05),
            p: 1.25,
          }}
        >
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.75 }}>
            <XCircle size={14} color={T.red} />
            <Typography
              sx={{
                fontSize: '0.8125rem',
                fontWeight: 600,
                color: T.textPrimary,
              }}
            >
              {t('dashboard.recentFailures.title')}
            </Typography>
          </Stack>
          <Stack spacing={0.4}>
            {currentFailures.slice(0, 3).map((a) => (
              <Stack
                key={`${a.type}-${a.id}`}
                direction="row"
                spacing={1}
                alignItems="baseline"
                sx={{ minWidth: 0 }}
              >
                <Typography
                  sx={{
                    fontFamily: T.mono,
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    color: T.textPrimary,
                    flexShrink: 0,
                  }}
                >
                  {a.repository}
                </Typography>
                <Tooltip title={formatDateTimeFull(a.timestamp)} arrow placement="top">
                  <Typography
                    sx={{
                      cursor: 'help',
                      fontSize: '0.75rem',
                      color: T.textMuted,
                      flexShrink: 0,
                    }}
                  >
                    {formatDistanceToNow(new Date(a.timestamp), { addSuffix: true })}
                  </Typography>
                </Tooltip>
                {a.error && (
                  <Tooltip title={translateBackendKey(a.error)} arrow placement="top">
                    <Typography
                      sx={{
                        fontFamily: T.mono,
                        fontSize: '0.75rem',
                        color: T.textMuted,
                        flexGrow: 1,
                        minWidth: 0,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        cursor: 'help',
                      }}
                    >
                      {translateBackendKey(a.error)}
                    </Typography>
                  </Tooltip>
                )}
              </Stack>
            ))}
            {currentFailures.length > 3 && (
              <Typography
                sx={{
                  fontSize: '0.75rem',
                  color: T.textMuted,
                  fontStyle: 'italic',
                  pt: 0.25,
                }}
              >
                {t('dashboard.recentFailures.moreCount', {
                  count: currentFailures.length - 3,
                })}
              </Typography>
            )}
          </Stack>
        </Box>
      )}

      <Box
        sx={{
          display: 'grid',
          // Auto-fit with a 300px floor lets cards reflow from 1 column (narrow viewports)
          // up to 4+ columns on wide screens without a hard breakpoint cap. The 300px
          // floor is sized for the worst-case DE top row (TYPE chip + "Nur Beobachtung"
          // observe chip + ScheduleBadge) plus padding, so the German build doesn't
          // wrap the chip strip onto a second line.
          // Single column on xs (any min larger than the viewport would
          // overflow). Auto-fit at sm+ where the 300px floor fits cleanly
          // and reflows from 1 to 4+ columns as width grows.
          gridTemplateColumns: {
            xs: 'minmax(0, 1fr)',
            sm: 'repeat(auto-fit, minmax(min(100%, 300px), 1fr))',
          },
          gap: 1.5,
        }}
      >
        {repos.map((repo) => {
          // Card color follows the backend's aggregate repository health.
          // Failed restore verification can make the card critical because recovery is at risk.
          const cardStatus: keyof typeof STATUS =
            repo.health_status === 'critical'
              ? 'critical'
              : repo.health_status === 'warning'
                ? 'warning'
                : 'healthy'
          const cs = STATUS[cardStatus]

          // Compact one-liner card for healthy repos. The dimension footer on a
          // healthy card is just "everything's fine" four times; collapse to a
          // single horizontal row so urgency (warning/critical) gets the visual
          // weight. Same outer surface, border, hover, and click target.
          if (repo.health_status === 'healthy') {
            const lastBackupLabel = repo.last_backup
              ? formatDistanceToNow(new Date(repo.last_backup), { addSuffix: false })
              : t('common.never')

            return (
              <Box
                key={repo.id}
                onClick={onOpenRepositories}
                sx={{
                  bgcolor: T.bgCard,
                  border: `1px solid ${alpha(cs.color, 0.38)}`,
                  borderRadius: '10px',
                  p: 1.25,
                  cursor: 'pointer',
                  transition: 'border-color 0.18s, background-color 0.18s',
                  '&:hover': {
                    borderColor: alpha(cs.color, 0.5),
                    bgcolor: alpha(cs.color, 0.03),
                  },
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <PulseDot color={cs.color} />
                  <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                    <Typography
                      sx={{
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        color: T.textPrimary,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {repo.name}
                    </Typography>
                    <Stack
                      direction="row"
                      spacing={0.75}
                      alignItems="center"
                      sx={{ mt: 0.25, minWidth: 0 }}
                    >
                      <RepoTypeChips repo={repo} T={T} />
                      <Typography
                        sx={{
                          fontFamily: T.mono,
                          fontSize: '0.75rem',
                          color: T.textMuted,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          minWidth: 0,
                        }}
                      >
                        {t('dashboard.repositoryHealth.archiveCountShort', {
                          count: repo.archive_count,
                        })}
                        {' · '}
                        {repo.total_size}
                      </Typography>
                    </Stack>
                  </Box>
                  <Stack alignItems="flex-end" spacing={0.4} sx={{ flexShrink: 0 }}>
                    <Typography
                      sx={{
                        fontFamily: T.mono,
                        fontSize: '0.75rem',
                        color: T.textMuted,
                        lineHeight: 1.2,
                        textAlign: 'right',
                      }}
                    >
                      {lastBackupLabel}
                    </Typography>
                    {repo.has_schedule && (
                      <ScheduleBadge
                        nextRun={repo.next_run}
                        hasSchedule={repo.has_schedule}
                        scheduleEnabled={repo.schedule_enabled}
                        scheduleName={repo.schedule_name}
                        scheduleTimezone={repo.schedule_timezone}
                        nowMs={nowMs}
                      />
                    )}
                  </Stack>
                </Stack>
              </Box>
            )
          }

          return (
            <Box
              key={repo.id}
              onClick={onOpenRepositories}
              sx={{
                // Subtle status tint (~5% alpha) on critical/warning cards so they
                // register as different at a glance, without the wall-of-color
                // effect the original 15% tints created. Healthy cards stay on
                // the brand-emerald T.bgCard via the compact branch above.
                // See `tokens.tsx` for the two-tone surface documentation.
                bgcolor: alpha(cs.color, 0.05),
                border: `1px solid ${alpha(cs.color, 0.38)}`,
                borderRadius: '10px',
                p: 1.25,
                cursor: 'pointer',
                transition: 'border-color 0.18s, background-color 0.18s',
                '&:hover': {
                  borderColor: alpha(cs.color, 0.5),
                  bgcolor: alpha(cs.color, 0.08),
                },
              }}
            >
              {/* Top row: status dot + type chip | next-run pill */}
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 0.55 }}
              >
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <PulseDot color={cs.color} />
                  <RepoTypeChips repo={repo} T={T} />
                </Stack>
                {/* Skip the badge entirely when there is no schedule. The absence of a */}
                {/* schedule pill already conveys "manual"; the literal label was noise. */}
                {repo.has_schedule && (
                  <ScheduleBadge
                    nextRun={repo.next_run}
                    hasSchedule={repo.has_schedule}
                    scheduleEnabled={repo.schedule_enabled}
                    scheduleName={repo.schedule_name}
                    scheduleTimezone={repo.schedule_timezone}
                    nowMs={nowMs}
                  />
                )}
              </Stack>

              {/* Name + stats */}
              <Typography
                sx={{
                  fontSize: '0.875rem',
                  fontWeight: 600,
                  color: T.textPrimary,
                  mb: 0.4,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {repo.name}
              </Typography>
              <Stack direction="row" spacing={1.5} sx={{ mb: 0.75 }}>
                <Typography sx={{ fontFamily: T.mono, fontSize: '0.75rem', color: T.textMuted }}>
                  {t('dashboard.repositoryHealth.archiveCountShort', {
                    count: repo.archive_count,
                  })}
                </Typography>
                <Typography sx={{ fontFamily: T.mono, fontSize: '0.75rem', color: T.textMuted }}>
                  {repo.total_size}
                </Typography>
              </Stack>

              {Boolean(repo.backup_plan_count) && (
                <Stack
                  direction="row"
                  spacing={0.75}
                  alignItems="center"
                  sx={{ mb: 0.75, minWidth: 0 }}
                >
                  <Chip
                    label={t('dashboard.repositoryHealth.planCount', {
                      count: repo.backup_plan_count,
                    })}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.75rem',
                      bgcolor: T.blueDim,
                      color: T.blue,
                      border: `1px solid ${alpha(T.blue, 0.15)}`,
                      fontFamily: T.mono,
                    }}
                  />
                  {repo.backup_plan_names?.slice(0, 1).map((name) => (
                    <Typography
                      key={name}
                      sx={{
                        fontSize: '0.75rem',
                        color: T.textMuted,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        minWidth: 0,
                      }}
                    >
                      {name}
                    </Typography>
                  ))}
                </Stack>
              )}

              {/* ── Divider ── */}
              <Box sx={{ height: '1px', bgcolor: T.border, mb: 0.65 }} />

              {/* ── Dimension status row: BACKUP · CHECK · COMPACT · RESTORE ── */}
              <DimStatusGrid
                mode={repo.mode}
                dim={repo.dimension_health}
                lastBackup={repo.last_backup}
                lastCheck={repo.last_check}
                lastCompact={
                  repo.mode === 'observe' ? String(repo.archive_count) : repo.last_compact
                }
                lastRestoreCheck={repo.last_restore_check}
                latestRestoreCheckStatus={repo.latest_restore_check_status}
                latestRestoreCheckError={repo.latest_restore_check_error}
                restoreCheckConfigured={repo.restore_check_configured}
              />
            </Box>
          )
        })}
      </Box>
      {repos.length === 0 && (
        <Typography sx={{ color: T.textMuted, textAlign: 'center', py: 4, fontSize: '0.875rem' }}>
          {t('dashboard.noRepositoriesShort')}
        </Typography>
      )}
    </Box>
  )
}
