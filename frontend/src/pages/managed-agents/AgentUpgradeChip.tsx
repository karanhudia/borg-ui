import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentUpgradeStatus } from '../../services/api'
import { agentChipSx } from './agentChipSx'

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
    // A pin decides the target whatever the status is. An endpoint pinned below
    // the served version reads as `outdated` against its pin, so naming the
    // served version here would point the operator at a version the pin
    // forbids. This mirrors `desired or available` in app/core/agent_versions.py.
    if (pinnedVersion) {
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
      sx={agentChipSx}
    />
  )

  const title = tooltipText()
  return title ? (
    <Tooltip title={title} arrow>
      {chip}
    </Tooltip>
  ) : (
    chip
  )
}
