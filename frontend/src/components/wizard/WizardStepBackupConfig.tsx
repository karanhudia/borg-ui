import { Box, Alert, Typography } from '@mui/material'
import CompressionSettings from '../CompressionSettings'
import ExcludePatternInput from '../ExcludePatternInput'
import AdvancedRepositoryOptions from '../AdvancedRepositoryOptions'

export interface BackupConfigStepData {
  compression: string
  excludePatterns: string[]
  customFlags: string
  remotePath: string
  preBackupScript: string
  postBackupScript: string
  preHookTimeout: number
  postHookTimeout: number
  continueOnHookFailure: boolean
}

interface WizardStepBackupConfigProps {
  repositoryId?: number | null
  dataSource: 'local' | 'remote'
  repositoryMode: 'full' | 'observe'
  data: BackupConfigStepData
  onChange: (data: Partial<BackupConfigStepData>) => void
  onBrowseExclude: () => void
}

export default function WizardStepBackupConfig({
  repositoryId,
  dataSource,
  repositoryMode,
  data,
  onChange,
  onBrowseExclude,
}: WizardStepBackupConfigProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Compression Settings */}
      <CompressionSettings
        value={data.compression}
        onChange={(value) => onChange({ compression: value })}
      />

      {/* Exclude Patterns - Now works for both local and remote sources */}
      <ExcludePatternInput
        patterns={data.excludePatterns}
        onChange={(patterns) => onChange({ excludePatterns: patterns })}
        onBrowseClick={onBrowseExclude}
      />

      {/* Info for remote data source */}
      {dataSource === 'remote' && (
        <Alert severity="info">
          <Typography variant="body2">
            Remote directories are mounted via SSHFS preserving their original paths. Exclude
            patterns work the same as local sources (e.g., <code>*/var/cache/*</code>).
          </Typography>
        </Alert>
      )}

      {/* Advanced Options */}
      <AdvancedRepositoryOptions
        repositoryId={repositoryId}
        mode={repositoryMode}
        remotePath={data.remotePath}
        preBackupScript={data.preBackupScript}
        postBackupScript={data.postBackupScript}
        preHookTimeout={data.preHookTimeout}
        postHookTimeout={data.postHookTimeout}
        continueOnHookFailure={data.continueOnHookFailure}
        customFlags={data.customFlags}
        onRemotePathChange={(value) => onChange({ remotePath: value })}
        onPreBackupScriptChange={(value) => onChange({ preBackupScript: value })}
        onPostBackupScriptChange={(value) => onChange({ postBackupScript: value })}
        onPreHookTimeoutChange={(value) => onChange({ preHookTimeout: value })}
        onPostHookTimeoutChange={(value) => onChange({ postHookTimeout: value })}
        onContinueOnHookFailureChange={(value) => onChange({ continueOnHookFailure: value })}
        onCustomFlagsChange={(value) => onChange({ customFlags: value })}
      />
    </Box>
  )
}
