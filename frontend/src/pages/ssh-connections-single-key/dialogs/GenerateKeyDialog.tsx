import type { Dispatch, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
} from '@mui/material'

interface GenerateKeyDialogProps {
  t: TFunction
  open: boolean
  setOpen: Dispatch<SetStateAction<boolean>>
  keyType: string
  setKeyType: Dispatch<SetStateAction<string>>
  pending: boolean
  onGenerate: () => void
}

export function GenerateKeyDialog({
  t,
  open,
  setOpen,
  keyType,
  setKeyType,
  pending,
  onGenerate,
}: GenerateKeyDialogProps) {
  return (
    <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('sshConnections.generateDialog.title')}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          <Alert severity="info">{t('sshConnections.generateDialog.info')}</Alert>

          <FormControl fullWidth>
            <InputLabel>{t('sshConnections.generateDialog.keyType')}</InputLabel>
            <Select
              value={keyType}
              label={t('sshConnections.generateDialog.keyType')}
              onChange={(e) => setKeyType(e.target.value)}
            >
              <MenuItem value="ed25519">{t('sshConnections.generateDialog.ed25519')}</MenuItem>
              <MenuItem value="rsa">{t('sshConnections.generateDialog.rsa')}</MenuItem>
              <MenuItem value="ecdsa">{t('sshConnections.generateDialog.ecdsa')}</MenuItem>
            </Select>
          </FormControl>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setOpen(false)}>{t('common.buttons.cancel')}</Button>
        <Button variant="contained" onClick={onGenerate} disabled={pending}>
          {pending
            ? t('sshConnections.generateDialog.generating')
            : t('sshConnections.generateDialog.generate')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
