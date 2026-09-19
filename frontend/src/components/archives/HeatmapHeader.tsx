import type { ReactNode } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

/** The calendar's title, a line about what it spans, and the caller's
 * controls on the right: the same head over the day and hour views. */
export default function HeatmapHeader({
  summary,
  toolbar,
}: {
  summary: ReactNode
  toolbar?: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <Stack
      direction="row"
      sx={{ alignItems: 'flex-start', justifyContent: 'space-between', gap: 2, flexWrap: 'wrap' }}
    >
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
          {t('archives.heatmap.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary" data-testid="heatmap-summary">
          {summary}
        </Typography>
      </Box>
      {toolbar}
    </Stack>
  )
}
