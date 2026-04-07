import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Stack, Typography, Box, Tooltip } from '@mui/material'
import { Info } from 'lucide-react'
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
  const { t } = useTranslation()

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
        label={t('wizard.scheduleWizard.config.scheduleLabel')}
        helperText={t('wizard.scheduleWizard.config.scheduleHelper')}
        required
        size="medium"
      />

      {nextRunTimes && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, pl: 0.25 }}>
          <Tooltip
            title={
              <Stack spacing={0.5} sx={{ py: 0.25 }}>
                <Typography variant="caption" fontWeight={600}>
                  {t('wizard.scheduleWizard.config.nextRunTimes')}
                </Typography>
                {nextRunTimes.map((time, index) => (
                  <Typography
                    key={index}
                    variant="caption"
                    sx={{ fontFamily: 'monospace', opacity: 0.9 }}
                  >
                    {time}
                  </Typography>
                ))}
              </Stack>
            }
            arrow
            placement="right"
          >
            <Box
              component="span"
              tabIndex={0}
              aria-label={t('wizard.scheduleWizard.config.nextRunTimes')}
              sx={{
                display: 'inline-flex',
                cursor: 'help',
                color: 'text.disabled',
                '&:hover': { color: 'text.secondary' },
                '&:focus-visible': {
                  outline: '2px solid',
                  outlineColor: 'primary.main',
                  borderRadius: 0.5,
                },
              }}
            >
              <Info size={14} />
            </Box>
          </Tooltip>
          <Typography variant="caption" color="text.secondary">
            {t('wizard.scheduleWizard.config.nextRunTimes')} {nextRunTimes[0]}
          </Typography>
        </Box>
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
