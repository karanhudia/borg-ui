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
} from '@mui/material'
import type { ImportKeyPayload } from '../types'

interface ImportKeyDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  importForm: ImportKeyPayload
  setImportForm: Dispatch<SetStateAction<ImportKeyPayload>>
  pending: boolean
  onImport: () => void
}

export function ImportKeyDialog({
  t,
  open,
  setOpen,
  importForm,
  setImportForm,
  pending,
  onImport,
}: ImportKeyDialogProps) {
  return (
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.importDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info">
            Import an existing SSH key from your filesystem (e.g., mounted volume). The key will be
            read from the specified paths and stored in the database.
          </Alert>

          <TextField
            label={t('sshConnections.importDialog.keyName')}
            fullWidth
            value={importForm.name}
            onChange={(e) => setImportForm({ ...importForm, name: e.target.value })}
            placeholder="System SSH Key"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.importDialog.privateKeyPath')}
            fullWidth
            required
            value={importForm.private_key_path}
            onChange={(e) => setImportForm({ ...importForm, private_key_path: e.target.value })}
            placeholder="/home/borg/.ssh/id_ed25519 or /root/.ssh/id_rsa"
            helperText="Absolute path to the private key file"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.importDialog.publicKeyPath')}
            fullWidth
            value={importForm.public_key_path}
            onChange={(e) => setImportForm({ ...importForm, public_key_path: e.target.value })}
            placeholder="Leave empty to auto-detect (adds .pub to private key path)"
            helperText="If not provided, will try {private_key_path}.pub"
            InputLabelProps={{ shrink: true }}
          />
          <TextField
            label={t('sshConnections.importDialog.description')}
            fullWidth
            value={importForm.description}
            onChange={(e) => setImportForm({ ...importForm, description: e.target.value })}
            placeholder="Imported system SSH key"
            InputLabelProps={{ shrink: true }}
            multiline
            rows={2}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>Cancel</Button>
        <Button
          variant="contained"
          onClick={onImport}
          disabled={pending || !importForm.private_key_path}
        >
          {pending
            ? t('sshConnections.importDialog.importing')
            : t('sshConnections.importDialog.import')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
