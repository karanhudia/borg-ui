import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { agentChipSx } from './agentChipSx'

/**
 * Shown on an endpoint that carries no self-upgrade helper, so an operator can
 * see why it is not part of server-driven upgrades. An endpoint enrolled
 * before the helper existed, one whose operator declined it, and one enrolled
 * over http all land here, and all are fixed the same way: one reinstall.
 */
export default function AgentManualUpgradeChip() {
  const { t } = useTranslation()

  return (
    <Tooltip title={t('managedAgents.page.upgrade.manualOnlyTooltip')} arrow>
      <Chip
        size="small"
        variant="outlined"
        color="default"
        label={t('managedAgents.page.upgrade.manualOnly')}
        sx={agentChipSx}
      />
    </Tooltip>
  )
}
