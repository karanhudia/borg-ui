import { Box, Chip, Link as MuiLink, Typography, alpha, useTheme } from '@mui/material'
import { AlertTriangle, Scissors } from 'lucide-react'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import CategoryToken from '../CategoryToken'
import SyncStateChip from '../archives/SyncStateChip'
import RebuildMenu from './RebuildMenu'
import StageTrack from './StageTrack'
import { elapsedSince, useNow } from './elapsed'
import { PLAN_COLOR, PLAN_LABEL } from '../../core/features'
import { parseBackendDate } from '../../utils/dateUtils'
import { HUB_GRID_COLUMNS, type RepositoryTrack, type StageState } from './repositoryTrack'
import type { HubRepository, RebuildStage } from '../../types/operations'

interface RepositoryHubRowProps {
  // Null for the system lane (package installs and other work with no
  // repository), which has a track but no derived data.
  repository: HubRepository | null
  track: RepositoryTrack | null
  historyAvailable: boolean
  totalHistoryRows: number
  onOpen: () => void
  onRetry: (stage: StageState) => void
  onRebuild: (stage: RebuildStage) => void
}

function ago(value: string): string {
  return formatDistanceToNow(parseBackendDate(value), { addSuffix: true })
}

function Cell({
  primary,
  secondary,
  muted = false,
}: {
  primary: React.ReactNode
  secondary?: React.ReactNode
  muted?: boolean
}) {
  return (
    <Box sx={{ minWidth: 0, gridColumn: { xs: '1 / -1', md: 'auto' } }}>
      <Typography
        variant="body2"
        sx={{
          fontWeight: muted ? 400 : 600,
          color: muted ? 'text.secondary' : 'text.primary',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {primary}
      </Typography>
      {secondary && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 1,
            mt: 0.25,
            color: 'text.secondary',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {secondary}
        </Box>
      )}
    </Box>
  )
}

function Flag({
  icon,
  label,
  color,
}: {
  icon: React.ReactNode
  label: string
  color: 'error.main' | 'warning.main'
}) {
  return (
    <Typography
      component="span"
      variant="caption"
      sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, color, fontWeight: 600 }}
    >
      {icon}
      {label}
    </Typography>
  )
}

function HistoryCell({
  repository,
  historyAvailable,
  totalHistoryRows,
}: {
  repository: HubRepository
  historyAvailable: boolean
  totalHistoryRows: number
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const { history, archives } = repository

  if (!historyAvailable) {
    return (
      <Cell
        primary={
          <Chip
            size="small"
            label={PLAN_LABEL.pro}
            sx={{
              height: 20,
              fontSize: '0.65rem',
              fontWeight: 700,
              bgcolor: alpha(PLAN_COLOR.pro, 0.15),
              color: PLAN_COLOR.pro,
            }}
          />
        }
      />
    )
  }
  if (history.rows === 0 && history.indexed === 0) {
    return <Cell muted primary={t('operations.background.hub.historyNone')} />
  }
  const share = totalHistoryRows > 0 ? Math.round((history.rows / totalHistoryRows) * 100) : null
  return (
    <Cell
      primary={t('operations.background.hub.historyCoverage', {
        indexed: history.indexed.toLocaleString(),
        total: archives.toLocaleString(),
      })}
      secondary={
        <>
          <Typography component="span" variant="caption">
            {t('operations.background.hub.historyRows', { count: history.rows })}
            {share != null && share > 0 && (
              <Typography
                component="span"
                variant="caption"
                sx={{ color: theme.palette.text.disabled, ml: 0.5 }}
              >
                ({t('operations.background.hub.historyShare', { percent: share })})
              </Typography>
            )}
          </Typography>
          {history.failed > 0 && (
            <Flag
              icon={<AlertTriangle size={12} />}
              color="error.main"
              label={t('operations.background.hub.historyFailed', { count: history.failed })}
            />
          )}
          {history.truncated > 0 && (
            <Flag
              icon={<Scissors size={12} />}
              color="warning.main"
              label={t('operations.background.hub.historyTruncated', {
                count: history.truncated,
              })}
            />
          )}
          {history.pending > 0 && (
            <Typography component="span" variant="caption">
              {t('operations.background.hub.historyPending', { count: history.pending })}
            </Typography>
          )}
        </>
      }
    />
  )
}

export default function RepositoryHubRow({
  repository,
  track,
  historyAvailable,
  totalHistoryRows,
  onOpen,
  onRetry,
  onRebuild,
}: RepositoryHubRowProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const running =
    track != null && (track.foreground != null || track.stages.some((s) => s.status === 'running'))
  const now = useNow(running)
  const name = repository?.repository_name ?? track?.repositoryName ?? ''
  const repositoryId = repository?.repository_id ?? track?.repositoryId ?? null
  const active = track != null && track.stages.some((s) => s.status !== 'idle')

  return (
    <Box
      data-testid="repository-row"
      sx={{
        py: 2,
        borderBottom: `1px solid ${theme.palette.divider}`,
        '&:last-of-type': { borderBottom: 'none' },
      }}
    >
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: HUB_GRID_COLUMNS,
          columnGap: 2,
          rowGap: 1.5,
          alignItems: 'start',
        }}
      >
        <Box sx={{ minWidth: 0 }}>
          {repositoryId != null ? (
            <Typography
              component="button"
              type="button"
              aria-label={t('operations.background.hub.openDetails', { repository: name })}
              onClick={onOpen}
              sx={{
                all: 'unset',
                cursor: 'pointer',
                font: 'inherit',
                fontWeight: 600,
                color: 'text.primary',
                '&:hover': { textDecoration: 'underline' },
                '&:focus-visible': {
                  outline: `2px solid ${theme.palette.primary.main}`,
                  outlineOffset: 2,
                  borderRadius: 0.5,
                },
              }}
            >
              {name}
            </Typography>
          ) : (
            <Typography sx={{ fontWeight: 600 }}>{name}</Typography>
          )}
          {track?.foreground && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.75, flexWrap: 'wrap' }}>
              <CategoryToken category={track.foreground.category} />
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {t('operations.background.foregroundRunning', {
                  kind: t(`operations.kind.${track.foreground.kind}`),
                  elapsed: elapsedSince(track.foreground.started_at, now),
                })}
                {track.foreground.backup_plan_name
                  ? ` (${t('operations.background.plan')}: ${track.foreground.backup_plan_name})`
                  : ''}
              </Typography>
              {repositoryId != null && (
                <MuiLink
                  component={RouterLink}
                  to={`/activity?repository_id=${repositoryId}`}
                  variant="body2"
                >
                  {t('operations.background.viewRuns')}
                </MuiLink>
              )}
            </Box>
          )}
        </Box>

        {repository ? (
          <>
            <Cell
              muted={repository.last_stats_at == null}
              primary={
                repository.last_stats_at
                  ? t('operations.background.hub.statsRefreshed', {
                      ago: ago(repository.last_stats_at),
                    })
                  : t('operations.background.hub.statsNever')
              }
            />
            <Box sx={{ minWidth: 0, gridColumn: { xs: '1 / -1', md: 'auto' } }}>
              <SyncStateChip
                state={repository.sync_state}
                lastSyncedAt={repository.last_synced_at}
                showRebuild={false}
              />
              <Typography
                variant="caption"
                sx={{
                  display: 'block',
                  mt: 0.5,
                  color: 'text.secondary',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {t('operations.background.hub.rowArchives', { count: repository.archives })}
              </Typography>
            </Box>
            <HistoryCell
              repository={repository}
              historyAvailable={historyAvailable}
              totalHistoryRows={totalHistoryRows}
            />
          </>
        ) : (
          <Box sx={{ display: { xs: 'none', md: 'block' }, gridColumn: { md: 'span 3' } }} />
        )}

        <Box
          sx={{
            justifySelf: 'end',
            mt: -0.5,
            gridColumn: { xs: '2', md: 'auto' },
            gridRow: { xs: '1', md: 'auto' },
          }}
        >
          {repositoryId != null && (
            <RebuildMenu
              variant="icon"
              label={t('operations.background.rebuildRow', { repository: name })}
              onSelect={onRebuild}
            />
          )}
        </Box>
      </Box>

      {active && track && (
        <Box
          sx={{
            mt: 1.5,
            mx: -2.5,
            px: 2.5,
            py: 1.5,
            bgcolor: alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.08 : 0.04),
          }}
        >
          <StageTrack stages={track.stages} now={now} onRetry={onRetry} />
        </Box>
      )}
    </Box>
  )
}
