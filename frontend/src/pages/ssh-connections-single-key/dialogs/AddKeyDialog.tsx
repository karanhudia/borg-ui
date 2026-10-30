import { useEffect, useState } from 'react'
import {
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Tab,
  Tabs,
  TextField,
} from '@mui/material'
import { KeyRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'

export type AddKeyInput =
  | { mode: 'generate'; name: string; key_type: string }
  | { mode: 'import'; name: string; private_key_path: string; public_key_path: string }
  | { mode: 'paste'; name: string; private_key: string }

type Mode = AddKeyInput['mode']

interface AddKeyDialogProps {
  open: boolean
  pending?: boolean
  onClose: () => void
  onSubmit: (input: AddKeyInput) => void
}

const KEY_TYPES = ['ed25519', 'rsa', 'ecdsa'] as const

export function AddKeyDialog({ open, pending = false, onClose, onSubmit }: AddKeyDialogProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('generate')
  const [name, setName] = useState('')
  const [keyType, setKeyType] = useState<string>('ed25519')
  const [privateKeyPath, setPrivateKeyPath] = useState('')
  const [publicKeyPath, setPublicKeyPath] = useState('')
  const [privateKey, setPrivateKey] = useState('')

  useEffect(() => {
    if (open) return
    // The dialog stays mounted, so drop the pasted key as soon as it closes.
    setMode('generate')
    setName('')
    setKeyType('ed25519')
    setPrivateKeyPath('')
    setPublicKeyPath('')
    setPrivateKey('')
  }, [open])

  const trimmedName = name.trim()
  const canSubmit =
    !pending &&
    trimmedName !== '' &&
    (mode === 'generate' ||
      (mode === 'import' && privateKeyPath.trim() !== '') ||
      (mode === 'paste' && privateKey.trim() !== ''))

  const submit = () => {
    if (mode === 'generate') onSubmit({ mode, name: trimmedName, key_type: keyType })
    else if (mode === 'import')
      onSubmit({
        mode,
        name: trimmedName,
        private_key_path: privateKeyPath.trim(),
        public_key_path: publicKeyPath.trim(),
      })
    else onSubmit({ mode, name: trimmedName, private_key: privateKey })
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={pending ? undefined : () => onClose()}
      maxWidth="sm"
      fullWidth
      footer={
        <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
          <Button onClick={onClose} disabled={pending}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            variant="contained"
            onClick={submit}
            disabled={!canSubmit}
            startIcon={pending ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            {pending
              ? t('sshConnections.extraKeys.addDialog.submitting')
              : t('sshConnections.extraKeys.addDialog.submit')}
          </Button>
        </DialogActions>
      }
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <KeyRound size={18} />
        {t('sshConnections.extraKeys.addDialog.title')}
      </DialogTitle>
      <DialogContent>
        <Tabs
          value={mode}
          onChange={(_, next: Mode) => setMode(next)}
          variant="fullWidth"
          sx={{ mb: 2, borderBottom: 1, borderColor: 'divider' }}
        >
          <Tab value="generate" label={t('sshConnections.extraKeys.addDialog.tabGenerate')} />
          <Tab value="import" label={t('sshConnections.extraKeys.addDialog.tabImport')} />
          <Tab value="paste" label={t('sshConnections.extraKeys.addDialog.tabPaste')} />
        </Tabs>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.25, pt: 0.5 }}>
          <TextField
            label={t('sshConnections.extraKeys.addDialog.keyName')}
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder={t('sshConnections.extraKeys.addDialog.keyNamePlaceholder')}
            required
            fullWidth
            disabled={pending}
          />
          {mode === 'generate' && (
            <TextField
              select
              label={t('sshConnections.extraKeys.addDialog.keyType')}
              value={keyType}
              onChange={(event) => setKeyType(event.target.value)}
              fullWidth
              disabled={pending}
            >
              {KEY_TYPES.map((type) => (
                <MenuItem key={type} value={type}>
                  {t(`sshConnections.generateDialog.${type}`)}
                </MenuItem>
              ))}
            </TextField>
          )}
          {mode === 'import' && (
            <>
              <TextField
                label={t('sshConnections.extraKeys.addDialog.privateKeyPath')}
                value={privateKeyPath}
                onChange={(event) => setPrivateKeyPath(event.target.value)}
                placeholder="/root/.ssh/id_ed25519"
                helperText={t('sshConnections.extraKeys.addDialog.privateKeyPathHelper')}
                required
                fullWidth
                disabled={pending}
              />
              <TextField
                label={t('sshConnections.extraKeys.addDialog.publicKeyPath')}
                value={publicKeyPath}
                onChange={(event) => setPublicKeyPath(event.target.value)}
                helperText={t('sshConnections.extraKeys.addDialog.publicKeyPathHelper')}
                fullWidth
                disabled={pending}
              />
            </>
          )}
          {mode === 'paste' && (
            <TextField
              label={t('sshConnections.extraKeys.addDialog.privateKey')}
              value={privateKey}
              onChange={(event) => setPrivateKey(event.target.value)}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
              helperText={t('sshConnections.extraKeys.addDialog.privateKeyHelper')}
              required
              fullWidth
              multiline
              minRows={6}
              disabled={pending}
              slotProps={{ htmlInput: { spellCheck: false, style: { fontFamily: 'monospace' } } }}
            />
          )}
        </Box>
      </DialogContent>
    </ResponsiveDialog>
  )
}
