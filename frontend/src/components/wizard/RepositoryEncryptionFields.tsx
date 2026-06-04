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

const BORG1_ENCRYPTION_OPTIONS = [
  { value: 'repokey', label: 'Repository Key', desc: 'Key stored in repository (recommended)' },
  { value: 'repokey-blake2', label: 'Repository Key (BLAKE2)', desc: 'Faster hashing variant' },
  { value: 'keyfile', label: 'Key File', desc: 'Key stored in a separate file' },
  { value: 'keyfile-blake2', label: 'Key File (BLAKE2)', desc: 'Key file with faster hashing' },
  { value: 'none', label: 'None', desc: 'No encryption (not recommended)' },
]

const BORG2_ENCRYPTION_OPTIONS = [
  {
    value: 'repokey-aes-ocb',
    label: 'Repository Key (AES-OCB)',
    desc: 'Default for Borg 2 · recommended',
  },
  {
    value: 'repokey-chacha20-poly1305',
    label: 'Repository Key (ChaCha20)',
    desc: 'Alternative AEAD cipher',
  },
  { value: 'keyfile-aes-ocb', label: 'Key File (AES-OCB)', desc: 'Key stored in a separate file' },
  {
    value: 'keyfile-chacha20-poly1305',
    label: 'Key File (ChaCha20)',
    desc: 'Key file with ChaCha20',
  },
  { value: 'none', label: 'None', desc: 'No encryption (not recommended)' },
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
                <MenuItem key={opt.value} value={opt.value}>
                  <Box>
                    <Typography variant="body2" fontWeight={600}>
                      {opt.label}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {opt.desc}
                    </Typography>
                  </Box>
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          {data.encryption === 'none' && (
            <Alert severity="warning">
              <Typography variant="body2" fontWeight={600} gutterBottom>
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
          <Typography variant="body2" color="text.secondary">
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
          InputProps={{
            startAdornment: (
              <Box sx={{ mr: 1, display: 'flex', color: 'text.secondary' }}>
                <Key size={18} />
              </Box>
            ),
            endAdornment: (
              <InputAdornment position="end">
                <IconButton
                  aria-label={showPassphrase ? 'Hide passphrase' : 'Show passphrase'}
                  onClick={() => setShowPassphrase((v) => !v)}
                  edge="end"
                  size="small"
                >
                  {showPassphrase ? <EyeOff size={18} /> : <Eye size={18} />}
                </IconButton>
              </InputAdornment>
            ),
          }}
        />
      )}
    </>
  )
}
