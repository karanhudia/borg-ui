import type { TFunction } from 'i18next'
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
} from '@mui/material'
import type { SSHConnection, SystemSSHKey } from '../types'

interface DeleteKeyDialogProps {
  t: TFunction
  open: boolean
  setOpen: (open: boolean) => void
  systemKey: SystemSSHKey | undefined
  connections: SSHConnection[]
  pending: boolean
  onDelete: () => void
}

export function DeleteKeyDialog({
  t,
  open,
  setOpen,
  systemKey,
  connections,
  pending,
  onDelete,
}: DeleteKeyDialogProps) {
  return (
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.deleteKeyDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="warning" sx={{ mb: 1 }}>
            <Typography variant="body2" fontWeight={600} gutterBottom>
              {t('sshConnections.deleteKeyDialog.confirm')}
            </Typography>
          </Alert>

          {systemKey && (
            <Box
              sx={{
                p: 2,
                bgcolor: 'background.default',
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <Stack spacing={1}>
                <Typography variant="body2">
                  <strong>Key Name:</strong> {systemKey.name}
                </Typography>
                <Typography variant="body2">
                  <strong>Key Type:</strong> {systemKey.key_type?.toUpperCase()}
                </Typography>
                <Typography variant="body2">
                  <strong>Active Connections:</strong> {connections.length}
                </Typography>
                {systemKey.fingerprint && (
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}
                  >
                    <strong>Fingerprint:</strong> {systemKey.fingerprint}
                  </Typography>
                )}
              </Stack>
            </Box>
          )}

          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            This action will:
          </Typography>
          <Box component="ul" sx={{ m: 0, pl: 3 }}>
            <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
              {t('sshConnections.deleteKeyDialog.warning1')}
            </Typography>
            <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
              Mark {connections.length} connection(s) as failed
            </Typography>
            <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
              Clear SSH key from any repositories using it
            </Typography>
          </Box>

          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body2">{t('sshConnections.deleteKeyDialog.warning2')}</Typography>
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
        <Button variant="contained" color="error" onClick={onDelete} disabled={pending}>
          {pending ? 'Deleting...' : 'Delete SSH Key'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
