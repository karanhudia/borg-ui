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
 * Confirms one endpoint's remote upgrade. The endpoint reinstalls itself and
 * disconnects while it does, so the operator is told that plainly before
 * confirming rather than after the row goes quiet.
 */
export default function AgentUpgradeDialog({
  agent,
  open,
  busy = false,
  onConfirm,
  onCancel,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  busy?: boolean
  onConfirm: (agent: AgentMachineResponse) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  // A pin decides the target whatever the server serves, mirroring
  // `desired or available` in app/core/agent_versions.py.
  const targetVersion = agent?.desired_agent_version || agent?.available_agent_version

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
            disabled={busy || !agent}
            onClick={() => agent && onConfirm(agent)}
          >
            {t('managedAgents.page.upgradeDialog.confirm')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.upgradeDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ mt: 0.5 }}>
          <Typography sx={{ fontWeight: 700 }}>
            {[agent?.name, agent?.hostname].filter(Boolean).join(' · ')}
          </Typography>
          <Typography sx={{ color: 'text.secondary' }}>
            {targetVersion
              ? t('managedAgents.page.upgradeDialog.descriptionWithVersion', {
                  version: targetVersion,
                })
              : t('managedAgents.page.upgradeDialog.description')}
          </Typography>
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.upgradeDialog.disconnectWarning')}{' '}
            {t('managedAgents.page.upgradeDialog.busyWarning')}
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
