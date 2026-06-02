import React from 'react'
import { useTranslation } from 'react-i18next'
import { Alert, FormControlLabel, Stack, Switch } from '@mui/material'
import SchedulePicker from '../../shared/SchedulePicker'
import ArchiveNameTemplateInput from '../../ArchiveNameTemplateInput'

interface WizardStepScheduleConfigData {
  scheduleEnabled: boolean
  cronExpression: string
  timezone?: string
  archiveNameTemplate: string
}

interface WizardStepScheduleConfigProps {
  data: WizardStepScheduleConfigData
  jobName: string
  onChange: (updates: Partial<WizardStepScheduleConfigData>) => void
}

const WizardStepScheduleConfig: React.FC<WizardStepScheduleConfigProps> = ({
  data,
  jobName,
  onChange,
}) => {
  const { t } = useTranslation()

  return (
    <Stack spacing={2}>
      <FormControlLabel
        sx={{
          m: 0,
          alignItems: 'center',
          gap: 1,
          '& .MuiFormControlLabel-label': { lineHeight: 1.35 },
        }}
        control={
          <Switch
            checked={!data.scheduleEnabled}
            onChange={(event) => onChange({ scheduleEnabled: !event.target.checked })}
          />
        }
        label={t('wizard.scheduleWizard.config.manualOnlyLabel')}
      />

      {data.scheduleEnabled ? (
        <SchedulePicker
          cronExpression={data.cronExpression}
          timezone={data.timezone || 'UTC'}
          onChange={(updates) => onChange(updates)}
          required
          size="medium"
          cronLabel={t('wizard.scheduleWizard.config.scheduleLabel')}
          cronHelperText={t('wizard.scheduleWizard.config.scheduleHelper')}
        />
      ) : (
        <Alert severity="info" sx={{ alignItems: 'center' }}>
          {t('wizard.scheduleWizard.config.manualOnlyHelper')}
        </Alert>
      )}

      <ArchiveNameTemplateInput
        value={data.archiveNameTemplate}
        onChange={(template) => onChange({ archiveNameTemplate: template })}
        jobName={jobName || 'example-job'}
        size="medium"
      />
    </Stack>
  )
}

export default WizardStepScheduleConfig
