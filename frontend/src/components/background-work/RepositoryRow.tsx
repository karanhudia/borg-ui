import { useEffect, useState } from 'react'
import {
  Box,
  Button,
  LinearProgress,
  Link as MuiLink,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import CategoryToken from '../CategoryToken'
import RebuildMenu from './RebuildMenu'
import { formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'
import {
  REBUILD_STAGE_FOR,
  TRACK_GRID_COLUMNS,
  type RepositoryTrack,
  type StageState,
} from './repositoryTrack'
import type { RebuildStage } from '../../types/operations'

interface RepositoryRowProps {
  track: RepositoryTrack
  onOpen: () => void
  onRetry: (stage: StageState) => void
  onRebuild: (stage: RebuildStage) => void
}

function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [active])
  return now
}

function elapsedSince(startedAt: string | null, now: number): string {
  if (!startedAt) return ''
  const seconds = Math.max(0, Math.floor((now - parseBackendDate(startedAt).getTime()) / 1000))
  return formatDurationSeconds(seconds)
}

function StageSegment({
  stage,
  now,
  onRetry,
}: {
  stage: StageState
  now: number
  onRetry: (stage: StageState) => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const barColor = {
    idle: 'transparent',
    done: theme.palette.success.main,
    running: theme.palette.primary.main,
    waiting: 'transparent',
    failed: theme.palette.error.main,
  }[stage.status]
  const outline =
    stage.status === 'waiting'
      ? `1px dashed ${alpha(theme.palette.text.primary, 0.35)}`
      : stage.status === 'idle'
        ? `1px solid ${theme.palette.divider}`
        : 'none'
  const progress = stage.operation?.progress_percent ?? null

  let caption: string | null = null
  if (stage.status === 'done') caption = t('operations.background.stageDone')
  else if (stage.status === 'failed') caption = t('operations.background.stageFailed')
  else if (stage.status === 'waiting' && stage.reason)
    caption = t(`operations.background.reason.${stage.reason}`)
  else if (stage.status === 'running') {
    const elapsed = elapsedSince(stage.operation?.started_at ?? null, now)
    const counted =
      stage.operation?.progress_current != null && stage.operation?.progress_total != null
        ? `${stage.operation.progress_current}/${stage.operation.progress_total}`
        : null
    caption = [elapsed, counted].filter(Boolean).join(', ')
  }

  return (
    <Box data-testid={`stage-${stage.key}`} data-status={stage.status} sx={{ minWidth: 0 }}>
      <Typography
        variant="caption"
        sx={{ display: { xs: 'block', md: 'none' }, color: 'text.secondary', mb: 0.5 }}
      >
        {t(`operations.background.stage.${stage.key}`)}
      </Typography>
      {stage.status === 'running' ? (
        <LinearProgress
          variant={progress != null ? 'determinate' : 'indeterminate'}
          value={progress ?? undefined}
          sx={{ height: 6, borderRadius: 3 }}
        />
      ) : (
        <Box
          sx={{
            height: 6,
            borderRadius: 3,
            bgcolor: barColor,
            border: outline,
            boxSizing: 'border-box',
          }}
        />
      )}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 0.5, minHeight: 24 }}>
        {caption && (
          <Typography
            variant="caption"
            noWrap
            sx={{
              color: stage.status === 'failed' ? 'error.main' : 'text.secondary',
              fontWeight: stage.status === 'running' ? 600 : 400,
            }}
          >
            {caption}
          </Typography>
        )}
        {stage.status === 'failed' && REBUILD_STAGE_FOR[stage.key] && (
          <Button
            size="small"
            color="error"
            variant="text"
            sx={{ minWidth: 0, px: 0.75, py: 0, fontSize: '0.75rem' }}
            onClick={(event) => {
              event.stopPropagation()
              onRetry(stage)
            }}
          >
            {t('operations.background.retry')}
          </Button>
        )}
      </Box>
    </Box>
  )
}

export default function RepositoryRow({ track, onOpen, onRetry, onRebuild }: RepositoryRowProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const running = track.foreground != null || track.stages.some((s) => s.status === 'running')
  const now = useNow(running)

  return (
    <Box
      data-testid="repository-row"
      sx={{
        display: 'grid',
        gridTemplateColumns: TRACK_GRID_COLUMNS,
        columnGap: 2,
        rowGap: 1.5,
        alignItems: 'start',
        py: 2,
        borderBottom: `1px solid ${theme.palette.divider}`,
        '&:last-of-type': { borderBottom: 'none' },
      }}
    >
      <Box sx={{ minWidth: 0 }}>
        {track.repositoryId != null ? (
          <Typography
            component="button"
            type="button"
            aria-label={t('operations.background.openTrack', { repository: track.repositoryName })}
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
            {track.repositoryName}
          </Typography>
        ) : (
          <Typography sx={{ fontWeight: 600 }}>{track.repositoryName}</Typography>
        )}
        {track.foreground && (
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
            {track.repositoryId != null && (
              <MuiLink
                component={RouterLink}
                to={`/activity?repository_id=${track.repositoryId}`}
                variant="body2"
              >
                {t('operations.background.viewRuns')}
              </MuiLink>
            )}
          </Box>
        )}
      </Box>
      {track.stages.map((stage) => (
        <StageSegment key={stage.key} stage={stage} now={now} onRetry={onRetry} />
      ))}
      <Box sx={{ justifySelf: { xs: 'start', md: 'end' }, mt: -0.5 }}>
        {track.repositoryId != null && (
          <RebuildMenu
            variant="icon"
            label={t('operations.background.rebuildRow', { repository: track.repositoryName })}
            onSelect={onRebuild}
          />
        )}
      </Box>
    </Box>
  )
}
