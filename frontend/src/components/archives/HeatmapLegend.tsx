import { Box, Stack, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'

interface HeatmapLegendProps {
  // False when this calendar has no flags to describe: the prune preview
  // colours its days by verdict, so the flag rows would name markers it
  // never draws.
  showFlags?: boolean
  missedTotal?: number
  // Without a schedule or plan cron the cadence is unknown, so no day is
  // judged and "0 missed days" would be a claim the data cannot make.
  cadenceKnown?: boolean
}

const SCALE_STEPS = [0.25, 0.425, 0.6, 0.775, 0.95]
const SWATCH = 12

export default function HeatmapLegend({
  showFlags = true,
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

  // One outlined cell means one thing to the calendar: this run stands out
  // from the seven before it. Size and duration had a legend row each and
  // the same swatch, which promised a distinction the cells do not draw;
  // the day's own label names which it was.
  const rows: { key: 'missed' | 'unusualRun'; sample: object }[] = showFlags
    ? [
        {
          key: 'missed',
          sample: { bgcolor: alpha(theme.palette.error.main, 0.16) },
        },
        {
          key: 'unusualRun',
          sample: {
            bgcolor: alpha(theme.palette.primary.main, 0.6),
            boxShadow: `inset 0 0 0 2px ${theme.palette.warning.main}`,
          },
        },
      ]
    : []

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
        {rows.map(({ key, sample }) => (
          <Stack key={key} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
            {swatch(sample)}
            <Typography variant="caption" color="text.secondary">
              {key === 'missed'
                ? t('archives.heatmap.legendMissed')
                : t('archives.heatmap.unusualRun')}
              {key === 'missed'
                ? cadenceKnown
                  ? missedTotal != null
                    ? ` (${t('archives.heatmap.missedTotal', { count: missedTotal })})`
                    : ''
                  : ` (${t('archives.heatmap.cadenceUnknown')})`
                : ''}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Stack>
  )
}
