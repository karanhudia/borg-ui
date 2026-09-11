import { Box, Chip, LinearProgress, Typography, alpha, useTheme } from '@mui/material'
import { Activity as ActivityIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ActivityItem } from '../Activity'
import type { ActionButton } from '../../components/RowActions'
import RowActions from '../../components/RowActions'
import { formatTimeRange } from '../../utils/dateUtils'
import { ACTIVE_STATUSES, runTitle, umbrella } from './runs'

interface RunningNowProps {
  items: ActivityItem[]
  actions: ActionButton<ActivityItem>[]
}

// What Borg UI is doing right now, lifted out of the ledger so a running
// backup is the first thing on the page rather than a row to hunt for.
export default function RunningNow({ items, actions }: RunningNowProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const active = items.filter((item) => ACTIVE_STATUSES.has(item.status))
  if (active.length === 0) return null

  return (
    <Box
      data-testid="running-now"
      sx={{
        mb: 3,
        p: 2,
        borderRadius: 3,
        border: 1,
        borderColor: alpha(theme.palette.primary.main, 0.25),
        background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.08)}, transparent 70%)`,
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
        <ActivityIcon size={16} color={theme.palette.primary.main} />
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {t('activity.runningNow.title')}
        </Typography>
        <Chip size="small" label={active.length} color="primary" sx={{ height: 20 }} />
      </Box>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'repeat(auto-fill, minmax(320px, 1fr))' },
          gap: 1.5,
        }}
      >
        {active.map((item) => {
          const running = item.status === 'running'
          const percent = item.progress_percent ?? null
          return (
            <Box
              key={item.activity_key ?? `${item.type}-${item.id}`}
              data-testid="running-now-card"
              sx={{
                p: 1.5,
                borderRadius: 2,
                bgcolor: 'background.paper',
                border: 1,
                borderColor: 'divider',
                minWidth: 0,
              }}
            >
              <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, minWidth: 0 }}>
                <Typography variant="body2" sx={{ fontWeight: 600 }} noWrap>
                  {item.repository || item.package_name || item.archive_name || ''}
                </Typography>
                <Typography variant="body2" sx={{ color: 'text.secondary' }} noWrap>
                  {runTitle(item, t)}
                </Typography>
                <Box sx={{ ml: 'auto', flexShrink: 0 }}>
                  <RowActions row={item} actions={actions} iconOpacity={0.7} />
                </Box>
              </Box>
              <Typography
                variant="caption"
                sx={{ color: 'text.secondary', display: 'block', mt: 0.25 }}
                noWrap
              >
                {[
                  umbrella(item, t).label,
                  running
                    ? formatTimeRange(item.started_at, null, 'running')
                    : t('activity.runningNow.queued'),
                  item.progress_message,
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </Typography>
              <LinearProgress
                variant={running && percent != null ? 'determinate' : 'indeterminate'}
                value={percent ?? undefined}
                sx={{
                  mt: 1,
                  height: 4,
                  borderRadius: 999,
                  bgcolor: alpha(theme.palette.primary.main, 0.12),
                  ...(!running && { opacity: 0.5 }),
                  '@media (prefers-reduced-motion: reduce)': {
                    '& .MuiLinearProgress-bar': { animation: 'none' },
                  },
                }}
              />
            </Box>
          )
        })}
      </Box>
    </Box>
  )
}
