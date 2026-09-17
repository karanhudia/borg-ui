import { beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { renderWithProviders, screen, waitFor } from '../../test/test-utils'
import LogManagementTab from '../LogManagementTab'

const getSystemSettingsMock = vi.fn()
const getLogStorageStatsMock = vi.fn()

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: () => getSystemSettingsMock(),
    getLogStorageStats: () => getLogStorageStatsMock(),
    updateSystemSettings: vi.fn(),
    manualLogCleanup: vi.fn(),
  },
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return { ...actual, toast: { success: vi.fn(), error: vi.fn() } }
})

const settings = {
  settings: {
    log_retention_days: 30,
    log_save_policy: 'failed_and_warnings',
    log_max_total_size_mb: 500,
    log_cleanup_on_startup: true,
    cleanup_retention_days: 90,
  },
}

const storage = {
  storage: {
    total_size_mb: 42.7,
    file_count: 128,
    oldest_log_date: '2026-01-05T04:00:00+00:00',
    newest_log_date: '2026-01-31T02:15:00+00:00',
    usage_percent: 9,
    files_by_type: { backup: 96 },
    limit_mb: 500,
    retention_days: 30,
  },
}

describe('LogManagementTab storage figures', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getSystemSettingsMock.mockResolvedValue({ data: settings })
  })

  it('shows the figures from the storage route', async () => {
    getLogStorageStatsMock.mockResolvedValue({ data: storage })
    renderWithProviders(<LogManagementTab />)

    await waitFor(() => expect(screen.getByText('128')).toBeInTheDocument())
    expect(screen.getByText('Total Size')).toBeInTheDocument()
    expect(screen.queryByText(/unavailable right now/)).not.toBeInTheDocument()
  })

  it('keeps the last figures and warns when a refetch fails', async () => {
    getLogStorageStatsMock.mockResolvedValue({ data: storage })
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    renderWithProviders(<LogManagementTab />, { queryClient })
    await waitFor(() => expect(screen.getByText('128')).toBeInTheDocument())

    getLogStorageStatsMock.mockRejectedValue(new Error('500'))
    await queryClient.refetchQueries({ queryKey: ['log-storage-stats'] })

    await waitFor(() => expect(screen.getByText(/unavailable right now/)).toBeInTheDocument())
    // the stale figures stay, under the warning
    expect(screen.getByText('128')).toBeInTheDocument()
  })

  it('warns instead of showing zero figures when the route answers without them', async () => {
    getLogStorageStatsMock.mockResolvedValue({ data: {} })
    renderWithProviders(<LogManagementTab />)

    await waitFor(() => expect(screen.getByText(/unavailable right now/)).toBeInTheDocument())
    expect(screen.queryByText('Total Size')).not.toBeInTheDocument()
  })

  it('warns instead of showing zero figures when the route fails from the start', async () => {
    getLogStorageStatsMock.mockRejectedValue(new Error('500'))
    renderWithProviders(<LogManagementTab />)

    await waitFor(() => expect(screen.getByText(/unavailable right now/)).toBeInTheDocument())
    // no figure grid whose zeros would read as an empty store
    expect(screen.queryByText('Total Size')).not.toBeInTheDocument()
    // the cleanup stays reachable
    expect(screen.getByRole('button', { name: /Run Cleanup Now/ })).toBeInTheDocument()
  })
})
