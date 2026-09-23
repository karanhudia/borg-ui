import {
  Box,
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
import CurrentStage from './CurrentStage'
import { elapsedSince, useNow } from './elapsed'
import { parseBackendDate } from '../../utils/dateUtils'
import {
  HUB_GRID_COLUMNS,
  currentStage,
  type RepositoryTrack,
  type StageState,
} from './repositoryTrack'
import type { HubRepository } from '../../types/operations'

interface RepositoryHubRowProps {
  // Null for the system lane (package installs and other work with no
  // repository), which has a track but no derived data.
  repository: HubRepository | null
  track: RepositoryTrack | null
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

// When any of the repository's derived data last changed, and the one
// thing about it that needs a look, if any. Which stage kept what lives in
// the repository's dialog (RepositoryDataTiles), so a new stage never adds
// a column here.
function LastUpdatedCell({ repository }: { repository: HubRepository }) {
  const { t } = useTranslation()
  const mode = repository.index_mode ?? 'full'
  if (mode === 'off') {
    return <Cell muted primary={t('operations.background.hub.modeOff')} />
  }
  const newest = [repository.last_synced_at, repository.last_history_at, repository.last_stats_at]
    .filter((value): value is string => value != null)
    .sort((x, y) => parseBackendDate(y).getTime() - parseBackendDate(x).getTime())[0]
  const { history } = repository
  const flags = (
    <>
      {repository.sync_state !== 'fresh' && (
        <SyncStateChip state={repository.sync_state} lastSyncedAt={repository.last_synced_at} />
      )}
      {mode === 'full' && history.failed > 0 && (
        <Flag
          icon={<AlertTriangle size={12} />}
          color="error.main"
          label={t('operations.background.hub.historyFailed', { count: history.failed })}
        />
      )}
      {mode === 'full' && history.truncated > 0 && (
        <Flag
          icon={<Scissors size={12} />}
          color="warning.main"
          label={t('operations.background.hub.historyTruncated', { count: history.truncated })}
        />
      )}
    </>
  )
  const needsLook =
    repository.sync_state !== 'fresh' ||
    (mode === 'full' && (history.failed > 0 || history.truncated > 0))
  return (
    <Cell
      muted={newest == null}
      primary={
        newest
          ? t('operations.background.hub.updatedAgo', { ago: ago(newest) })
          : t('operations.background.hub.updatedNever')
      }
      secondary={
        needsLook ? (
          flags
        ) : (
          <Typography variant="caption">
            {t('operations.background.hub.rowArchives', { count: repository.archives })}
          </Typography>
        )
      }
    />
  )
}

export default function RepositoryHubRow({
  repository,
  track,
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
  const stage = currentStage(track)

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

        <CurrentStage
          stage={stage}
          now={now}
          onRetry={onRetry}
          // Nothing is refreshed for an `off` repository, so "Idle" would
          // promise work that never comes (spec 6.8). A manual one-off run
          // still shows its stage.
          restLabel={
            repository && (repository.index_mode ?? 'full') === 'off'
              ? t('operations.background.hub.trackOff')
              : t('operations.background.strip.idle')
          }
        />

        {repository ? (
          <LastUpdatedCell repository={repository} />
        ) : (
          <Box sx={{ display: { xs: 'none', md: 'block' } }} />
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
    </Box>
  )
}
