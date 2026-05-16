import { Stack, TextField } from '@mui/material'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import SourceLocationsInput from '../../../components/SourceLocationsInput'
import {
  normalizeSourceLocations,
  summarizeSourceLocations,
} from '../../../utils/backupPlanPayload'
import type { BackupPlanWizardStepProps } from './types'

type SourceStepProps = Pick<
  BackupPlanWizardStepProps,
  | 'wizardState'
  | 'sshConnections'
  | 'updateState'
  | 'openSourceExplorer'
  | 'openExcludeExplorer'
  | 't'
>

export function SourceStep({
  wizardState,
  sshConnections,
  updateState,
  openSourceExplorer,
  openExcludeExplorer,
  t,
}: SourceStepProps) {
  return (
    <Stack spacing={3}>
      <TextField
        label={t('backupPlans.wizard.fields.planName')}
        value={wizardState.name}
        onChange={(event) => updateState({ name: event.target.value })}
        required
        fullWidth
      />
      <TextField
        label={t('backupPlans.wizard.fields.description')}
        value={wizardState.description}
        onChange={(event) => updateState({ description: event.target.value })}
        multiline
        rows={2}
        fullWidth
      />
      <SourceLocationsInput
        repositoryLocation="local"
        sourceLocations={wizardState.sourceLocations || []}
        sshConnections={sshConnections}
        onChange={(sourceLocations) => {
          const normalized = normalizeSourceLocations({
            ...wizardState,
            sourceLocations,
          })
          const summary = summarizeSourceLocations(normalized)
          updateState({
            sourceLocations,
            sourceType: summary.sourceType === 'remote' ? 'remote' : 'local',
            sourceSshConnectionId: summary.sourceSshConnectionId || '',
            sourceDirectories: summary.sourceDirectories,
          })
        }}
        onBrowse={openSourceExplorer}
      />
      <ExcludePatternInput
        patterns={wizardState.excludePatterns}
        onChange={(excludePatterns) => updateState({ excludePatterns })}
        onBrowseClick={openExcludeExplorer}
      />
    </Stack>
  )
}
