import {
  Box,
  FormControl,
  FormControlLabel,
  Checkbox,
  Typography,
  Alert,
  Paper,
  Radio,
  RadioGroup,
} from '@mui/material'
import { Shield, FileWarning, Settings2, Lock } from 'lucide-react'

export interface RestoreOptionsStepData {
  conflictResolution: 'ask' | 'overwrite' | 'skip' | 'keep_both'
  createBackup: boolean
  makeParentDirs: boolean
  restorePermissions: boolean
  restoreOwner: boolean
}

interface WizardStepRestoreOptionsProps {
  data: RestoreOptionsStepData
  onChange: (data: Partial<RestoreOptionsStepData>) => void
}

export default function WizardStepRestoreOptions({
  data,
  onChange,
}: WizardStepRestoreOptionsProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Header */}
      <Box>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
          Configure restore options
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Choose how to handle conflicts and what attributes to restore
        </Typography>
      </Box>

      {/* Conflict Resolution Section */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          bgcolor: 'background.default',
          borderColor: '#9c27b0',
          borderWidth: 1,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <FileWarning size={20} color="#9c27b0" />
          <Typography variant="subtitle2" fontWeight={600}>
            File Conflict Resolution
          </Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          What should happen if a file already exists at the restore location?
        </Typography>

        <FormControl fullWidth>
          <RadioGroup
            value={data.conflictResolution}
            onChange={(e) =>
              onChange({
                conflictResolution: e.target.value as 'ask' | 'overwrite' | 'skip' | 'keep_both',
              })
            }
          >
            <FormControlLabel
              value="ask"
              control={<Radio sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }} />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    Ask for each file
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Prompt for action when conflicts are detected
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="overwrite"
              control={<Radio sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }} />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    Overwrite existing files
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Replace files without confirmation
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="skip"
              control={<Radio sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }} />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    Skip existing files
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Keep current files, don't restore
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              value="keep_both"
              control={<Radio sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }} />}
              label={
                <Box>
                  <Typography variant="body2" fontWeight={600}>
                    Keep both files
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Rename restored file with timestamp suffix
                  </Typography>
                </Box>
              }
            />
          </RadioGroup>
        </FormControl>
      </Paper>

      {/* Safety Options Section */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          bgcolor: 'background.default',
          borderColor: '#9c27b0',
          borderWidth: 1,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Shield size={20} color="#9c27b0" />
          <Typography variant="subtitle2" fontWeight={600}>
            Safety Options
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={data.createBackup}
                onChange={(e) => onChange({ createBackup: e.target.checked })}
                sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }}
              />
            }
            label={
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Create backup of existing files
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Save a copy with .bak extension before overwriting
                </Typography>
              </Box>
            }
          />

          <FormControlLabel
            control={
              <Checkbox
                checked={data.makeParentDirs}
                onChange={(e) => onChange({ makeParentDirs: e.target.checked })}
                sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }}
              />
            }
            label={
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Create parent directories
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Automatically create missing directories in the path
                </Typography>
              </Box>
            }
          />
        </Box>
      </Paper>

      {/* Permissions Section */}
      <Paper
        variant="outlined"
        sx={{
          p: 2,
          bgcolor: 'background.default',
          borderColor: '#9c27b0',
          borderWidth: 1,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
          <Lock size={20} color="#9c27b0" />
          <Typography variant="subtitle2" fontWeight={600}>
            File Attributes
          </Typography>
        </Box>

        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={data.restorePermissions}
                onChange={(e) => onChange({ restorePermissions: e.target.checked })}
                sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }}
              />
            }
            label={
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Restore file permissions
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Apply original permission modes (chmod)
                </Typography>
              </Box>
            }
          />

          <FormControlLabel
            control={
              <Checkbox
                checked={data.restoreOwner}
                onChange={(e) => onChange({ restoreOwner: e.target.checked })}
                sx={{ color: '#9c27b0', '&.Mui-checked': { color: '#9c27b0' } }}
              />
            }
            label={
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Restore file ownership
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Apply original user and group (requires root/sudo)
                </Typography>
              </Box>
            }
          />
        </Box>
      </Paper>

      {/* Warnings and Info */}
      {data.conflictResolution === 'overwrite' && !data.createBackup && (
        <Alert severity="warning" icon={<FileWarning size={18} />}>
          <Typography variant="body2">
            <strong>Warning:</strong> Files will be overwritten without backup. This action cannot
            be undone. Consider enabling "Create backup of existing files" for safety.
          </Typography>
        </Alert>
      )}

      {data.restoreOwner && (
        <Alert severity="info" icon={<Settings2 size={18} />}>
          <Typography variant="body2">
            <strong>Note:</strong> Restoring file ownership typically requires root privileges. The
            restore operation may fail if running without sufficient permissions.
          </Typography>
        </Alert>
      )}
    </Box>
  )
}
