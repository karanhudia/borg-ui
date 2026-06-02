import { fireEvent, screen, waitFor } from '@testing-library/react'
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
      getInfo: vi.fn(),
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
  default: () => null,
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
    onCheck,
    onJobCompleted,
  }: {
    repositories: Array<typeof mockRepository>
    onCheck: (repository: typeof mockRepository) => void
    onJobCompleted: (repositoryId: number) => void
  }) => {
    if (repositories.length === 0) {
      return <div>loading repositories</div>
    }

    return (
      <>
        <button type="button" onClick={() => onCheck(repositories[0])}>
          start check
        </button>
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
    vi.mocked(repositoriesAPI.getRepositoryCheckJobs).mockResolvedValue({
      data: {
        jobs: [
          {
            id: 23,
            repository_id: 1,
            status: 'failed',
            started_at: '2026-01-01T00:00:00Z',
            completed_at: '2026-01-01T00:00:05Z',
            error_message: 'Repository is not initialized',
            progress: 100,
            progress_message: 'Check failed',
            scheduled_check: false,
          },
        ],
      },
    } as Awaited<ReturnType<typeof repositoriesAPI.getRepositoryCheckJobs>>)
    mockCheckRepository.mockResolvedValue({ data: { job_id: 23 } })
  })

  it('announces stored error details when a manual check job fails after the spinner stops', async () => {
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

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Repository is not initialized')
      )
    })
  })
})
