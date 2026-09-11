import { Box } from '@mui/material'
import AdvancedRepositoryOptions from '../AdvancedRepositoryOptions'
import CompressionSettings from '../CompressionSettings'
import IndexModeSettings from '../repositories/IndexModeSettings'
import type { IndexMode } from '../../types/operations'

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
  uploadRatelimitMb: string
  indexMode: IndexMode
  historyIndexExcludes: string[]
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

      {/* Spec 6.8 makes the mode a decision about a repository that exists,
          and PUT is the only route that accepts it, so it is offered when
          editing rather than at creation. */}
      {repositoryId != null && (
        <IndexModeSettings
          mode={data.indexMode}
          excludes={data.historyIndexExcludes}
          onModeChange={(indexMode) => onChange({ indexMode })}
          onExcludesChange={(historyIndexExcludes) => onChange({ historyIndexExcludes })}
        />
      )}

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
        uploadRatelimitMb={data.uploadRatelimitMb}
        onRemotePathChange={(value) => onChange({ remotePath: value })}
        onPreBackupScriptChange={(value) => onChange({ preBackupScript: value })}
        onPostBackupScriptChange={(value) => onChange({ postBackupScript: value })}
        onPreHookTimeoutChange={(value) => onChange({ preHookTimeout: value })}
        onPostHookTimeoutChange={(value) => onChange({ postHookTimeout: value })}
        onHookFailureModeChange={(value) => onChange({ hookFailureMode: value })}
        onCustomFlagsChange={(value) => onChange({ customFlags: value })}
        onUploadRatelimitMbChange={(value) => onChange({ uploadRatelimitMb: value })}
      />
    </Box>
  )
}
