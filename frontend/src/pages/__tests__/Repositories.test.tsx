import { fireEvent, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { renderWithProviders } from '../../test/test-utils'
import Repositories from '../Repositories'
import { backupPlansAPI, repositoriesAPI } from '../../services/api'
import { toast } from 'react-hot-toast'

const { mockCheckRepository } = vi.hoisted(() => ({
  mockCheckRepository: vi.fn(),
}))

const mockRepository = {
  id: 1,
  name: 'Broken Repo',
  path: '/repo/broken',
  encryption: 'repokey',
  compression: 'lz4',
  source_directories: [],
  exclude_patterns: [],
  last_backup: null,
  last_check: null,
  last_compact: null,
  total_size: null,
  archive_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: null,
  mode: 'full',
}

const buildCheckJob = (
  overrides: Partial<{
    id: number
    repository_id: number
    status: string
    started_at: string
    completed_at: string
    error_message: string | null
    progress: number
    progress_message: string
    scheduled_check: boolean
  }> = {}
) => ({
  id: 23,
  repository_id: 1,
  status: 'failed',
  started_at: '2026-01-01T00:00:00Z',
  completed_at: '2026-01-01T00:00:05Z',
  error_message: 'Repository is not initialized',
  progress: 100,
  progress_message: 'Check failed',
  scheduled_check: false,
  ...overrides,
})

const mockLatestCheckJob = (job: ReturnType<typeof buildCheckJob>) => {
  vi.mocked(repositoriesAPI.getRepositoryCheckJobs).mockResolvedValue({
    data: { jobs: [job] },
  } as Awaited<ReturnType<typeof repositoriesAPI.getRepositoryCheckJobs>>)
}

vi.mock('react-hot-toast', () => {
  const toastMock = Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
  })

  return {
    toast: toastMock,
    Toaster: () => null,
  }
})

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: () => true,
  }),
}))

vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    canDo: () => true,
  }),
}))

vi.mock('../../hooks/useLockBreakPermissions', () => ({
  useLockBreakPermissions: () => ({
    canBreakLock: () => true,
    lockBreakingEnabled: true,
  }),
}))

vi.mock('../../context/AppContext', () => ({
  useAppState: () => ({
    refetch: vi.fn(),
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackMaintenance: vi.fn(),
    trackRepository: vi.fn(),
    EventAction: {
      START: 'Start',
      COMPLETE: 'Complete',
      FAIL: 'Fail',
      SEARCH: 'Search',
      FILTER: 'Filter',
      DELETE: 'Delete',
    },
  }),
}))

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    getRepositories: vi.fn(),
    getRepositoryCheckJobs: vi.fn(),
    permanentlyDeleteRepository: vi.fn(),
  },
  backupPlansAPI: {
    list: vi.fn(),
    get: vi.fn(),
    createFromRepository: vi.fn(),
  },
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: vi.fn(function BorgApiClientMock() {
    return {
      checkRepository: mockCheckRepository,
      getInfo: vi.fn().mockResolvedValue({ data: { info: null } }),
    }
  }),
}))

vi.mock('../../components/CheckWarningDialog', () => ({
  default: ({
    open,
    onConfirm,
  }: {
    open: boolean
    onConfirm: (options: { maxDuration: number; checkExtraFlags: string }) => void
  }) =>
    open ? (
      <button type="button" onClick={() => onConfirm({ maxDuration: 3600, checkExtraFlags: '' })}>
        confirm check
      </button>
    ) : null,
}))

vi.mock('../../components/CompactWarningDialog', () => ({
  default: () => null,
}))

vi.mock('../../components/RepositoryWizard', () => ({
  default: () => null,
}))

vi.mock('../../components/PruneRepositoryDialog', () => ({
  default: () => null,
}))

vi.mock('../../components/RepositoryWipeDialog', () => ({
  default: () => null,
}))

vi.mock('../../components/RepositoryInfoDialog', () => ({
  default: ({
    open,
    repository,
    onRunRecoveryCheck,
    canRunRecoveryCheck,
  }: {
    open: boolean
    repository: typeof mockRepository | null
    onRunRecoveryCheck?: (repository: typeof mockRepository) => void
    canRunRecoveryCheck?: boolean
  }) =>
    open && repository ? (
      <div>
        <span>{repository.name} info dialog</span>
        {onRunRecoveryCheck ? (
          <button
            type="button"
            disabled={!canRunRecoveryCheck}
            onClick={() => onRunRecoveryCheck(repository)}
          >
            Run guided check
          </button>
        ) : null}
      </div>
    ) : null,
}))

vi.mock('../repositories-page/CreateBackupPlanDialog', () => ({
  CreateBackupPlanDialog: () => null,
}))

vi.mock('../repositories-page/RepositoriesHeader', () => ({
  RepositoriesHeader: () => null,
}))

vi.mock('../repositories-page/RepositoriesToolbar', () => ({
  RepositoriesToolbar: () => null,
}))

vi.mock('../repositories-page/RepositoryGroups', () => ({
  RepositoryGroups: ({
    repositories,
    canBreakLock,
    onCheck,
    onViewInfo,
    onBreakLock,
    onPermanentDelete,
    canPermanentDeleteRepository,
    onJobCompleted,
  }: {
    repositories: Array<typeof mockRepository>
    canBreakLock: (repository: typeof mockRepository) => boolean
    canPermanentDeleteRepository: (repository: typeof mockRepository) => boolean
    onCheck: (repository: typeof mockRepository) => void
    onViewInfo: (repository: typeof mockRepository) => void
    onBreakLock: (repository: typeof mockRepository) => void
    onPermanentDelete: (repository: typeof mockRepository) => void
    onJobCompleted: (repositoryId: number) => void
  }) => {
    if (repositories.length === 0) {
      return <div>loading repositories</div>
    }

    return (
      <>
        <span>{repositories[0].name}</span>
        <button type="button" onClick={() => onCheck(repositories[0])}>
          start check
        </button>
        <button type="button" onClick={() => onViewInfo(repositories[0])}>
          view info
        </button>
        {canBreakLock(repositories[0]) ? (
          <button type="button" onClick={() => onBreakLock(repositories[0])}>
            break lock
          </button>
        ) : null}
        {canPermanentDeleteRepository(repositories[0]) ? (
          <button type="button" onClick={() => onPermanentDelete(repositories[0])}>
            permanent delete
          </button>
        ) : null}
        <button type="button" onClick={() => onJobCompleted(1)}>
          complete check
        </button>
      </>
    )
  },
}))

describe('Repositories', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [mockRepository] },
    } as Awaited<ReturnType<typeof repositoriesAPI.getRepositories>>)
    vi.mocked(backupPlansAPI.list).mockResolvedValue({
      data: { backup_plans: [] },
    } as Awaited<ReturnType<typeof backupPlansAPI.list>>)
    mockLatestCheckJob(buildCheckJob())
    mockCheckRepository.mockResolvedValue({ data: { job_id: 23 } })
    vi.mocked(repositoriesAPI.permanentlyDeleteRepository).mockResolvedValue({
      data: { success: true },
    } as Awaited<ReturnType<typeof repositoriesAPI.permanentlyDeleteRepository>>)
  })

  async function runManualCheckToCompletion() {
    renderWithProviders(<Repositories />)

    fireEvent.click(await screen.findByRole('button', { name: 'start check' }))
    fireEvent.click(screen.getByRole('button', { name: 'confirm check' }))

    await waitFor(() => {
      expect(mockCheckRepository).toHaveBeenCalledWith({
        maxDuration: 3600,
        checkExtraFlags: '',
      })
    })

    fireEvent.click(screen.getByRole('button', { name: 'complete check' }))
  }

  it('announces stored error details when a manual check job fails after the spinner stops', async () => {
    await runManualCheckToCompletion()

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Repository is not initialized')
      )
    })
  })

  it('announces success when a manual check job completes cleanly', async () => {
    mockLatestCheckJob(buildCheckJob({ status: 'completed', error_message: null }))

    await runManualCheckToCompletion()

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Check completed')
    })
  })

  it('announces warnings when a manual check job completes with warnings', async () => {
    mockLatestCheckJob(buildCheckJob({ status: 'completed_with_warnings', error_message: null }))

    await runManualCheckToCompletion()

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith('Check completed with warnings', { icon: '!' })
    })
  })

  it('announces a fallback error when a failed manual check has no stored message', async () => {
    mockLatestCheckJob(buildCheckJob({ error_message: null }))

    await runManualCheckToCompletion()

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Check failed: Check failed')
    })
  })

  it('still announces completion when the check job summary lookup fails', async () => {
    vi.mocked(repositoriesAPI.getRepositoryCheckJobs).mockRejectedValue(new Error('lookup failed'))

    await runManualCheckToCompletion()

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Check completed')
    })
  })

  it('opens the existing check confirmation from the repository info recovery action', async () => {
    renderWithProviders(<Repositories />)

    fireEvent.click(await screen.findByRole('button', { name: 'view info' }))
    expect(await screen.findByText('Broken Repo info dialog')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Run guided check' }))

    expect(screen.getByRole('button', { name: 'confirm check' })).toBeInTheDocument()
  })

  it('opens the lock dialog from the repository break lock action', async () => {
    renderWithProviders(<Repositories />)

    fireEvent.click(await screen.findByRole('button', { name: 'break lock' }))

    expect(await screen.findByRole('heading', { name: 'Repository Locked' })).toBeInTheDocument()
    expect(
      screen.getByText('Broken Repo is locked by another process or has a stale lock.')
    ).toBeInTheDocument()
  })

  it('permanently deletes a repository after typed confirmation and removes it from the list', async () => {
    const user = userEvent.setup()
    vi.mocked(repositoriesAPI.getRepositories)
      .mockResolvedValueOnce({
        data: { repositories: [mockRepository] },
      } as Awaited<ReturnType<typeof repositoriesAPI.getRepositories>>)
      .mockResolvedValue({
        data: { repositories: [] },
      } as Awaited<ReturnType<typeof repositoriesAPI.getRepositories>>)
    renderWithProviders(<Repositories />)

    expect(await screen.findByText('Broken Repo')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'permanent delete' }))

    expect(
      await screen.findByRole('heading', { name: 'Permanently delete repository files' })
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Permanently delete files' })).toBeDisabled()

    await user.type(screen.getByLabelText('Type repository name to confirm'), 'Broken Repo')
    await user.click(screen.getByRole('button', { name: 'Permanently delete files' }))

    await waitFor(() => {
      expect(repositoriesAPI.permanentlyDeleteRepository).toHaveBeenCalledWith(1, {
        confirmation_phrase: 'Broken Repo',
        understood: true,
      })
    })
    await waitFor(() => {
      expect(screen.queryByText('Broken Repo')).not.toBeInTheDocument()
    })
    expect(toast.success).toHaveBeenCalledWith('Repository permanently deleted')
  })

  it('keeps the repository visible when permanent deletion fails', async () => {
    const user = userEvent.setup()
    vi.mocked(repositoriesAPI.permanentlyDeleteRepository).mockRejectedValue({
      response: { data: { detail: 'permission denied' } },
    })
    renderWithProviders(<Repositories />)

    expect(await screen.findByText('Broken Repo')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'permanent delete' }))
    await user.type(screen.getByLabelText('Type repository name to confirm'), 'Broken Repo')
    await user.click(screen.getByRole('button', { name: 'Permanently delete files' }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('permission denied')
    })
    expect(screen.getByText('Broken Repo')).toBeInTheDocument()
  })
})
