import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fireEvent,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
  within,
} from '../../test/test-utils'
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
    // Rows say how they went with a coloured dot, so the page says once
    // what the colours mean.
    const legend = screen.getByTestId('activity-legend')
    expect(legend).toHaveTextContent('Completed')
    expect(legend).toHaveTextContent('Failed')
    expect(legend).toHaveTextContent('Warnings')
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

  describe('deleting a row', () => {
    // A full first page, so the feed offers a second one and stops polling
    // once it is loaded.
    const firstPage = Array.from({ length: 50 }, (_, index) => ({
      ...backup,
      id: 100 + index,
      trigger: 'manual',
      backup_plan_name: null,
      repository: `repo-${100 + index}`,
      sort_at: new Date(Date.UTC(2026, 8, 20, 12, 0, 50 - index)).toISOString(),
    }))
    const doomed = {
      ...firstPage[0],
      id: 7,
      repository: 'doomed-repo',
      sort_at: '2026-09-19T12:00:00+00:00',
    }
    const keeper = {
      ...firstPage[0],
      id: 8,
      repository: 'kept-repo',
      sort_at: '2026-09-19T11:00:00+00:00',
    }

    // Only a refetch serves this row: once it shows, the refetch has landed.
    const fresh = {
      ...firstPage[0],
      id: 9,
      repository: 'fresh-repo',
      sort_at: '2026-09-19T10:00:00+00:00',
    }

    const serveFeed = (secondPage: unknown[]) =>
      (activityAPI.list as ReturnType<typeof vi.fn>).mockImplementation(
        async (params: { before?: string }) => ({
          data: params.before ? secondPage : firstPage,
        })
      )

    const listMock = () => activityAPI.list as ReturnType<typeof vi.fn>

    // Resolves or rejects only when the test says so.
    const deferred = <T,>() => {
      let resolve: (value: T) => void = () => {}
      let reject: (error: Error) => void = () => {}
      const promise = new Promise<T>((res, rej) => {
        resolve = res
        reject = rej
      })
      return { promise, resolve, reject }
    }

    const loadSecondPage = async () => {
      const user = userEvent.setup()
      renderWithProviders(<Activity />)
      await screen.findByText('repo-100')
      await user.click(screen.getByRole('button', { name: /^load more$/i }))
      await screen.findByText('doomed-repo')
      return user
    }

    const confirmDelete = async (
      user: ReturnType<typeof userEvent.setup>,
      repository = 'doomed-repo'
    ) => {
      const entry = screen
        .getAllByTestId('run-entry')
        .find((row) => row.textContent?.includes(repository))!
      await user.click(within(entry).getByRole('button', { name: /^delete$/i }))
      await user.click(await screen.findByRole('button', { name: /^delete permanently$/i }))
      await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    }

    it('drops the row from a later page at once and refetches the feed', async () => {
      serveFeed([doomed, keeper])
      const request = deferred<unknown>()
      vi.spyOn(activityAPI, 'deleteJob').mockReturnValue(request.promise as never)

      await confirmDelete(await loadSecondPage())

      expect(activityAPI.deleteJob).toHaveBeenCalledWith('backup', 7)
      // Gone while the request is still out, from the page's own query.
      await waitFor(() => expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument())
      expect(screen.getByText('kept-repo')).toBeInTheDocument()
      expect(screen.getByText('repo-100')).toBeInTheDocument()

      // Once the server confirms, the feed is fetched again: polling is off
      // with two pages loaded, so nothing else would.
      serveFeed([keeper, fresh])
      request.resolve({ data: {} })
      expect(await screen.findByText('fresh-repo')).toBeInTheDocument()
      expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument()
      expect(screen.getByText('kept-repo')).toBeInTheDocument()
    })

    it('refetches only once the last of several deletes has settled', async () => {
      serveFeed([doomed, keeper])
      const first = deferred<unknown>()
      const second = deferred<unknown>()
      vi.spyOn(activityAPI, 'deleteJob')
        .mockReturnValueOnce(first.promise as never)
        .mockReturnValueOnce(second.promise as never)

      const user = await loadSecondPage()
      await confirmDelete(user, 'doomed-repo')
      await waitFor(() => expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument())
      await confirmDelete(user, 'kept-repo')
      await waitFor(() => expect(screen.queryByText('kept-repo')).not.toBeInTheDocument())

      // The server has dropped the first row only; a refetch now would put
      // the second one back while its delete is still out.
      serveFeed([keeper])
      const calls = listMock().mock.calls.length
      first.resolve({ data: {} })
      await new Promise((resolve) => setTimeout(resolve, 100))
      expect(listMock().mock.calls.length).toBe(calls)
      expect(screen.queryByText('kept-repo')).not.toBeInTheDocument()

      serveFeed([fresh])
      second.resolve({ data: {} })
      expect(await screen.findByText('fresh-repo')).toBeInTheDocument()
      expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument()
      expect(screen.queryByText('kept-repo')).not.toBeInTheDocument()
    })

    it('does not let a refresh already under way bring the row back', async () => {
      serveFeed([doomed, keeper])
      vi.spyOn(activityAPI, 'deleteJob').mockReturnValue(new Promise(() => {}) as never)
      const user = await loadSecondPage()

      // A refresh that left before the delete answers with the row still in it.
      const stale = deferred<void>()
      const staleAnswered = deferred<void>()
      listMock().mockImplementation(async (params: { before?: string }) => {
        await stale.promise
        staleAnswered.resolve()
        return { data: params.before ? [doomed, keeper] : firstPage }
      })
      const calls = listMock().mock.calls.length
      await user.click(screen.getByRole('button', { name: /^refresh activity$/i }))
      await waitFor(() => expect(listMock().mock.calls.length).toBeGreaterThan(calls))
      await confirmDelete(user)
      await waitFor(() => expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument())

      // The cancelled refresh has no result to wait for: give the answer
      // time to be applied, which it would be had it not been cancelled.
      stale.resolve()
      await staleAnswered.promise
      await new Promise((resolve) => setTimeout(resolve, 50))
      expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument()
    })

    // Two deletes out at once, the refetch that follows them held back, so
    // what the page shows is the rollback alone.
    const deleteBoth = async () => {
      serveFeed([doomed, keeper])
      const first = deferred<unknown>()
      const second = deferred<unknown>()
      vi.spyOn(activityAPI, 'deleteJob')
        .mockReturnValueOnce(first.promise as never)
        .mockReturnValueOnce(second.promise as never)
      const user = await loadSecondPage()
      await confirmDelete(user, 'doomed-repo')
      await confirmDelete(user, 'kept-repo')
      await waitFor(() => expect(screen.queryByText('kept-repo')).not.toBeInTheDocument())
      expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument()
      listMock().mockReturnValue(new Promise(() => {}))
      return { first, second }
    }

    it('puts back only the failed row while another delete is out', async () => {
      const { first, second } = await deleteBoth()

      first.reject(new Error('job not found'))
      expect(await screen.findByText('doomed-repo')).toBeInTheDocument()
      expect(screen.queryByText('kept-repo')).not.toBeInTheDocument()

      second.reject(new Error('job not found'))
      expect(await screen.findByText('kept-repo')).toBeInTheDocument()
      expect(screen.getByText('doomed-repo')).toBeInTheDocument()
    })

    it('keeps a row deleted meanwhile out when an earlier delete fails', async () => {
      const { first, second } = await deleteBoth()

      second.resolve({ data: {} })
      await waitFor(() => expect(activityAPI.deleteJob).toHaveBeenCalledTimes(2))
      first.reject(new Error('job not found'))
      expect(await screen.findByText('doomed-repo')).toBeInTheDocument()
      expect(screen.queryByText('kept-repo')).not.toBeInTheDocument()
    })

    it('puts the row back when the delete fails', async () => {
      serveFeed([doomed, keeper])
      const request = deferred<unknown>()
      vi.spyOn(activityAPI, 'deleteJob').mockReturnValue(request.promise as never)

      await confirmDelete(await loadSecondPage())
      await waitFor(() => expect(screen.queryByText('doomed-repo')).not.toBeInTheDocument())

      // Hold the refetch that follows, so only the rollback can restore it.
      listMock().mockReturnValue(new Promise(() => {}))
      request.reject(new Error('job not found'))
      expect(await screen.findByText('doomed-repo')).toBeInTheDocument()
      expect(screen.getByText('kept-repo')).toBeInTheDocument()
    })
  })
})
