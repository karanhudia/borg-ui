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
} from '@mui/material'
import { Shield, Key, FileKey } from 'lucide-react'

export interface SecurityStepData {
  encryption: string
  passphrase: string
  remotePath: string
  selectedKeyfile: File | null
}

interface WizardStepSecurityProps {
  mode: 'create' | 'edit' | 'import'
  data: SecurityStepData
  onChange: (data: Partial<SecurityStepData>) => void
}

export default function WizardStepSecurity({ mode, data, onChange }: WizardStepSecurityProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Encryption Selection - Only for create mode */}
      {mode === 'create' && (
        <>
          <FormControl fullWidth>
            <InputLabel>Encryption Method</InputLabel>
            <Select
              value={data.encryption}
              label="Encryption Method"
              onChange={(e) => onChange({ encryption: e.target.value })}
            >
              <MenuItem value="repokey">
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    Repokey (Recommended)
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Key stored in repository, protected by passphrase
                  </Typography>
                </Box>
              </MenuItem>
              <MenuItem value="keyfile">
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    Keyfile
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Key stored separately, requires passphrase + keyfile
                  </Typography>
                </Box>
              </MenuItem>
              <MenuItem value="none">
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    None (Unencrypted)
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    No encryption - data stored in plaintext
                  </Typography>
                </Box>
              </MenuItem>
            </Select>
          </FormControl>

          {data.encryption === 'none' && (
            <Alert severity="warning">
              <Typography variant="body2" fontWeight={600} gutterBottom>
                Security Warning
              </Typography>
              <Typography variant="body2">
                Your backup data will be stored without encryption. Anyone with access to the
                repository can read your files. This is not recommended for sensitive data.
              </Typography>
            </Alert>
          )}
        </>
      )}

      {/* Encryption info for edit mode only */}
      {mode === 'edit' && (
        <Alert severity="info" icon={<Shield size={20} />}>
          <Typography variant="body2">
            Encryption settings cannot be changed after repository creation.
          </Typography>
        </Alert>
      )}

      {/* Passphrase Input */}
      {data.encryption !== 'none' && (
        <TextField
          label={mode === 'edit' ? 'Passphrase (Optional)' : 'Passphrase'}
          type="password"
          value={data.passphrase}
          onChange={(e) => onChange({ passphrase: e.target.value })}
          placeholder={
            mode === 'edit' ? 'Leave blank to keep last saved passphrase' : 'Enter passphrase'
          }
          required={mode !== 'edit'}
          fullWidth
          helperText={
            mode === 'edit'
              ? 'Optional - leave blank to keep last saved passphrase'
              : 'Keep this safe - you cannot access backups without it!'
          }
          InputProps={{
            startAdornment: (
              <Box sx={{ mr: 1, display: 'flex', color: 'text.secondary' }}>
                <Key size={18} />
              </Box>
            ),
          }}
        />
      )}

      {/* Keyfile Upload - Only for import mode */}
      {mode === 'import' && (
        <Box>
          <Typography
            variant="subtitle2"
            gutterBottom
            sx={{ display: 'flex', alignItems: 'center', gap: 1 }}
          >
            <FileKey size={18} />
            Borg Keyfile (Optional)
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
            Upload keyfile if using keyfile/keyfile-blake2 encryption (found in
            ~/.config/borg/keys/)
          </Typography>
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
            {data.selectedKeyfile ? `Selected: ${data.selectedKeyfile.name}` : 'Choose Keyfile'}
            <input
              type="file"
              hidden
              accept=".key,*"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  onChange({ selectedKeyfile: e.target.files[0] })
                }
              }}
            />
          </Button>
          {data.selectedKeyfile && (
            <Alert severity="success" sx={{ mt: 1.5 }}>
              Keyfile will be uploaded after import
            </Alert>
          )}
        </Box>
      )}

      {/* Remote Path */}
      <TextField
        label="Remote Borg Path (Optional)"
        value={data.remotePath}
        onChange={(e) => onChange({ remotePath: e.target.value })}
        placeholder="/usr/local/bin/borg"
        fullWidth
        helperText="Path to borg executable on remote (if not in PATH)"
      />
    </Box>
  )
}
