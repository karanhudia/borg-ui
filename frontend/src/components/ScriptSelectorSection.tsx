import React from 'react'
import {
  Box,
  Typography,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  FormControlLabel,
  Checkbox,
} from '@mui/material'
import ScriptParameterInputs, { ScriptParameter } from './ScriptParameterInputs'

interface Script {
  id: number
  name: string
  parameters?: ScriptParameter[] | null
}

interface ScriptSelectorSectionProps {
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  runRepositoryScripts: boolean
  scripts: Script[]
  onPreChange: (id: number | null) => void
  onPostChange: (id: number | null) => void
  onRunRepoScriptsChange: (value: boolean) => void
  // Script parameters
  preBackupScriptParameters?: Record<string, string>
  postBackupScriptParameters?: Record<string, string>
  onPreParametersChange?: (params: Record<string, string>) => void
  onPostParametersChange?: (params: Record<string, string>) => void
  disabled?: boolean
  size?: 'small' | 'medium'
}

const ScriptSelectorSection: React.FC<ScriptSelectorSectionProps> = ({
  preBackupScriptId,
  postBackupScriptId,
  runRepositoryScripts,
  scripts,
  onPreChange,
  onPostChange,
  onRunRepoScriptsChange,
  preBackupScriptParameters = {},
  postBackupScriptParameters = {},
  onPreParametersChange,
  onPostParametersChange,
  disabled = false,
  size = 'medium',
}) => {
  // Find selected scripts to get their parameters
  const selectedPreScript = scripts.find((s) => s.id === preBackupScriptId)
  const selectedPostScript = scripts.find((s) => s.id === postBackupScriptId)

  return (
    <Box sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        Schedule-Level Scripts
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        These scripts run once per schedule (e.g., wake server before all backups, shutdown after)
      </Typography>

      <Stack spacing={2}>
        <FormControl fullWidth size={size}>
          <InputLabel sx={{ fontSize: size === 'medium' ? '1.1rem' : '0.875rem' }}>
            Pre-Backup Script (runs once before all backups)
          </InputLabel>
          <Select
            value={preBackupScriptId || ''}
            onChange={(e) => onPreChange(e.target.value ? Number(e.target.value) : null)}
            label="Pre-Backup Script (runs once before all backups)"
            disabled={disabled}
            sx={{
              fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
              minHeight: size === 'medium' ? 56 : undefined,
            }}
          >
            <MenuItem value="">
              <em>None</em>
            </MenuItem>
            {scripts.map((script) => (
              <MenuItem key={script.id} value={script.id}>
                {script.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Pre-backup script parameters */}
        {selectedPreScript &&
          selectedPreScript.parameters &&
          selectedPreScript.parameters.length > 0 &&
          onPreParametersChange && (
            <Box sx={{ pl: 2, pt: 1 }}>
              <ScriptParameterInputs
                parameters={selectedPreScript.parameters}
                values={preBackupScriptParameters}
                onChange={onPreParametersChange}
                showDescriptions={true}
              />
            </Box>
          )}

        <FormControl fullWidth size={size}>
          <InputLabel sx={{ fontSize: size === 'medium' ? '1.1rem' : '0.875rem' }}>
            Post-Backup Script (runs once after all backups)
          </InputLabel>
          <Select
            value={postBackupScriptId || ''}
            onChange={(e) => onPostChange(e.target.value ? Number(e.target.value) : null)}
            label="Post-Backup Script (runs once after all backups)"
            disabled={disabled}
            sx={{
              fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
              minHeight: size === 'medium' ? 56 : undefined,
            }}
          >
            <MenuItem value="">
              <em>None</em>
            </MenuItem>
            {scripts.map((script) => (
              <MenuItem key={script.id} value={script.id}>
                {script.name}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {/* Post-backup script parameters */}
        {selectedPostScript &&
          selectedPostScript.parameters &&
          selectedPostScript.parameters.length > 0 &&
          onPostParametersChange && (
            <Box sx={{ pl: 2, pt: 1 }}>
              <ScriptParameterInputs
                parameters={selectedPostScript.parameters}
                values={postBackupScriptParameters}
                onChange={onPostParametersChange}
                showDescriptions={true}
              />
            </Box>
          )}

        <FormControlLabel
          control={
            <Checkbox
              checked={runRepositoryScripts}
              onChange={(e) => onRunRepoScriptsChange(e.target.checked)}
              disabled={disabled}
            />
          }
          label={
            <Box>
              <Typography variant="body2">Run repository-level scripts</Typography>
              <Typography variant="caption" color="text.secondary">
                If enabled, each repository's pre/post scripts will run during its backup
              </Typography>
            </Box>
          }
        />
      </Stack>
    </Box>
  )
}

export default ScriptSelectorSection
