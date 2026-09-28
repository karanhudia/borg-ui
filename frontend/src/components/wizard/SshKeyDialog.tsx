import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material'
import { KeyRound, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../shared/ResponsiveDialog'

export type SshKeyCreateInput = {
  name: string
  private_key: string
}

interface SshKeyDialogProps {
  open: boolean
  isCreating?: boolean
  error?: string | null
  disablePortal?: boolean
  onClose: () => void
  onCreate: (data: SshKeyCreateInput) => void
}

export default function SshKeyDialog({
  open,
  isCreating = false,
  error = null,
  disablePortal,
  onClose,
  onCreate,
}: SshKeyDialogProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [privateKey, setPrivateKey] = useState('')

  useEffect(() => {
    if (open) {
      setName('')
      setPrivateKey('')
    }
  }, [open])

  const canSubmit = name.trim() !== '' && privateKey.trim() !== '' && !isCreating

  return (
    <ResponsiveDialog
      open={open}
      onClose={isCreating ? undefined : () => onClose()}
      maxWidth="sm"
      fullWidth
      disablePortal={disablePortal}
      footer={
        <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
          <Button onClick={onClose} disabled={isCreating}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={() => onCreate({ name: name.trim(), private_key: privateKey })}
            disabled={!canSubmit}
            startIcon={
              isCreating ? <CircularProgress size={16} color="inherit" /> : <Plus size={16} />
            }
          >
            {t('wizard.cloudMirror.sshKeyDialogSubmit')}
          </Button>
        </DialogActions>
      }
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <KeyRound size={18} />
        {t('wizard.cloudMirror.sshKeyDialogTitle')}
      </DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.25, pt: 1.25 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label={t('wizard.cloudMirror.sshKeyNameLabel')}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="borgbase-sftp"
            required
            fullWidth
            disabled={isCreating}
          />
          <TextField
            label={t('wizard.cloudMirror.sshKeyPrivateKeyLabel')}
            value={privateKey}
            onChange={(event) => setPrivateKey(event.target.value)}
            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
            helperText={t('wizard.cloudMirror.sshKeyPrivateKeyHelper')}
            required
            fullWidth
            multiline
            minRows={6}
            disabled={isCreating}
            slotProps={{ htmlInput: { spellCheck: false, style: { fontFamily: 'monospace' } } }}
          />
        </Box>
      </DialogContent>
    </ResponsiveDialog>
  )
}
