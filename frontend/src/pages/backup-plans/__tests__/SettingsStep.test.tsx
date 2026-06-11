import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createInitialState } from '../state'
import { SettingsStep } from '../wizard-step/SettingsStep'
import type { WizardState } from '../types'

const translations: Record<string, string> = {
  'backupPlans.wizard.fields.archiveNameTemplate': 'Archive name',
  'backupPlans.wizard.fields.extraBorgFlags': 'Extra Borg flags',
  'backupPlans.wizard.fields.maxParallelRepositories': 'Max parallel repositories',
  'backupPlans.wizard.fields.runRepositories': 'Run repositories',
  'backupPlans.wizard.fields.uploadSpeedLimit': 'Upload speed limit',
  'backupPlans.wizard.settings.addUploadPolicy': 'Add upload policy',
  'backupPlans.wizard.settings.archiveNameHelper': 'Archive name helper',
  'backupPlans.wizard.settings.daytimePolicyLabel': 'Daytime cap',
  'backupPlans.wizard.settings.extraBorgFlagsHelper': 'Extra Borg flags helper',
  'backupPlans.wizard.settings.parallelLabel': 'Parallel',
  'backupPlans.wizard.settings.parallelRequiresPro': 'Requires Pro',
  'backupPlans.wizard.settings.parallelTooltip': 'Run in parallel',
  'backupPlans.wizard.settings.policyEndTime': 'End time',
  'backupPlans.wizard.settings.policyLabel': 'Policy label',
  'backupPlans.wizard.settings.policyLimit': 'Policy upload limit',
  'backupPlans.wizard.settings.policyStartTime': 'Start time',
  'backupPlans.wizard.settings.removeUploadPolicy': 'Remove upload policy',
  'backupPlans.wizard.settings.seriesLabel': 'Series',
  'backupPlans.wizard.settings.uploadPoliciesHelper':
    'Time windows override the constant upload limit.',
  'backupPlans.wizard.settings.uploadPoliciesTitle': 'Scheduled upload limits',
  'backupPlans.wizard.settings.uploadSpeedHelper': 'MB/s. Empty means unlimited.',
}

const t = (key: string) => translations[key] || key

function renderSettings(
  wizardState: WizardState,
  updateState = vi.fn<(updates: Partial<WizardState>) => void>()
) {
  render(
    <SettingsStep
      wizardState={wizardState}
      canUseMultiRepository
      updateState={updateState}
      t={t as never}
    />
  )
  return updateState
}

describe('SettingsStep scheduled upload policies', () => {
  it('adds a default daytime upload policy row', async () => {
    const user = userEvent.setup()
    const updateState = renderSettings(createInitialState())

    await user.click(screen.getByRole('button', { name: 'Add upload policy' }))

    expect(updateState).toHaveBeenLastCalledWith({
      uploadRatelimitSchedulePolicies: [
        {
          label: 'Daytime cap',
          startTime: '08:00',
          endTime: '18:00',
          uploadRatelimitMb: '',
        },
      ],
    })
  })

  it('emits edits for an existing policy row', async () => {
    const state = {
      ...createInitialState(),
      uploadRatelimitSchedulePolicies: [
        {
          label: 'Daytime cap',
          startTime: '08:00',
          endTime: '18:00',
          uploadRatelimitMb: '0.5',
        },
      ],
    }
    const updateState = renderSettings(state)

    const limitInput = screen.getByLabelText('Policy upload limit')
    fireEvent.change(limitInput, { target: { value: '1.25' } })

    expect(updateState).toHaveBeenLastCalledWith({
      uploadRatelimitSchedulePolicies: [
        {
          label: 'Daytime cap',
          startTime: '08:00',
          endTime: '18:00',
          uploadRatelimitMb: '1.25',
        },
      ],
    })
  })
})
