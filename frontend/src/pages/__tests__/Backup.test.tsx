import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Backup from '../Backup'

const runBackupMock = vi.fn()

const { trackBackup, toastSuccess, toastError } = vi.hoisted(() => ({
  trackBackup: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}))

const { getManualJobsMock, backupJobsTableMock } = vi.hoisted(() => ({
  getManualJobsMock: vi.fn(),
  backupJobsTableMock: vi.fn(),
}))

let locationState: Record<string, unknown> | null = null
let canManageAll = false
let canDoBackup = true
let repositoriesPayload: Array<Record<string, unknown>> = []
let manualJobsPayload: Array<Record<string, unknown>> = []

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackBackup,
    EventAction: {
      START: 'Start',
      STOP: 'Stop',
      FILTER: 'Filter',
    },
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: (permission: string) =>
      permission === 'repositories.manage_all' ? canManageAll : false,
  }),
}))

vi.mock('../../hooks/usePermissions', () => ({
  usePermissions: () => ({
    canDo: () => canDoBackup,
  }),
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

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useLocation: () => ({ state: locationState }),
  }
})

vi.mock('../../components/RepoSelect', () => ({
  default: ({
    repositories,
    value,
    onChange,
  }: {
    repositories: Array<{ id: number; path: string; name: string }>
    value: string
    onChange: (value: string) => void
  }) => (
    <div>
      <div data-testid="selected-repository">{value || 'none'}</div>
      {repositories.map((repo) => (
        <button key={repo.id} onClick={() => onChange(repo.path)}>
          choose {repo.name}
        </button>
      ))}
    </div>
  ),
}))

vi.mock('../../components/BackupJobsTable', () => ({
  default: (props: unknown) => {
    backupJobsTableMock(props)
    return <div>backup jobs table</div>
  },
}))

vi.mock('../../components/LogViewerDialog', () => ({
  default: () => null,
}))

vi.mock('../../services/api', () => ({
  backupAPI: {
    getManualJobs: getManualJobsMock.mockImplementation(() =>
      Promise.resolve({
        data: {
          jobs: manualJobsPayload,
        },
      })
    ),
    cancelJob: vi.fn(() => Promise.resolve({ data: {} })),
  },
  repositoriesAPI: {
    getRepositories: vi.fn(() =>
      Promise.resolve({
        data: {
          repositories: repositoriesPayload,
        },
      })
    ),
  },
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: vi.fn(function MockBorgApiClient() {
    return {
      runBackup: runBackupMock,
    }
  }),
}))

describe('Backup page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    locationState = null
    canManageAll = false
    canDoBackup = true
    runBackupMock.mockResolvedValue({ data: {} })
    repositoriesPayload = [
      {
        id: 1,
        name: 'Primary Repo',
        path: '/repos/primary',
        compression: 'zstd',
        exclude_patterns: ['*.tmp'],
        source_directories: ['/data'],
        mode: 'full',
      },
      {
        id: 2,
        name: 'Observe Repo',
        path: '/repos/observe',
        compression: 'zstd',
        exclude_patterns: [],
        source_directories: ['/observe'],
        mode: 'observe',
      },
    ]
    manualJobsPayload = []
  })

  it('preselects the repository from navigation state and starts a backup with that payload', async () => {
    const user = userEvent.setup()
    locationState = { repositoryPath: '/repos/primary' }

    renderWithProviders(<Backup />)

    expect(await screen.findByTestId('selected-repository')).toHaveTextContent('/repos/primary')

    await user.click(screen.getByRole('button', { name: /start backup/i }))

    await waitFor(() => {
      expect(runBackupMock).toHaveBeenCalledTimes(1)
    })
    expect(toastSuccess).toHaveBeenCalledWith('Backup started successfully!')
    expect(trackBackup).toHaveBeenCalledWith(
      'Start',
      undefined,
      expect.objectContaining({
        id: 1,
        path: '/repos/primary',
      })
    )
  })

  it('uses the version-aware BorgApiClient when starting a Borg 2 backup', async () => {
    const user = userEvent.setup()
    locationState = { repositoryPath: '/repos/primary' }
    repositoriesPayload = [
      {
        id: 1,
        name: 'Primary Repo',
        path: '/repos/primary',
        compression: 'zstd',
        exclude_patterns: ['*.tmp'],
        source_directories: ['/data'],
        mode: 'full',
        borg_version: 2,
      },
    ]

    renderWithProviders(<Backup />)

    await user.click(await screen.findByRole('button', { name: /start backup/i }))

    await waitFor(() => {
      expect(runBackupMock).toHaveBeenCalledTimes(1)
    })
  })

  it('filters out observe-only repositories from manual backup selection', async () => {
    renderWithProviders(<Backup />)

    expect(await screen.findByText('choose Primary Repo')).toBeInTheDocument()
    expect(screen.queryByText('choose Observe Repo')).not.toBeInTheDocument()
  })

  it('only loads recent jobs for the selected repository', async () => {
    const user = userEvent.setup()
    manualJobsPayload = [
      {
        id: 42,
        repository: '/repos/primary',
        status: 'completed',
      },
    ]

    renderWithProviders(<Backup />)

    await waitFor(() => {
      expect(getManualJobsMock).not.toHaveBeenCalled()
    })

    await user.click(await screen.findByRole('button', { name: /choose primary repo/i }))

    await waitFor(() => {
      expect(getManualJobsMock).toHaveBeenCalledWith('/repos/primary')
    })

    expect(backupJobsTableMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        jobs: manualJobsPayload,
      })
    )
  })

  it('labels the history section as recent manual jobs', async () => {
    renderWithProviders(<Backup />)

    expect(await screen.findByText('Recent Manual Jobs')).toBeInTheDocument()
    expect(
      screen.getByText('History of manual backup operations for the selected repository')
    ).toBeInTheDocument()
  })

  it('tracks repository selection and hides manual backup choices when backup permission is missing', async () => {
    const user = userEvent.setup()
    const { unmount } = renderWithProviders(<Backup />)

    await user.click(await screen.findByRole('button', { name: /choose primary repo/i }))

    expect(trackBackup).toHaveBeenCalledWith(
      'Filter',
      undefined,
      expect.objectContaining({
        id: 1,
        path: '/repos/primary',
      })
    )

    canDoBackup = false
    unmount()
    renderWithProviders(<Backup />)

    expect(screen.queryByRole('button', { name: /choose primary repo/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start backup/i })).toBeDisabled()
  })

  it('shows the generated borg command preview for the selected repository', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Backup />)

    await user.click(await screen.findByRole('button', { name: /choose primary repo/i }))

    expect(await screen.findByText(/borg create/i)).toBeInTheDocument()
    expect(screen.getByText(/\/repos\/primary::manual-backup-\{now\}/i)).toBeInTheDocument()
    expect(screen.getByText(/--exclude '\*\.tmp'/i)).toBeInTheDocument()
    expect(screen.getByText(/\/data/i)).toBeInTheDocument()
  })
})
