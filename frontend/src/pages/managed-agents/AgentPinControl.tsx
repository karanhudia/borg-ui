import { useEffect, useState } from 'react'
import {
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../components/shared/ResponsiveDialog'
import type { AgentDesiredVersionRequest, AgentMachineResponse } from '../../services/api'

const TRACK_SERVER = ''
const LEAVE_INSTALLED = ''

/**
 * Pins one endpoint to a version, or clears the pin so it tracks the server.
 *
 * The agent version list offers only what this server serves: the installer
 * installs from this server's wheelhouse and nowhere else, so a pin to any
 * other version could never be satisfied and the server rejects it.
 */
export default function AgentPinControl({
  agent,
  open,
  busy = false,
  onSave,
  onCancel,
}: {
  agent: AgentMachineResponse | null
  open: boolean
  busy?: boolean
  onSave: (agent: AgentMachineResponse, data: AgentDesiredVersionRequest) => void
  onCancel: () => void
}) {
  const { t } = useTranslation()
  const [agentVersion, setAgentVersion] = useState(TRACK_SERVER)
  const [borgVersion, setBorgVersion] = useState(LEAVE_INSTALLED)

  useEffect(() => {
    setAgentVersion(agent?.desired_agent_version || TRACK_SERVER)
    setBorgVersion(agent?.desired_borg_version || LEAVE_INSTALLED)
  }, [agent])

  const available = agent?.available_agent_version
  // A pin outlives a server upgrade, so an endpoint can carry a version this
  // server no longer serves. Show it, or the select renders blank and saving
  // would silently move the pin. It cannot be re-selected: the server rejects
  // a pin it cannot serve, so the only ways out are the served version or no
  // pin at all.
  const stalePin =
    agent?.desired_agent_version && agent.desired_agent_version !== available
      ? agent.desired_agent_version
      : null

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
            disabled={busy || !agent || agentVersion === stalePin}
            onClick={() =>
              agent &&
              onSave(agent, {
                // Empty means "no pin", and the server stores that as null.
                desired_agent_version: agentVersion || null,
                desired_borg_version: (borgVersion || null) as '1' | '2' | null,
              })
            }
          >
            {t('managedAgents.page.pinControl.save')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('managedAgents.page.pinControl.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Typography sx={{ color: 'text.secondary' }}>
            {t('managedAgents.page.pinControl.hint')}
          </Typography>
          <FormControl fullWidth>
            <InputLabel id="agent-pin-version-label">
              {t('managedAgents.page.pinControl.agentVersionLabel')}
            </InputLabel>
            <Select
              labelId="agent-pin-version-label"
              displayEmpty
              value={agentVersion}
              label={t('managedAgents.page.pinControl.agentVersionLabel')}
              onChange={(event) => setAgentVersion(event.target.value)}
            >
              <MenuItem value={TRACK_SERVER}>
                {t('managedAgents.page.pinControl.trackServer')}
              </MenuItem>
              {available ? <MenuItem value={available}>{available}</MenuItem> : null}
              {stalePin ? (
                <MenuItem value={stalePin} disabled>
                  {t('managedAgents.page.pinControl.unavailableVersion', {
                    version: stalePin,
                  })}
                </MenuItem>
              ) : null}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel id="agent-pin-borg-label">
              {t('managedAgents.page.pinControl.borgVersionLabel')}
            </InputLabel>
            <Select
              labelId="agent-pin-borg-label"
              displayEmpty
              value={borgVersion}
              label={t('managedAgents.page.pinControl.borgVersionLabel')}
              onChange={(event) => setBorgVersion(event.target.value)}
            >
              <MenuItem value={LEAVE_INSTALLED}>
                {t('managedAgents.page.pinControl.leaveAsInstalled')}
              </MenuItem>
              <MenuItem value="1">Borg 1</MenuItem>
              <MenuItem value="2">Borg 2</MenuItem>
            </Select>
          </FormControl>
          <Typography variant="body2" sx={{ color: 'text.secondary' }}>
            {t('managedAgents.page.pinControl.borgHint')}
          </Typography>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
