import {
  Box,
  Chip,
  IconButton,
  Link as MuiLink,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { AlertTriangle, ChevronRight, RotateCw, Scissors } from 'lucide-react'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import CategoryToken from '../CategoryToken'
import SyncStateChip from '../archives/SyncStateChip'
import StageTrack from './StageTrack'
import { elapsedSince, useNow } from './elapsed'
import { PLAN_COLOR, PLAN_LABEL } from '../../core/features'
import { parseBackendDate } from '../../utils/dateUtils'
import { HUB_GRID_COLUMNS, type RepositoryTrack, type StageState } from './repositoryTrack'
import type { HubRepository } from '../../types/operations'
import type { HistoryCapability } from '../../types/archives'

interface RepositoryHubRowProps {
  // Null for the system lane (package installs and other work with no
  // repository), which has a track but no derived data.
  repository: HubRepository | null
  track: RepositoryTrack | null
  historyAvailable: boolean
  totalHistoryRows: number
  onOpen: () => void
  onRetry: (stage: StageState) => void
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
          fontWeight: muted ? 400 : 500,
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
  const mode = repository.index_mode ?? 'full'
  // The repository's own reason for having no history stage (an agent
  // executes it), next to the plan-wide `historyAvailable`.
  const historyCapability: HistoryCapability = repository.history_capability ?? 'available'

  // Mode before plan (spec 6.8): an upgrade would not start indexing this
  // repository, so the Pro chip below would be a false promise.
  if (mode !== 'full') {
    return (
      <Cell
        muted
        primary={t(
          mode === 'archives'
            ? 'operations.background.hub.modeArchives'
            : 'operations.background.hub.modeOff'
        )}
      />
    )
  }
  // An index built before the repository moved to an agent is still real
  // data (the Changes tab serves it); only a repository with none says so.
  // Ahead of the plan chip either way: an upgrade would not unlock the
  // stage here, so without the plan the reason is the whole answer.
  if (
    historyCapability === 'agent_unsupported' &&
    (!historyAvailable || (history.indexed === 0 && history.rows === 0))
  ) {
    return <Cell muted primary={t('operations.background.hub.historyAgentUnsupported')} />
  }
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
        py: 1.5,
        mx: -2.5,
        px: 2.5,
        borderBottom: `1px solid ${theme.palette.divider}`,
        '&:last-of-type': { borderBottom: 'none' },
        transition: 'background-color 120ms ease',
        '&:hover': { bgcolor: alpha(theme.palette.text.primary, 0.02) },
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
              // Reads as a link, the way "View index runs" and the
              // breadcrumbs do: primary colour, underline on hover, and a
              // small chevron that says there is somewhere to go.
              sx={{
                all: 'unset',
                cursor: 'pointer',
                font: 'inherit',
                fontSize: theme.typography.body2.fontSize,
                fontWeight: 600,
                color: 'primary.main',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 0.25,
                '& svg': { opacity: 0.55, transition: 'opacity 120ms ease, transform 120ms ease' },
                '&:hover': { textDecoration: 'underline' },
                '&:hover svg': { opacity: 1, transform: 'translateX(2px)' },
                '&:focus-visible': {
                  outline: `2px solid ${theme.palette.primary.main}`,
                  outlineOffset: 2,
                  borderRadius: 0.5,
                },
              }}
            >
              {name}
              <ChevronRight size={14} aria-hidden />
            </Typography>
          ) : (
            <Typography variant="body2" sx={{ fontWeight: 600 }}>
              {name}
            </Typography>
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
            <Box sx={{ minWidth: 0, gridColumn: { xs: '1 / -1', md: 'auto' } }}>
              {/* An amber "out of date" chip on a repository nobody indexes
                  is the same false alarm the summary counts drop (spec 6.8),
                  so the state is stated plainly instead. */}
              {(repository.index_mode ?? 'full') === 'off' ? (
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {t('operations.background.hub.syncOff')}
                </Typography>
              ) : (
                <SyncStateChip
                  state={repository.sync_state}
                  lastSyncedAt={repository.last_synced_at}
                  showRebuild={false}
                />
              )}
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
            // The stages are chosen in the dialog, next to the run and the
            // archives that need a look, so the icon opens that rather
            // than a second menu with its own explanation.
            <Tooltip title={t('operations.background.rebuildRow', { repository: name })}>
              <IconButton
                size="small"
                aria-label={t('operations.background.rebuildRow', { repository: name })}
                onClick={onOpen}
              >
                <RotateCw size={16} />
              </IconButton>
            </Tooltip>
          )}
        </Box>
      </Box>

      {/* Nothing is refreshed for an `off` repository, so the four empty
          stage columns would read as work that failed to start (spec 6.8).
          A manual one-off run still shows its track, below. */}
      {repository && (repository.index_mode ?? 'full') === 'off' && !active && (
        <Typography variant="caption" sx={{ display: 'block', mt: 1.5, color: 'text.secondary' }}>
          {t('operations.background.hub.trackOff')}
        </Typography>
      )}

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
