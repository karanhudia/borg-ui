import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import {
  Box,
  Button,
  Checkbox,
  Dialog,
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
import { Info } from 'lucide-react'
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
  return (
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.deployDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
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
      <DialogActions>
        <Button onClick={() => setOpen(false)}>{t('common.buttons.cancel')}</Button>
        <Button
          variant="contained"
          onClick={onDeploy}
          disabled={
            pending || !connectionForm.host || !connectionForm.username || !connectionForm.password
          }
        >
          {pending
            ? t('sshConnections.deployDialog.deploying')
            : t('sshConnections.deployDialog.deploy')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
