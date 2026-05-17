import React from 'react'
import { useTranslation } from 'react-i18next'
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
  description?: string | null
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
  title?: string
  description?: string
  runRepositoryScriptsLabel?: string
  runRepositoryScriptsDescription?: string
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
  title,
  description,
  runRepositoryScriptsLabel,
  runRepositoryScriptsDescription,
}) => {
  // Find selected scripts to get their parameters
  const { t } = useTranslation()
  const selectedPreScript = scripts.find((s) => s.id === preBackupScriptId)
  const selectedPostScript = scripts.find((s) => s.id === postBackupScriptId)
  const noneLabel = t('scriptSelector.none')

  const renderScriptOption = (script: Script) => (
    <Box sx={{ minWidth: 0, width: '100%' }}>
      <Typography
        variant="body2"
        title={script.name}
        sx={{
          fontWeight: 500,
          lineHeight: 1.25,
          overflowWrap: 'anywhere',
          whiteSpace: 'normal',
        }}
      >
        {script.name}
      </Typography>
      {script.description && (
        <Typography
          variant="caption"
          color="text.secondary"
          title={script.description}
          sx={{
            display: 'block',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {script.description}
        </Typography>
      )}
    </Box>
  )

  const renderSelectedScript = (script: Script | undefined) => {
    if (!script) return <em>{noneLabel}</em>
    return (
      <Box sx={{ minWidth: 0 }}>
        <Typography
          component="span"
          variant="body2"
          title={script.name}
          sx={{
            display: 'block',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {script.name}
        </Typography>
      </Box>
    )
  }

  return (
    <Box sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
      <Typography variant="subtitle2" fontWeight={600} gutterBottom>
        {title || t('scriptSelector.title')}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        {description || t('scriptSelector.subtitle')}
      </Typography>

      <Stack spacing={2}>
        <FormControl fullWidth size={size}>
          <InputLabel sx={{ fontSize: size === 'medium' ? '1.1rem' : '0.875rem' }}>
            {t('scriptSelector.preBackup')}
          </InputLabel>
          <Select
            value={preBackupScriptId || ''}
            onChange={(e) => onPreChange(e.target.value ? Number(e.target.value) : null)}
            label={t('scriptSelector.preBackup')}
            disabled={disabled}
            renderValue={() => renderSelectedScript(selectedPreScript)}
            SelectDisplayProps={{ title: selectedPreScript?.name || noneLabel }}
            sx={{
              fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
              minHeight: size === 'medium' ? 56 : undefined,
              '& .MuiSelect-select': {
                minWidth: 0,
              },
            }}
          >
            <MenuItem value="">
              <em>{noneLabel}</em>
            </MenuItem>
            {scripts.map((script) => (
              <MenuItem key={script.id} value={script.id} title={script.name}>
                {renderScriptOption(script)}
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
            {t('scriptSelector.postBackup')}
          </InputLabel>
          <Select
            value={postBackupScriptId || ''}
            onChange={(e) => onPostChange(e.target.value ? Number(e.target.value) : null)}
            label={t('scriptSelector.postBackup')}
            disabled={disabled}
            renderValue={() => renderSelectedScript(selectedPostScript)}
            SelectDisplayProps={{ title: selectedPostScript?.name || noneLabel }}
            sx={{
              fontSize: size === 'medium' ? '1.1rem' : '0.875rem',
              minHeight: size === 'medium' ? 56 : undefined,
              '& .MuiSelect-select': {
                minWidth: 0,
              },
            }}
          >
            <MenuItem value="">
              <em>{noneLabel}</em>
            </MenuItem>
            {scripts.map((script) => (
              <MenuItem key={script.id} value={script.id} title={script.name}>
                {renderScriptOption(script)}
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
              <Typography variant="body2">
                {runRepositoryScriptsLabel || t('scriptSelector.runRepoScripts')}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {runRepositoryScriptsDescription || t('scriptSelector.runRepoScriptsDesc')}
              </Typography>
            </Box>
          }
        />
      </Stack>
    </Box>
  )
}

export default ScriptSelectorSection
