import { render, screen } from '@testing-library/react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import { createInitialState } from '../state'
import { ScheduleStep } from '../wizard-step/ScheduleStep'

const theme = createTheme()

const translations: Record<string, string> = {
  'backupPlans.wizard.schedule.title': 'Schedule',
  'backupPlans.wizard.schedule.description': 'Run this plan on a schedule.',
  'backupPlans.wizard.schedule.enabled': 'Enable schedule',
  'backupPlans.wizard.maintenance.title': 'Maintenance',
  'backupPlans.wizard.maintenance.description': 'Run maintenance after backups.',
  'backupPlans.wizard.maintenance.runPruneAfter': 'Run prune after backup',
  'backupPlans.wizard.maintenance.runCompactAfter': 'Run compact after prune',
  'backupPlans.wizard.maintenance.runCheckAfter': 'Run check after backup',
  'backupPlans.wizard.fields.checkMaxDuration': 'Max check duration',
  'backupPlans.wizard.fields.checkExtraFlags': 'Advanced check flags',
  'backupPlans.wizard.maintenance.checkMaxDurationHelper': 'Seconds. Use 0 for unlimited.',
  'backupPlans.wizard.maintenance.checkExtraFlagsHelper':
    'Additional borg check options appended to plan maintenance checks.',
  'checkFlagConflicts.durationConflict':
    'Set max duration to 0 (unlimited) to use {{flags}}. Positive durations run partial repository-only checks.',
}

const t = ((key: string, params?: Record<string, unknown>) =>
  (translations[key] || key).replace('{{flags}}', String(params?.flags ?? ''))) as TFunction

function renderScheduleStep(stateOverrides: Partial<ReturnType<typeof createInitialState>>) {
  const wizardState = { ...createInitialState(), ...stateOverrides }

  return render(
    <ThemeProvider theme={theme}>
      <ScheduleStep
        wizardState={wizardState}
        updateState={vi.fn()}
        handlePruneSettingsChange={vi.fn()}
        t={t}
      />
    </ThemeProvider>
  )
}

describe('Backup plan ScheduleStep', () => {
  it('warns when plan check flags require unlimited duration', () => {
    renderScheduleStep({
      runCheckAfter: true,
      checkMaxDuration: 3600,
      checkExtraFlags: '--archives-only',
    })

    expect(
      screen.getByText(/Set max duration to 0 \(unlimited\) to use --archives-only/)
    ).toBeInTheDocument()
  })
})
