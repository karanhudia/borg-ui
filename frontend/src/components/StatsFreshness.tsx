import { Box, CircularProgress, IconButton, Tooltip, Typography } from '@mui/material'
import { RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDateTimeFull, formatRelativeTime } from '../utils/dateUtils'
import type { SyncState } from '../types/archives'

export interface StatsFreshnessProps {
  /** The oldest stamp behind the figures (see `statsUpdatedAt`); null when
   * nothing has been indexed yet. */
  updatedAt: string | null
  /** The archive index's own verdict: `stale` turns the caption amber. */
  syncState?: SyncState
  /** A refresh or index run in flight: the caption says so and the button waits. */
  updating?: boolean
  onRefresh?: () => void
}

/** "Updated 2 hours ago" with the one button that refreshes every figure,
 * beside the stats it describes: the archive header and the info dialog
 * share it so the two can never disagree. */
export default function StatsFreshness({
  updatedAt,
  syncState,
  updating = false,
  onRefresh,
}: StatsFreshnessProps) {
  const { t } = useTranslation()
  const caption = updating
    ? t('repositoryStats.updating')
    : updatedAt
      ? t('repositoryStats.updated', { ago: formatRelativeTime(updatedAt) })
      : t('repositoryStats.notIndexed')
  const warn = !updating && (!updatedAt || syncState === 'stale')

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
      <Tooltip title={updatedAt && !updating ? formatDateTimeFull(updatedAt) : ''}>
        <Typography
          variant="caption"
          sx={{ color: warn ? 'warning.main' : 'text.secondary', whiteSpace: 'nowrap' }}
        >
          {caption}
        </Typography>
      </Tooltip>
      {onRefresh && (
        <Tooltip title={t('repositoryStats.refresh')}>
          <span>
            <IconButton
              size="small"
              aria-label={t('repositoryStats.refresh')}
              onClick={onRefresh}
              disabled={updating}
            >
              {updating ? <CircularProgress size={20} /> : <RefreshCw size={20} />}
            </IconButton>
          </span>
        </Tooltip>
      )}
    </Box>
  )
}
