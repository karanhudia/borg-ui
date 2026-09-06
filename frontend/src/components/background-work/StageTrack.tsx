import { Box, Button, LinearProgress, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { elapsedSince } from './elapsed'
import { REBUILD_STAGE_FOR, type StageState } from './repositoryTrack'

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
        sx={{
          display: 'block',
          color: stage.status === 'idle' ? 'text.disabled' : 'text.secondary',
          fontWeight: stage.status === 'running' ? 600 : 500,
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

// The four derivation stages of one run, side by side and self-labelled,
// so the track reads on its own wherever it is placed.
export default function StageTrack({ stages, now, onRetry }: StageTrackProps) {
  return (
    <Box
      data-testid="stage-track"
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', sm: 'repeat(4, minmax(0, 1fr))' },
        columnGap: 2,
        rowGap: 1,
      }}
    >
      {stages.map((stage) => (
        <StageSegment key={stage.key} stage={stage} now={now} onRetry={onRetry} />
      ))}
    </Box>
  )
}
