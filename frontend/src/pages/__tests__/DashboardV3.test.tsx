import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import Dashboard from '../DashboardV3'
import { formatDateTimeFull } from '../../utils/dateUtils'

// ─── Mocks ────────────────────────────────────────────────────────────────────

const mockNavigate = vi.fn()
const { getOverviewMock } = vi.hoisted(() => ({
  getOverviewMock: vi.fn(),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}))

vi.mock('../../context/ThemeContext', () => ({
  useTheme: () => ({ mode: 'dark', effectiveMode: 'dark' }),
}))

vi.mock('../../utils/basePath', () => ({
  BASE_PATH: '',
}))

vi.mock('../../services/api', () => ({
  dashboardAPI: {
    getOverview: getOverviewMock,
  },
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

const createQueryClient = () => new QueryClient({ defaultOptions: { queries: { retry: false } } })

function renderDashboard() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <Dashboard />
    </QueryClientProvider>
  )
}

function mockFetchSuccess(data: unknown) {
  getOverviewMock.mockResolvedValueOnce({ data })
}

function mockFetchError() {
  getOverviewMock.mockRejectedValueOnce(new Error('Failed'))
}

function makeOverview(overrides: Record<string, unknown> = {}) {
  return {
    summary: {
      total_repositories: 2,
      local_repositories: 1,
      ssh_repositories: 1,
      active_schedules: 1,
      total_schedules: 2,
      active_backup_plans: 1,
      total_backup_plans: 2,
      active_automations: 2,
      total_automations: 4,
      success_rate_30d: 83.3,
      successful_jobs_30d: 5,
      failed_jobs_30d: 1,
      total_jobs_30d: 6,
    },
    storage: {
      total_size: '10.5 GB',
      total_size_bytes: 11274289152,
      total_archives: 24,
      average_dedup_ratio: 2.5,
      breakdown: [
        { name: 'my-server', size: '6 GB', size_bytes: 6442450944, percentage: 57 },
        { name: 'backup-nas', size: '4.5 GB', size_bytes: 4831838208, percentage: 43 },
      ],
    },
    repository_health: [
      {
        id: 1,
        name: 'my-server',
        type: 'local',
        mode: 'full' as const,
        last_backup: '2026-03-30T10:00:00+00:00',
        last_check: '2026-03-29T10:00:00+00:00',
        last_compact: null,
        last_restore_check: '2026-03-28T10:00:00+00:00',
        archive_count: 14,
        total_size: '6 GB',
        health_status: 'healthy' as const,
        warnings: [],
        next_run: '2026-03-31T10:00:00+00:00',
        has_schedule: true,
        schedule_enabled: true,
        schedule_name: 'Daily',
        backup_plan_count: 1,
        backup_plan_scheduled_count: 1,
        backup_plan_names: ['Nightly Documents'],
        backup_plan_next_run: '2026-03-31T09:00:00+00:00',
        restore_check_configured: true,
        latest_restore_check_status: 'completed',
        latest_restore_check_error: null,
        dimension_health: {
          backup: 'healthy' as const,
          check: 'healthy' as const,
          compact: 'warning' as const,
          restore: 'healthy' as const,
        },
      },
      {
        id: 2,
        name: 'backup-nas',
        type: 'ssh',
        mode: 'observe' as const,
        last_backup: null,
        last_check: null,
        last_compact: null,
        last_restore_check: null,
        archive_count: 0,
        total_size: '0 B',
        health_status: 'critical' as const,
        warnings: ['No archives detected'],
        next_run: null,
        has_schedule: false,
        schedule_enabled: false,
        schedule_name: null,
        backup_plan_count: 0,
        backup_plan_scheduled_count: 0,
        backup_plan_names: [],
        backup_plan_next_run: null,
        restore_check_configured: false,
        latest_restore_check_status: null,
        latest_restore_check_error: null,
        dimension_health: {
          backup: 'critical' as const,
          check: 'unknown' as const,
          compact: 'critical' as const,
          restore: 'unknown' as const,
        },
      },
    ],
    upcoming_tasks: [],
    activity_feed: [
      {
        id: 1,
        type: 'backup',
        status: 'completed',
        repository: 'my-server',
        timestamp: '2026-03-30T10:00:00+00:00',
        message: 'Backup completed',
        error: null,
      },
      {
        id: 2,
        type: 'backup',
        status: 'failed',
        repository: 'backup-nas',
        timestamp: '2026-03-29T08:00:00+00:00',
        message: 'Backup failed',
        error: 'Connection refused',
      },
    ],
    system_metrics: {
      cpu_usage: 12,
      cpu_count: 4,
      memory_usage: 45,
      memory_total: 8589934592,
      memory_available: 4724464435,
      disk_usage: 68,
      disk_total: 107374182400,
      disk_free: 34359738368,
    },
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  getOverviewMock.mockResolvedValue({ data: makeOverview() })
  // Default: suppress localStorage access
  vi.stubGlobal('localStorage', { getItem: () => 'test-token' })
})

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('DashboardV3', () => {
  describe('API calls', () => {
    it('fetches overview through the shared dashboard API on mount', async () => {
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))
      expect(getOverviewMock).toHaveBeenCalledTimes(1)
    })

    it('renders overview data returned by the shared API', async () => {
      getOverviewMock.mockResolvedValueOnce({ data: makeOverview() })
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))
      expect(screen.getAllByText('backup-nas').length).toBeGreaterThan(0)
    })

    it('fetches exactly once on initial render', async () => {
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))
      expect(getOverviewMock).toHaveBeenCalledTimes(1)
    })
  })

  describe('loading and error states', () => {
    it('shows loading skeletons before data arrives', () => {
      getOverviewMock.mockReturnValueOnce(new Promise(() => {}) as never)
      renderDashboard()
      expect(document.querySelectorAll('.MuiSkeleton-root').length).toBeGreaterThan(0)
    })

    it('shows error alert when fetch fails', async () => {
      mockFetchError()
      renderDashboard()
      await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    })
  })

  describe('system status banner', () => {
    it('shows "All systems nominal" when no repos are critical or warning', async () => {
      const data = makeOverview({
        repository_health: [
          {
            ...makeOverview().repository_health[0],
            health_status: 'healthy',
            dimension_health: {
              backup: 'healthy',
              check: 'healthy',
              compact: 'healthy',
              restore: 'healthy',
            },
          },
        ],
      })
      mockFetchSuccess(data)
      renderDashboard()
      await waitFor(() => expect(screen.getByText('All systems nominal')).toBeInTheDocument())
    })

    it('shows critical count when repos are critical', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      // "1 critical" appears in both the status banner and the chips row
      await waitFor(() => expect(screen.getAllByText('1 critical').length).toBeGreaterThan(0))
    })
  })

  describe('quick stats bar', () => {
    it('renders total repository count', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('2')).toBeInTheDocument())
    })

    it('renders storage total', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getAllByText('10.5 GB').length).toBeGreaterThan(0))
    })

    it('renders automation ratio including backup plans and legacy schedules', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('2/4')).toBeInTheDocument())
    })

    it('shows "Never" when no repository has a past backup', async () => {
      const data = makeOverview({
        repository_health: makeOverview().repository_health.map((r) => ({
          ...r,
          last_backup: null,
        })),
      })
      mockFetchSuccess(data)
      renderDashboard()
      await waitFor(() => expect(screen.getAllByText('Never').length).toBeGreaterThan(0))
    })
  })

  describe('success donut', () => {
    it('shows success rate percentage', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('83%')).toBeInTheDocument())
    })

    it('shows passed and failed counts', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => {
        expect(screen.getByText('5')).toBeInTheDocument()
        expect(screen.getByText('1')).toBeInTheDocument()
      })
    })

    it('shows job ratio label', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('5/6 OK')).toBeInTheDocument())
    })
  })

  describe('repository health grid', () => {
    it('renders a card for each repository', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      // names appear in both the health grid and the storage legend
      await waitFor(() => {
        expect(screen.getAllByText('my-server').length).toBeGreaterThan(0)
        expect(screen.getAllByText('backup-nas').length).toBeGreaterThan(0)
      })
    })

    it('shows "No repositories" when list is empty', async () => {
      mockFetchSuccess(makeOverview({ repository_health: [] }))
      renderDashboard()
      await waitFor(() => expect(screen.getByText('No repositories')).toBeInTheDocument())
    })

    it('clicking a repo card navigates to /repositories', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))
      // 'my-server' appears in both the storage legend (index 0) and the health grid card (index 1)
      fireEvent.click(screen.getAllByText('my-server')[1])
      expect(mockNavigate).toHaveBeenCalledWith('/repositories')
    })

    it('shows "manual" badge for repos without a schedule', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('manual')).toBeInTheDocument())
    })

    it('shows "paused" badge for repos with a disabled schedule', async () => {
      const data = makeOverview({
        repository_health: makeOverview().repository_health.map((r, i) =>
          i === 0
            ? {
                ...r,
                has_schedule: true,
                schedule_enabled: false,
                backup_plan_count: 0,
                backup_plan_scheduled_count: 0,
                backup_plan_names: [],
                backup_plan_next_run: null,
              }
            : r
        ),
      })
      mockFetchSuccess(data)
      renderDashboard()
      await waitFor(() => expect(screen.getByText('paused')).toBeInTheDocument())
    })

    it('shows observe-only badge and monitoring dimensions for observe repositories', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getAllByText('Observe Only').length).toBeGreaterThan(0))
      expect(screen.getByText('FRESH')).toBeInTheDocument()
      expect(screen.getByText('ARCHIVES')).toBeInTheDocument()
      expect(screen.getAllByText('RESTORE').length).toBeGreaterThan(0)
    })

    it('shows restore check status for observe repositories', async () => {
      const observeRepo = {
        ...makeOverview().repository_health[1],
        restore_check_configured: true,
        latest_restore_check_status: 'failed',
        latest_restore_check_error: 'Probe path missing',
        dimension_health: {
          ...makeOverview().repository_health[1].dimension_health,
          restore: 'critical',
        },
      }
      mockFetchSuccess(makeOverview({ repository_health: [observeRepo] }))
      renderDashboard()

      await waitFor(() => expect(screen.getByText('Observe Only')).toBeInTheDocument())
      expect(screen.getByText('RESTORE')).toBeInTheDocument()
      expect(screen.getByText('Failed')).toBeInTheDocument()
    })

    it('shows restore verification as a health dimension for full repositories', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))

      expect(screen.getAllByText('RESTORE').length).toBeGreaterThan(0)
      expect(
        screen.getAllByLabelText(formatDateTimeFull('2026-03-28T10:00:00+00:00')).length
      ).toBeGreaterThan(0)
    })

    it('shows canary setup-needed restore checks as needs backup', async () => {
      const data = makeOverview({
        repository_health: makeOverview().repository_health.map((r, i) =>
          i === 0
            ? {
                ...r,
                last_restore_check: null,
                latest_restore_check_status: 'needs_backup',
                latest_restore_check_error: 'Run a backup, then run this restore check again.',
                dimension_health: {
                  ...r.dimension_health,
                  restore: 'warning',
                },
              }
            : r
        ),
      })
      mockFetchSuccess(data)
      renderDashboard()

      await waitFor(() => expect(screen.getByText('Needs backup')).toBeInTheDocument())
    })

    it('shows backup plan coverage on repository cards', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('Nightly Documents')).toBeInTheDocument())
      expect(screen.getByText('1 plan')).toBeInTheDocument()
    })

    it('adds full timestamp tooltips to relative health times', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))

      expect(
        screen.getAllByLabelText(formatDateTimeFull('2026-03-30T10:00:00+00:00')).length
      ).toBeGreaterThan(0)
      expect(
        screen.getAllByLabelText(formatDateTimeFull('2026-03-29T10:00:00+00:00')).length
      ).toBeGreaterThan(0)
    })
  })

  describe('storage panel', () => {
    it('shows storage total in bottom storage panel', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getAllByText('10.5 GB').length).toBeGreaterThan(0))
    })

    it('shows dedup ratio', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('2.50×')).toBeInTheDocument())
    })

    it('shows repo names in storage legend', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => {
        expect(screen.getAllByText('my-server').length).toBeGreaterThan(0)
        expect(screen.getAllByText('backup-nas').length).toBeGreaterThan(0)
      })
    })

    it('hides dedup ratio when null', async () => {
      const data = makeOverview({
        storage: { ...makeOverview().storage, average_dedup_ratio: null },
      })
      mockFetchSuccess(data)
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))
      expect(screen.queryByText(/Dedup ratio/)).not.toBeInTheDocument()
    })
  })

  describe('activity section', () => {
    it('shows "No activity recorded yet" when feed is empty', async () => {
      mockFetchSuccess(makeOverview({ activity_feed: [] }))
      renderDashboard()
      await waitFor(() => expect(screen.getByText('No activity recorded yet')).toBeInTheDocument())
    })

    it('shows recent failures section when feed has failures', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => expect(screen.getByText('Recent failures')).toBeInTheDocument())
    })

    it('shows failed repo name in recent failures', async () => {
      mockFetchSuccess(makeOverview())
      renderDashboard()
      await waitFor(() => {
        const failures = screen.getByText('Recent failures')
        expect(failures).toBeInTheDocument()
        expect(screen.getAllByText('backup-nas').length).toBeGreaterThan(0)
      })
    })

    it('hides recent failures section when no failures', async () => {
      const data = makeOverview({
        activity_feed: [
          {
            id: 1,
            type: 'backup',
            status: 'completed',
            repository: 'my-server',
            timestamp: '2026-03-30T10:00:00+00:00',
            message: 'ok',
            error: null,
          },
        ],
      })
      mockFetchSuccess(data)
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))
      expect(screen.queryByText('Recent failures')).not.toBeInTheDocument()
    })
  })

  describe('upcoming automation panel', () => {
    it('renders scheduled backup plans from upcoming tasks', async () => {
      mockFetchSuccess(
        makeOverview({
          upcoming_tasks: [
            {
              id: 7,
              type: 'backup_plan',
              name: 'Nightly Documents',
              repositories: ['my-server', 'backup-nas'],
              cron: '0 3 * * *',
              timezone: 'UTC',
              next_run: '2026-03-31T03:00:00+00:00',
            },
          ],
        })
      )

      renderDashboard()

      await waitFor(() => expect(screen.getByText('Upcoming backups')).toBeInTheDocument())
      expect(screen.getByText('Backup Plan')).toBeInTheDocument()
      expect(screen.getAllByText('Nightly Documents').length).toBeGreaterThan(0)
      expect(screen.getByText('2 repositories')).toBeInTheDocument()
    })
  })

  describe('refresh button', () => {
    it('triggers a new fetch when clicked', async () => {
      getOverviewMock.mockResolvedValue({ data: makeOverview() })
      renderDashboard()
      await waitFor(() => screen.getAllByText('my-server'))

      const callsBefore = getOverviewMock.mock.calls.length
      fireEvent.click(screen.getByText('Refresh'))
      await waitFor(() => expect(getOverviewMock.mock.calls.length).toBeGreaterThan(callsBefore))
    })
  })
})
