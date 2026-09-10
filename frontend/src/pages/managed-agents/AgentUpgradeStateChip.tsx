import { Chip, CircularProgress, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { agentChipSx } from './agentChipSx'

/**
 * What an in-flight or failed upgrade looks like on the row. The agent is
 * killed by the thing it is reporting on, so `requested` only means the server
 * asked and the endpoint acknowledged; the server resolves the rest, either on
 * the endpoint's next check-in or by timeout.
 */
export default function AgentUpgradeStateChip({
  state,
  targetVersion,
  error,
}: {
  state: string
  targetVersion?: string | null
  error?: string | null
}) {
  const { t } = useTranslation()

  // No spinner: nothing is happening on that machine yet, and a spinner would
  // say otherwise.
  if (state === 'queued') {
    return (
      <Tooltip title={t('managedAgents.page.upgradeState.queuedTooltip')} arrow>
        <Chip
          size="small"
          variant="outlined"
          label={t('managedAgents.page.upgradeState.queued')}
          sx={agentChipSx}
        />
      </Tooltip>
    )
  }

  if (state === 'requested') {
    return (
      <Tooltip title={t('managedAgents.page.upgradeState.upgradingTooltip')} arrow>
        <Chip
          size="small"
          variant="outlined"
          color="info"
          icon={<CircularProgress size={10} thickness={6} color="inherit" />}
          label={
            targetVersion
              ? t('managedAgents.page.upgradeState.upgradingTo', { version: targetVersion })
              : t('managedAgents.page.upgradeState.upgrading')
          }
          sx={agentChipSx}
        />
      </Tooltip>
    )
  }

  if (state === 'failed') {
    return (
      <Tooltip title={error || t('managedAgents.page.upgradeState.failedHint')} arrow>
        <Chip
          size="small"
          variant="outlined"
          color="error"
          label={t('managedAgents.page.upgradeState.failed')}
          sx={agentChipSx}
        />
      </Tooltip>
    )
  }

  return null
}
