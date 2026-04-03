/**
 * Regression tests for archive deletion cache invalidation (issue #352)
 *
 * After deleting an archive, the UI was showing stale repository statistics
 * because `repository-info` was not being invalidated alongside `repository-archives`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient } from '@tanstack/react-query'
import { renderWithProviders } from '../../test/test-utils'
import Archives from '../Archives'
import * as apiModule from '../../services/api'

// Mock heavy child components to keep the test focused on deletion logic
vi.mock('../../components/RepositorySelectorCard', () => ({
  default: ({ onChange }: { onChange: (id: number) => void }) => (
    <button onClick={() => onChange(1)}>Select Repo</button>
  ),
}))
vi.mock('../../components/RepositoryStatsGrid', () => ({
  default: () => <div data-testid="stats-grid" />,
}))
vi.mock('../../components/ArchivesList', () => ({
  default: ({ onDeleteArchive }: { onDeleteArchive: (name: string) => void }) => (
    <button data-testid="delete-archive-btn" onClick={() => onDeleteArchive('backup-2024-01-15')}>
      Trigger Delete
    </button>
  ),
}))
vi.mock('../../components/LastRestoreSection', () => ({ default: () => null }))
vi.mock('../../components/ArchiveContentsDialog', () => ({ default: () => null }))
vi.mock('../../components/MountArchiveDialog', () => ({ default: () => null }))
vi.mock('../../components/LockErrorDialog', () => ({ default: () => null }))
vi.mock('../../components/RestoreWizard', () => ({ default: () => null }))

vi.mock('../../services/api', () => ({
  archivesAPI: { deleteArchive: vi.fn(), downloadFile: vi.fn() },
  repositoriesAPI: {
    getRepositories: vi.fn(),
    listRepositoryArchives: vi.fn(),
    getRepositoryInfo: vi.fn(),
  },
  mountsAPI: { mountBorgArchive: vi.fn() },
  restoreAPI: { getRestoreJobs: vi.fn() },
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    useLocation: () => ({ state: null, pathname: '/archives' }),
  }
})

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackArchive: vi.fn(),
    EventAction: { DELETE: 'delete', FILTER: 'filter' },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      role: 'admin',
      created_at: '2024-01-01T00:00:00Z',
      global_permissions: ['repositories.manage_all'],
    },
    hasGlobalPermission: (permission: string) => permission === 'repositories.manage_all',
  }),
}))

const mockRepository = {
  id: 1,
  name: 'My Backups',
  path: '/backup/repo',
  location: '/backup/repo',
  archive_count: 1,
  last_modified: '2024-01-15T10:00:00Z',
  size: 1024 * 100,
}

describe('Archives page — delete cache invalidation (regression #352)', () => {
  let queryClient: QueryClient
  let setTimeoutCallback: (() => void) | null = null

  beforeEach(() => {
    setTimeoutCallback = null

    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false },
      },
    })

    // Seed query cache
    queryClient.setQueryData(['repositories'], { data: { repositories: [mockRepository] } })
    queryClient.setQueryData(['repository-archives', 1], { data: { archives: [] } })
    queryClient.setQueryData(['repository-info', 1], { data: { info: {} } })
    queryClient.setQueryData(['restore-jobs'], { data: { jobs: [] } })

    vi.mocked(apiModule.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [mockRepository] },
    } as never)
    vi.mocked(apiModule.repositoriesAPI.listRepositoryArchives).mockResolvedValue({
      data: { archives: [] },
    } as never)
    vi.mocked(apiModule.repositoriesAPI.getRepositoryInfo).mockResolvedValue({
      data: { info: {} },
    } as never)
    vi.mocked(apiModule.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: { jobs: [] },
    } as never)
    vi.mocked(apiModule.archivesAPI.deleteArchive).mockResolvedValue({
      data: { job_id: 'job-123' },
    } as never)

    // Intercept only the 2000ms setTimeout the component uses for invalidation,
    // letting all other setTimeout calls (react-query internals etc.) pass through
    const realSetTimeout = global.setTimeout
    vi.spyOn(global, 'setTimeout').mockImplementation(
      (fn: Parameters<typeof setTimeout>[0], delay?: number, ...args: unknown[]) => {
        if (delay === 2000) {
          setTimeoutCallback = fn as () => void
          return 999 as unknown as ReturnType<typeof setTimeout>
        }
        return realSetTimeout(fn, delay, ...args) as unknown as ReturnType<typeof setTimeout>
      }
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('invalidates both repository-archives AND repository-info after successful deletion', async () => {
    const user = userEvent.setup()
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    renderWithProviders(<Archives />, { queryClient })

    // Select the repository to enable the ArchivesList
    await user.click(screen.getByText('Select Repo'))

    // ArchivesList appears when a repository is selected
    await waitFor(() => {
      expect(screen.getByTestId('delete-archive-btn')).toBeInTheDocument()
    })

    // Trigger deletion via the mocked ArchivesList
    await user.click(screen.getByTestId('delete-archive-btn'))

    // DeleteArchiveDialog opens — confirm
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Delete Archive$/i })).toBeInTheDocument()
    })
    await user.click(screen.getByRole('button', { name: /^Delete Archive$/i }))

    // Verify the API was called
    await waitFor(() => {
      expect(apiModule.archivesAPI.deleteArchive).toHaveBeenCalledWith(
        '/backup/repo',
        'backup-2024-01-15'
      )
    })

    // Simulate the 2000ms setTimeout firing by calling the captured callback
    expect(setTimeoutCallback).not.toBeNull()
    await act(async () => {
      setTimeoutCallback!()
    })

    // Both queries must be invalidated — this is the regression check for #352
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['repository-archives', 1] })
    )
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['repository-info', 1] })
    )
  })
})
