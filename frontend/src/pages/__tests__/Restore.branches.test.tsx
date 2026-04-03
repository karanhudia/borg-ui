import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Restore from '../Restore'
import * as api from '../../services/api'

const borgListArchivesMock = vi.fn()
const borgGetInfoMock = vi.fn()
const borgGetArchiveInfoMock = vi.fn()
const scrollToMock = vi.fn()

vi.mock('../../components/RepositorySelectorCard', () => ({
  default: ({ onChange }: { onChange: (value: string) => void }) => (
    <button onClick={() => onChange('/repo/one')}>Choose Repo</button>
  ),
}))

vi.mock('../../components/RepositoryInfo', () => ({ default: () => null }))
vi.mock('../../components/RestoreJobCard', () => ({ default: () => null }))
vi.mock('../../components/PathSelectorField', () => ({
  default: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="Destination Path" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}))
vi.mock('../../components/ArchiveBrowserDialog', () => ({
  default: ({ open, archiveName }: { open: boolean; archiveName: string }) =>
    open ? <div>Browser for {archiveName}</div> : null,
}))
vi.mock('../../components/LockErrorDialog', () => ({
  default: ({ open, repositoryName }: { open: boolean; repositoryName: string }) =>
    open ? <div>Lock error for {repositoryName}</div> : null,
}))

vi.mock('../../components/DataTable', () => ({
  default: ({
    data,
    actions,
    emptyState,
  }: {
    data: Array<{ name?: string; id?: number }>
    actions?: Array<{ label: string; onClick: (item: { name?: string; id?: number }) => void }>
    emptyState?: { title?: string }
  }) => (
    <div>
      {data[0] && actions?.[0] ? (
        <button onClick={() => actions[0].onClick(data[0])}>{actions[0].label}</button>
      ) : (
        <span>{emptyState?.title}</span>
      )}
    </div>
  ),
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: class {
    listArchives = borgListArchivesMock
    getInfo = borgGetInfoMock
    getArchiveInfo = borgGetArchiveInfoMock
  },
}))

vi.mock('../../services/api', () => ({
  repositoriesAPI: {
    getRepositories: vi.fn(),
  },
  restoreAPI: {
    getRestoreJobs: vi.fn(),
    startRestore: vi.fn(),
  },
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackArchive: vi.fn(),
    EventAction: {
      FILTER: 'Filter',
      VIEW: 'View',
      START: 'Start',
      STOP: 'Stop',
    },
  }),
}))

const locationState = { current: null as null | Record<string, unknown> }

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    useLocation: () => ({ state: locationState.current, pathname: '/restore' }),
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

describe('Restore page branches', () => {
  const repository = {
    id: 1,
    name: 'Repo One',
    path: '/repo/one',
    borg_version: 2,
  }

  beforeEach(() => {
    vi.clearAllMocks()
    locationState.current = null
    vi.stubGlobal('scrollTo', scrollToMock)
    vi.mocked(api.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [repository] },
    } as never)
    vi.mocked(api.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: { jobs: [] },
    } as never)
    vi.mocked(api.restoreAPI.startRestore).mockResolvedValue({ data: { id: 5 } } as never)
    borgListArchivesMock.mockResolvedValue({
      data: {
        archives: [{ id: 'a1', name: 'archive-1', start: '2026-01-01T00:00:00Z' }],
      },
    })
    borgGetInfoMock.mockResolvedValue({ data: { info: {} } })
    borgGetArchiveInfoMock.mockResolvedValue({
      data: { archive: { stats: { nfiles: 10, original_size: 2048 } } },
    })
  })

  it('preselects the repository from navigation state and auto-opens the archive restore dialog', async () => {
    locationState.current = {
      repositoryPath: '/repo/one',
      repositoryId: 1,
      archiveName: 'archive-1',
    }
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    renderWithProviders(<Restore />, { queryClient })

    expect(await screen.findByText('Restore')).toBeInTheDocument()
    expect(await screen.findByRole('dialog', { name: /restore archive/i })).toBeInTheDocument()
    expect(scrollToMock).toHaveBeenCalledWith(0, 0)
    expect(await screen.findByText('Browser for archive-1')).toBeInTheDocument()
  })

  it('shows the lock dialog when archive loading returns a 423 lock error', async () => {
    const user = userEvent.setup()
    borgListArchivesMock.mockRejectedValue({
      response: { status: 423 },
    })

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    renderWithProviders(<Restore />, { queryClient })

    await user.click(await screen.findByText('Choose Repo'))

    await waitFor(() => {
      expect(screen.getByText('Lock error for Repo One')).toBeInTheDocument()
    })
  })
})
