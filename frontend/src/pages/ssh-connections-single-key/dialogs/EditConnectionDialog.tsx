import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import type { SSHConnection, UpdateConnectionPayload } from '../types'

interface EditConnectionDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  setSelectedConnection: Dispatch<SetStateAction<SSHConnection | null>>
  editConnectionForm: UpdateConnectionPayload
  setEditConnectionForm: Dispatch<SetStateAction<UpdateConnectionPayload>>
  pending: boolean
  onUpdate: () => void
}

export function EditConnectionDialog({
  t,
  open,
  setOpen,
  setSelectedConnection,
  editConnectionForm,
  setEditConnectionForm,
  pending,
  onUpdate,
}: EditConnectionDialogProps) {
  const close = () => {
    setOpen(false)
    setSelectedConnection(null)
  }

  return (
    <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.editConnectionDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <TextField
            label={t('sshConnections.deployDialog.host')}
            fullWidth
            value={editConnectionForm.host}
            onChange={(e) => setEditConnectionForm({ ...editConnectionForm, host: e.target.value })}
            placeholder="192.168.1.100 or example.com"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.username')}
            fullWidth
            value={editConnectionForm.username}
            onChange={(e) =>
              setEditConnectionForm({ ...editConnectionForm, username: e.target.value })
            }
            placeholder="root"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.port')}
            type="number"
            fullWidth
            value={editConnectionForm.port}
            onChange={(e) =>
              setEditConnectionForm({ ...editConnectionForm, port: parseInt(e.target.value) })
            }
            InputLabelProps={{ shrink: true }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={editConnectionForm.use_sftp_mode}
                onChange={(e) =>
                  setEditConnectionForm({ ...editConnectionForm, use_sftp_mode: e.target.checked })
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
          <FormControlLabel
            control={
              <Checkbox
                checked={editConnectionForm.use_sudo}
                onChange={(e) =>
                  setEditConnectionForm({ ...editConnectionForm, use_sudo: e.target.checked })
                }
              />
            }
            label={
              <Box>
                <Typography variant="body2">{t('sshConnections.deployDialog.useSudo')}</Typography>
                <Typography variant="caption" color="text.secondary">
                  {t('sshConnections.deployDialog.useSudoHint')}
                </Typography>
              </Box>
            }
          />
          <TextField
            label={t('sshConnections.deployDialog.defaultPath')}
            fullWidth
            value={editConnectionForm.default_path}
            onChange={(e) =>
              setEditConnectionForm({ ...editConnectionForm, default_path: e.target.value })
            }
            placeholder="/home"
            helperText="Starting directory for SSH file browsing (e.g., /home for Hetzner Storage Box)"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.mountPoint')}
            fullWidth
            value={editConnectionForm.mount_point}
            onChange={(e) =>
              setEditConnectionForm({ ...editConnectionForm, mount_point: e.target.value })
            }
            placeholder="hetzner or homeserver"
            helperText="Friendly name for this remote machine (e.g., hetzner, backup-server)"
            InputLabelProps={{ shrink: true }}
          />
          <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
            Update the connection details. You may want to test the connection after updating.
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button
          variant="contained"
          onClick={onUpdate}
          disabled={pending || !editConnectionForm.host || !editConnectionForm.username}
        >
          {pending ? 'Updating...' : t('sshConnections.editConnectionDialog.submit')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
