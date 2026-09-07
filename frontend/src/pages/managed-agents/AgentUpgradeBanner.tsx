import { Alert, AlertTitle, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import type { AgentMachineResponse } from '../../services/api'

/**
 * Counts endpoints running an older agent than this server serves.
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

  // Every outdated agent compares against the same served version, so reading
  // it off the first one is enough.
  const target = outdated[0].available_agent_version ?? ''

  return (
    <Alert severity="warning" variant="outlined" sx={{ mb: 2 }}>
      <AlertTitle sx={{ fontWeight: 700, mb: 0.25 }}>
        {t('managedAgents.page.upgrade.outdatedCount', { count: outdated.length })}
      </AlertTitle>
      <Typography variant="body2" color="text.secondary">
        {target ? `${t('managedAgents.page.upgrade.bannerBody', { version: target })} ` : ''}
        {t('managedAgents.page.upgrade.bannerManual')}
      </Typography>
    </Alert>
  )
}
