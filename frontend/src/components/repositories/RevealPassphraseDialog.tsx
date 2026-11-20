import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Check, Copy, Download, Eye, EyeOff } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { getApiErrorDetail } from '../../utils/apiErrors'
import { translateBackendKey } from '../../utils/translateBackendKey'
import { copyText } from '../../utils/clipboard'
import ResponsiveDialog from '../shared/ResponsiveDialog'

export interface RevealedPassphrase {
  passphrase: string
  encryption: string
  has_keyfile: boolean
}

export type ReauthMode = 'password' | 'name'

interface RevealPassphraseDialogProps {
  open: boolean
  repositoryName: string
  /** password for local accounts, name for single sign-on and proxy auth */
  reauth: ReauthMode
  onReveal: (body: { password?: string; repository_name?: string }) => Promise<RevealedPassphrase>
  onAcknowledge: () => Promise<void>
  onDownloadKeyfile: () => void
  onClose: () => void
  /** Stories only: start on the revealed step. */
  initialRevealed?: RevealedPassphrase
}

const codeSx = {
  m: 0,
  p: 1.5,
  borderRadius: 1.5,
  border: '1px solid',
  borderColor: 'divider',
  bgcolor: 'action.hover',
  fontFamily: 'monospace',
  fontSize: '0.9375rem',
  wordBreak: 'break-all',
} as const

/** Re-authenticate, then show a generated passphrase until the user saves it. */
export default function RevealPassphraseDialog({
  open,
  repositoryName,
  reauth,
  onReveal,
  onAcknowledge,
  onDownloadKeyfile,
  onClose,
  initialRevealed,
}: RevealPassphraseDialogProps) {
  const { t } = useTranslation()
  const [value, setValue] = useState('')
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [revealed, setRevealed] = useState<RevealedPassphrase | null>(initialRevealed ?? null)
  const [copied, setCopied] = useState(false)

  const close = () => {
    setValue('')
    setError(null)
    setRevealed(initialRevealed ?? null)
    onClose()
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      setRevealed(
        await onReveal(reauth === 'password' ? { password: value } : { repository_name: value })
      )
      setValue('')
    } catch (caught) {
      setError(
        translateBackendKey(getApiErrorDetail(caught), 'repositories.revealPassphrase.failed')
      )
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    if (!revealed || !(await copyText(revealed.passphrase))) {
      toast.error(t('common.errors.copyFailed'))
      return
    }
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const acknowledge = async () => {
    setBusy(true)
    try {
      await onAcknowledge()
      close()
    } catch (caught) {
      setError(
        translateBackendKey(getApiErrorDetail(caught), 'repositories.revealPassphrase.failed')
      )
    } finally {
      setBusy(false)
    }
  }

  const label =
    reauth === 'password'
      ? t('repositories.revealPassphrase.passwordLabel')
      : t('repositories.revealPassphrase.nameLabel')

  return (
    <ResponsiveDialog
      open={open}
      onClose={close}
      maxWidth="sm"
      fullWidth
      footer={
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={close}>{t('repositories.revealPassphrase.close')}</Button>
          {revealed ? (
            <Button variant="contained" onClick={acknowledge} disabled={busy}>
              {t('repositories.revealPassphrase.saved')}
            </Button>
          ) : (
            <Button variant="contained" onClick={submit} disabled={busy || !value}>
              {t('repositories.revealPassphrase.show')}
            </Button>
          )}
        </DialogActions>
      }
    >
      <DialogTitle>
        {t('repositories.revealPassphrase.title', { name: repositoryName })}
      </DialogTitle>
      <DialogContent>
        {revealed ? (
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t('repositories.revealPassphrase.keepItSafe')}
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'stretch', flexWrap: 'wrap' }}>
              <Box component="code" sx={{ ...codeSx, flex: 1, minWidth: 0 }}>
                {revealed.passphrase}
              </Box>
              <Button
                variant="outlined"
                onClick={copy}
                startIcon={copied ? <Check size={16} /> : <Copy size={16} />}
                sx={{ minHeight: 44 }}
              >
                {copied
                  ? t('repositories.revealPassphrase.copied')
                  : t('repositories.revealPassphrase.copy')}
              </Button>
            </Box>
            {revealed.has_keyfile && (
              <Stack spacing={1} sx={{ alignItems: 'flex-start' }}>
                <Typography variant="body2" color="text.secondary">
                  {t('repositories.revealPassphrase.keyfileHint')}
                </Typography>
                <Button
                  variant="outlined"
                  startIcon={<Download size={16} />}
                  onClick={onDownloadKeyfile}
                  sx={{ minHeight: 44 }}
                >
                  {t('repositories.revealPassphrase.downloadKeyfile')}
                </Button>
              </Stack>
            )}
            {error && (
              <Alert severity="error" role="alert">
                {error}
              </Alert>
            )}
          </Stack>
        ) : (
          <Stack
            component="form"
            spacing={2}
            sx={{ pt: 1 }}
            onSubmit={(event) => {
              event.preventDefault()
              if (value && !busy) void submit()
            }}
          >
            <Typography variant="body2" color="text.secondary">
              {reauth === 'password'
                ? t('repositories.revealPassphrase.passwordIntro')
                : t('repositories.revealPassphrase.nameIntro', { name: repositoryName })}
            </Typography>
            <TextField
              autoFocus
              fullWidth
              label={label}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              type={reauth === 'password' && !visible ? 'password' : 'text'}
              autoComplete={reauth === 'password' ? 'current-password' : 'off'}
              error={Boolean(error)}
              slotProps={
                reauth === 'password'
                  ? {
                      input: {
                        endAdornment: (
                          <InputAdornment position="end">
                            <IconButton
                              aria-label={
                                visible
                                  ? t('repositories.revealPassphrase.hidePassword')
                                  : t('repositories.revealPassphrase.showPassword')
                              }
                              onClick={() => setVisible((v) => !v)}
                              edge="end"
                            >
                              {visible ? <EyeOff size={18} /> : <Eye size={18} />}
                            </IconButton>
                          </InputAdornment>
                        ),
                      },
                    }
                  : undefined
              }
            />
            {error && (
              <Alert severity="error" role="alert">
                {error}
              </Alert>
            )}
          </Stack>
        )}
      </DialogContent>
    </ResponsiveDialog>
  )
}
