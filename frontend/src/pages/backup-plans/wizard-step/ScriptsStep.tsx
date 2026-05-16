import { Alert, Stack } from '@mui/material'

import ScriptSelectorSection from '../../../components/ScriptSelectorSection'
import type { BackupPlanWizardStepProps } from './types'

type ScriptsStepProps = Pick<
  BackupPlanWizardStepProps,
  'wizardState' | 'scripts' | 'loadingScripts' | 'updateState' | 't'
>

export function ScriptsStep({
  wizardState,
  scripts,
  loadingScripts,
  updateState,
  t,
}: ScriptsStepProps) {
  return (
    <Stack spacing={2}>
      {loadingScripts && <Alert severity="info">{t('backupPlans.wizard.scripts.loading')}</Alert>}
      <ScriptSelectorSection
        preBackupScriptId={wizardState.preBackupScriptId}
        postBackupScriptId={wizardState.postBackupScriptId}
        preBackupScriptParameters={wizardState.preBackupScriptParameters}
        postBackupScriptParameters={wizardState.postBackupScriptParameters}
        runRepositoryScripts={wizardState.runRepositoryScripts}
        scripts={scripts}
        onPreChange={(id) =>
          updateState({
            preBackupScriptId: id,
            preBackupScriptParameters: {},
          })
        }
        onPostChange={(id) =>
          updateState({
            postBackupScriptId: id,
            postBackupScriptParameters: {},
          })
        }
        onPreParametersChange={(params) => updateState({ preBackupScriptParameters: params })}
        onPostParametersChange={(params) => updateState({ postBackupScriptParameters: params })}
        onRunRepoScriptsChange={(value) => updateState({ runRepositoryScripts: value })}
        title={t('backupPlans.wizard.scripts.title')}
        description={t('backupPlans.wizard.scripts.description')}
        runRepositoryScriptsLabel={t('backupPlans.wizard.scripts.runRepositoryScripts')}
        runRepositoryScriptsDescription={t('backupPlans.wizard.scripts.runRepositoryScriptsHelper')}
        disabled={loadingScripts}
      />
    </Stack>
  )
}
