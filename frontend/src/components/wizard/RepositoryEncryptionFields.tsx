import { useState } from 'react'
import {
  Alert,
  Box,
  FormControl,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
} from '@mui/material'
import { Eye, EyeOff, Key, Shield } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { usePlan } from '../../hooks/usePlan'

export interface RepositoryEncryptionData {
  encryption: string
  passphrase: string
}

interface RepositoryEncryptionFieldsProps {
  mode: 'create' | 'edit' | 'import'
  borgVersion?: 1 | 2
  data: RepositoryEncryptionData
  onChange: (data: Partial<RepositoryEncryptionData>) => void
}

const BORG1_ENCRYPTION_OPTIONS = ['repokey', 'repokey-blake2', 'keyfile', 'keyfile-blake2', 'none']
const BORG2_ENCRYPTION_OPTIONS = [
  'repokey-aes-ocb',
  'repokey-chacha20-poly1305',
  'keyfile-aes-ocb',
  'keyfile-chacha20-poly1305',
  'none',
]

export default function RepositoryEncryptionFields({
  mode,
  borgVersion = 1,
  data,
  onChange,
}: RepositoryEncryptionFieldsProps) {
  const { t } = useTranslation()
  const { can } = usePlan()
  const [showPassphrase, setShowPassphrase] = useState(false)

  const encryptionOptions =
    borgVersion === 2 && can('borg_v2') ? BORG2_ENCRYPTION_OPTIONS : BORG1_ENCRYPTION_OPTIONS

  return (
    <>
      {(mode === 'create' || mode === 'import') && (
        <>
          <FormControl fullWidth>
            <InputLabel>{t('wizard.security.encryptionMethodLabel')}</InputLabel>
            <Select
              value={data.encryption}
              label={t('wizard.security.encryptionMethodLabel')}
              onChange={(e) => onChange({ encryption: e.target.value })}
            >
              {encryptionOptions.map((opt) => (
                <MenuItem key={opt} value={opt}>
                  <Box>
                    <Typography
                      variant="body2"
                      sx={{
                        fontWeight: 600,
                      }}
                    >
                      {t(`wizard.security.options.${opt}.label`)}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{
                        color: 'text.secondary',
                      }}
                    >
                      {t(`wizard.security.options.${opt}.description`)}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {data.encryption === 'none' && (
            <Alert severity="warning">
              <Typography
                variant="body2"
                gutterBottom
                sx={{
                  fontWeight: 600,
                }}
              >
                {t('wizard.security.securityWarningTitle')}
              </Typography>
              <Typography variant="body2">{t('wizard.security.securityWarningBody')}</Typography>
            </Alert>
          )}
        </>
      )}

      {mode === 'edit' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Shield size={14} style={{ color: 'inherit', opacity: 0.45, flexShrink: 0 }} />
          <Typography
            variant="body2"
            sx={{
              color: 'text.secondary',
            }}
          >
            {t('wizard.security.encryptionReadonly')}
          </Typography>
        </Box>
      )}

      {data.encryption !== 'none' && (
        <TextField
          label={
            mode === 'edit'
              ? t('wizard.security.passphraseOptional')
              : t('wizard.security.passphraseRequired')
          }
          type={showPassphrase ? 'text' : 'password'}
          value={data.passphrase}
          onChange={(e) => onChange({ passphrase: e.target.value })}
          placeholder={
            mode === 'edit'
              ? t('wizard.security.passphrasePlaceholderEdit')
              : t('wizard.security.passphrasePlaceholderCreate')
          }
          required={mode !== 'edit'}
          fullWidth
          helperText={
            mode === 'edit'
              ? t('wizard.security.passphraseHelperEdit')
              : t('wizard.security.passphraseHelperCreate')
          }
          slotProps={{
            input: {
              startAdornment: (
                <Box sx={{ mr: 1, display: 'flex', color: 'text.secondary' }}>
                  <Key size={18} />
                </Box>
              ),
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    aria-label={
                      showPassphrase
                        ? t('wizard.review.hidePassphrase')
                        : t('wizard.review.showPassphrase')
                    }
                    onClick={() => setShowPassphrase((v) => !v)}
                    edge="end"
                    size="small"
                  >
                    {showPassphrase ? <EyeOff size={18} /> : <Eye size={18} />}
                  </IconButton>
                </InputAdornment>
              ),
            },
          }}
        />
      )}
    </>
  )
}
