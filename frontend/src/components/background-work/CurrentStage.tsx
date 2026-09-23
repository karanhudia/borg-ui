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
  else if (stage.status === 'waiting' && stage.reason) {
    // `lane_busy` is the only reason with a placeholder; without a kind to
    // fill it the queued wording is used, so the raw `{{kind}}` can never
    // reach the page however a caller built the stage.
    const named = stage.reason === 'lane_busy' && stage.reasonKind
    caption = t(
      `operations.background.reason.${named ? 'lane_busy' : stage.reason === 'lane_busy' ? 'queued' : stage.reason}`,
      named
        ? { kind: t(`operations.kind.${stage.reasonKind}`, { defaultValue: stage.reasonKind }) }
        : {}
    )
  } else if (stage.status === 'running') {
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
        sx={{ display: 'block', color: 'text.primary', fontWeight: 600, mb: 0.5 }}
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

interface CurrentStageProps {
  // Null when the repository is at rest: the cell stays empty.
  stage: StageState | null
  now: number
  onRetry: (stage: StageState) => void
}

// The stage a repository is in right now (`currentStage`), with its
// progress, why it waits, or a retry when it failed. The strip above the
// table counts the same thing across every repository.
export default function CurrentStage({ stage, now, onRetry }: CurrentStageProps) {
  return (
    <Box data-testid="current-stage" sx={{ minWidth: 0, gridColumn: { xs: '1 / -1', md: 'auto' } }}>
      {stage && <StageSegment stage={stage} now={now} onRetry={onRetry} />}
    </Box>
  )
}
