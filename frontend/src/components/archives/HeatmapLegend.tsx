import { Box, Chip, Stack, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { PLAN_LABEL, PLAN_COLOR } from '../../core/features'
import type { HeatmapResponse } from '../../types/archives'

interface HeatmapLegendProps {
  // Undefined when this calendar has no flags to describe, which is not the
  // same as a plan that lacks them: the rows are left out rather than
  // offered as an upgrade.
  flagsAvailable?: HeatmapResponse['flags_available']
  missedTotal?: number
  // Without a schedule or plan cron the cadence is unknown, so no day is
  // judged and "0 missed days" would be a claim the data cannot make.
  cadenceKnown?: boolean
}

const SCALE_STEPS = [0.25, 0.425, 0.6, 0.775, 0.95]
const SWATCH = 12

export default function HeatmapLegend({
  flagsAvailable,
  missedTotal,
  cadenceKnown = true,
}: HeatmapLegendProps) {
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
  }[] =
    flagsAvailable === undefined
      ? []
      : [
          {
            key: 'missed',
            available: flagsAvailable.missed_run,
            sample: { bgcolor: alpha(theme.palette.error.main, 0.16) },
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
    <Stack
      direction="row"
      useFlexGap
      sx={{ flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}
    >
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
      <Stack
        direction="row"
        spacing={2.5}
        useFlexGap
        sx={{ flexWrap: 'wrap', alignItems: 'center' }}
      >
        {rows.map(({ key, available, sample }) => (
          <Stack key={key} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
            {swatch(sample)}
            <Typography variant="caption" color="text.secondary">
              {key === 'missed' ? t('archives.heatmap.legendMissed') : t(`archives.heatmap.${key}`)}
              {key === 'missed' && available
                ? cadenceKnown
                  ? missedTotal != null
                    ? ` (${t('archives.heatmap.missedTotal', { count: missedTotal })})`
                    : ''
                  : ` (${t('archives.heatmap.cadenceUnknown')})`
                : ''}
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
    </Stack>
  )
}
