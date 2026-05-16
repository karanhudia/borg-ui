import { useState } from 'react'
import {
  Box,
  TextField,
  Typography,
  Alert,
  Button,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material'
import { FileKey, Upload, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import RepositoryEncryptionFields from './RepositoryEncryptionFields'

export interface SecurityStepData {
  encryption: string
  passphrase: string
  remotePath: string
  selectedKeyfile: File | null
}

interface WizardStepSecurityProps {
  mode: 'create' | 'edit' | 'import'
  borgVersion?: 1 | 2
  data: SecurityStepData
  onChange: (data: Partial<SecurityStepData>) => void
  showRemotePath?: boolean
}

export default function WizardStepSecurity({
  mode,
  borgVersion = 1,
  data,
  onChange,
  showRemotePath = true,
}: WizardStepSecurityProps) {
  const { t } = useTranslation()
  const [keyfileMode, setKeyfileMode] = useState<'file' | 'paste'>('file')
  const [keyfileText, setKeyfileText] = useState('')

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

  const isKeyfileEncryption = data.encryption.includes('keyfile')

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <RepositoryEncryptionFields
        mode={mode}
        borgVersion={borgVersion}
        data={{
          encryption: data.encryption,
          passphrase: data.passphrase,
        }}
        onChange={onChange}
      />

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

      {showRemotePath && (
        <TextField
          label={t('wizard.security.remoteBorgPath')}
          value={data.remotePath}
          onChange={(e) => onChange({ remotePath: e.target.value })}
          placeholder={borgVersion === 2 ? '/usr/local/bin/borg2' : '/usr/local/bin/borg'}
          fullWidth
          helperText={t('wizard.security.remoteBorgPathHelper')}
        />
      )}
    </Box>
  )
}
