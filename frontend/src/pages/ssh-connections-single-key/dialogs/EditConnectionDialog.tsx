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
import { SshHostField } from './SshHostField'

interface EditConnectionDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  setSelectedConnection: Dispatch<SetStateAction<SSHConnection | null>>
  editConnectionForm: UpdateConnectionPayload
  setEditConnectionForm: Dispatch<SetStateAction<UpdateConnectionPayload>>
  hostError?: string
  setHostError: Dispatch<SetStateAction<string | undefined>>
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
  hostError,
  setHostError,
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
          <SshHostField
            label={t('sshConnections.deployDialog.host')}
            value={editConnectionForm.host}
            placeholder={t('sshConnections.deployDialog.hostPlaceholder')}
            hostError={hostError}
            onHostChange={(host) => {
              setEditConnectionForm({ ...editConnectionForm, host })
              setHostError(undefined)
            }}
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
                  {t('sshConnections.deployDialog.sftpModeHint')}
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
            helperText={t('sshConnections.deployDialog.defaultPathHelper')}
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.mountPoint')}
            fullWidth
            value={editConnectionForm.mount_point}
            onChange={(e) =>
              setEditConnectionForm({ ...editConnectionForm, mount_point: e.target.value })
            }
            placeholder={t('sshConnections.deployDialog.mountPointPlaceholder')}
            helperText={t('sshConnections.deployDialog.mountPointHelper')}
            InputLabelProps={{ shrink: true }}
          />
          <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
            {t('sshConnections.editConnectionDialog.updateInfo')}
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.buttons.cancel')}</Button>
        <Button
          variant="contained"
          onClick={onUpdate}
          disabled={pending || !editConnectionForm.host || !editConnectionForm.username}
        >
          {pending
            ? t('sshConnections.editConnectionDialog.updating')
            : t('sshConnections.editConnectionDialog.submit')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
