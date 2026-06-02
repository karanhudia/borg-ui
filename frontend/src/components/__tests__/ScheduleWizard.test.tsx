import { screen, fireEvent } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ScheduleWizard, { type ScheduledJob } from '../ScheduleWizard'
import { renderWithProviders } from '../../test/test-utils'
import { type Repository } from '../../types'

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track: vi.fn(),
    EventCategory: { BACKUP: 'backup' },
    EventAction: { CREATE: 'create', EDIT: 'edit' },
  }),
}))

vi.mock('../MultiRepositorySelector', () => ({
  default: ({
    repositories,
    selectedIds,
    onChange,
  }: {
    repositories: Array<{ id: number; name: string }>
    selectedIds: number[]
    onChange: (ids: number[]) => void
  }) => (
    <div>
      {repositories.map((repo) => {
        const selected = selectedIds.includes(repo.id)
        return (
          <button
            key={repo.id}
            type="button"
            aria-pressed={selected}
            onClick={() =>
              onChange(
                selected ? selectedIds.filter((id) => id !== repo.id) : [...selectedIds, repo.id]
              )
            }
          >
            {repo.name}
          </button>
        )
      })}
    </div>
  ),
}))

const repositories: Repository[] = [
  {
    id: 7,
    name: 'Archive drive',
    path: '/repos/archive-drive',
    mode: 'full',
  },
]

const manualOnlyJob: ScheduledJob = {
  id: 42,
  name: 'External drive maintenance',
  schedule_enabled: false,
  cron_expression: null,
  timezone: null,
  repository: null,
  repository_id: null,
  repository_ids: [7],
  enabled: true,
  description: 'Runs when the drive is connected',
  archive_name_template: '{job_name}-{now}',
  run_repository_scripts: false,
  pre_backup_script_id: null,
  post_backup_script_id: null,
  pre_backup_script_parameters: {},
  post_backup_script_parameters: {},
  run_prune_after: true,
  run_compact_after: true,
  prune_keep_hourly: 0,
  prune_keep_daily: 7,
  prune_keep_weekly: 4,
  prune_keep_monthly: 6,
  prune_keep_quarterly: 0,
  prune_keep_yearly: 1,
}

describe('ScheduleWizard', () => {
  it('creates manual-only jobs without cron or timezone data', () => {
    const onClose = vi.fn()
    const onSubmit = vi.fn()

    renderWithProviders(
      <ScheduleWizard
        open
        mode="create"
        repositories={repositories}
        scripts={[]}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    )

    fireEvent.change(screen.getByLabelText(/Job Name/i), {
      target: { value: 'External drive maintenance' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Archive drive' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    fireEvent.click(screen.getByLabelText(/Run manually only/i))

    for (let step = 0; step < 3; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    }

    fireEvent.click(screen.getByRole('button', { name: 'Create Schedule' }))

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'External drive maintenance',
        repository_ids: [7],
        cron_expression: null,
        timezone: null,
      })
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('submits manual-only jobs without cron or timezone data', () => {
    const onClose = vi.fn()
    const onSubmit = vi.fn()

    renderWithProviders(
      <ScheduleWizard
        open
        mode="edit"
        scheduledJob={manualOnlyJob}
        repositories={repositories}
        scripts={[]}
        onClose={onClose}
        onSubmit={onSubmit}
      />
    )

    for (let step = 0; step < 4; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    }

    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }))

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'External drive maintenance',
        repository_ids: [7],
        cron_expression: null,
        timezone: null,
        run_prune_after: true,
        run_compact_after: true,
      })
    )
    expect(onClose).toHaveBeenCalled()
  })
})
