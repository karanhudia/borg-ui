import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import {
  Box,
  Button,
  Checkbox,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormHelperText,
  InputLabel,
  InputAdornment,
  MenuItem,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { Info } from 'lucide-react'
import RichSelectRow from '../../../components/shared/RichSelectRow'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import { createConnectionForm } from '../formDefaults'
import {
  remoteMachineSetupPresets,
  type RemoteMachineSetupPreset,
  type RemoteMachineSetupPresetId,
} from '../connectionPresets'
import type { DeployConnectionPayload } from '../types'
import { SshHostField } from './SshHostField'

interface DeployKeyDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  connectionForm: DeployConnectionPayload
  setConnectionForm: Dispatch<SetStateAction<DeployConnectionPayload>>
  hostError?: string
  setHostError: Dispatch<SetStateAction<string | undefined>>
  pending: boolean
  onDeploy: () => void
}

function getPresetIdForForm(connectionForm: DeployConnectionPayload): RemoteMachineSetupPresetId {
  const matchingPreset = remoteMachineSetupPresets.find((preset) => {
    if (preset.id === 'custom') {
      return false
    }

    return Object.entries(preset.defaults).every(([key, value]) => {
      return connectionForm[key as keyof DeployConnectionPayload] === value
    })
  })

  return matchingPreset?.id ?? 'custom'
}

export function DeployKeyDialog({
  t,
  open,
  setOpen,
  connectionForm,
  setConnectionForm,
  hostError,
  setHostError,
  pending,
  onDeploy,
}: DeployKeyDialogProps) {
  const [selectedPreset, setSelectedPreset] = useState<RemoteMachineSetupPresetId>(() =>
    getPresetIdForForm(connectionForm)
  )
  const wasOpenRef = useRef(open)

  useEffect(() => {
    if (open && !wasOpenRef.current) {
      setSelectedPreset(getPresetIdForForm(connectionForm))
    }
    wasOpenRef.current = open
  }, [connectionForm, open])

  const presetLabels: Record<
    RemoteMachineSetupPresetId,
    { title: string; description: string; defaults: string }
  > = {
    custom: {
      title: t('sshConnections.deployDialog.presetCustom'),
      description: t('sshConnections.deployDialog.presetCustomDescription'),
      defaults: t('sshConnections.deployDialog.presetCustomDefaults'),
    },
    linux: {
      title: t('sshConnections.deployDialog.presetLinux'),
      description: t('sshConnections.deployDialog.presetLinuxDescription'),
      defaults: t('sshConnections.deployDialog.presetLinuxDefaults'),
    },
    borgbase: {
      title: t('sshConnections.deployDialog.presetBorgBase'),
      description: t('sshConnections.deployDialog.presetBorgBaseDescription'),
      defaults: t('sshConnections.deployDialog.presetBorgBaseDefaults'),
    },
    hetzner: {
      title: t('sshConnections.deployDialog.presetHetzner'),
      description: t('sshConnections.deployDialog.presetHetznerDescription'),
      defaults: t('sshConnections.deployDialog.presetHetznerDefaults'),
    },
    nas: {
      title: t('sshConnections.deployDialog.presetNas'),
      description: t('sshConnections.deployDialog.presetNasDescription'),
      defaults: t('sshConnections.deployDialog.presetNasDefaults'),
    },
  }

  const close = () => setOpen(false)

  const applyPreset = (presetId: RemoteMachineSetupPresetId) => {
    const preset = remoteMachineSetupPresets.find((item) => item.id === presetId)
    if (!preset) return

    setConnectionForm((current) => {
      const nextForm =
        preset.id === 'custom'
          ? createConnectionForm()
          : {
              ...current,
              ...preset.defaults,
            }

      return {
        ...nextForm,
        host: current.host,
        password: current.password,
      }
    })
    setHostError(undefined)
    setSelectedPreset(preset.id)
  }

  const getPresetLabel = (presetId: RemoteMachineSetupPresetId) => presetLabels[presetId]
  const renderPresetRow = (preset: RemoteMachineSetupPreset) => {
    const Icon = preset.icon
    const label = getPresetLabel(preset.id)

    return (
      <RichSelectRow
        icon={
          <Box
            aria-hidden
            component="span"
            data-testid={`remote-machine-preset-icon-${preset.id}`}
            style={{ color: preset.color, display: 'inline-flex', lineHeight: 0 }}
          >
            <Icon size={18} />
          </Box>
        }
        primary={label.title}
        secondary={`${label.description} ${label.defaults}`}
      />
    )
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={close}
      maxWidth="md"
      fullWidth
      footer={
        <DialogActions>
          <Button onClick={close}>{t('common.buttons.cancel')}</Button>
          <Button
            variant="contained"
            onClick={onDeploy}
            disabled={
              pending ||
              !connectionForm.host ||
              !connectionForm.username ||
              !connectionForm.password
            }
          >
            {pending
              ? t('sshConnections.deployDialog.deploying')
              : t('sshConnections.deployDialog.deploy')}
          </Button>
        </DialogActions>
      }
    >
      <DialogTitle>{t('sshConnections.deployDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <FormControl fullWidth>
            <InputLabel id="deploy-key-setup-preset-label">
              {t('sshConnections.deployDialog.setupPreset')}
            </InputLabel>
            <Select
              labelId="deploy-key-setup-preset-label"
              label={t('sshConnections.deployDialog.setupPreset')}
              value={selectedPreset}
              onChange={(event) => applyPreset(event.target.value as RemoteMachineSetupPresetId)}
              renderValue={(value) => {
                const preset =
                  remoteMachineSetupPresets.find((item) => item.id === value) ??
                  remoteMachineSetupPresets[0]
                return renderPresetRow(preset)
              }}
              sx={{
                '& .MuiSelect-select': {
                  alignItems: 'center',
                  display: 'flex',
                  minHeight: 40,
                },
              }}
            >
              {remoteMachineSetupPresets.map((preset) => (
                <MenuItem key={preset.id} value={preset.id} sx={{ py: 1 }}>
                  {renderPresetRow(preset)}
                </MenuItem>
              ))}
            </Select>
            <FormHelperText>{t('sshConnections.deployDialog.setupPresetHint')}</FormHelperText>
          </FormControl>
          <SshHostField
            label={t('sshConnections.deployDialog.host')}
            value={connectionForm.host}
            placeholder={t('sshConnections.deployDialog.hostPlaceholder')}
            hostError={hostError}
            onHostChange={(host) => {
              setConnectionForm({ ...connectionForm, host })
              setHostError(undefined)
            }}
          />
          <TextField
            label={t('sshConnections.deployDialog.username')}
            fullWidth
            value={connectionForm.username}
            onChange={(e) => setConnectionForm({ ...connectionForm, username: e.target.value })}
            placeholder="root"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.port')}
            type="number"
            fullWidth
            value={connectionForm.port}
            onChange={(e) =>
              setConnectionForm({ ...connectionForm, port: parseInt(e.target.value) })
            }
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.password')}
            type="password"
            fullWidth
            value={connectionForm.password}
            onChange={(e) => setConnectionForm({ ...connectionForm, password: e.target.value })}
            placeholder={t('sshConnections.deployDialog.passwordPlaceholder')}
            InputLabelProps={{ shrink: true }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <Tooltip title={t('sshConnections.deployDialog.passwordHelp')} arrow>
                    <Box
                      component="span"
                      sx={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        color: 'text.secondary',
                        cursor: 'help',
                      }}
                    >
                      <Info size={18} />
                    </Box>
                  </Tooltip>
                </InputAdornment>
              ),
            }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={connectionForm.use_sftp_mode}
                onChange={(e) =>
                  setConnectionForm({ ...connectionForm, use_sftp_mode: e.target.checked })
                }
              />
            }
            label={
              <Box>
                <Typography variant="body2">{t('sshConnections.deployDialog.sftpMode')}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('sshConnections.deployDialog.sftpModeHint')}
                </Typography>
              </Box>
            }
          />
          <TextField
            label={t('sshConnections.deployDialog.defaultPath')}
            fullWidth
            value={connectionForm.default_path}
            onChange={(e) => setConnectionForm({ ...connectionForm, default_path: e.target.value })}
            placeholder="/home"
            helperText={t('sshConnections.deployDialog.defaultPathHelper')}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.sshPathPrefix')}
            fullWidth
            value={connectionForm.ssh_path_prefix}
            onChange={(e) =>
              setConnectionForm({ ...connectionForm, ssh_path_prefix: e.target.value })
            }
            placeholder="/volume1"
            helperText={t('sshConnections.deployDialog.sshPathPrefixHelper')}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.mountPoint')}
            fullWidth
            value={connectionForm.mount_point}
            onChange={(e) => setConnectionForm({ ...connectionForm, mount_point: e.target.value })}
            placeholder={t('sshConnections.deployDialog.mountPointPlaceholder')}
            helperText={t('sshConnections.deployDialog.mountPointHelper')}
            InputLabelProps={{ shrink: true }}
          />
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
