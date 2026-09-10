import { Button, Paper, Stack, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'

/**
 * Appears only while endpoints are selected. Flat surface, no accent border,
 * matching the page's other inline action surfaces.
 */
export default function AgentBulkUpgradeBar({
  count,
  busy = false,
  onUpgrade,
  onClear,
}: {
  count: number
  busy?: boolean
  onUpgrade: () => void
  onClear: () => void
}) {
  const { t } = useTranslation()
  if (count === 0) {
    return null
  }

  return (
    <Paper variant="outlined" sx={{ p: 1.5, mb: 2, borderRadius: 2 }}>
      <Stack direction="row" spacing={1} sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Typography variant="body2" sx={{ flexGrow: 1 }}>
          {t('managedAgents.page.upgrade.selectedCount', { count })}
        </Typography>
        <Button size="small" onClick={onClear} disabled={busy}>
          {t('managedAgents.page.upgrade.clearSelection')}
        </Button>
        <Button size="small" variant="contained" onClick={onUpgrade} disabled={busy}>
          {t('managedAgents.page.upgrade.upgradeSelected', { count })}
        </Button>
      </Stack>
    </Paper>
  )
}
