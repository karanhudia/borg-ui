import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  IconButton,
  InputAdornment,
  Stack,
  TextField,
  Typography,
} from '@mui/material'
import { Download, Eye, EyeOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import {
  MIN_PASSPHRASE_LENGTH,
  usesEncryption,
  type QuickStartAnswers,
  type QuickStartStepProps,
} from '../quickStartState'

function downloadPassphrase(answers: QuickStartAnswers) {
  const text = [
    `Borg UI repository: ${answers.name.trim()}`,
    `Location: ${answers.destinationPath.trim()}`,
    `Passphrase: ${answers.passphrase}`,
    '',
  ].join('\n')
  const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${answers.name.trim() || 'borg'}-passphrase.txt`
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Revoking in the same task can cancel the download in some browsers.
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export default function QuickStartProtectStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()
  const [visible, setVisible] = useState(false)
  const encrypted = usesEncryption(answers)
  const tooShort =
    answers.passphrase.length > 0 && answers.passphrase.length < MIN_PASSPHRASE_LENGTH
  const mismatch =
    answers.passphraseConfirm.length > 0 && answers.passphraseConfirm !== answers.passphrase
  const readyToSave =
    answers.passphrase.length >= MIN_PASSPHRASE_LENGTH &&
    answers.passphrase === answers.passphraseConfirm

  const toggle = (
    <InputAdornment position="end">
      <IconButton
        size="small"
        edge="end"
        onClick={() => setVisible((value) => !value)}
        aria-label={
          visible ? t('quickStart.protect.hidePassphrase') : t('quickStart.protect.showPassphrase')
        }
      >
        {visible ? <EyeOff size={16} /> : <Eye size={16} />}
      </IconButton>
    </InputAdornment>
  )

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h3">
          {t('quickStart.protect.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {t('quickStart.protect.hint')}
        </Typography>
      </Box>

      <TextField
        label={t('quickStart.protect.nameLabel')}
        value={answers.name}
        onChange={(event) => onChange({ name: event.target.value })}
        helperText={t('quickStart.protect.nameHint')}
        required
        size="small"
        fullWidth
      />

      {encrypted ? (
        <>
          <TextField
            label={t('quickStart.protect.passphraseLabel')}
            type={visible ? 'text' : 'password'}
            value={answers.passphrase}
            onChange={(event) => onChange({ passphrase: event.target.value })}
            error={tooShort}
            helperText={t('quickStart.protect.passphraseHint', { count: MIN_PASSPHRASE_LENGTH })}
            autoComplete="new-password"
            required
            size="small"
            fullWidth
            slotProps={{ input: { endAdornment: toggle } }}
          />
          <TextField
            label={t('quickStart.protect.confirmLabel')}
            type={visible ? 'text' : 'password'}
            value={answers.passphraseConfirm}
            onChange={(event) => onChange({ passphraseConfirm: event.target.value })}
            error={mismatch}
            helperText={mismatch ? t('quickStart.protect.mismatch') : ' '}
            autoComplete="new-password"
            required
            size="small"
            fullWidth
          />
          <Alert
            severity="warning"
            variant="outlined"
            action={
              <Button
                color="inherit"
                size="small"
                startIcon={<Download size={14} />}
                disabled={!readyToSave}
                onClick={() => downloadPassphrase(answers)}
              >
                {t('quickStart.protect.download')}
              </Button>
            }
          >
            {t('quickStart.protect.warning')}
          </Alert>
          <FormControlLabel
            control={
              <Checkbox
                checked={answers.passphraseSaved}
                onChange={(event) => onChange({ passphraseSaved: event.target.checked })}
              />
            }
            label={t('quickStart.protect.savedConfirm')}
          />
        </>
      ) : (
        <Alert severity="warning" variant="outlined">
          {t('quickStart.protect.unencrypted')}
        </Alert>
      )}
    </Stack>
  )
}
