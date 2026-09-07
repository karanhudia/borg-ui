import { Alert, AlertTitle, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentMachineResponse } from '../../services/api'

/**
 * The version an endpoint should be running: its pin if it has one, otherwise
 * whatever this server serves.
 */
const effectiveTarget = (agent: AgentMachineResponse): string =>
  agent.desired_agent_version ?? agent.available_agent_version ?? ''

/**
 * Counts endpoints running an older agent than they should be.
 *
 * Informational only: upgrading is still a manual reinstall from each agent's
 * card, so this deliberately carries no action button.
 */
export default function AgentUpgradeBanner({ agents }: { agents: AgentMachineResponse[] }) {
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

  return (
    <Alert severity="warning" variant="outlined" sx={{ mb: 2 }}>
      <AlertTitle sx={{ fontWeight: 700, mb: 0.25 }}>
        {t('managedAgents.page.upgrade.outdatedCount', { count: outdated.length })}
      </AlertTitle>
      <Typography variant="body2" color="text.secondary">
        {sharedTarget
          ? `${t('managedAgents.page.upgrade.bannerBody', { version: sharedTarget })} `
          : `${t('managedAgents.page.upgrade.bannerMixedTargets')} `}
        {t('managedAgents.page.upgrade.bannerManual')}
      </Typography>
    </Alert>
  )
}
