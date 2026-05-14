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

interface DeployKeyDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  connectionForm: DeployConnectionPayload
  setConnectionForm: Dispatch<SetStateAction<DeployConnectionPayload>>
  pending: boolean
  onDeploy: () => void
}

export function DeployKeyDialog({
  t,
  open,
  setOpen,
  connectionForm,
  setConnectionForm,
  pending,
  onDeploy,
}: DeployKeyDialogProps) {
  return (
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.deployDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label={t('sshConnections.deployDialog.host')}
            fullWidth
            value={connectionForm.host}
            onChange={(e) => setConnectionForm({ ...connectionForm, host: e.target.value })}
            placeholder="192.168.1.100 or example.com"
            InputLabelProps={{ shrink: true }}
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
            placeholder="Server password (for initial deployment)"
            InputLabelProps={{ shrink: true }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <Tooltip
                    title="The password is used to deploy your public key to the server's authorized_keys file. After deployment, you'll connect using the SSH key."
                    arrow
                  >
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
                  Required by Hetzner Storage Box. Disable for Synology NAS or older SSH servers.
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
            helperText="Starting directory for SSH file browsing (e.g., /home for Hetzner Storage Box)"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.mountPoint')}
            fullWidth
            value={connectionForm.mount_point}
            onChange={(e) => setConnectionForm({ ...connectionForm, mount_point: e.target.value })}
            placeholder="hetzner or homeserver"
            helperText="Friendly name for this remote machine (e.g., hetzner, backup-server)"
            InputLabelProps={{ shrink: true }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
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
