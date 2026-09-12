import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Activity from '../Activity'
import { activityAPI, repositoriesAPI } from '../../services/api'

const track = vi.fn()

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track,
    EventCategory: { NAVIGATION: 'Navigation' },
    EventAction: { FILTER: 'Filter' },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: (permission: string) => permission === 'repositories.manage_all',
  }),
}))

vi.mock('../../hooks/useLockBreakPermissions', () => ({
  useLockBreakPermissions: () => ({ canBreakLock: () => true, lockBreakingEnabled: true }),
}))

vi.mock('../../hooks/useOperationEvents', () => ({ useOperationEvents: () => {} }))

vi.mock('../../components/LogViewerDialog', () => ({
  default: ({ open }: { open: boolean }) => (open ? <div>Log Viewer</div> : null),
}))

const noon = () => {
  const day = new Date()
  day.setHours(12, 0, 0, 0)
  return day.toISOString()
}

const backup = {
  id: 7,
  type: 'backup',
  kind: 'backup',
  category: 'backup',
  trigger: 'plan',
  backup_plan_name: 'Nightly',
  status: 'completed',
  started_at: noon(),
  completed_at: noon(),
  error_message: null,
  repository: 'repo7',
  repository_id: 1,
  log_file_path: '/logs/job7.log',
  archive_name: null,
  package_name: null,
  repository_path: '/backup/repo7',
  has_logs: true,
}

describe('Activity page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(activityAPI, 'list').mockResolvedValue({ data: [backup] } as never)
    vi.spyOn(repositoriesAPI, 'getRepositories').mockResolvedValue({
      data: { repositories: [{ id: 1, name: 'nas', path: '/mnt/nas' }] },
    } as never)
    vi.spyOn(repositoriesAPI, 'getStatus').mockResolvedValue({
      data: {
        cells: [
          {
            cell: 'backup',
            status: 'completed',
            completed_at: noon(),
            age_seconds: 60,
            threshold_days: 2,
            overdue: false,
            running: false,
            source: 'archive',
          },
          {
            cell: 'check',
            status: null,
            completed_at: null,
            age_seconds: null,
            threshold_days: 30,
            overdue: true,
            running: false,
            source: null,
          },
        ],
        overdue_available: true,
      },
    } as never)
  })

  it('lists runs with what they belong to and says what is shown', async () => {
    renderWithProviders(<Activity />)
    await screen.findByTestId('run-entry')
    expect(screen.getByTestId('umbrella-band')).toHaveTextContent('Plan · Nightly')
    expect(activityAPI.list).toHaveBeenCalledWith({ limit: 50 })
    expect(screen.getByTestId('activity-summary')).toHaveTextContent(
      '1 run · across 1 repository · index runs hidden'
    )
  })

  it('passes filters into the activity API and tracks them', async () => {
    const user = userEvent.setup()
    renderWithProviders(<Activity />)
    await screen.findByTestId('run-entry')

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^type$/i }))
    await user.click(await screen.findByRole('option', { name: /^Restore Check$/i }))
    await waitFor(() =>
      expect(activityAPI.list).toHaveBeenLastCalledWith({ limit: 50, job_type: 'restore_check' })
    )
    expect(track).toHaveBeenCalledWith('Navigation', 'Filter', {
      filter_kind: 'type',
      filter_value: 'restore_check',
    })

    fireEvent.mouseDown(screen.getByRole('combobox', { name: /^status$/i }))
    await user.click(await screen.findByRole('option', { name: /^failed$/i }))
    await waitFor(() =>
      expect(activityAPI.list).toHaveBeenLastCalledWith({
        limit: 50,
        job_type: 'restore_check',
        status: 'failed',
      })
    )

    await user.click(screen.getByRole('button', { name: /^index$/i }))
    await waitFor(() =>
      expect(activityAPI.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ category: ['index'] })
      )
    )
    expect(screen.getByTestId('activity-summary')).not.toHaveTextContent('index runs hidden')
  })

  it('refreshes on demand', async () => {
    renderWithProviders(<Activity />)
    await screen.findByTestId('run-entry')
    const calls = (activityAPI.list as ReturnType<typeof vi.fn>).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: /^refresh activity$/i }))
    await waitFor(() =>
      expect((activityAPI.list as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(
        calls
      )
    )
  })

  it('pins a repository from the URL: same timeline, plus its header', async () => {
    renderWithProviders(<Activity />, { initialRoute: '/activity?repository_id=1' })
    expect(await screen.findByRole('heading', { name: 'nas' })).toBeInTheDocument()
    await waitFor(() =>
      expect(activityAPI.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ repository_id: 1 })
      )
    )
    const cells = await screen.findAllByTestId('health-cell')
    expect(cells).toHaveLength(2)
    expect(cells[1]).toHaveTextContent(/overdue/i)
    expect(screen.getByTestId('activity-summary')).not.toHaveTextContent('across')
    expect(screen.getByRole('link', { name: /all activity/i })).toHaveAttribute('href', '/activity')
    expect(await screen.findByTestId('run-entry')).toBeInTheDocument()
  })

  it('switches scope from the repository selector', async () => {
    renderWithProviders(<Activity />, { initialRoute: '/activity' })
    await screen.findByTestId('run-entry')
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /repository/i }))
    fireEvent.click(await screen.findByRole('option', { name: /nas/ }))
    await waitFor(() => expect(window.location.search).toBe('?repository_id=1'))
  })

  it('seeds the category filter from the URL and drops unknown values', async () => {
    renderWithProviders(<Activity />, {
      initialRoute: '/activity?repository_id=1&category=index&category=bogus',
    })
    await waitFor(() =>
      expect(activityAPI.list).toHaveBeenLastCalledWith(
        expect.objectContaining({ repository_id: 1, category: ['index'] })
      )
    )
    expect(screen.getByRole('button', { name: /^index$/i })).toHaveAttribute('aria-pressed', 'true')
  })

  it('lifts running work into the live strip and opens its logs', async () => {
    ;(activityAPI.list as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: [
        backup,
        {
          ...backup,
          id: 11,
          type: 'rclone_hydrate',
          kind: 'rclone_sync',
          category: 'mirror',
          trigger: 'manual',
          status: 'running',
          completed_at: null,
          repository: 'Cloud Hydrate Repo',
          progress_percent: 55,
        },
      ],
    })
    renderWithProviders(<Activity />)
    const strip = await screen.findByTestId('running-now')
    expect(strip).toHaveTextContent('Cloud Hydrate Repo')
    expect(strip).toHaveTextContent('Cloud Hydrate')
    expect(screen.getAllByTestId('run-entry')).toHaveLength(2)
    await userEvent.click(screen.getAllByRole('button', { name: /view logs/i })[0])
    expect(await screen.findByText('Log Viewer')).toBeInTheDocument()
  })
})
