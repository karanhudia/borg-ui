import { useEffect, useState } from 'react'
import { Alert, Box, Button, Stack, TextField, Typography } from '@mui/material'
import { Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQueryClient } from '@tanstack/react-query'

import SshConnectionSelect from '../shared/SshConnectionSelect'
import { getApiErrorDetail } from '../../utils/apiErrors'
import { translateBackendKey } from '../../utils/translateBackendKey'
import { connectNewMachine, SshConnectError, useSshConnections } from './quickStartSsh'

interface QuickStartSshConnectProps {
  value: number | ''
  onChange: (connectionId: number) => void
  label: string
  /** settings.ssh.manage: without it only existing connections can be picked. */
  canAddMachine: boolean
  /** Reports a key deploy in flight, so the dialog can refuse to close under it. */
  onBusyChange?: (busy: boolean) => void
}

const emptyForm = { host: '', username: '', port: '22', password: '' }

/** Pick an SSH connection, or add a machine by installing the key with a one-time password. */
export default function QuickStartSshConnect({
  value,
  onChange,
  label,
  canAddMachine,
  onBusyChange,
}: QuickStartSshConnectProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  // A failed deploy leaves a connection row behind; it cannot run backups, so it is not offered.
  const connections = useSshConnections().filter((connection) => connection.status !== 'failed')
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState(emptyForm)
  const [connecting, setConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    onBusyChange?.(connecting)
    return () => onBusyChange?.(false)
  }, [connecting, onBusyChange])

  const showForm = canAddMachine && (adding || connections.length === 0)
  const port = Number(form.port)
  const formValid =
    form.host.trim() &&
    form.username.trim() &&
    form.password &&
    Number.isInteger(port) &&
    port > 0 &&
    port < 65536

  const connect = async () => {
    setConnecting(true)
    setError(null)
    try {
      const id = await connectNewMachine({ ...form, port })
      await queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      onChange(id)
      setForm(emptyForm)
      setAdding(false)
    } catch (caught) {
      setError(
        caught instanceof SshConnectError
          ? t('quickStart.ssh.connectFailed', { reason: caught.message })
          : translateBackendKey(getApiErrorDetail(caught))
      )
    } finally {
      setConnecting(false)
    }
  }

  const field = (key: keyof typeof emptyForm) => ({
    value: form[key],
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [key]: event.target.value })),
    size: 'small' as const,
    fullWidth: true,
    disabled: connecting,
  })

  if (!canAddMachine && connections.length === 0) {
    return (
      <Alert severity="info" variant="outlined">
        {t('quickStart.ssh.noConnectionsNoPermission')}
      </Alert>
    )
  }

  return (
    <Stack spacing={1.5}>
      {connections.length > 0 && !showForm && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} sx={{ alignItems: 'stretch' }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <SshConnectionSelect
              value={value}
              onChange={onChange}
              connections={connections}
              label={label}
              emptyMessage=""
              hideEmptyAlert
            />
          </Box>
          {canAddMachine && (
            <Button
              variant="outlined"
              startIcon={<Plus size={16} />}
              onClick={() => setAdding(true)}
              sx={{ flexShrink: 0 }}
            >
              {t('quickStart.ssh.addMachine')}
            </Button>
          )}
        </Stack>
      )}

      {showForm && (
        <Box sx={{ border: 1, borderColor: 'divider', borderRadius: 2, p: 2 }} component="fieldset">
          <Typography variant="subtitle2" component="legend" sx={{ px: 0.5 }}>
            {t('quickStart.ssh.newMachine')}
          </Typography>
          <Stack spacing={1.5}>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              {t('quickStart.ssh.newMachineHint')}
            </Typography>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5}>
              <TextField
                label={t('quickStart.ssh.host')}
                placeholder="nas.local"
                {...field('host')}
                autoComplete="off"
              />
              <TextField
                label={t('quickStart.ssh.port')}
                {...field('port')}
                type="number"
                sx={{ width: { sm: 120 }, flexShrink: 0 }}
              />
            </Stack>
            <TextField
              label={t('quickStart.ssh.username')}
              placeholder="backup"
              {...field('username')}
              autoComplete="off"
            />
            <TextField
              label={t('quickStart.ssh.password')}
              {...field('password')}
              type="password"
              autoComplete="off"
              helperText={t('quickStart.ssh.passwordHint')}
            />
            {error && (
              <Alert severity="error" role="alert">
                {error}
              </Alert>
            )}
            <Stack direction="row" spacing={1} sx={{ justifyContent: 'flex-end' }}>
              {connections.length > 0 && (
                <Button
                  onClick={() => {
                    // Do not keep a typed password around once the form is gone.
                    setForm(emptyForm)
                    setError(null)
                    setAdding(false)
                  }}
                  disabled={connecting}
                >
                  {t('common.buttons.cancel')}
                </Button>
              )}
              <Button variant="contained" onClick={connect} disabled={!formValid || connecting}>
                {connecting ? t('quickStart.ssh.connecting') : t('quickStart.ssh.connect')}
              </Button>
            </Stack>
          </Stack>
        </Box>
      )}
    </Stack>
  )
}
