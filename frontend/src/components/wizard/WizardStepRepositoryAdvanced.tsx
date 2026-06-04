import { Box } from '@mui/material'
import AdvancedRepositoryOptions from '../AdvancedRepositoryOptions'
import CompressionSettings from '../CompressionSettings'

type OnFailureMode = 'fail' | 'continue' | 'skip'

export interface RepositoryAdvancedStepData {
  compression: string
  remotePath: string
  preBackupScript: string
  postBackupScript: string
  preHookTimeout: number
  postHookTimeout: number
  hookFailureMode: OnFailureMode
  customFlags: string
}

interface WizardStepRepositoryAdvancedProps {
  repositoryId?: number | null
  repositoryMode: 'full' | 'observe'
  data: RepositoryAdvancedStepData
  onChange: (data: Partial<RepositoryAdvancedStepData>) => void
}

export default function WizardStepRepositoryAdvanced({
  repositoryId,
  repositoryMode,
  data,
  onChange,
}: WizardStepRepositoryAdvancedProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <CompressionSettings
        value={data.compression}
        onChange={(value) => onChange({ compression: value })}
      />

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
    </Box>
  )
}
