import { useState } from 'react'
import {
  Box,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Alert,
  Button,
  ToggleButton,
  ToggleButtonGroup,
  InputAdornment,
  IconButton,
} from '@mui/material'
import { Shield, Key, FileKey, Upload, FileText, Eye, EyeOff } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePlan } from '../../hooks/usePlan'

export interface SecurityStepData {
  encryption: string
  passphrase: string
  remotePath: string
  selectedKeyfile: File | null
}

// Encryption options grouped by borg version — defined once, used in the Select below
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

interface WizardStepSecurityProps {
  mode: 'create' | 'edit' | 'import'
  borgVersion?: 1 | 2
  data: SecurityStepData
  onChange: (data: Partial<SecurityStepData>) => void
}

export default function WizardStepSecurity({
  mode,
  borgVersion = 1,
  data,
  onChange,
}: WizardStepSecurityProps) {
  const { t } = useTranslation()
  const { can } = usePlan()
  const [keyfileMode, setKeyfileMode] = useState<'file' | 'paste'>('file')
  const [keyfileText, setKeyfileText] = useState('')
  const [showPassphrase, setShowPassphrase] = useState(false)

  const handleKeyfileModeChange = (_: unknown, newMode: 'file' | 'paste' | null) => {
    if (newMode === null) return
    setKeyfileMode(newMode)
    setKeyfileText('')
    onChange({ selectedKeyfile: null })
  }

  const handleKeyfileTextChange = (text: string) => {
    setKeyfileText(text)
    if (text.trim()) {
      const file = new File([text], 'borg_keyfile', { type: 'text/plain' })
      onChange({ selectedKeyfile: file })
    } else {
      onChange({ selectedKeyfile: null })
    }
  }

  const encryptionOptions =
    borgVersion === 2 && can('borg_v2') ? BORG2_ENCRYPTION_OPTIONS : BORG1_ENCRYPTION_OPTIONS
  const isKeyfileEncryption = data.encryption.includes('keyfile')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Encryption Selection - create and import mode */}
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

      {/* Encryption info for edit mode only */}
      {mode === 'edit' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
          <Shield size={14} style={{ color: 'inherit', opacity: 0.45, flexShrink: 0 }} />
          <Typography variant="body2" color="text.secondary">
            {t('wizard.security.encryptionReadonly')}
          </Typography>
        </Box>
      )}

      {/* Passphrase Input */}
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

      {/* Keyfile Upload - import mode only, and only when encryption is keyfile-based */}
      {mode === 'import' && isKeyfileEncryption && (
        <Box>
          <Typography
            variant="subtitle2"
            gutterBottom
            sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
          >
            <FileKey size={18} />
            {t('wizard.security.borgKeyfileTitle')}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
            {t('wizard.security.borgKeyfileDesc')}
          </Typography>

          <ToggleButtonGroup
            value={keyfileMode}
            exclusive
            onChange={handleKeyfileModeChange}
            size="small"
            sx={{ mb: 1.5 }}
          >
            <ToggleButton value="file">
              <Upload size={16} style={{ marginRight: 6 }} />
              {t('wizard.security.uploadFile')}
            </ToggleButton>
            <ToggleButton value="paste">
              <FileText size={16} style={{ marginRight: 6 }} />
              {t('wizard.security.pasteContent')}
            </ToggleButton>
          </ToggleButtonGroup>

          {keyfileMode === 'file' ? (
            <Button
              variant="outlined"
              component="label"
              fullWidth
              startIcon={<FileKey size={18} />}
              sx={{
                justifyContent: 'flex-start',
                py: 1.5,
                borderStyle: 'dashed',
                '&:hover': {
                  borderStyle: 'solid',
                },
              }}
            >
              {data.selectedKeyfile
                ? t('wizard.security.selectedKeyfile', { name: data.selectedKeyfile.name })
                : t('wizard.security.chooseKeyfile')}
              <input
                type="file"
                hidden
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    onChange({ selectedKeyfile: e.target.files[0] })
                  }
                }}
              />
            </Button>
          ) : (
            <TextField
              multiline
              rows={6}
              fullWidth
              placeholder="BORG_KEY ..."
              value={keyfileText}
              onChange={(e) => handleKeyfileTextChange(e.target.value)}
              inputProps={{
                style: { fontFamily: 'monospace', fontSize: '0.85rem' },
              }}
            />
          )}

          {data.selectedKeyfile && (
            <Alert severity="success" sx={{ mt: 1.5 }}>
              {keyfileMode === 'file'
                ? t('wizard.security.keyfileUploadNote')
                : t('wizard.security.keyfileContentNote')}
            </Alert>
          )}
        </Box>
      )}

      {/* Remote Path */}
      <TextField
        label={t('wizard.security.remoteBorgPath')}
        value={data.remotePath}
        onChange={(e) => onChange({ remotePath: e.target.value })}
        placeholder={borgVersion === 2 ? '/usr/local/bin/borg2' : '/usr/local/bin/borg'}
        fullWidth
        helperText={t('wizard.security.remoteBorgPathHelper')}
      />
    </Box>
  )
}
