import { Stack, TextField } from '@mui/material'

import ExcludePatternInput from '../../../components/ExcludePatternInput'
import { WizardStepDataSource } from '../../../components/wizard'
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
      <WizardStepDataSource
        repositoryLocation="local"
        repoSshConnectionId=""
        repositoryMode="full"
        data={{
          dataSource: wizardState.sourceType,
          sourceSshConnectionId: wizardState.sourceSshConnectionId,
          sourceDirs: wizardState.sourceDirectories,
        }}
        sshConnections={sshConnections}
        onChange={(updates) => {
          updateState({
            ...(updates.dataSource ? { sourceType: updates.dataSource } : {}),
            ...(updates.sourceSshConnectionId !== undefined
              ? { sourceSshConnectionId: updates.sourceSshConnectionId }
              : {}),
            ...(updates.sourceDirs !== undefined ? { sourceDirectories: updates.sourceDirs } : {}),
          })
        }}
        onBrowseSource={openSourceExplorer}
        onBrowseRemoteSource={openSourceExplorer}
      />
      <ExcludePatternInput
        patterns={wizardState.excludePatterns}
        onChange={(excludePatterns) => updateState({ excludePatterns })}
        onBrowseClick={openExcludeExplorer}
      />
    </Stack>
  )
}
