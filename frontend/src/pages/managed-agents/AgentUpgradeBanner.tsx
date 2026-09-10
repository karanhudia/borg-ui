import { Alert, AlertTitle, Button, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentMachineResponse } from '../../services/api'
import { canUpgradeNow } from './agentUpgradeEligibility'

/**
 * The version an endpoint should be running: its pin if it has one, otherwise
 * whatever this server serves.
 */
const effectiveTarget = (agent: AgentMachineResponse): string =>
  agent.desired_agent_version ?? agent.available_agent_version ?? ''

/**
 * Counts endpoints running an older agent than they should be, and offers to
 * upgrade the ones the server can actually move.
 *
 * The count in the action is the number that will move, not the number that is
 * outdated: an endpoint with no self-upgrade helper still needs one manual
 * reinstall, and is called out separately rather than silently included.
 */
export default function AgentUpgradeBanner({
  agents,
  busy = false,
  onUpgradeAll,
}: {
  agents: AgentMachineResponse[]
  busy?: boolean
  onUpgradeAll?: (agents: AgentMachineResponse[]) => void
}) {
  const { t } = useTranslation()
  const outdated = agents.filter((agent) => agent.upgrade_status === 'outdated')
  if (outdated.length === 0) {
    return null
  }

  // Outdated endpoints do not necessarily share a target: one pinned below the
  // served version is outdated against its pin, not against what the server
  // serves. Naming a single version when they differ would tell the operator
  // to install something a pin forbids, so only name it when it is unambiguous.
  const targets = new Set(outdated.map(effectiveTarget).filter(Boolean))
  const sharedTarget = targets.size === 1 ? [...targets][0] : null
  const upgradable = outdated.filter(canUpgradeNow)
  const manualOnly = outdated.length - upgradable.length

  return (
    <Alert
      severity="warning"
      variant="outlined"
      sx={{ mb: 2 }}
      action={
        onUpgradeAll && upgradable.length > 0 ? (
          <Button
            size="small"
            variant="contained"
            disabled={busy}
            onClick={() => onUpgradeAll(upgradable)}
          >
            {t('managedAgents.page.upgrade.upgradeAll', { count: upgradable.length })}
          </Button>
        ) : undefined
      }
    >
      <AlertTitle sx={{ fontWeight: 700, mb: 0.25 }}>
        {t('managedAgents.page.upgrade.outdatedCount', { count: outdated.length })}
      </AlertTitle>
      <Typography variant="body2" color="text.secondary">
        {sharedTarget
          ? t('managedAgents.page.upgrade.bannerBody', { version: sharedTarget })
          : t('managedAgents.page.upgrade.bannerMixedTargets')}
        {manualOnly > 0
          ? ` ${t('managedAgents.page.upgrade.bannerManualOnly', { count: manualOnly })}`
          : ''}
      </Typography>
    </Alert>
  )
}
