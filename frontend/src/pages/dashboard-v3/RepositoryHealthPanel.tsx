import { Box, Chip, Stack, Typography } from '@mui/material'
import { Server } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { DimStatusGrid, PulseDot, ScheduleBadge } from './health'
import { STATUS, type Tokens } from './tokens'
import type { DashboardOverview } from './types'

type RepositoryHealth = DashboardOverview['repository_health']

export function RepositoryHealthPanel({
  T,
  surface,
  repos,
  criticalCount,
  warningCount,
  healthyCount,
  nowMs,
  onOpenRepositories,
}: {
  T: Tokens
  surface: Record<string, unknown>
  repos: RepositoryHealth
  criticalCount: number
  warningCount: number
  healthyCount: number
  nowMs: number
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
                border: `1px solid ${T.red}30`,
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
                border: `1px solid ${T.amber}30`,
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
                border: `1px solid ${T.green}30`,
                fontFamily: T.mono,
              }}
            />
          )}
        </Stack>
      </Stack>

      <Box
        sx={{
          display: 'grid',
          // Auto-fit with a 300px floor lets cards reflow from 1 column (narrow viewports)
          // up to 4+ columns on wide screens without a hard breakpoint cap. The 300px
          // floor is sized for the worst-case DE top row (TYPE chip + "Nur Beobachtung"
          // observe chip + ScheduleBadge) plus padding, so the German build doesn't
          // wrap the chip strip onto a second line.
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
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

          return (
            <Box
              key={repo.id}
              onClick={onOpenRepositories}
              sx={{
                bgcolor: cs.dim,
                border: `1px solid ${cs.color}30`,
                borderRadius: '10px',
                p: 1.25,
                cursor: 'pointer',
                transition: 'border-color 0.18s, background-color 0.18s',
                '&:hover': {
                  borderColor: cs.color + '80',
                  bgcolor: cs.color + '12',
                },
              }}
            >
              {/* ── Top row: status dot + type chip | next-run pill ── */}
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 0.55 }}
              >
                <Stack direction="row" spacing={0.75} alignItems="center">
                  <PulseDot color={cs.color} />
                  <Chip
                    label={repo.type.toUpperCase()}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.6875rem',
                      bgcolor: T.repoBadgeBg,
                      color: T.textMuted,
                      border: `1px solid ${T.border}`,
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
                        border: `1px solid ${T.indigo}30`,
                        fontFamily: T.mono,
                        px: 0.5,
                      }}
                    />
                  )}
                </Stack>
                <ScheduleBadge
                  nextRun={repo.next_run}
                  hasSchedule={repo.has_schedule}
                  scheduleEnabled={repo.schedule_enabled}
                  scheduleName={repo.schedule_name}
                  scheduleTimezone={repo.schedule_timezone}
                  nowMs={nowMs}
                />
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
                      border: `1px solid ${T.blue}25`,
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
