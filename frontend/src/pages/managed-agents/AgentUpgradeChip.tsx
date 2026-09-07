import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentUpgradeStatus } from '../../services/api'

const STATUS_COLOR: Record<AgentUpgradeStatus, 'success' | 'warning' | 'info' | 'default'> = {
  up_to_date: 'success',
  outdated: 'warning',
  ahead: 'info',
  pinned: 'info',
  unknown: 'default',
}

const STATUS_LABEL: Record<AgentUpgradeStatus, string> = {
  up_to_date: 'managedAgents.page.upgrade.upToDate',
  outdated: 'managedAgents.page.upgrade.outdated',
  ahead: 'managedAgents.page.upgrade.ahead',
  pinned: 'managedAgents.page.upgrade.pinned',
  unknown: 'managedAgents.page.upgrade.unknown',
}

/**
 * How the agent version an endpoint reports compares to the version it should
 * be running. `targetVersion` is what this server serves; `pinnedVersion` is
 * set only when an operator pinned the endpoint to a specific version.
 */
export default function AgentUpgradeChip({
  status,
  targetVersion,
  pinnedVersion,
}: {
  status: AgentUpgradeStatus
  targetVersion?: string | null
  pinnedVersion?: string | null
}) {
  const { t } = useTranslation()

  const tooltipText = () => {
    if (status === 'pinned' && pinnedVersion) {
      return t('managedAgents.page.upgrade.pinnedTooltip', { version: pinnedVersion })
    }
    if (status === 'unknown') {
      return t('managedAgents.page.upgrade.unknownTooltip')
    }
    if (targetVersion) {
      return t('managedAgents.page.upgrade.targetTooltip', { version: targetVersion })
    }
    return ''
  }

  const chip = (
    <Chip
      size="small"
      variant="outlined"
      color={STATUS_COLOR[status]}
      label={t(STATUS_LABEL[status])}
      sx={{ height: 18, fontSize: '0.58rem', fontWeight: 600, '& .MuiChip-label': { px: 0.75 } }}
    />
  )

  const title = tooltipText()
  return title ? (
    <Tooltip title={title} arrow>
      <span>{chip}</span>
    </Tooltip>
  ) : (
    chip
  )
}
