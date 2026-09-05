/**
 * Archives page: the database-backed heatmap/list view (spec 10.3).
 *
 * The page reads `archivesAPI.listStored` instead of the live
 * `BorgApiClient.listArchives()`, defaults to the heatmap, and lets the user
 * switch to the list view with the choice persisted to `localStorage`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient } from '@tanstack/react-query'
import { renderWithProviders } from '../../test/test-utils'
import Archives from '../Archives'
import * as apiModule from '../../services/api'

const getInfoMock = vi.fn()
const listStoredMock = vi.fn()
const getHeatmapMock = vi.fn()

vi.mock('../../components/RepositorySelectorCard', () => ({
  default: ({ onChange }: { onChange: (id: number) => void }) => (
    <button onClick={() => onChange(1)}>Select Repo</button>
  ),
}))
vi.mock('../../components/RepositoryStatsGrid', () => ({
  default: () => <div data-testid="stats-grid" />,
}))
vi.mock('../../components/LastRestoreSection', () => ({ default: () => null }))
vi.mock('../../components/ArchiveContentsDialog', () => ({ default: () => null }))
vi.mock('../../components/MountArchiveDialog', () => ({ default: () => null }))
vi.mock('../../components/LockErrorDialog', () => ({ default: () => null }))
vi.mock('../../components/RestoreWizard', () => ({ default: () => null }))
vi.mock('../../components/ArchivesList', () => ({
  default: () => <div data-testid="archives-list" />,
}))
vi.mock('../../components/archives/SyncStateChip', () => ({
  default: ({ state }: { state: string }) => <div data-testid="sync-state-chip">{state}</div>,
}))
vi.mock('../../components/archives/ArchiveSearchField', () => ({
  default: () => <div data-testid="archive-search-field" />,
}))
vi.mock('../../components/archives/ArchiveSeriesHeatmap', () => ({
  default: () => <div data-testid="archive-series-heatmap" />,
}))

vi.mock('../../services/api', () => ({
  archivesAPI: {
    listStored: vi.fn(),
    getHeatmap: vi.fn(),
    rebuild: vi.fn(),
    deleteArchive: vi.fn(),
    downloadFile: vi.fn(),
  },
  repositoriesAPI: { getRepositories: vi.fn() },
  mountsAPI: { mountBorgArchive: vi.fn() },
  restoreAPI: { getRestoreJobs: vi.fn() },
}))

vi.mock('../../services/borgApi', () => ({
  BorgApiClient: vi.fn(function MockBorgApiClient() {
    return { getInfo: getInfoMock }
  }),
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
    EventAction: { VIEW: 'view', FILTER: 'filter' },
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

const storedResponse = {
  data: {
    archives: [
      {
        id: 1,
        repository_id: 1,
        borg_id: 'abc123',
        name: 'backup-2026-01-01',
        series: 'default',
        start: '2026-01-01T00:00:00Z',
        end: '2026-01-01T00:05:00Z',
        duration_seconds: 300,
        nfiles: 10,
        original_size: 1000,
        compressed_size: 500,
        deduplicated_size: 400,
        hostname: null,
        username: null,
        comment: null,
        backup_operation_id: null,
        history_state: 'indexed',
        history_indexed_at: null,
        history_rows: null,
        history_truncated: false,
        first_seen_at: null,
        last_seen_at: null,
      },
    ],
    series: ['default'],
    sync_state: 'fresh',
    last_synced_at: '2026-01-01T00:10:00Z',
    history_available: true,
  },
}

const heatmapResponse = {
  data: {
    since: null,
    until: null,
    series: [],
    flags_available: { missed_run: false, size_outlier: false, duration_outlier: false },
  },
}

describe('Archives page, database-backed view (spec 10.3)', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    localStorage.clear()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false },
      },
    })

    vi.mocked(apiModule.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [mockRepository] },
    } as never)
    vi.mocked(apiModule.restoreAPI.getRestoreJobs).mockResolvedValue({
      data: { jobs: [] },
    } as never)
    getInfoMock.mockResolvedValue({ data: { info: {} } })
    listStoredMock.mockResolvedValue(storedResponse)
    getHeatmapMock.mockResolvedValue(heatmapResponse)
    vi.mocked(apiModule.archivesAPI.listStored).mockImplementation(listStoredMock)
    vi.mocked(apiModule.archivesAPI.getHeatmap).mockImplementation(getHeatmapMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.clearAllMocks()
  })

  it('reads the stored archive list instead of the live borg listing', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()

    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => {
      expect(listStoredMock).toHaveBeenCalledWith(1)
    })
  })

  it('renders the heatmap and sync chip by default', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()

    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => {
      expect(screen.getByTestId('archive-series-heatmap')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('archives-list')).not.toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByTestId('sync-state-chip')).toHaveTextContent('fresh')
    })
  })

  it('switches to the list view and persists the choice', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()

    await user.click(screen.getByText('Select Repo'))
    await waitFor(() => {
      expect(screen.getByTestId('archive-series-heatmap')).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: 'List' }))

    await waitFor(() => {
      expect(screen.getByTestId('archives-list')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('archive-series-heatmap')).not.toBeInTheDocument()
    expect(localStorage.getItem('archives-view-mode')).toBe('list')
  })

  it('honours a persisted list view preference on mount', async () => {
    localStorage.setItem('archives-view-mode', 'list')
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()

    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => {
      expect(listStoredMock).toHaveBeenCalledWith(1)
    })
    await waitFor(() => {
      expect(screen.getByTestId('archives-list')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('archive-series-heatmap')).not.toBeInTheDocument()
  })
})
