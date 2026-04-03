import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import BackupJobsTable from '../BackupJobsTable'
import { QueryClient } from '@tanstack/react-query'

const { toastSuccess, toastError, buildDownloadUrlMock, repositoriesListMock } = vi.hoisted(() => ({
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  buildDownloadUrlMock: vi.fn((path: string) => `https://example.test${path}`),
  repositoriesListMock: vi.fn(),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: toastSuccess,
      error: toastError,
    },
  }
})

vi.mock('../DataTable', () => ({
  default: ({
    data,
    actions,
  }: {
    data: Array<Record<string, unknown>>
    actions?: Array<{
      label: string
      onClick: (row: Record<string, unknown>) => void
      show?: (row: Record<string, unknown>) => boolean
    }>
  }) => (
    <div>
      {data.map((row) => (
        <div key={String(row.id)}>
          <span>{String(row.id)}</span>
          {actions
            ?.filter((action) => (action.show ? action.show(row) : true))
            .map((action) => (
              <button key={`${row.id}-${action.label}`} onClick={() => action.onClick(row)}>
                {action.label}
              </button>
            ))}
        </div>
      ))}
    </div>
  ),
}))

vi.mock('../StatusBadge', () => ({
  default: ({ status }: { status: string }) => <span>{status}</span>,
}))
vi.mock('../RepositoryCell', () => ({
  default: ({ repositoryPath }: { repositoryPath: string }) => <span>{repositoryPath}</span>,
}))
vi.mock('../ErrorDetailsDialog', () => ({ default: () => null }))
vi.mock('../LogViewerDialog', () => ({ default: () => null }))
vi.mock('../LockErrorDialog', () => ({
  default: ({
    open,
    repositoryId,
    repositoryName,
    onLockBroken,
  }: {
    open: boolean
    repositoryId: number
    repositoryName: string
    onLockBroken?: () => void
  }) =>
    open ? (
      <div>
        Break lock for {repositoryName} ({repositoryId})
        <button onClick={onLockBroken}>Lock Broken</button>
      </div>
    ) : null,
}))
vi.mock('../CancelJobDialog', () => ({
  default: ({
    open,
    onConfirm,
    onClose,
    jobId,
  }: {
    open: boolean
    onConfirm: () => void
    onClose: () => void
    jobId?: number
  }) =>
    open ? (
      <div>
        <span>Cancel job {jobId}</span>
        <button onClick={onConfirm}>Confirm Cancel</button>
        <button onClick={onClose}>Close Cancel</button>
      </div>
    ) : null,
}))
vi.mock('../DeleteJobDialog', () => ({
  default: ({
    open,
    onConfirm,
    onClose,
    jobId,
  }: {
    open: boolean
    onConfirm: () => void
    onClose: () => void
    jobId?: number
  }) =>
    open ? (
      <div>
        <span>Delete job {jobId}</span>
        <button onClick={onConfirm}>Confirm Delete</button>
        <button onClick={onClose}>Close Delete</button>
      </div>
    ) : null,
}))

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    list: repositoriesListMock,
  },
}))

vi.mock('../../utils/downloadUrl', () => ({
  buildDownloadUrl: buildDownloadUrlMock,
}))

describe('BackupJobsTable action internals', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('access_token', 'token-123')
    repositoriesListMock.mockResolvedValue({
      data: {
        repositories: [
          {
            id: 77,
            name: 'Repo 77',
            path: '/backup/repo77',
            borg_version: 2,
          },
        ],
      },
    })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn(),
    } as never)
  })

  it('downloads logs through the generated activity URL when no custom callback is provided', async () => {
    const user = userEvent.setup()
    const originalCreateElement = document.createElement.bind(document)
    const anchor = originalCreateElement('a')
    const clickSpy = vi.spyOn(anchor, 'click').mockImplementation(() => {})
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tagName) => {
      if (tagName === 'a') {
        return anchor
      }
      return originalCreateElement(tagName)
    })
    const appendSpy = vi.spyOn(document.body, 'appendChild')
    const removeSpy = vi.spyOn(document.body, 'removeChild')

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 10,
            repository: '/backup/repo10',
            repository_path: '/backup/repo10',
            type: 'backup',
            status: 'completed',
            started_at: '2026-04-01T10:00:00Z',
            completed_at: '2026-04-01T10:10:00Z',
            has_logs: true,
          },
        ]}
        actions={{ downloadLogs: true }}
      />
    )

    await user.click(screen.getByRole('button', { name: /download logs/i }))

    expect(buildDownloadUrlMock).toHaveBeenCalledWith('/activity/backup/10/logs/download')
    expect(anchor.href).toBe('https://example.test/activity/backup/10/logs/download')
    expect(anchor.download).toBe('backup-10-logs.txt')
    expect(clickSpy).toHaveBeenCalled()
    expect(appendSpy).toHaveBeenCalled()
    expect(removeSpy).toHaveBeenCalled()
    expect(toastSuccess).toHaveBeenCalled()

    createElementSpy.mockRestore()
    appendSpy.mockRestore()
    removeSpy.mockRestore()
    clickSpy.mockRestore()
  })

  it('cancels running jobs through the activity API when using the built-in handler', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 20,
            repository: '/backup/repo20',
            repository_path: '/backup/repo20',
            type: 'restore',
            status: 'running',
            started_at: '2026-04-01T11:00:00Z',
          },
        ]}
        actions={{ cancel: true }}
      />
    )

    await user.click(screen.getByRole('button', { name: /^cancel$/i }))
    await user.click(screen.getByRole('button', { name: /confirm cancel/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/activity/restore/20/cancel', {
        method: 'POST',
        headers: {
          Authorization: 'Bearer token-123',
        },
      })
    })
    expect(toastSuccess).toHaveBeenCalled()
  })

  it('shows an error toast when built-in job cancellation fails', async () => {
    const user = userEvent.setup()
    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      json: vi.fn(),
    } as never)

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 21,
            repository: '/backup/repo21',
            repository_path: '/backup/repo21',
            type: 'backup',
            status: 'running',
            started_at: '2026-04-01T11:00:00Z',
          },
        ]}
        actions={{ cancel: true }}
      />
    )

    await user.click(screen.getByRole('button', { name: /^cancel$/i }))
    await user.click(screen.getByRole('button', { name: /confirm cancel/i }))

    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Failed to cancel job')
    })
  })

  it('rolls back optimistic cache updates when built-in delete fails', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false },
      },
    })
    const initialManualJobs = [
      {
        id: 40,
        repository: '/backup/repo40',
        repository_path: '/backup/repo40',
        type: 'backup',
        status: 'completed',
        started_at: '2026-04-01T10:00:00Z',
      },
      {
        id: 41,
        repository: '/backup/repo41',
        repository_path: '/backup/repo41',
        type: 'backup',
        status: 'completed',
        started_at: '2026-04-01T10:05:00Z',
      },
    ]
    const initialActivityData = {
      jobs: [
        {
          id: 40,
          repository: '/backup/repo40',
          repository_path: '/backup/repo40',
          type: 'backup',
          status: 'completed',
          started_at: '2026-04-01T10:00:00Z',
        },
      ],
    }

    queryClient.setQueryData(['backup-status-manual'], initialManualJobs)
    queryClient.setQueryData(['activity'], initialActivityData)
    vi.mocked(global.fetch).mockResolvedValue({
      ok: false,
      json: vi.fn().mockResolvedValue({ detail: 'Delete failed from API' }),
    } as never)

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 40,
            repository: '/backup/repo40',
            repository_path: '/backup/repo40',
            type: 'backup',
            status: 'completed',
            started_at: '2026-04-01T10:00:00Z',
          },
        ]}
        canDeleteJobs={true}
        canBreakLocks={true}
        actions={{ delete: true }}
      />,
      { queryClient }
    )

    await user.click(screen.getByRole('button', { name: /^delete$/i }))
    await user.click(screen.getByRole('button', { name: /confirm delete/i }))

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith('/api/activity/backup/40', {
        method: 'DELETE',
        headers: {
          Authorization: 'Bearer token-123',
        },
      })
    })
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Delete failed from API')
    })
    expect(queryClient.getQueryData(['backup-status-manual'])).toEqual(initialManualJobs)
    expect(queryClient.getQueryData(['activity'])).toEqual(initialActivityData)
  })

  it('resolves break-lock repository details from the fetched repository list', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 30,
            repository: '/backup/repo77',
            repository_path: '/backup/repo77',
            type: 'backup',
            status: 'failed',
            started_at: '2026-04-01T12:00:00Z',
            completed_at: '2026-04-01T12:05:00Z',
            error_message: 'LOCK_ERROR::/backup/repo77\n[Exit Code 73] lock failure',
          },
        ]}
        canDeleteJobs={true}
        canBreakLocks={true}
        actions={{ breakLock: true }}
      />
    )

    await user.click(await screen.findByRole('button', { name: /break lock/i }))

    expect(await screen.findByText(/Break lock for Repo 77 \(77\)/i)).toBeInTheDocument()
  })

  it('shows an error when a lock error references a repository that is not in the fetched list', async () => {
    const user = userEvent.setup()
    repositoriesListMock.mockResolvedValue({
      data: {
        repositories: [],
      },
    })

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 31,
            repository: '/backup/missing',
            repository_path: '/backup/missing',
            type: 'backup',
            status: 'failed',
            started_at: '2026-04-01T12:00:00Z',
            completed_at: '2026-04-01T12:05:00Z',
            error_message: 'LOCK_ERROR::/backup/missing\n[Exit Code 73] lock failure',
          },
        ]}
        canDeleteJobs={true}
        canBreakLocks={true}
        actions={{ breakLock: true }}
      />
    )

    await user.click(await screen.findByRole('button', { name: /break lock/i }))

    expect(toastError).toHaveBeenCalledWith('Repository not found')
  })

  it('invalidates backup-related queries after a lock is marked as broken', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false },
      },
    })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    renderWithProviders(
      <BackupJobsTable
        jobs={[
          {
            id: 32,
            repository: '/backup/repo77',
            repository_path: '/backup/repo77',
            type: 'backup',
            status: 'failed',
            started_at: '2026-04-01T12:00:00Z',
            completed_at: '2026-04-01T12:05:00Z',
            error_message: 'LOCK_ERROR::/backup/repo77\n[Exit Code 73] lock failure',
          },
        ]}
        canDeleteJobs={true}
        canBreakLocks={true}
        actions={{ breakLock: true }}
      />,
      { queryClient }
    )

    await user.click(await screen.findByRole('button', { name: /break lock/i }))
    await user.click(await screen.findByRole('button', { name: /lock broken/i }))

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['activity'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['backup-status'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['backup-status-manual'] })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['backup-status-scheduled'] })
  })
})
