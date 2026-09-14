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
import type { OperationItem } from '../../types/operations'

const getInfoMock = vi.fn()
const listStoredMock = vi.fn()
const getHeatmapMock = vi.fn()

vi.mock('../../components/RepositorySelectorCard', () => ({
  default: ({ onChange }: { onChange: (id: number) => void }) => (
    <button onClick={() => onChange(1)}>Select Repo</button>
  ),
}))
const statsProps: Array<Record<string, unknown>> = []
vi.mock('../../components/RepositoryStats', () => ({
  default: (props: Record<string, unknown>) => {
    statsProps.push(props)
    return <div data-testid="stats-grid" />
  },
}))
const operationEventHandlers: { onUpdated: ((op: OperationItem) => void) | null } = {
  onUpdated: null,
}
vi.mock('../../hooks/useOperationEvents', () => ({
  useOperationEvents: (onUpdated: (op: OperationItem) => void) => {
    operationEventHandlers.onUpdated = onUpdated
  },
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
vi.mock('../../components/archives/ArchiveHourlyHeatmap', () => ({
  default: () => <div data-testid="archive-hourly-heatmap" />,
}))

vi.mock('../../services/api', () => ({
  archivesAPI: {
    listStored: vi.fn(),
    getHeatmap: vi.fn(),
    rebuild: vi.fn(),
    deleteArchive: vi.fn(),
    downloadFile: vi.fn(),
  },
  repositoriesAPI: {
    getRepositories: vi.fn(),
    getStorage: vi.fn(),
  },
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

const listStorage = { size_bytes: 1024 * 100, original_size: null }
const detailStorage = { size_bytes: 1024 * 100, original_size: 1000 }

const mockRepository = {
  id: 1,
  name: 'My Backups',
  path: '/backup/repo',
  location: '/backup/repo',
  archive_count: 1,
  last_modified: '2024-01-15T10:00:00Z',
  size: 1024 * 100,
  storage: listStorage,
  index_pending_kinds: ['stats'],
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
    repository: { days: [], missed_days: [], first: null, last: null, count: 0 },
    series: [],
    cadence_known: false,
    retention_since: null,
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

    statsProps.length = 0
    vi.mocked(apiModule.repositoriesAPI.getRepositories).mockResolvedValue({
      data: { repositories: [mockRepository] },
    } as never)
    vi.mocked(apiModule.repositoriesAPI.getStorage).mockResolvedValue({
      data: { repository_id: 1, storage: detailStorage, index_pending_kinds: [] },
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

  it('hands the header the detail storage once it arrives, the list columns before', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => {
      const last = statsProps[statsProps.length - 1]
      expect(last?.storage).toEqual(detailStorage)
    })
    expect(statsProps.some((p) => p.storage === listStorage)).toBe(true)
    const last = statsProps[statsProps.length - 1]
    // the pending kinds follow the detail too, so the placeholders clear
    expect(last.indexPendingKinds).toEqual([])
    expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledWith(1)
  })

  it('keeps an explicit null from the detail instead of the list columns', async () => {
    vi.mocked(apiModule.repositoriesAPI.getStorage).mockResolvedValue({
      data: { repository_id: 1, storage: null, index_pending_kinds: [] },
    } as never)
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => expect(statsProps[statsProps.length - 1]?.storage).toBeNull())
  })

  it('falls back to the list columns when the detail cannot be read', async () => {
    vi.mocked(apiModule.repositoriesAPI.getStorage).mockRejectedValue(new Error('offline'))
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByTestId('stats-grid')).toBeInTheDocument())
    expect(statsProps[statsProps.length - 1]?.storage).toEqual(listStorage)
  })

  it('passes no archive count when the stored list could not be read', async () => {
    listStoredMock.mockRejectedValue(new Error('lost'))
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => expect(statsProps[statsProps.length - 1]?.archiveCount).toBeNull())
  })

  it('refreshes the detail and the list when index work of the repository ends, failed included', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    // the first read plus the refetch the live info's sync triggers
    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(2))
    const listCalls = vi.mocked(apiModule.repositoriesAPI.getRepositories).mock.calls.length

    operationEventHandlers.onUpdated?.({
      id: 7,
      kind: 'archive_sync',
      category: 'index',
      status: 'failed',
      repository_id: 1,
    } as OperationItem)

    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(3), {
      timeout: 4000,
    })
    await waitFor(() =>
      expect(
        vi.mocked(apiModule.repositoriesAPI.getRepositories).mock.calls.length
      ).toBeGreaterThan(listCalls)
    )
    // another repository's work is not this page's business, not even
    // after the debounce a refresh of its own would have waited for
    operationEventHandlers.onUpdated?.({
      id: 8,
      kind: 'stats',
      category: 'index',
      status: 'completed',
      repository_id: 2,
    } as OperationItem)
    await new Promise((resolve) => setTimeout(resolve, 1800))
    expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(3)
  })

  it('refetches the figures once the live info has synced the stored columns', async () => {
    let resolveInfo: (value: unknown) => void = () => {}
    getInfoMock.mockReturnValue(
      new Promise((resolve) => {
        resolveInfo = resolve
      })
    )
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(1))

    resolveInfo({ data: { info: {} } })

    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(2))
  })

  it('refetches the figures when index work is queued, so the header can say indexing', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    await waitFor(() => expect(screen.getByTestId('stats-grid')).toBeInTheDocument())
    await waitFor(() => expect(getInfoMock).toHaveBeenCalled())
    await new Promise((resolve) => setTimeout(resolve, 100))
    const before = vi.mocked(apiModule.repositoriesAPI.getStorage).mock.calls.length

    operationEventHandlers.onUpdated?.({
      id: 21,
      kind: 'archive_sync',
      category: 'index',
      status: 'queued',
      repository_id: 1,
    } as OperationItem)

    await waitFor(
      () =>
        expect(vi.mocked(apiModule.repositoriesAPI.getStorage).mock.calls.length).toBeGreaterThan(
          before
        ),
      { timeout: 4000 }
    )
  })

  it('refetches the figures once for a burst of index stages ending together', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    // the first read plus the refetch the live info's sync triggers
    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(2))

    for (const [id, kind] of [
      [11, 'stats'],
      [12, 'archive_sync'],
      [13, 'history_merge'],
    ] as const) {
      operationEventHandlers.onUpdated?.({
        id,
        kind,
        category: 'index',
        status: 'completed',
        repository_id: 1,
      } as OperationItem)
    }

    await waitFor(() => expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(3), {
      timeout: 4000,
    })
    // past the debounce again: the burst's one refetch was the only one
    await new Promise((resolve) => setTimeout(resolve, 1800))
    expect(apiModule.repositoriesAPI.getStorage).toHaveBeenCalledTimes(3)
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

  it('shows no restore strip when the repository has never been restored', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    await waitFor(() => expect(screen.getByTestId('archive-series-heatmap')).toBeInTheDocument())
    expect(screen.queryByText(/no recent restores/i)).not.toBeInTheDocument()
  })

  it('switches the heatmap to hours and remembers it', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    await waitFor(() => expect(screen.getByTestId('archive-series-heatmap')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^hours$/i }))
    expect(screen.getByTestId('archive-hourly-heatmap')).toBeInTheDocument()
    expect(localStorage.getItem('archives-heatmap-scale')).toBe('hours')
    localStorage.removeItem('archives-heatmap-scale')
  })

  it('links to the repository operations view from the toolbar', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()
    await user.click(screen.getByText('Select Repo'))
    expect(await screen.findByRole('link', { name: /operations/i })).toHaveAttribute(
      'href',
      '/activity?repository_id=1'
    )
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
