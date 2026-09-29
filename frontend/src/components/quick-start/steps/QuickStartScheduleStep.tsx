import { Box, Stack, Typography } from '@mui/material'
import { CalendarClock, CalendarDays, Clock3, SlidersHorizontal } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import SchedulePicker from '../../shared/SchedulePicker'
import QuickStartChoiceCard from '../QuickStartChoiceCard'
import {
  SCHEDULE_PRESET_CRON,
  type QuickStartSchedulePreset,
  type QuickStartStepProps,
} from '../quickStartState'

const PRESETS: { key: QuickStartSchedulePreset; icon: typeof Clock3 }[] = [
  { key: 'daily', icon: CalendarClock },
  { key: 'every6h', icon: Clock3 },
  { key: 'weekly', icon: CalendarDays },
  { key: 'custom', icon: SlidersHorizontal },
]

export default function QuickStartScheduleStep({ answers, onChange }: QuickStartStepProps) {
  const { t } = useTranslation()

  const selectPreset = (preset: QuickStartSchedulePreset) => {
    onChange({
      schedulePreset: preset,
      cronExpression: preset === 'custom' ? answers.cronExpression : SCHEDULE_PRESET_CRON[preset],
      settings: { ...answers.settings, scheduleEnabled: true },
    })
  }

  return (
    <Stack spacing={2}>
      <Box>
        <Typography variant="h6" component="h3">
          {t('quickStart.schedule.title')}
        </Typography>
        <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.5 }}>
          {t('quickStart.schedule.hint', { timezone: answers.timezone })}
        </Typography>
      </Box>
      <Box
        role="radiogroup"
        aria-label={t('quickStart.schedule.title')}
        sx={{ display: 'grid', gap: 1.5, gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr' } }}
      >
        {PRESETS.map(({ key, icon: Icon }) => (
          <QuickStartChoiceCard
            key={key}
            icon={<Icon size={20} />}
            title={t(`quickStart.schedule.presets.${key}`)}
            description={t(`quickStart.schedule.presets.${key}Desc`)}
            selected={answers.settings.scheduleEnabled && answers.schedulePreset === key}
            onSelect={() => selectPreset(key)}
          />
        ))}
      </Box>
      {answers.schedulePreset === 'custom' && (
        <SchedulePicker
          cronExpression={answers.cronExpression}
          timezone={answers.timezone}
          onChange={(updates) =>
            onChange({
              ...(updates.cronExpression !== undefined
                ? { cronExpression: updates.cronExpression }
                : {}),
              ...(updates.timezone !== undefined ? { timezone: updates.timezone } : {}),
            })
          }
          size="small"
          required
        />
      )}
    </Stack>
  )
}
