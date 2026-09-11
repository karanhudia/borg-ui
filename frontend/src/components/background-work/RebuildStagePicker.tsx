import { Box, Chip, Stack, Typography, alpha, useTheme } from '@mui/material'
import { BarChart3, ChevronRight, History, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { PLAN_COLOR, PLAN_LABEL } from '../../core/features'
import { REBUILD_STAGES } from './repositoryTrack'
import type { RebuildStage } from '../../types/operations'

const STAGE_ICONS = { stats: BarChart3, archives: Layers, history: History } as const

interface RebuildStagePickerProps {
  value: RebuildStage
  onChange: (stage: RebuildStage) => void
  historyLocked: boolean
  // Why the history stage is locked: the plan (a Pro chip) or the
  // repository's executor (an agent's repository cannot be diffed).
  historyLockedReason?: 'plan' | 'agent'
}

// The three derived-data stages as cards. Picking one marks it and every
// later stage for rebuild and shows earlier stages as kept, so the cost
// of the choice is visible before the button is pressed.
export default function RebuildStagePicker({
  value,
  onChange,
  historyLocked,
  historyLockedReason = 'plan',
}: RebuildStagePickerProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const startIndex = REBUILD_STAGES.indexOf(value)

  return (
    <Box
      role="radiogroup"
      aria-label={t('operations.background.rebuildTitle')}
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', md: '1fr auto 1fr auto 1fr' },
        gap: 1.5,
        alignItems: 'stretch',
      }}
    >
      {REBUILD_STAGES.map((key, index) => {
        const Icon = STAGE_ICONS[key]
        const locked = key === 'history' && historyLocked
        const selected = key === value
        const willRebuild = index >= startIndex && !locked
        const color = willRebuild ? theme.palette.primary.main : theme.palette.text.secondary
        return (
          <Box key={key} sx={{ display: 'contents' }}>
            {index > 0 && (
              <Box
                aria-hidden
                sx={{
                  display: { xs: 'none', md: 'flex' },
                  alignItems: 'center',
                  color: 'text.disabled',
                }}
              >
                <ChevronRight size={18} />
              </Box>
            )}
            <Box
              role="radio"
              aria-checked={selected}
              aria-disabled={locked || undefined}
              tabIndex={locked ? -1 : 0}
              data-testid={`rebuild-stage-${key}`}
              data-state={locked ? 'locked' : willRebuild ? 'rebuild' : 'kept'}
              onClick={() => !locked && onChange(key)}
              onKeyDown={(event) => {
                if (!locked && (event.key === 'Enter' || event.key === ' ')) {
                  event.preventDefault()
                  onChange(key)
                }
              }}
              sx={{
                p: 2,
                borderRadius: 2,
                cursor: locked ? 'not-allowed' : 'pointer',
                opacity: locked ? 0.6 : 1,
                border: `1px solid ${selected ? theme.palette.primary.main : theme.palette.divider}`,
                boxShadow: selected
                  ? `0 0 0 2px ${alpha(theme.palette.primary.main, 0.2)}`
                  : 'none',
                bgcolor: willRebuild
                  ? alpha(theme.palette.primary.main, theme.palette.mode === 'dark' ? 0.12 : 0.05)
                  : 'transparent',
                transition: 'background-color 150ms ease, border-color 150ms ease',
                '&:hover': locked ? {} : { borderColor: theme.palette.primary.main },
                '&:focus-visible': {
                  outline: `2px solid ${theme.palette.primary.main}`,
                  outlineOffset: 2,
                },
              }}
            >
              <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 1 }}>
                <Box
                  sx={{
                    width: 28,
                    height: 28,
                    borderRadius: '8px',
                    bgcolor: alpha(color, 0.12),
                    color,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Icon size={15} />
                </Box>
                <Typography variant="subtitle2" sx={{ fontWeight: 700, flex: 1 }}>
                  {index + 1}. {t(`operations.background.stages.${key}.title`)}
                </Typography>
                {locked && historyLockedReason === 'agent' ? (
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 600, color: 'text.disabled', textAlign: 'right' }}
                  >
                    {t('operations.background.stageAgentUnsupported')}
                  </Typography>
                ) : locked ? (
                  <Chip
                    size="small"
                    label={PLAN_LABEL.pro}
                    sx={{
                      height: 20,
                      fontSize: '0.65rem',
                      bgcolor: alpha(PLAN_COLOR.pro, 0.15),
                      color: PLAN_COLOR.pro,
                    }}
                  />
                ) : (
                  <Typography
                    variant="caption"
                    sx={{ fontWeight: 600, color: willRebuild ? 'primary.main' : 'text.disabled' }}
                  >
                    {selected
                      ? t('operations.background.stageStart')
                      : willRebuild
                        ? t('operations.background.stageWillRebuild')
                        : t('operations.background.stageKept')}
                  </Typography>
                )}
              </Stack>
              <Typography variant="body2" sx={{ mb: 0.5 }}>
                {t(`operations.background.stages.${key}.what`)}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.secondary' }}>
                {t(`operations.background.stages.${key}.cost`)}
              </Typography>
            </Box>
          </Box>
        )
      })}
    </Box>
  )
}
