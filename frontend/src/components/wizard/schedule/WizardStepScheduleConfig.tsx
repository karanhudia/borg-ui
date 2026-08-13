import React from 'react'
import { useTranslation } from 'react-i18next'
import { Stack } from '@mui/material'
import SchedulePicker from '../../shared/SchedulePicker'
import ArchiveNameTemplateInput from '../../ArchiveNameTemplateInput'

interface WizardStepScheduleConfigData {
  cronExpression: string
  timezone?: string
  scheduleMode?: 'cron' | 'availability'
  availabilityCheckIntervalMinutes?: number
  minimumSuccessIntervalHours?: number
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
      <SchedulePicker
        cronExpression={data.cronExpression}
        timezone={data.timezone || 'UTC'}
        onChange={(updates) => onChange(updates)}
        scheduleMode={data.scheduleMode}
        availabilityCheckIntervalMinutes={data.availabilityCheckIntervalMinutes}
        minimumSuccessIntervalHours={data.minimumSuccessIntervalHours}
        showTriggerMode
        required
        size="medium"
        cronLabel={t('wizard.scheduleWizard.config.scheduleLabel')}
        cronHelperText={t('wizard.scheduleWizard.config.scheduleHelper')}
      />

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
