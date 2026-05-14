import type { Dispatch, SetStateAction } from 'react'
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
      <DialogTitle>Deploy SSH Key to Connection</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info">
            This will deploy your current system SSH key to this connection. You'll need to provide
            the password to authenticate.
          </Alert>
          {selectedConnection && (
            <Box sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography variant="body2">
                <strong>Host:</strong> {selectedConnection.host}
              </Typography>
              <Typography variant="body2">
                <strong>Username:</strong> {selectedConnection.username}
              </Typography>
              <Typography variant="body2">
                <strong>Port:</strong> {selectedConnection.port}
              </Typography>
            </Box>
          )}
          <TextField
            label="Password"
            type="password"
            fullWidth
            value={redeployPassword}
            onChange={(e) => setRedeployPassword(e.target.value)}
            placeholder="Enter SSH password"
            helperText="Password is used to deploy the public key to authorized_keys"
            InputLabelProps={{ shrink: true }}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Cancel</Button>
        <Button
          variant="contained"
          onClick={onConfirmRedeploy}
          disabled={pending || !redeployPassword}
        >
          {pending ? 'Deploying...' : 'Deploy Key'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
