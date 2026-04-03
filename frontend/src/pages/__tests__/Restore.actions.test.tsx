import { QueryClient } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Restore from '../Restore'
import * as api from '../../services/api'

const trackArchive = vi.fn()
const borgListArchivesMock = vi.fn()
const borgGetInfoMock = vi.fn()
const borgGetArchiveInfoMock = vi.fn()

vi.mock('../../components/RepositorySelectorCard', () => ({
  default: ({ onChange }: { onChange: (value: string) => void }) => (
    <button onClick={() => onChange('/repo/one')}>Choose Repo</button>
  ),
}))

vi.mock('../../components/RepositoryInfo', () => ({ default: () => null }))
vi.mock('../../components/RestoreJobCard', () => ({ default: () => null }))
vi.mock('../../components/LockErrorDialog', () => ({ default: () => null }))
vi.mock('../../components/ArchiveBrowserDialog', () => ({ default: () => null }))

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

vi.mock('../../components/PathSelectorField', () => ({
  default: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => (
    <input aria-label="Destination Path" value={value} onChange={(e) => onChange(e.target.value)} />
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
    trackArchive,
    EventAction: {
      FILTER: 'Filter',
      VIEW: 'View',
      START: 'Start',
      STOP: 'Stop',
    },
  }),
}))

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    useLocation: () => ({ state: null, pathname: '/restore' }),
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

describe('Restore page actions', () => {
  const repository = {
    id: 1,
    name: 'Repo One',
    path: '/repo/one',
    borg_version: 1,
  }

  beforeEach(() => {
    vi.clearAllMocks()
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

  it('tracks filter/start/stop and calls restore API from the restore dialog', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    })

    renderWithProviders(<Restore />, { queryClient })

    await user.click(await screen.findByText('Choose Repo'))
    await waitFor(() => {
      expect(trackArchive).toHaveBeenCalledWith('Filter', repository)
    })

    await user.click(await screen.findByText('Restore'))
    await waitFor(() => {
      expect(trackArchive).toHaveBeenCalledWith('View', repository)
    })

    const destinationInput = await screen.findByLabelText('Destination Path')
    await user.type(destinationInput, '/restore/target')
    await user.click(screen.getByRole('button', { name: /start restore/i }))

    await waitFor(() => {
      expect(api.restoreAPI.startRestore).toHaveBeenCalledWith(
        '/repo/one',
        'archive-1',
        [],
        '/restore/target',
        1
      )
    })
    expect(trackArchive).toHaveBeenCalledWith('Start', repository)

    await user.click(await screen.findByText('Restore'))
    await user.click(screen.getByRole('button', { name: /cancel/i }))
    expect(trackArchive).toHaveBeenCalledWith('Stop', repository)
  })
})
