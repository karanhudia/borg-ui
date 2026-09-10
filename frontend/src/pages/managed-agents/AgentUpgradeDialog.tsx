import {
  Alert,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../components/shared/ResponsiveDialog'
import type { AgentMachineResponse } from '../../services/api'

/**
 * Confirms a remote upgrade for one endpoint or for a whole selection. Each
 * endpoint reinstalls itself and disconnects while it does, so the operator is
 * told that plainly before confirming rather than after the rows go quiet.
 */
export default function AgentUpgradeDialog({
  agents,
  open,
  busy = false,
  onConfirm,
  onCancel,
}: {
  agents: AgentMachineResponse[]
  open: boolean
  busy?: boolean
  onConfirm: (agents: AgentMachineResponse[]) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  // A pin decides the target whatever the server serves, mirroring
  // `desired or available` in app/core/agent_versions.py. Endpoints in one
  // request do not have to agree, so a single version is named only when they
  // do: naming one otherwise would promise an upgrade a pin forbids.
  const targets = new Set(
    agents
      .map((agent) => agent.desired_agent_version || agent.available_agent_version)
      .filter(Boolean)
  )
  const sharedTarget = targets.size === 1 ? [...targets][0] : null

  return (
    <ResponsiveDialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="sm"
      footer={
        <DialogActions>
          <Button onClick={onCancel}>{t('common.buttons.cancel')}</Button>
          <Button
            variant="contained"
            disabled={busy || agents.length === 0}
            onClick={() => agents.length > 0 && onConfirm(agents)}
          >
            {t('managedAgents.page.upgradeDialog.confirm')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>
        {t('managedAgents.page.upgradeDialog.title', { count: agents.length })}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <Stack spacing={0.25}>
            {agents.map((agent) => (
              <Typography key={agent.id} sx={{ fontWeight: 700 }}>
                {[agent.name, agent.hostname].filter(Boolean).join(' · ')}
              </Typography>
            ))}
          </Stack>
          <Typography sx={{ color: 'text.secondary' }}>
            {sharedTarget
              ? t('managedAgents.page.upgradeDialog.descriptionWithVersion', {
                  count: agents.length,
                  version: sharedTarget,
                })
              : t('managedAgents.page.upgradeDialog.mixedTargets')}
          </Typography>
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.upgradeDialog.disconnectWarning', {
              count: agents.length,
            })}{' '}
            {t('managedAgents.page.upgradeDialog.busyWarning')}
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
