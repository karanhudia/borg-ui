import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import type { TFunction } from 'i18next'

import { createInitialState } from '../state'
import { ScheduleStep } from './ScheduleStep'

const translations: Record<string, string> = {
  'backupPlans.wizard.schedule.title': 'Schedule',
  'backupPlans.wizard.schedule.description': 'Run this plan on a schedule.',
  'backupPlans.wizard.schedule.enabled': 'Enable schedule',
  'backupPlans.wizard.maintenance.title': 'Maintenance',
  'backupPlans.wizard.maintenance.description': 'Run maintenance after backups.',
  'backupPlans.wizard.maintenance.runPruneAfter': 'Run prune after backup',
  'backupPlans.wizard.maintenance.runCompactAfter': 'Run compact after prune',
  'backupPlans.wizard.maintenance.runCheckAfter': 'Run check after backup',
  'backupPlans.wizard.fields.cronExpression': 'Cron expression',
  'backupPlans.wizard.fields.timezone': 'Timezone',
  'backupPlans.wizard.fields.checkMaxDuration': 'Max check duration',
  'backupPlans.wizard.fields.checkExtraFlags': 'Advanced check flags',
  'backupPlans.wizard.schedule.cronHelper': 'Use cron syntax for scheduled runs.',
  'backupPlans.wizard.maintenance.checkMaxDurationHelper': 'Seconds. Use 0 for unlimited.',
  'backupPlans.wizard.maintenance.checkExtraFlagsHelper':
    'Additional borg check options appended to plan maintenance checks.',
  'checkFlagConflicts.durationConflict':
    'Set max duration to 0 (unlimited) to use {{flags}}. Positive durations run partial repository-only checks.',
}

const t = ((key: string, params?: Record<string, unknown>) =>
  (translations[key] || key).replace('{{flags}}', String(params?.flags ?? ''))) as TFunction

const conflictState = {
  ...createInitialState(),
  runCheckAfter: true,
  checkMaxDuration: 3600,
  checkExtraFlags: '--archives-only',
}

const meta = {
  title: 'Backup Plans/ScheduleStep',
  parameters: { layout: 'centered' },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const CheckFlagConflict: Story = {
  render: () => (
    <Box sx={{ width: 720, maxWidth: 'calc(100vw - 32px)' }}>
      <ScheduleStep
        wizardState={conflictState}
        updateState={() => {}}
        handlePruneSettingsChange={() => {}}
        t={t}
      />
    </Box>
  ),
}
