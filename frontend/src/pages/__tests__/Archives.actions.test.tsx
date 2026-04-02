import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Archives from '../Archives'
import * as apiModule from '../../services/api'

const trackArchive = vi.fn()
const borgListArchivesMock = vi.fn()
const borgGetInfoMock = vi.fn()

vi.mock('../../components/RepositorySelectorCard', () => ({
  default: ({ onChange }: { onChange: (id: number) => void }) => (
    <button onClick={() => onChange(1)}>Select Repo</button>
  ),
}))

vi.mock('../../components/RepositoryStatsGrid', () => ({ default: () => <div>Stats</div> }))
vi.mock('../../components/LastRestoreSection', () => ({ default: () => null }))
vi.mock('../../components/LockErrorDialog', () => ({ default: () => null }))

vi.mock('../../components/ArchivesList', () => ({
  default: ({
    onViewArchive,
    onRestoreArchive,
    onMountArchive,
  }: {
    onViewArchive: (archive: { name: string; start: string }) => void
    onRestoreArchive: (archive: { name: string; start: string }) => void
    onMountArchive: (archive: { name: string; start: string }) => void
  }) => {
    const archive = { name: 'archive-1', start: '2026-01-01T00:00:00Z' }
    return (
      <div>
        <button onClick={() => onViewArchive(archive)}>View Archive</button>
        <button onClick={() => onRestoreArchive(archive)}>Restore Archive</button>
        <button onClick={() => onMountArchive(archive)}>Mount Archive</button>
      </div>
    )
  },
}))

vi.mock('../../components/ArchiveContentsDialog', () => ({
  default: ({
    open,
    onDownloadFile,
  }: {
    open: boolean
    onDownloadFile: (archiveName: string, filePath: string) => void
  }) =>
    open ? (
      <button onClick={() => onDownloadFile('archive-1', '/etc/hosts')}>Download File</button>
    ) : null,
}))

vi.mock('../../components/MountArchiveDialog', () => ({
  default: ({ open, onConfirm }: { open: boolean; onConfirm: () => void }) =>
    open ? <button onClick={onConfirm}>Confirm Mount</button> : null,
}))

vi.mock('../../components/DeleteArchiveDialog', () => ({ default: () => null }))

vi.mock('../../components/RestoreWizard', () => ({
  default: ({
    open,
    onRestore,
  }: {
    open: boolean
    onRestore: (data: {
      restore_strategy: string
      custom_path?: string
      selected_paths: string[]
      destination_type: string
      destination_connection_id: number | null
    }) => void
  }) =>
    open ? (
      <button
        onClick={() =>
          onRestore({
            restore_strategy: 'custom',
            custom_path: '/restore/here',
            selected_paths: ['/var/lib/app'],
            destination_type: 'local',
            destination_connection_id: null,
          })
        }
      >
        Confirm Restore
      </button>
    ) : null,
}))

vi.mock('../../hooks/useRepositoryStats', () => ({
  useRepositoryStats: () => ({ totalSize: 1 }),
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: vi.fn().mockImplementation(() => ({
    listArchives: borgListArchivesMock,
    getInfo: borgGetInfoMock,
  })),
}))

vi.mock('../../services/api', () => ({
  archivesAPI: {
    deleteArchive: vi.fn(),
    downloadFile: vi.fn(),
  },
  repositoriesAPI: {
    getRepositories: vi.fn(),
  },
  mountsAPI: {
    mountBorgArchive: vi.fn(),
  },
  restoreAPI: {
    getRestoreJobs: vi.fn(),
    startRestore: vi.fn(),
  },
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackArchive,
    EventAction: {
      FILTER: 'Filter',
      VIEW: 'View',
      START: 'Start',
      MOUNT: 'Mount',
    },
  }),
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    useLocation: () => ({ state: null, pathname: '/archives' }),
  }
})

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('Archives page actions', () => {
  const repository = {
    id: 1,
    name: 'Repo One',
    path: '/repo/one',
    borg_version: 1,
    mode: 'full',
    repository_type: 'local',
  }

  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiModule.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [repository] },
    } as never)
    vi.mocked(apiModule.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: { jobs: [] },
    } as never)
    vi.mocked(apiModule.restoreAPI.startRestore).mockResolvedValue({
      data: { job_id: 42 },
    } as never)
    vi.mocked(apiModule.mountsAPI.mountBorgArchive).mockResolvedValue({
      data: { mount_point: '/mnt/archive-1' },
    } as never)
    borgListArchivesMock.mockResolvedValue({
      data: {
        archives: [{ id: 'a1', name: 'archive-1', start: '2026-01-01T00:00:00Z' }],
      },
    })
    borgGetInfoMock.mockResolvedValue({ data: { info: {} } })
  })

  it('tracks filter/view and calls download, restore, and mount APIs from archive actions', async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })
    const user = userEvent.setup()

    renderWithProviders(<Archives />, { queryClient })

    await user.click(await screen.findByText('Select Repo'))

    await waitFor(() => {
      expect(trackArchive).toHaveBeenCalledWith('Filter', repository)
    })

    await user.click(screen.getByText('View Archive'))
    await user.click(await screen.findByText('Download File'))

    expect(apiModule.archivesAPI.downloadFile).toHaveBeenCalledWith(
      '/repo/one',
      'archive-1',
      '/etc/hosts'
    )
    expect(trackArchive).toHaveBeenCalledWith('View', repository)

    await user.click(screen.getByText('Restore Archive'))
    await user.click(await screen.findByText('Confirm Restore'))

    await waitFor(() => {
      expect(apiModule.restoreAPI.startRestore).toHaveBeenCalledWith(
        '/repo/one',
        'archive-1',
        ['/var/lib/app'],
        '/restore/here',
        1,
        'local',
        null
      )
    })
    expect(trackArchive).toHaveBeenCalledWith('Start', repository)

    await user.click(screen.getByText('Mount Archive'))
    await user.click(await screen.findByText('Confirm Mount'))

    await waitFor(() => {
      expect(apiModule.mountsAPI.mountBorgArchive).toHaveBeenCalledWith({
        repository_id: 1,
        archive_name: 'archive-1',
        mount_point: 'archive-1',
      })
    })
    expect(trackArchive).toHaveBeenCalledWith('Mount', repository)
  })
})
