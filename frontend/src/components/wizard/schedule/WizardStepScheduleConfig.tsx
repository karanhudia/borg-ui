import React, { useMemo } from 'react'
import { Stack, Alert, Typography, Box } from '@mui/material'
import CronExpressionInput from '../../CronExpressionInput'
import ArchiveNameTemplateInput from '../../ArchiveNameTemplateInput'
import CronExpressionParser from 'cron-parser'

interface WizardStepScheduleConfigData {
  cronExpression: string
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
  // Calculate next 3 run times
  const nextRunTimes = useMemo(() => {
    try {
      const interval = CronExpressionParser.parse(data.cronExpression)
      const times: string[] = []
      for (let i = 0; i < 3; i++) {
        times.push(interval.next().toDate().toLocaleString())
      }
      return times
    } catch {
      return null
    }
  }, [data.cronExpression])

  return (
    <Stack spacing={2}>
      <CronExpressionInput
        value={data.cronExpression}
        onChange={(cron) => onChange({ cronExpression: cron })}
        label="Schedule (Cron Expression)"
        helperText="Click the clock icon to use the visual builder."
        required
        size="medium"
      />

      {nextRunTimes && (
        <Alert severity="info" sx={{ py: 0.5 }}>
          <Typography variant="body2" fontWeight={600} gutterBottom>
            Next 3 Run Times:
          </Typography>
          <Box component="ul" sx={{ pl: 2, my: 0 }}>
            {nextRunTimes.map((time, index) => (
              <li key={index}>
                <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>
                  {time}
                </Typography>
              </li>
            ))}
          </Box>
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
