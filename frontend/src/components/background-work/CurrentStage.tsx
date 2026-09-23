import { Box, Button, LinearProgress, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { elapsedSince } from './elapsed'
import { REBUILD_STAGE_FOR, type StageState } from './repositoryTrack'

function waitCaption(stage: StageState, t: ReturnType<typeof useTranslation>['t']): string | null {
  if (!stage.reason) return null
  // `lane_busy` is the only reason with a placeholder; without a kind to
  // fill it the queued wording is used, so the raw `{{kind}}` can never
  // reach the page however a caller built the stage.
  const named = stage.reason === 'lane_busy' && stage.reasonKind
  return t(
    `operations.background.reason.${named ? 'lane_busy' : stage.reason === 'lane_busy' ? 'queued' : stage.reason}`,
    named
      ? { kind: t(`operations.kind.${stage.reasonKind}`, { defaultValue: stage.reasonKind }) }
      : {}
  )
}

function StageLine({ stage, now }: { stage: StageState; now: number }) {
  const { t } = useTranslation()
  const running = stage.status === 'running'
  const operation = stage.operation
  const counted =
    operation?.progress_current != null && operation?.progress_total != null
      ? `${operation.progress_current}/${operation.progress_total}`
      : null
  const meta = running
    ? [elapsedSince(operation?.started_at ?? null, now), counted].filter(Boolean).join(', ')
    : null
  return (
    <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, minWidth: 0 }}>
      <Typography variant="body2" noWrap sx={{ fontWeight: 500, minWidth: 0 }}>
        {t(`operations.background.stage.${stage.key}`)}
      </Typography>
      {meta && (
        <Typography
          variant="caption"
          noWrap
          sx={{ color: 'text.secondary', fontVariantNumeric: 'tabular-nums', flexShrink: 0 }}
        >
          {meta}
        </Typography>
      )}
    </Box>
  )
}

// The same two lines as the data cells beside it (a primary line and a
// secondary one), so a row keeps its height when work starts or stops.
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
  const progress = stage.operation?.progress_percent ?? null

  let secondary: React.ReactNode = null
  if (stage.status === 'running') {
    // The product's progress bar (Activity runs, running backups): thin,
    // rounded, on a tint of the primary colour.
    secondary = (
      <LinearProgress
        variant={progress != null ? 'determinate' : 'indeterminate'}
        value={progress ?? undefined}
        sx={{
          mt: 1,
          height: 4,
          borderRadius: 999,
          bgcolor: alpha(theme.palette.primary.main, 0.12),
          '& .MuiLinearProgress-bar': { borderRadius: 999 },
          '@media (prefers-reduced-motion: reduce)': {
            '& .MuiLinearProgress-bar': { animation: 'none' },
          },
        }}
      />
    )
  } else if (stage.status === 'failed') {
    secondary = (
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Typography variant="caption" sx={{ color: 'error.main', fontWeight: 600 }}>
          {t('operations.background.stageFailed')}
        </Typography>
        {REBUILD_STAGE_FOR[stage.key] && (
          <Button
            size="small"
            color="error"
            variant="text"
            sx={{ minWidth: 0, px: 0.75, py: 0, fontSize: '0.75rem', lineHeight: 1.6 }}
            onClick={(event) => {
              event.stopPropagation()
              onRetry(stage)
            }}
          >
            {t('operations.background.retry')}
          </Button>
        )}
      </Box>
    )
  } else if (stage.status === 'waiting') {
    const caption = waitCaption(stage, t)
    secondary = caption && (
      <Typography variant="caption" sx={{ display: 'block', color: 'text.secondary' }}>
        {caption}
      </Typography>
    )
  }

  return (
    <Box data-testid={`stage-${stage.key}`} data-status={stage.status} sx={{ minWidth: 0 }}>
      <StageLine stage={stage} now={now} />
      {secondary && <Box sx={{ mt: 0.25 }}>{secondary}</Box>}
    </Box>
  )
}

interface CurrentStageProps {
  // Null when the repository is at rest.
  stage: StageState | null
  now: number
  onRetry: (stage: StageState) => void
  // What the cell says at rest: "Idle", or why nothing runs here at all.
  restLabel: string
}

// The stage a repository is in right now (`currentStage`), with its
// progress, why it waits, or a retry when it failed. The strip above the
// table counts the same thing across every repository.
export default function CurrentStage({ stage, now, onRetry, restLabel }: CurrentStageProps) {
  return (
    <Box data-testid="current-stage" sx={{ minWidth: 0, gridColumn: { xs: '1 / -1', md: 'auto' } }}>
      {stage ? (
        <StageSegment stage={stage} now={now} onRetry={onRetry} />
      ) : (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {restLabel}
        </Typography>
      )}
    </Box>
  )
}
