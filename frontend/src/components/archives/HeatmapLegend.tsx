import { Box, Chip, Stack, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { PLAN_LABEL, PLAN_COLOR } from '../../core/features'
import type { HeatmapResponse } from '../../types/archives'

interface HeatmapLegendProps {
  flagsAvailable: HeatmapResponse['flags_available']
}

const SCALE_STEPS = [0.25, 0.425, 0.6, 0.775, 0.95]
const SWATCH = 10

export default function HeatmapLegend({ flagsAvailable }: HeatmapLegendProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  const swatch = (sx: object) => (
    <Box
      sx={{ width: SWATCH, height: SWATCH, borderRadius: '2px', boxSizing: 'border-box', ...sx }}
    />
  )

  const rows: {
    key: 'missed' | 'sizeOutlier' | 'durationOutlier'
    available: boolean
    sample: object
  }[] = [
    {
      key: 'missed',
      available: flagsAvailable.missed_run,
      sample: {
        bgcolor: alpha(theme.palette.text.primary, 0.06),
        border: `1px dashed ${theme.palette.error.main}`,
      },
    },
    {
      key: 'sizeOutlier',
      available: flagsAvailable.size_outlier,
      sample: {
        bgcolor: alpha(theme.palette.primary.main, 0.6),
        boxShadow: `inset 0 0 0 2px ${theme.palette.warning.main}`,
      },
    },
    {
      key: 'durationOutlier',
      available: flagsAvailable.duration_outlier,
      sample: {
        bgcolor: alpha(theme.palette.primary.main, 0.6),
        boxShadow: `inset 0 0 0 2px ${theme.palette.warning.main}`,
      },
    },
  ]

  return (
    <Stack direction="row" spacing={3} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
      <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center' }}>
        <Typography variant="caption" color="text.secondary">
          {t('archives.heatmap.legendLess')}
        </Typography>
        {swatch({ bgcolor: alpha(theme.palette.text.primary, 0.06) })}
        {SCALE_STEPS.map((step) => (
          <Box key={step}>{swatch({ bgcolor: alpha(theme.palette.primary.main, step) })}</Box>
        ))}
        <Typography variant="caption" color="text.secondary">
          {t('archives.heatmap.legendMore')}
        </Typography>
      </Stack>
      {rows.map(({ key, available, sample }) => (
        <Stack key={key} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
          {swatch(sample)}
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
