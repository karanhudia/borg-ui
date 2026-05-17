import { beforeEach, describe, expect, it, vi } from 'vitest'
import { within } from '@testing-library/react'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Backup from '../Backup'

const runBackupMock = vi.fn()

const { trackBackup, toastSuccess, toastError, navigateMock } = vi.hoisted(() => ({
  trackBackup: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  navigateMock: vi.fn(),
}))

const {
  getManualJobsMock,
  backupJobsTableMock,
  backupPlansListMock,
  backupPlansListRunsMock,
  backupPlansRunMock,
  backupPlansCancelRunMock,
} = vi.hoisted(() => ({
  getManualJobsMock: vi.fn(),
  backupJobsTableMock: vi.fn(),
  backupPlansListMock: vi.fn(),
  backupPlansListRunsMock: vi.fn(),
  backupPlansRunMock: vi.fn(),
  backupPlansCancelRunMock: vi.fn(),
}))

let locationState: Record<string, unknown> | null = null
let canManageAll = false
let canDoBackup = true
let repositoriesPayload: Array<Record<string, unknown>> = []
let manualJobsPayload: Array<Record<string, unknown>> = []
let backupPlansPayload: Array<Record<string, unknown>> = []
let backupPlanRunsPayload: Array<Record<string, unknown>> = []

async function openLegacyBackupTab(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole('tab', { name: /legacy backup/i }))
}

async function selectBackupPlan(user: ReturnType<typeof userEvent.setup>, name: RegExp | string) {
  await user.click(await screen.findByRole('combobox', { name: /backup plan/i }))
  await user.click(await screen.findByRole('option', { name }))
}

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
    useNavigate: () => navigateMock,
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
  backupPlansAPI: {
    list: backupPlansListMock.mockImplementation(() =>
      Promise.resolve({
        data: {
          backup_plans: backupPlansPayload,
        },
      })
    ),
    run: backupPlansRunMock.mockImplementation(() =>
      Promise.resolve({
        data: {
          id: 99,
          backup_plan_id: 7,
          trigger: 'manual',
          status: 'pending',
          repositories: [],
        },
      })
    ),
    listRuns: backupPlansListRunsMock.mockImplementation(() =>
      Promise.resolve({
        data: {
          runs: backupPlanRunsPayload,
        },
      })
    ),
    cancelRun: backupPlansCancelRunMock.mockImplementation(() => Promise.resolve({ data: {} })),
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
    backupPlansRunMock.mockResolvedValue({
      data: {
        id: 99,
        backup_plan_id: 7,
        trigger: 'manual',
        status: 'pending',
        repositories: [],
      },
    })
    backupPlansPayload = []
    backupPlanRunsPayload = []
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

  it('defaults to the backup plans tab and keeps legacy backup separate', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Backup />)

    expect(await screen.findByRole('tab', { name: /backup plans/i })).toHaveAttribute(
      'aria-selected',
      'true'
    )
    expect(await screen.findByRole('button', { name: /create backup plan/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /choose primary repo/i })).not.toBeInTheDocument()

    await openLegacyBackupTab(user)

    expect(screen.getByRole('tab', { name: /legacy backup/i })).toHaveAttribute(
      'aria-selected',
      'true'
    )
    expect(await screen.findByRole('button', { name: /choose primary repo/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /create backup plan/i })).not.toBeInTheDocument()
  })

  it('preselects the repository from navigation state and starts a backup with that payload', async () => {
    const user = userEvent.setup()
    locationState = { repositoryPath: '/repos/primary' }

    renderWithProviders(<Backup />)

    expect(await screen.findByRole('tab', { name: /legacy backup/i })).toHaveAttribute(
      'aria-selected',
      'true'
    )
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
    const user = userEvent.setup()

    renderWithProviders(<Backup />)
    await openLegacyBackupTab(user)

    expect(await screen.findByText('choose Primary Repo')).toBeInTheDocument()
    expect(screen.queryByText('choose Observe Repo')).not.toBeInTheDocument()
  })

  it('runs a backup plan from the primary manual backup control', async () => {
    const user = userEvent.setup()
    backupPlansPayload = [
      {
        id: 7,
        name: 'Nightly Plan',
        enabled: true,
        repository_count: 1,
        repository_run_mode: 'series',
        source_directories: ['/data'],
        exclude_patterns: [],
        schedule_enabled: false,
        compression: 'lz4',
      },
    ]

    renderWithProviders(<Backup />)

    const runButton = await screen.findByRole('button', { name: /run backup plan/i })
    await selectBackupPlan(user, /nightly plan/i)
    await waitFor(() => {
      expect(runButton).toBeEnabled()
    })
    await user.click(runButton)

    await waitFor(() => {
      expect(backupPlansRunMock).toHaveBeenCalledWith(7)
    })
    expect(toastSuccess).toHaveBeenCalledWith('Backup plan started')
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('does not select a backup plan by default', async () => {
    backupPlansPayload = [
      {
        id: 7,
        name: 'Nightly Plan',
        enabled: true,
        repository_count: 1,
        repository_run_mode: 'series',
        source_directories: ['/data'],
        exclude_patterns: [],
        schedule_enabled: false,
        compression: 'lz4',
      },
    ]

    renderWithProviders(<Backup />)

    const runButton = await screen.findByRole('button', { name: /run backup plan/i })

    expect(await screen.findByText('Select a backup plan')).toBeInTheDocument()
    expect(screen.queryByText('Nightly Plan')).not.toBeInTheDocument()
    await waitFor(() => {
      expect(runButton).toBeDisabled()
    })
    expect(backupPlansRunMock).not.toHaveBeenCalled()
  })

  it('shows running backup plan runs from every plan regardless of selected plan', async () => {
    const user = userEvent.setup()
    backupPlansPayload = [
      {
        id: 7,
        name: 'Nightly Plan',
        enabled: true,
        repository_count: 1,
        repository_run_mode: 'series',
        source_directories: ['/data'],
        exclude_patterns: [],
        schedule_enabled: false,
        compression: 'lz4',
      },
      {
        id: 8,
        name: 'Weekly Plan',
        enabled: true,
        repository_count: 1,
        repository_run_mode: 'series',
        source_directories: ['/warehouse'],
        exclude_patterns: [],
        schedule_enabled: false,
        compression: 'lz4',
      },
    ]
    backupPlanRunsPayload = [
      {
        id: 99,
        backup_plan_id: 7,
        trigger: 'manual',
        status: 'running',
        started_at: '2026-01-01T10:00:00Z',
        repositories: [
          {
            id: 100,
            repository_id: 1,
            status: 'running',
            repository: {
              id: 1,
              name: 'Primary Repo',
              path: '/repos/primary',
            },
            backup_job: {
              id: 42,
              repository: '/repos/primary',
              repository_id: 1,
              status: 'running',
              progress: 50,
              has_logs: true,
              progress_details: {
                nfiles: 12,
                original_size: 1024,
                backup_speed: 1.5,
                current_file: '/data/file.txt',
              },
            },
          },
        ],
      },
      {
        id: 100,
        backup_plan_id: 8,
        trigger: 'manual',
        status: 'running',
        started_at: '2026-01-01T11:00:00Z',
        repositories: [
          {
            id: 101,
            repository_id: 3,
            status: 'running',
            repository: {
              id: 3,
              name: 'Warehouse Repo',
              path: '/repos/warehouse',
            },
            backup_job: {
              id: 43,
              repository: '/repos/warehouse',
              repository_id: 3,
              status: 'running',
              progress: 25,
              has_logs: true,
              progress_details: {
                nfiles: 3,
                original_size: 2048,
                backup_speed: 2.5,
                current_file: '/warehouse/file.txt',
              },
            },
          },
        ],
      },
    ]

    renderWithProviders(<Backup />)

    await selectBackupPlan(user, /nightly plan/i)

    const activeSection = await screen.findByRole('region', {
      name: /running backup plan runs/i,
    })
    expect(within(activeSection).getByText('Nightly Plan')).toBeInTheDocument()
    expect(within(activeSection).getByText('Weekly Plan')).toBeInTheDocument()
    expect(within(activeSection).getByText('/data/file.txt')).toBeInTheDocument()
    expect(within(activeSection).getByText('/warehouse/file.txt')).toBeInTheDocument()
  })

  it('shows active backup plan runs with per-repository status and cancellation', async () => {
    const user = userEvent.setup()
    backupPlansPayload = [
      {
        id: 7,
        name: 'Nightly Plan',
        enabled: true,
        repository_count: 1,
        repository_run_mode: 'series',
        source_directories: ['/data'],
        exclude_patterns: [],
        schedule_enabled: false,
        compression: 'lz4',
      },
    ]
    backupPlanRunsPayload = [
      {
        id: 99,
        backup_plan_id: 7,
        trigger: 'manual',
        status: 'running',
        started_at: '2026-01-01T10:00:00Z',
        repositories: [
          {
            id: 100,
            repository_id: 1,
            status: 'running',
            repository: {
              id: 1,
              name: 'Primary Repo',
              path: '/repos/primary',
            },
            backup_job: {
              id: 42,
              repository: '/repos/primary',
              repository_id: 1,
              status: 'running',
              progress: 50,
              has_logs: true,
              progress_details: {
                nfiles: 12,
                original_size: 1024,
                backup_speed: 1.5,
                current_file: '/data/file.txt',
              },
            },
          },
        ],
      },
    ]

    renderWithProviders(<Backup />)

    const activeSection = await screen.findByRole('region', { name: /running backup plan runs/i })
    expect(activeSection).toBeInTheDocument()
    expect(within(activeSection).getByText('Nightly Plan')).toBeInTheDocument()
    expect(within(activeSection).getByText('Primary Repo')).toBeInTheDocument()
    expect(within(activeSection).getByText('/data/file.txt')).toBeInTheDocument()

    await user.click(within(activeSection).getByRole('button', { name: /cancel run/i }))

    await waitFor(() => {
      expect(backupPlansCancelRunMock).toHaveBeenCalledWith(99)
    })
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

    await openLegacyBackupTab(user)
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
    const user = userEvent.setup()

    renderWithProviders(<Backup />)
    await openLegacyBackupTab(user)

    expect(await screen.findByText('Recent Manual Jobs')).toBeInTheDocument()
    expect(
      screen.getByText('History of manual backup operations for the selected repository')
    ).toBeInTheDocument()
  })

  it('tracks repository selection and hides manual backup choices when backup permission is missing', async () => {
    const user = userEvent.setup()
    const { unmount } = renderWithProviders(<Backup />)

    await openLegacyBackupTab(user)
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
    await openLegacyBackupTab(user)

    expect(screen.queryByRole('button', { name: /choose primary repo/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start backup/i })).toBeDisabled()
  })

  it('shows the generated borg command preview for the selected repository', async () => {
    const user = userEvent.setup()

    renderWithProviders(<Backup />)

    await openLegacyBackupTab(user)
    await user.click(await screen.findByRole('button', { name: /choose primary repo/i }))

    expect(await screen.findByText(/borg create/i)).toBeInTheDocument()
    expect(screen.getByText(/\/repos\/primary::manual-backup-\{now\}/i)).toBeInTheDocument()
    expect(screen.getByText(/--exclude '\*\.tmp'/i)).toBeInTheDocument()
    expect(screen.getByText(/\/data/i)).toBeInTheDocument()
  })
})
