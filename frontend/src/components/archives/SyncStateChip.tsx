import { Box, Chip, Link as MuiLink } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { parseBackendDate } from '../../utils/dateUtils'
import type { SyncState } from '../../types/archives'

interface SyncStateChipProps {
  state: SyncState
  lastSyncedAt: string | null
  onRebuild: () => void
}

export default function SyncStateChip({ state, lastSyncedAt, onRebuild }: SyncStateChipProps) {
  const { t } = useTranslation()
  const label =
    state === 'fresh' && lastSyncedAt
      ? t('archives.sync.fresh', {
          ago: formatDistanceToNow(parseBackendDate(lastSyncedAt), { addSuffix: true }),
        })
      : t(`archives.sync.${state}`)

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Chip size="small" label={label} />
      {state !== 'syncing' && (
        <MuiLink component="button" type="button" variant="caption" onClick={onRebuild}>
          {t('archives.sync.rebuild')}
        </MuiLink>
      )}
    </Box>
  )
}
