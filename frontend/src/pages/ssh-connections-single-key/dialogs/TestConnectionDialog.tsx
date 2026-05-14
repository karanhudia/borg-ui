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
  TextField,
  Typography,
} from '@mui/material'
import type { TestConnectionPayload } from '../types'

interface TestConnectionDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  testConnectionForm: TestConnectionPayload
  setTestConnectionForm: Dispatch<SetStateAction<TestConnectionPayload>>
  pending: boolean
  onTest: () => void
}

export function TestConnectionDialog({
  t,
  open,
  setOpen,
  testConnectionForm,
  setTestConnectionForm,
  pending,
  onTest,
}: TestConnectionDialogProps) {
  return (
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.manualConnectionDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
            <Typography variant="body2" fontWeight={600} gutterBottom>
              {t('sshConnections.manualConnectionDialog.instructions.title')}
            </Typography>
            <Typography variant="caption" component="div" sx={{ mb: 0.5 }}>
              1. {t('sshConnections.manualConnectionDialog.instructions.step1')}
            </Typography>
            <Typography variant="caption" component="div" sx={{ mb: 0.5 }}>
              2. {t('sshConnections.manualConnectionDialog.instructions.step2')}
            </Typography>
            <Typography variant="caption" component="div">
              3. {t('sshConnections.manualConnectionDialog.instructions.step3')}
            </Typography>
          </Alert>

          <TextField
            label={t('sshConnections.deployDialog.host')}
            fullWidth
            value={testConnectionForm.host}
            onChange={(e) => setTestConnectionForm({ ...testConnectionForm, host: e.target.value })}
            placeholder="192.168.1.100 or example.com"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.username')}
            fullWidth
            value={testConnectionForm.username}
            onChange={(e) =>
              setTestConnectionForm({ ...testConnectionForm, username: e.target.value })
            }
            placeholder="root"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.deployDialog.port')}
            type="number"
            fullWidth
            value={testConnectionForm.port}
            onChange={(e) =>
              setTestConnectionForm({ ...testConnectionForm, port: parseInt(e.target.value) })
            }
            InputLabelProps={{ shrink: true }}
          />

          <Alert severity="success" sx={{ fontSize: '0.85rem' }}>
            This will test the connection and add it to your connections list if successful.
          </Alert>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
        <Button
          variant="contained"
          onClick={onTest}
          disabled={pending || !testConnectionForm.host || !testConnectionForm.username}
        >
          {pending ? 'Testing...' : t('sshConnections.manualConnectionDialog.submit')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
