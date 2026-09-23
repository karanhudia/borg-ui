import {
  Box,
  ButtonBase,
  Chip,
  IconButton,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { STAGE_ORDER, type StageKey } from './repositoryTrack'
import type { StageCount, StageCounts } from './hubRows'
import type { PausableStage } from '../../types/operations'

interface StageStripProps {
  counts: StageCounts
  selected: StageKey | null
  onSelect: (stage: StageKey | null) => void
  pausedStages: PausableStage[]
  canManage: boolean
  onTogglePause: (stage: PausableStage, paused: boolean) => void
  // Rendered inside the File history block: the index worker stepper, the
  // one stage with a pool of workers to size.
  historyExtra?: React.ReactNode
}

function Breakdown({ count }: { count: StageCount }) {
  const { t } = useTranslation()
  if (count.total === 0) {
    return (
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {t('operations.background.strip.idle')}
      </Typography>
    )
  }
  const parts = (['running', 'waiting', 'failed'] as const).filter((part) => count[part] > 0)
  return (
    <Typography variant="caption" sx={{ color: 'text.secondary' }}>
      {parts.map((part, index) => (
        <Box
          component="span"
          key={part}
          sx={part === 'failed' ? { color: 'error.main', fontWeight: 600 } : undefined}
        >
          {index > 0 && ' · '}
          {t(`operations.background.strip.${part}`, { count: count[part] })}
        </Box>
      ))}
    </Typography>
  )
}

// One block per stage a repository moves through, in run order, each with
// how many repositories are in it right now. A block filters the table to
// its repositories, and every stage but connect (a synchronous request with
// nothing ever queued) can be paused on its own.
export default function StageStrip({
  counts,
  selected,
  onSelect,
  pausedStages,
  canManage,
  onTogglePause,
  historyExtra,
}: StageStripProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  return (
    <Box
      role="group"
      aria-label={t('operations.background.strip.label')}
      sx={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: 1.5,
      }}
    >
      {STAGE_ORDER.map((key) => {
        const count = counts[key]
        const label = t(`operations.background.stage.${key}`)
        const pausable = key !== 'connect'
        const paused = pausable && pausedStages.includes(key)
        const isSelected = selected === key
        return (
          <Box
            key={key}
            data-testid={`stage-block-${key}`}
            sx={{
              position: 'relative',
              border: `1px solid ${isSelected ? theme.palette.primary.main : theme.palette.divider}`,
              boxShadow: isSelected ? `inset 0 0 0 1px ${theme.palette.primary.main}` : 'none',
              borderRadius: 2,
              bgcolor: isSelected
                ? alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.1 : 0.04)
                : 'background.paper',
              transition: 'border-color 150ms ease, background-color 150ms ease',
              '&:hover': { borderColor: isSelected ? undefined : theme.palette.text.disabled },
            }}
          >
            <ButtonBase
              aria-pressed={isSelected}
              aria-label={label}
              onClick={() => onSelect(isSelected ? null : key)}
              sx={{
                display: 'block',
                width: '100%',
                textAlign: 'left',
                borderRadius: 2,
                px: 1.75,
                pt: 1.25,
                pb: historyExtra && key === 'history' ? 0.5 : 1.25,
                '&.Mui-focusVisible': {
                  outline: `2px solid ${theme.palette.primary.main}`,
                  outlineOffset: 2,
                },
              }}
            >
              <Typography
                variant="caption"
                noWrap
                sx={{
                  display: 'block',
                  color: 'text.secondary',
                  fontWeight: 600,
                  // Room for the pause button in the corner.
                  pr: pausable ? 3.5 : 0,
                }}
              >
                {label}
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography
                  component="div"
                  sx={{
                    fontSize: '1.5rem',
                    fontWeight: 700,
                    lineHeight: 1.3,
                    fontVariantNumeric: 'tabular-nums',
                    color: count.total === 0 ? 'text.disabled' : 'text.primary',
                  }}
                >
                  {count.total}
                </Typography>
                {paused && (
                  <Chip
                    size="small"
                    label={t('operations.background.strip.paused')}
                    sx={{
                      height: 20,
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      bgcolor: alpha(theme.palette.warning.main, 0.16),
                      color: theme.palette.mode === 'dark' ? 'warning.light' : 'warning.dark',
                    }}
                  />
                )}
              </Box>
              <Breakdown count={count} />
            </ButtonBase>
            {key === 'history' && historyExtra && (
              <Box sx={{ px: 1.25, pb: 1 }}>{historyExtra}</Box>
            )}
            {pausable && canManage && (
              <Tooltip
                title={t(
                  paused
                    ? 'operations.background.strip.resumeStage'
                    : 'operations.background.strip.pauseStage',
                  { stage: label }
                )}
              >
                <IconButton
                  size="small"
                  aria-label={t(
                    paused
                      ? 'operations.background.strip.resumeStage'
                      : 'operations.background.strip.pauseStage',
                    { stage: label }
                  )}
                  onClick={() => onTogglePause(key, !paused)}
                  sx={{ position: 'absolute', right: 4, top: 4 }}
                >
                  {paused ? <Play size={14} /> : <Pause size={14} />}
                </IconButton>
              </Tooltip>
            )}
          </Box>
        )
      })}
    </Box>
  )
}
