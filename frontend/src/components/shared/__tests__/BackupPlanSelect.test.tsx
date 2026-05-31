import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import BackupPlanSelect, { type BackupPlanSummary } from '../BackupPlanSelect'

const plans: BackupPlanSummary[] = [
  {
    id: 11,
    name: 'Docker volumes',
    source_type: 'local',
    repository_count: 2,
    schedule_enabled: true,
  },
  {
    id: 12,
    name: 'Postgres data',
    source_type: 'remote',
    repository_count: 1,
    schedule_enabled: false,
  },
]

describe('BackupPlanSelect', () => {
  it('renders the selected plan using the shared rich row format', () => {
    render(
      <BackupPlanSelect
        value={11}
        onChange={vi.fn()}
        plans={plans}
        label="Backup Plan"
        emptyMessage="No backup plans configured."
      />
    )

    const combobox = screen.getByRole('combobox', { name: /Backup Plan/i })
    expect(combobox).toHaveTextContent('Docker volumes')
    expect(combobox).toHaveTextContent('Local source')
    expect(combobox).toHaveTextContent('2 repositories')
    expect(combobox).toHaveTextContent('Scheduled')
  })

  it('calls onChange with the selected plan id', async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()

    render(
      <BackupPlanSelect
        value={11}
        onChange={onChange}
        plans={plans}
        label="Backup Plan"
        emptyMessage="No backup plans configured."
      />
    )

    await user.click(screen.getByRole('combobox', { name: /Backup Plan/i }))
    const listbox = await screen.findByRole('listbox')
    await user.click(within(listbox).getByRole('option', { name: /Postgres data/i }))

    expect(onChange).toHaveBeenCalledWith(12)
  })

  it('renders a placeholder when no plan is selected', () => {
    render(
      <BackupPlanSelect
        value=""
        onChange={vi.fn()}
        plans={plans}
        label="Backup Plan"
        emptyMessage="No backup plans configured."
        placeholder="Select a backup plan"
      />
    )

    expect(screen.getByRole('combobox', { name: /Backup Plan/i })).toHaveTextContent(
      'Select a backup plan'
    )
  })

  it('renders the provided empty state when no plans exist', () => {
    render(
      <BackupPlanSelect
        value=""
        onChange={vi.fn()}
        plans={[]}
        label="Backup Plan"
        emptyMessage="No backup plans configured."
      />
    )

    expect(screen.getByRole('alert')).toHaveTextContent('No backup plans configured.')
  })
})
