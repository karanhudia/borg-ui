import { Box, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { statusLabel } from '../../components/StatusBadge'
import { statusColor } from './entryGrid'

// One entry per colour the rail can show, not one per status: skipped,
// cancelled and queued share the muted dot, so the legend names the one a
// reader is most likely to meet.
const LEGEND = ['completed', 'running', 'failed', 'completed_with_warnings', 'skipped']

// Most rows say how they went with a coloured dot and nothing else, so the
// page says once what the colours mean.
export default function StatusLegend() {
  const { t } = useTranslation()
  return (
    <Box
      data-testid="activity-legend"
      sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', columnGap: 1.5, rowGap: 0.5 }}
    >
      {LEGEND.map((status) => (
        <Box key={status} sx={{ display: 'flex', alignItems: 'center', gap: 0.625 }}>
          <Box
            aria-hidden
            sx={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              bgcolor: (theme) => statusColor(theme, status),
            }}
          />
          <Typography variant="caption" sx={{ color: 'text.secondary' }}>
            {statusLabel(status, t)}
          </Typography>
        </Box>
      ))}
    </Box>
  )
}
