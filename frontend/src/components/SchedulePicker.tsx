import React, { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Autocomplete, Box, Stack, TextField, Tooltip, Typography } from '@mui/material'
import { Info } from 'lucide-react'
import CronExpressionParser from 'cron-parser'
import CronExpressionInput from './CronExpressionInput'
import { getBrowserTimeZone, getSupportedTimeZones } from '../utils/dateUtils'

interface SchedulePickerProps {
  cronExpression: string
  timezone: string
  onChange: (updates: { cronExpression?: string; timezone?: string }) => void
  disabled?: boolean
  required?: boolean
  size?: 'small' | 'medium'
  cronLabel?: string
  cronHelperText?: string
  timezoneLabel?: string
  /** How many upcoming runs to show in the preview tooltip. Defaults to 3. */
  previewRunCount?: number
}

/**
 * Reusable schedule picker: cron expression (with visual builder dialog) +
 * timezone autocomplete + next-run preview. Used by both the schedule wizard
 * config step and the backup plan wizard schedule step.
 *
 * Caller is responsible for any surrounding "enable schedule" toggle — this
 * component only renders the picker itself.
 */
const SchedulePicker: React.FC<SchedulePickerProps> = ({
  cronExpression,
  timezone,
  onChange,
  disabled,
  required,
  size = 'medium',
  cronLabel,
  cronHelperText,
  timezoneLabel,
  previewRunCount = 3,
}) => {
  const { t } = useTranslation()
  const effectiveTimezone = timezone || 'UTC'
  const browserTimezone = getBrowserTimeZone()
  const timezoneOptions = useMemo(
    () => getSupportedTimeZones(effectiveTimezone),
    [effectiveTimezone]
  )

  const nextRunTimes = useMemo(() => {
    try {
      const interval = CronExpressionParser.parse(cronExpression, { tz: effectiveTimezone })
      const times: Array<{ scheduleTime: string; localTime: string | null }> = []
      for (let i = 0; i < previewRunCount; i++) {
        const nextDate = interval.next().toDate()
        const scheduleTime = nextDate.toLocaleString(undefined, {
          dateStyle: 'medium',
          timeStyle: 'short',
          timeZone: effectiveTimezone,
        })
        const localTime =
          effectiveTimezone === browserTimezone
            ? null
            : nextDate.toLocaleString(undefined, {
                dateStyle: 'medium',
                timeStyle: 'short',
                timeZone: browserTimezone,
              })
        times.push({ scheduleTime, localTime })
      }
      return times
    } catch {
      return null
    }
  }, [cronExpression, effectiveTimezone, browserTimezone, previewRunCount])

  const formatRunTime = (run: { scheduleTime: string; localTime: string | null }) =>
    run.localTime ? `${run.scheduleTime} (${run.localTime} local)` : run.scheduleTime

  return (
    <Stack spacing={2}>
      <CronExpressionInput
        value={cronExpression}
        onChange={(cron) => onChange({ cronExpression: cron })}
        label={cronLabel ?? t('wizard.scheduleWizard.config.scheduleLabel')}
        helperText={cronHelperText ?? t('wizard.scheduleWizard.config.scheduleHelper')}
        required={required}
        disabled={disabled}
        size={size}
      />

      <Autocomplete
        options={timezoneOptions}
        value={effectiveTimezone}
        onChange={(_, value) => {
          if (value) onChange({ timezone: value })
        }}
        disableClearable
        disabled={disabled}
        fullWidth
        size={size}
        autoHighlight
        renderInput={(params) => (
          <TextField
            {...params}
            label={
              timezoneLabel ??
              t('wizard.scheduleWizard.config.timezoneLabel', { defaultValue: 'Timezone' })
            }
            required={required}
            placeholder="Asia/Kolkata"
          />
        )}
      />

      {nextRunTimes && nextRunTimes.length > 0 && (
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
                      {time.scheduleTime} {effectiveTimezone}
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
    </Stack>
  )
}

export default SchedulePicker
