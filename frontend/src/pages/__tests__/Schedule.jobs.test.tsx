import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor, within } from '../../test/test-utils'
import type { Repository } from '../../types'
import Schedule from '../Schedule'

const { track, mockState } = vi.hoisted(() => ({
  track: vi.fn(),
  mockState: {
    repositories: [
      {
        id: 1,
        name: 'Legacy source repo',
        path: '/backup/legacy-source',
        mode: 'full',
        source_directories: ['/srv/data'],
      },
      {
        id: 2,
        name: 'Plan-owned repo',
        path: '/backup/plan-owned',
        mode: 'full',
        source_directories: [],
        source_locations: [],
      },
    ] as Repository[],
    jobs: [
      {
        id: 11,
        name: 'Legacy server batch',
        cron_expression: '0 2 * * *',
        timezone: 'UTC',
        repository: null,
        repository_id: null,
        repository_ids: [1],
        enabled: true,
        last_run: null,
        next_run: '2026-06-04T02:00:00Z',
        created_at: '2026-06-03T00:00:00Z',
        updated_at: null,
        description: 'Wake server, back up repositories, then power off.',
        archive_name_template: null,
        run_repository_scripts: false,
        pre_backup_script_id: null,
        post_backup_script_id: null,
        run_prune_after: true,
        run_compact_after: true,
        prune_keep_hourly: 0,
        prune_keep_daily: 7,
        prune_keep_weekly: 4,
        prune_keep_monthly: 6,
        prune_keep_quarterly: 0,
        prune_keep_yearly: 1,
        last_prune: null,
        last_compact: null,
      },
    ],
  },
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track,
    EventCategory: { BACKUP: 'backup' },
    EventAction: {
      COMPLETE: 'complete',
      CREATE: 'create',
      DELETE: 'delete',
      EDIT: 'edit',
      FAIL: 'fail',
      START: 'start',
    },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: (permission: string) => permission === 'repositories.manage_all',
  }),
}))

vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    canDo: () => true,
  }),
}))

vi.mock('../../hooks/useTrackedJobOutcomes', () => ({
  useTrackedJobOutcomes: () => undefined,
}))

vi.mock('../../components/ScheduleWizard', () => ({
  default: ({ open, repositories }: { open: boolean; repositories: Repository[] }) =>
    open ? (
      <div role="dialog" aria-label="Legacy job wizard">
        {repositories.map((repository) => (
          <span key={repository.id}>{repository.name}</span>
        ))}
      </div>
    ) : null,
}))

vi.mock('../../services/api', () => ({
  scheduleAPI: {
    createScheduledJob: vi.fn(() => Promise.resolve({ data: {} })),
    deleteScheduledJob: vi.fn(() => Promise.resolve({ data: {} })),
    duplicateScheduledJob: vi.fn(() => Promise.resolve({ data: {} })),
    getScheduledJobs: vi.fn(() => Promise.resolve({ data: { jobs: mockState.jobs } })),
    getUpcomingJobs: vi.fn(() => Promise.resolve({ data: { upcoming_jobs: [] } })),
    runScheduledJobNow: vi.fn(() => Promise.resolve({ data: {} })),
    toggleScheduledJob: vi.fn(() => Promise.resolve({ data: {} })),
    updateScheduledJob: vi.fn(() => Promise.resolve({ data: {} })),
  },
  repositoriesAPI: {
    getCheckSchedule: vi.fn(() =>
      Promise.resolve({
        data: {
          check_cron_expression: null,
          check_schedule_enabled: false,
          check_timezone: null,
        },
      })
    ),
    getRepositories: vi.fn(() =>
      Promise.resolve({ data: { repositories: mockState.repositories } })
    ),
    getRestoreCheckSchedule: vi.fn(() =>
      Promise.resolve({
        data: {
          restore_check_cron_expression: null,
          restore_check_schedule_enabled: false,
          restore_check_timezone: null,
        },
      })
    ),
  },
  backupAPI: {
    cancelJob: vi.fn(() => Promise.resolve({ data: {} })),
    getAllJobs: vi.fn(() => Promise.resolve({ data: { jobs: [] } })),
  },
  scriptsAPI: {
    list: vi.fn(() => Promise.resolve({ data: [] })),
  },
  backupPlansAPI: {
    cancelRun: vi.fn(() => Promise.resolve({ data: {} })),
    get: vi.fn(() => Promise.resolve({ data: {} })),
    list: vi.fn(() => Promise.resolve({ data: { backup_plans: [] } })),
    listRuns: vi.fn(() => Promise.resolve({ data: { runs: [] } })),
  },
}))

describe('Schedule Jobs page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
  })

  it('shows executable jobs and limits legacy job creation to source-backed repositories', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Schedule />, { initialRoute: '/schedule' })

    expect(await screen.findByRole('heading', { name: 'Jobs' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Executable Jobs' })).toBeInTheDocument()

    expect(await screen.findByText('Legacy Repository Jobs')).toBeInTheDocument()
    expect(screen.getByText('Legacy server batch')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Create legacy job' }))

    const dialog = await screen.findByRole('dialog', { name: 'Legacy job wizard' })
    await waitFor(() => {
      expect(within(dialog).getByText('Legacy source repo')).toBeInTheDocument()
    })
    expect(within(dialog).queryByText('Plan-owned repo')).not.toBeInTheDocument()
  })
})
