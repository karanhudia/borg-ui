import {
  Alert,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../components/shared/ResponsiveDialog'
import type { AgentMachineResponse } from '../../services/api'
import CopyableCodeBlock from './CopyableCodeBlock'
import { buildSetServerCommand, isSafeServerUrlForCommand } from './agentSetServerCommandText'

/**
 * Hands the operator one command that moves an endpoint to a new server
 * address.
 *
 * The endpoint's current `server_url` is not stored on the server, so the
 * field cannot be prefilled from the record. It prefills with this server's
 * own base URL, which is the value the operator almost always wants and the
 * same one the enrollment command uses, and points at `borg-ui-agent status`
 * for reading what the endpoint actually holds.
 */
export default function AgentSetServerDialog({
  agent,
  open,
  defaultServerUrl,
  onCopy,
  onCancel,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  defaultServerUrl: string
  onCopy: (value: string) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [serverUrl, setServerUrl] = useState(defaultServerUrl)
  // Reset per target so an edit made for one endpoint is not carried to the
  // next card the operator opens.
  useEffect(() => {
    setServerUrl(defaultServerUrl)
  }, [agent, defaultServerUrl])

  const valid = isSafeServerUrlForCommand(serverUrl)
  const command = buildSetServerCommand(serverUrl, agent?.agent_version)

  return (
    <ResponsiveDialog
      open={open}
      onClose={onCancel}
      fullWidth
      maxWidth="md"
      footer={
        <DialogActions>
          <Button onClick={onCancel}>{t('common.buttons.close')}</Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.setServerDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 0.5 }}>
          <Stack spacing={0.5}>
            <Typography sx={{ fontWeight: 700 }}>
              {[agent?.name, agent?.hostname].filter(Boolean).join(' · ')}
            </Typography>
            <Typography sx={{ color: 'text.secondary' }}>
              {t('managedAgents.page.setServerDialog.description')}
            </Typography>
          </Stack>
          <TextField
            fullWidth
            size="small"
            value={serverUrl}
            onChange={(event) => setServerUrl(event.target.value)}
            label={t('managedAgents.page.setServerDialog.fieldLabel')}
            error={serverUrl.length > 0 && !valid}
            helperText={
              serverUrl.length > 0 && !valid
                ? t('managedAgents.page.setServerDialog.invalidUrl')
                : t('managedAgents.page.setServerDialog.fieldHelper')
            }
          />
          {valid ? (
            <>
              <CopyableCodeBlock
                value={command}
                copyLabel={t('managedAgents.page.setServerDialog.copyCommand')}
                onCopy={() => onCopy(command)}
              />
              <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                {t('managedAgents.page.setServerDialog.runHint')}
              </Typography>
            </>
          ) : null}
          <Alert severity="info" sx={{ borderRadius: 1.5 }}>
            {t('managedAgents.page.setServerDialog.statusHint')}
          </Alert>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
