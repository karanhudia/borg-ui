import { describe, it, expect, vi, beforeEach } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/test-utils'
import AppSidebar from '../AppSidebar'

const {
  mockApiGet,
  mockGetSystemSettings,
  mockListBackupPlans,
  mockSetAppVersion,
  mockTabEnablement,
  mockGetTabDisabledReason,
} = vi.hoisted(() => ({
  mockApiGet: vi.fn().mockResolvedValue({ data: {} }),
  mockGetSystemSettings: vi.fn().mockResolvedValue({ data: { settings: {} } }),
  mockListBackupPlans: vi.fn().mockResolvedValue({ data: { backup_plans: [] } }),
  mockSetAppVersion: vi.fn(),
  mockTabEnablement: {
    dashboard: true,
    connections: true,
    repositories: true,
    backups: true,
    archives: true,
    schedule: true,
  },
  mockGetTabDisabledReason: vi.fn<(key: string) => string | null>(() => null),
}))

vi.mock('../../services/api', () => ({
  default: { get: mockApiGet },
  settingsAPI: {
    getSystemSettings: mockGetSystemSettings,
  },
  backupPlansAPI: {
    list: mockListBackupPlans,
  },
}))

vi.mock('../../utils/analytics', () => ({
  setAppVersion: mockSetAppVersion,
}))

vi.mock('../SidebarVersionInfo', () => ({
  default: () => <div>Sidebar Version Info</div>,
}))

vi.mock('../../context/AppContext', () => ({
  useTabEnablement: () => ({
    tabEnablement: mockTabEnablement,
    getTabDisabledReason: mockGetTabDisabledReason,
  }),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: 'admin',
      email: 'admin@example.com',
      role: 'admin',
      global_permissions: [
        'settings.users.manage',
        'settings.system.manage',
        'settings.mqtt.manage',
        'settings.packages.manage',
        'settings.scripts.manage',
        'settings.export_import.manage',
        'settings.beta.manage',
        'settings.mounts.manage',
        'settings.ssh.manage',
      ],
    },
    hasGlobalPermission: () => true,
  }),
}))

function renderSidebar({
  initialRoute,
  systemSettings = {},
}: {
  initialRoute?: string
  systemSettings?: Record<string, unknown>
} = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity },
      mutations: { retry: false },
    },
  })
  queryClient.setQueryData(['systemSettings'], { settings: systemSettings })
  queryClient.setQueryData(['backup-plans'], { data: { backup_plans: [] } })

  return renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />, {
    initialRoute,
    queryClient,
  })
}

describe('AppSidebar', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    Object.assign(mockTabEnablement, {
      dashboard: true,
      connections: true,
      repositories: true,
      backups: true,
      archives: true,
      schedule: true,
    })
    mockGetTabDisabledReason.mockReturnValue(null)
    mockGetSystemSettings.mockResolvedValue({ data: { settings: {} } })
    mockListBackupPlans.mockResolvedValue({ data: { backup_plans: [] } })
    mockApiGet.mockResolvedValue({
      data: { app_version: '1.78.0', borg_version: 'borg 1.4.0', borg2_version: 'borg2 2.0.0' },
    })
  })

  it('renders the app name', async () => {
    renderSidebar()
    await waitFor(() => expect(screen.getAllByText('Borg UI').length).toBeGreaterThan(0))
  })

  it('renders a link to the dashboard', async () => {
    renderSidebar()
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: /borg ui/i })[0]).toHaveAttribute(
        'href',
        '/dashboard'
      )
    )
  })

  it('renders primary nav items', async () => {
    renderSidebar()
    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /dashboard/i }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('link', { name: /repositories/i }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('link', { name: /cloud storage/i })[0]).toHaveAttribute(
        'href',
        '/cloud-storage'
      )
      expect(screen.getAllByRole('link', { name: /manual backup/i }).length).toBeGreaterThan(0)
      expect(screen.queryAllByRole('link', { name: /managed agents/i })).toHaveLength(0)
    })
  })

  it('shows Managed Agents navigation when its beta flag is enabled', async () => {
    renderSidebar({
      systemSettings: { managed_agents_beta_enabled: true },
    })

    const managedAgentLinks = screen.getAllByRole('link', { name: /managed agents/i })
    expect(managedAgentLinks[0]).toHaveAttribute('href', '/managed-agents')
  })

  it('renders the version info section', async () => {
    renderSidebar()
    await waitFor(() =>
      expect(screen.getAllByText('Sidebar Version Info').length).toBeGreaterThan(0)
    )
  })

  it('fetches system info and forwards the app version to analytics', async () => {
    renderSidebar()

    await waitFor(
      () => {
        expect(mockApiGet).toHaveBeenCalledWith('/system/info')
        expect(mockSetAppVersion).toHaveBeenCalledWith('1.78.0')
      },
      { timeout: 10000 }
    )
  })

  it('shows MQTT settings navigation when enabled', async () => {
    const user = userEvent.setup()
    renderSidebar({
      systemSettings: { mqtt_beta_enabled: true },
    })

    await user.click(await screen.findAllByText('System').then((items) => items[0]))

    expect(await screen.findAllByRole('link', { name: 'MQTT' })).not.toHaveLength(0)
  })

  it('auto-expands the matching settings group for the current route', async () => {
    renderSidebar({
      initialRoute: '/settings/appearance',
    })

    expect(await screen.findAllByRole('link', { name: /appearance/i })).not.toHaveLength(0)
  })

  it('renders disabled tabs without navigation links when the tab is unavailable', async () => {
    mockTabEnablement.repositories = false
    mockGetTabDisabledReason.mockReturnValue('Requires upgrade')

    renderSidebar()

    await waitFor(() => {
      expect(screen.queryAllByRole('link', { name: /repositories/i })).toHaveLength(0)
      expect(screen.getAllByText('Repositories').length).toBeGreaterThan(0)
    })
  })
})
