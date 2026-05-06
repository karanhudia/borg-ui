import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Stack, Typography, Box, Tooltip, TextField, Autocomplete } from '@mui/material'
import { Info } from 'lucide-react'
import CronExpressionInput from '../../CronExpressionInput'
import ArchiveNameTemplateInput from '../../ArchiveNameTemplateInput'
import CronExpressionParser from 'cron-parser'
import { getBrowserTimeZone, getSupportedTimeZones } from '../../../utils/dateUtils'

interface WizardStepScheduleConfigData {
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
  const scheduleTimezone = data.timezone || 'UTC'
  const browserTimezone = getBrowserTimeZone()
  const timezoneOptions = useMemo(() => getSupportedTimeZones(scheduleTimezone), [scheduleTimezone])

  // Calculate next 3 run times
  const nextRunTimes = useMemo(() => {
    try {
      const interval = CronExpressionParser.parse(data.cronExpression, { tz: scheduleTimezone })
      const times: Array<{ scheduleTime: string; localTime: string | null }> = []
      for (let i = 0; i < 3; i++) {
        const nextDate = interval.next().toDate()
        const scheduleTime = nextDate.toLocaleString(undefined, {
          dateStyle: 'medium',
          timeStyle: 'short',
          timeZone: scheduleTimezone,
        })
        const localTime =
          scheduleTimezone === browserTimezone
            ? null
            : nextDate.toLocaleString(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short',
                timeZone: browserTimezone,
              })
        times.push({
          scheduleTime,
          localTime,
        })
      }
      return times
    } catch {
      return null
    }
  }, [data.cronExpression, scheduleTimezone, browserTimezone])

  const formatRunTime = (run: { scheduleTime: string; localTime: string | null }) =>
    run.localTime ? `${run.scheduleTime} (${run.localTime} local)` : run.scheduleTime

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

      <Autocomplete
        options={timezoneOptions}
        value={scheduleTimezone}
        onChange={(_, value) => {
          if (value) onChange({ timezone: value })
        }}
        disableClearable
        fullWidth
        size="medium"
        autoHighlight
        renderInput={(params) => (
          <TextField
            {...params}
            label={t('wizard.scheduleWizard.config.timezoneLabel', { defaultValue: 'Timezone' })}
            required
            placeholder="Asia/Kolkata"
          />
        )}
      />

      {nextRunTimes && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, pl: 0.25 }}>
          <Tooltip
            title={
              <Stack spacing={0.75} sx={{ py: 0.25 }}>
                <Typography variant="caption" fontWeight={600}>
                  {t('wizard.scheduleWizard.config.nextRunTimes')}
                </Typography>
                {nextRunTimes.map((time, index) => (
                  <Box key={index} sx={{ display: 'flex', flexDirection: 'column', gap: 0.15 }}>
                    <Typography variant="caption" sx={{ fontFamily: 'monospace', opacity: 0.95 }}>
                      {time.scheduleTime} {scheduleTimezone}
                    </Typography>
                    {time.localTime && (
                      <Typography variant="caption" sx={{ fontFamily: 'monospace', opacity: 0.75 }}>
                        {time.localTime} local
                      </Typography>
                    )}
                  </Box>
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
            {t('wizard.scheduleWizard.config.nextRunTimes')} {formatRunTime(nextRunTimes[0])}
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
