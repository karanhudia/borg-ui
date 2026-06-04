import { Box, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import ExcludePatternInput from '../ExcludePatternInput'
import AdvancedRepositoryOptions from '../AdvancedRepositoryOptions'
import CompressionSettings from '../CompressionSettings'

type OnFailureMode = 'fail' | 'continue' | 'skip'

export interface BackupConfigStepData {
  compression: string
  excludePatterns: string[]
  customFlags: string
  remotePath: string
  preBackupScript: string
  postBackupScript: string
  preHookTimeout: number
  postHookTimeout: number
  hookFailureMode: OnFailureMode
}

interface WizardStepBackupConfigProps {
  repositoryId?: number | null
  dataSource: 'local' | 'remote'
  repositoryMode: 'full' | 'observe'
  data: BackupConfigStepData
  onChange: (data: Partial<BackupConfigStepData>) => void
  onBrowseExclude?: () => void
  showAdvancedOptions?: boolean
}

export default function WizardStepBackupConfig({
  repositoryId,
  dataSource,
  repositoryMode,
  data,
  onChange,
  onBrowseExclude,
  showAdvancedOptions = true,
}: WizardStepBackupConfigProps) {
  const { t } = useTranslation()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {repositoryMode === 'full' && (
        <CompressionSettings
          value={data.compression}
          onChange={(value) => onChange({ compression: value })}
        />
      )}

      {/* Exclude Patterns - Now works for both local and remote sources */}
      <ExcludePatternInput
        patterns={data.excludePatterns}
        onChange={(patterns) => onChange({ excludePatterns: patterns })}
        onBrowseClick={onBrowseExclude}
      />

      {/* Info for remote data source */}
      {dataSource === 'remote' && (
        <Typography variant="body2" color="text.secondary">
          {t('wizard.backupConfig.remoteSshfsNote')}
        </Typography>
      )}

      {showAdvancedOptions && (
        <AdvancedRepositoryOptions
          repositoryId={repositoryId}
          mode={repositoryMode}
          remotePath={data.remotePath}
          preBackupScript={data.preBackupScript}
          postBackupScript={data.postBackupScript}
          preHookTimeout={data.preHookTimeout}
          postHookTimeout={data.postHookTimeout}
          hookFailureMode={data.hookFailureMode}
          customFlags={data.customFlags}
          onRemotePathChange={(value) => onChange({ remotePath: value })}
          onPreBackupScriptChange={(value) => onChange({ preBackupScript: value })}
          onPostBackupScriptChange={(value) => onChange({ postBackupScript: value })}
          onPreHookTimeoutChange={(value) => onChange({ preHookTimeout: value })}
          onPostHookTimeoutChange={(value) => onChange({ postHookTimeout: value })}
          onHookFailureModeChange={(value) => onChange({ hookFailureMode: value })}
          onCustomFlagsChange={(value) => onChange({ customFlags: value })}
        />
      )}
    </Box>
  )
}
