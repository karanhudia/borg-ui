import { Box, Chip, CircularProgress, alpha, useTheme } from '@mui/material'
import { AlertTriangle, CheckCircle2, CircleDashed } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { parseBackendDate } from '../../utils/dateUtils'
import type { SyncState } from '../../types/archives'

interface SyncStateChipProps {
  state: SyncState
  lastSyncedAt: string | null
}

// The archive index's freshness, coloured by state: green when fresh,
// amber when stale, neutral when never built, blue while syncing.
export default function SyncStateChip({ state, lastSyncedAt }: SyncStateChipProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const label =
    state === 'fresh' && lastSyncedAt
      ? t('archives.sync.fresh', {
          ago: formatDistanceToNow(parseBackendDate(lastSyncedAt), { addSuffix: true }),
        })
      : t(`archives.sync.${state}`)

  const color = {
    fresh: theme.palette.success.main,
    stale: theme.palette.warning.main,
    never: theme.palette.text.secondary,
    syncing: theme.palette.primary.main,
  }[state]
  const icon = {
    fresh: <CheckCircle2 size={14} />,
    stale: <AlertTriangle size={14} />,
    never: <CircleDashed size={14} />,
    syncing: <CircularProgress size={12} thickness={5} sx={{ color }} />,
  }[state]

  return (
    <Chip
      size="small"
      icon={<Box sx={{ display: 'flex', alignItems: 'center', pl: 0.5, color }}>{icon}</Box>}
      label={label}
      sx={{
        bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.16 : 0.1),
        color,
        fontWeight: 600,
        '& .MuiChip-icon': { color },
      }}
    />
  )
}
