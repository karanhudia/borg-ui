import { Box, Button, LinearProgress, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { elapsedSince } from './elapsed'
import {
  HUB_GRID_COLUMNS,
  REBUILD_STAGE_FOR,
  STAGE_ORDER,
  type StageState,
} from './repositoryTrack'

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
    skipped: alpha(theme.palette.text.primary, 0.12),
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
  else if (stage.status === 'skipped') caption = t('operations.background.stageSkipped')
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
      {/* On desktop the table header above the track names the column;
          on small screens the columns stack, so each segment says which
          stage it is. */}
      <Typography
        variant="caption"
        sx={{
          display: { xs: 'block', md: 'none' },
          color: 'text.secondary',
          fontWeight: 500,
          mb: 0.5,
        }}
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

interface StageTrackProps {
  stages: StageState[]
  now: number
  onRetry: (stage: StageState) => void
}

// One run's stages laid out on the hub grid, so every stage sits under
// the table column that describes it: connect under the repository name,
// then stats, archive list, and file history. A stage the run never had
// leaves its column empty rather than shifting the others.
export default function StageTrack({ stages, now, onRetry }: StageTrackProps) {
  return (
    <Box
      data-testid="stage-track"
      sx={{
        display: 'grid',
        gridTemplateColumns: HUB_GRID_COLUMNS,
        columnGap: 2,
        rowGap: 1.5,
        alignItems: 'start',
      }}
    >
      {STAGE_ORDER.map((key) => {
        const stage = stages.find((s) => s.key === key)
        const present = stage != null && stage.status !== 'idle'
        return (
          <Box
            key={key}
            data-testid={`stage-cell-${key}`}
            data-stage={key}
            data-empty={present ? 'false' : 'true'}
            sx={{
              minWidth: 0,
              display: { xs: present ? 'block' : 'none', md: 'block' },
              gridColumn: { xs: '1 / -1', md: 'auto' },
            }}
          >
            {present && stage && <StageSegment stage={stage} now={now} onRetry={onRetry} />}
          </Box>
        )
      })}
      <Box sx={{ display: { xs: 'none', md: 'block' } }} />
    </Box>
  )
}
