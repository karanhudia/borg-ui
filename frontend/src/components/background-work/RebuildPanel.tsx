import { useState } from 'react'
import { Box, Button, Chip, Stack, Typography, alpha, useTheme } from '@mui/material'
import { BarChart3, ChevronRight, History, Layers, RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import RepositorySelectorCard from '../RepositorySelectorCard'
import { PLAN_COLOR, PLAN_LABEL } from '../../core/features'
import type { RebuildStage } from '../../types/operations'
import type { Repository } from '@/types'

const STAGES: RebuildStage[] = ['stats', 'archives', 'history']
const STAGE_ICONS = { stats: BarChart3, archives: Layers, history: History } as const

interface RebuildPanelProps {
  repositories: Repository[]
  historyLocked: boolean
  submitting?: boolean
  onRebuild: (repositoryId: number, stage: RebuildStage) => void
}

// Explains the three derived-data stages in the order the runner builds
// them and lets the user pick where a rebuild starts. Everything after the
// chosen stage is rebuilt too, and the panel says so before the button is
// pressed.
export default function RebuildPanel({
  repositories,
  historyLocked,
  submitting = false,
  onRebuild,
}: RebuildPanelProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [repositoryId, setRepositoryId] = useState<number | null>(repositories[0]?.id ?? null)
  const [stage, setStage] = useState<RebuildStage>('stats')

  const repository = repositories.find((repo) => repo.id === repositoryId) ?? repositories[0]
  const startIndex = STAGES.indexOf(stage)
  const rebuilt = STAGES.slice(startIndex).filter((s) => !(s === 'history' && historyLocked))
  const stageNames = rebuilt.map((s) => t(`operations.background.stages.${s}.title`).toLowerCase())
  const summary =
    startIndex === 0
      ? t('operations.background.rebuildSummaryAll', { repository: repository?.name ?? '' })
      : t('operations.background.rebuildSummary', {
          repository: repository?.name ?? '',
          stages: stageNames.join(t('operations.background.stageJoin')),
        })

  return (
    <Box
      sx={{
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: 2,
        bgcolor: 'background.paper',
        p: 3,
      }}
    >
      <Stack
        direction={{ xs: 'column', md: 'row' }}
        spacing={3}
        sx={{ alignItems: { md: 'flex-start' }, mb: 3 }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: 'center', mb: 0.5 }}>
            <RotateCw size={16} />
            <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
              {t('operations.background.rebuildTitle')}
            </Typography>
          </Stack>
          <Typography variant="body2" sx={{ color: 'text.secondary', maxWidth: 640 }}>
            {t('operations.background.rebuildDescription')}
          </Typography>
        </Box>
        <Box sx={{ width: { xs: '100%', md: 360 }, flexShrink: 0 }}>
          <RepositorySelectorCard
            repositories={repositories}
            value={repository?.id ?? null}
            onChange={(next) => setRepositoryId(Number(next))}
            sx={{ mb: 0 }}
          />
        </Box>
      </Stack>

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
        {STAGES.map((key, index) => {
          const Icon = STAGE_ICONS[key]
          const locked = key === 'history' && historyLocked
          const selected = key === stage
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
                onClick={() => !locked && setStage(key)}
                onKeyDown={(event) => {
                  if (!locked && (event.key === 'Enter' || event.key === ' ')) {
                    event.preventDefault()
                    setStage(key)
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
                  {locked ? (
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
                      sx={{
                        fontWeight: 600,
                        color: willRebuild ? 'primary.main' : 'text.disabled',
                      }}
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

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ alignItems: { sm: 'center' }, justifyContent: 'space-between', mt: 3 }}
      >
        <Typography variant="body2" sx={{ color: 'text.secondary', maxWidth: 720 }}>
          {summary}
        </Typography>
        <Button
          variant="contained"
          disableElevation
          disabled={submitting || repository == null}
          startIcon={<RotateCw size={16} />}
          onClick={() => repository && onRebuild(repository.id, stage)}
          sx={{ flexShrink: 0 }}
        >
          {t('operations.background.rebuildAction')}
        </Button>
      </Stack>
    </Box>
  )
}
