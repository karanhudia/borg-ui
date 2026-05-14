import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import type { SSHConnection } from '../types'

interface DeleteConnectionDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  selectedConnection: SSHConnection | null
  setSelectedConnection: Dispatch<SetStateAction<SSHConnection | null>>
  pending: boolean
  onConfirmDelete: () => void
}

export function DeleteConnectionDialog({
  t,
  open,
  setOpen,
  selectedConnection,
  setSelectedConnection,
  pending,
  onConfirmDelete,
}: DeleteConnectionDialogProps) {
  const close = () => {
    setOpen(false)
    setSelectedConnection(null)
  }

  return (
    <Dialog open={open} onClose={close} maxWidth="xs" fullWidth>
      <DialogTitle>{t('sshConnections.deleteConnectionDialog.title')}</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          Are you sure you want to delete this connection?
        </Alert>
        {selectedConnection && (
          <Stack spacing={1}>
            <Typography variant="body2">
              <strong>Host:</strong> {selectedConnection.host}
            </Typography>
            <Typography variant="body2">
              <strong>Username:</strong> {selectedConnection.username}
            </Typography>
            <Typography variant="body2">
              <strong>Port:</strong> {selectedConnection.port}
            </Typography>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button variant="contained" color="error" onClick={onConfirmDelete} disabled={pending}>
          {pending
            ? t('sshConnections.deleteConnectionDialog.deleting')
            : t('sshConnections.deleteConnectionDialog.delete')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
