import React from 'react'
import { useTranslation } from 'react-i18next'
import { Stack, Alert } from '@mui/material'
import ScriptSelectorSection from '../../ScriptSelectorSection'
import { Script } from '../../ScheduleWizard'

interface WizardStepScriptsData {
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  preBackupScriptParameters: Record<string, string>
  postBackupScriptParameters: Record<string, string>
  runRepositoryScripts: boolean
}

interface WizardStepScriptsProps {
  data: WizardStepScriptsData
  scripts: Script[]
  repositoryCount: number
  onChange: (updates: Partial<WizardStepScriptsData>) => void
}

const WizardStepScripts: React.FC<WizardStepScriptsProps> = ({
  data,
  scripts,
  repositoryCount,
  onChange,
}) => {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <Alert severity="info" sx={{ py: 0.5 }}>
        {t('wizard.scheduleWizard.scripts.scheduleLevelNote')}
      </Alert>

      {repositoryCount > 0 ? (
        <ScriptSelectorSection
          preBackupScriptId={data.preBackupScriptId}
          postBackupScriptId={data.postBackupScriptId}
          preBackupScriptParameters={data.preBackupScriptParameters}
          postBackupScriptParameters={data.postBackupScriptParameters}
          runRepositoryScripts={data.runRepositoryScripts}
          scripts={scripts}
          onPreChange={(id) => onChange({ preBackupScriptId: id })}
          onPostChange={(id) => onChange({ postBackupScriptId: id })}
          onPreParametersChange={(params) => onChange({ preBackupScriptParameters: params })}
          onPostParametersChange={(params) => onChange({ postBackupScriptParameters: params })}
          onRunRepoScriptsChange={(value) => onChange({ runRepositoryScripts: value })}
          size="medium"
        />
      ) : (
        <Alert severity="warning" sx={{ py: 0.5 }}>
          {t('wizard.scheduleWizard.scripts.selectRepoFirst')}
        </Alert>
      )}
    </Stack>
  )
}

export default WizardStepScripts
