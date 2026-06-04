import { useEffect, useRef, useState } from 'react'
import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import {
  Box,
  Button,
  ButtonBase,
  Checkbox,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  InputAdornment,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { alpha } from '@mui/material/styles'
import { Info } from 'lucide-react'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import { createConnectionForm } from '../formDefaults'
import { remoteMachineSetupPresets, type RemoteMachineSetupPresetId } from '../connectionPresets'
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

    setConnectionForm(
      preset.id === 'custom'
        ? createConnectionForm()
        : {
            ...connectionForm,
            ...preset.defaults,
            host: connectionForm.host,
            password: connectionForm.password,
          }
    )
    setHostError(undefined)
    setSelectedPreset(preset.id)
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
          <Box>
            <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
              {t('sshConnections.deployDialog.setupPreset')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t('sshConnections.deployDialog.setupPresetHint')}
            </Typography>
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, minmax(0, 1fr))',
                  md: 'repeat(3, minmax(0, 1fr))',
                },
                gap: 1,
              }}
            >
              {remoteMachineSetupPresets.map((preset) => {
                const Icon = preset.icon
                const selected = selectedPreset === preset.id
                const label = presetLabels[preset.id]

                return (
                  <ButtonBase
                    key={preset.id}
                    component="button"
                    type="button"
                    aria-pressed={selected}
                    onClick={() => applyPreset(preset.id)}
                    sx={(theme) => ({
                      alignItems: 'flex-start',
                      border: 1,
                      borderColor: selected ? 'primary.main' : 'divider',
                      borderRadius: 1,
                      bgcolor: selected
                        ? alpha(
                            theme.palette.primary.main,
                            theme.palette.mode === 'dark' ? 0.18 : 0.08
                          )
                        : 'background.paper',
                      color: 'text.primary',
                      cursor: 'pointer',
                      display: 'flex',
                      gap: 1.25,
                      justifyContent: 'flex-start',
                      minHeight: 112,
                      p: 1.5,
                      textAlign: 'left',
                      transition:
                        'border-color 180ms ease, background-color 180ms ease, box-shadow 180ms ease',
                      width: '100%',
                      '&:hover': {
                        borderColor: selected ? 'primary.main' : 'text.secondary',
                        bgcolor: selected
                          ? alpha(
                              theme.palette.primary.main,
                              theme.palette.mode === 'dark' ? 0.22 : 0.1
                            )
                          : 'action.hover',
                      },
                      '&:focus-visible': {
                        outline: `2px solid ${theme.palette.primary.main}`,
                        outlineOffset: 2,
                      },
                    })}
                  >
                    <Box
                      aria-hidden="true"
                      sx={(theme) => ({
                        alignItems: 'center',
                        bgcolor: selected
                          ? alpha(
                              theme.palette.primary.main,
                              theme.palette.mode === 'dark' ? 0.24 : 0.12
                            )
                          : 'action.hover',
                        borderRadius: 1,
                        color: selected ? 'primary.main' : 'text.secondary',
                        display: 'flex',
                        flexShrink: 0,
                        height: 32,
                        justifyContent: 'center',
                        width: 32,
                      })}
                    >
                      <Icon size={18} />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {label.title}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block', lineHeight: 1.35, mt: 0.25 }}
                      >
                        {label.description}
                      </Typography>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: 'block', fontFamily: 'monospace', mt: 0.75 }}
                      >
                        {label.defaults}
                      </Typography>
                    </Box>
                  </ButtonBase>
                )
              })}
            </Box>
          </Box>
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
