import type { Dispatch, SetStateAction } from 'react'
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
  TextField,
  Typography,
} from '@mui/material'
import type { SSHConnection } from '../types'

interface RedeployKeyDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  selectedConnection: SSHConnection | null
  setSelectedConnection: Dispatch<SetStateAction<SSHConnection | null>>
  redeployPassword: string
  setRedeployPassword: Dispatch<SetStateAction<string>>
  pending: boolean
  onConfirmRedeploy: () => void
}

export function RedeployKeyDialog({
  t,
  open,
  setOpen,
  selectedConnection,
  setSelectedConnection,
  redeployPassword,
  setRedeployPassword,
  pending,
  onConfirmRedeploy,
}: RedeployKeyDialogProps) {
  const close = () => {
    setOpen(false)
    setSelectedConnection(null)
    setRedeployPassword('')
  }

  return (
    <Dialog open={open} onClose={close} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.redeployDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info">{t('sshConnections.redeployDialog.info')}</Alert>
          {selectedConnection && (
            <Box sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography variant="body2">
                <strong>{t('sshConnections.deployDialog.host')}:</strong> {selectedConnection.host}
              </Typography>
              <Typography variant="body2">
                <strong>{t('sshConnections.deployDialog.username')}:</strong>{' '}
                {selectedConnection.username}
              </Typography>
              <Typography variant="body2">
                <strong>{t('sshConnections.deployDialog.port')}:</strong> {selectedConnection.port}
              </Typography>
            </Box>
          )}
          <TextField
            label={t('sshConnections.deployDialog.password')}
            type="password"
            fullWidth
            value={redeployPassword}
            onChange={(e) => setRedeployPassword(e.target.value)}
            placeholder={t('sshConnections.redeployDialog.passwordPlaceholder')}
            helperText={t('sshConnections.redeployDialog.passwordHelper')}
            InputLabelProps={{ shrink: true }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>{t('common.buttons.cancel')}</Button>
        <Button
          variant="contained"
          onClick={onConfirmRedeploy}
          disabled={pending || !redeployPassword}
        >
          {pending
            ? t('sshConnections.deployDialog.deploying')
            : t('sshConnections.deployDialog.deploy')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
