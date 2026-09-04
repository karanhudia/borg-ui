import { Box, Chip, Stack, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { PLAN_LABEL, PLAN_COLOR } from '../../core/features'
import type { HeatmapResponse } from '../../types/archives'

interface HeatmapLegendProps {
  flagsAvailable: HeatmapResponse['flags_available']
}

const SCALE_STEPS = [0.15, 0.35, 0.55, 0.75, 0.95]

export default function HeatmapLegend({ flagsAvailable }: HeatmapLegendProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  const anomalyRows: { key: 'missed' | 'sizeOutlier' | 'durationOutlier'; available: boolean }[] = [
    { key: 'missed', available: flagsAvailable.missed_run },
    { key: 'sizeOutlier', available: flagsAvailable.size_outlier },
    { key: 'durationOutlier', available: flagsAvailable.duration_outlier },
  ]

  return (
    <Stack direction="row" spacing={3} sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          {t('archives.heatmap.legendLess')}
        </Typography>
        {SCALE_STEPS.map((step) => (
          <Box
            key={step}
            sx={{
              width: 12,
              height: 12,
              borderRadius: 0.5,
              backgroundColor: alpha(theme.palette.primary.main, step),
            }}
          />
        ))}
        <Typography variant="caption" color="text.secondary">
          {t('archives.heatmap.legendMore')}
        </Typography>
      </Stack>
      {anomalyRows.map(({ key, available }) => (
        <Stack key={key} direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
          <Box
            sx={{
              width: 12,
              height: 12,
              borderRadius: 0.5,
              outline: `2px solid ${theme.palette.warning.main}`,
            }}
          />
          <Typography variant="caption" color="text.secondary">
            {t(`archives.heatmap.${key}`)}
          </Typography>
          {!available && (
            <Chip
              size="small"
              label={PLAN_LABEL.pro}
              sx={{
                height: 18,
                fontSize: '0.65rem',
                backgroundColor: alpha(PLAN_COLOR.pro, 0.15),
                color: PLAN_COLOR.pro,
              }}
            />
          )}
        </Stack>
      ))}
    </Stack>
  )
}
