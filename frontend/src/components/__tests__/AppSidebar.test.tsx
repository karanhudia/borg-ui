import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderWithProviders, screen, waitFor, userEvent } from '../../test/test-utils'
import AppSidebar from '../AppSidebar'

const {
  mockApiGet,
  mockGetSystemSettings,
  mockSetAppVersion,
  mockTabEnablement,
  mockGetTabDisabledReason,
} = vi.hoisted(() => ({
  mockApiGet: vi.fn().mockResolvedValue({ data: {} }),
  mockGetSystemSettings: vi.fn().mockResolvedValue({ data: { settings: {} } }),
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
    mockApiGet.mockResolvedValue({
      data: { app_version: '1.78.0', borg_version: 'borg 1.4.0', borg2_version: 'borg2 2.0.0' },
    })
  })

  it('renders the app name', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getAllByText('Borg UI').length).toBeGreaterThan(0))
  })

  it('renders a link to the dashboard', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getAllByRole('link', { name: /borg ui/i })[0]).toHaveAttribute(
        'href',
        '/dashboard'
      )
    )
  })

  it('renders primary nav items', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getAllByRole('link', { name: /dashboard/i }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('link', { name: /repositories/i }).length).toBeGreaterThan(0)
      expect(screen.getAllByRole('link', { name: /manual backup/i }).length).toBeGreaterThan(0)
    })
  })

  it('renders the version info section', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getAllByText('Sidebar Version Info').length).toBeGreaterThan(0)
    )
  })

  it('fetches system info and forwards the app version to analytics', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(mockApiGet).toHaveBeenCalledWith('/system/info')
      expect(mockSetAppVersion).toHaveBeenCalledWith('1.78.0')
    })
  })

  it('shows restore navigation when enabled in system settings', async () => {
    mockGetSystemSettings.mockResolvedValue({
      data: { settings: { show_restore_tab: true } },
    })

    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)

    expect(await screen.findAllByRole('link', { name: /restore/i })).not.toHaveLength(0)
  })

  it('shows MQTT settings navigation when enabled', async () => {
    const user = userEvent.setup()
    mockGetSystemSettings.mockResolvedValue({
      data: { settings: { mqtt_beta_enabled: true } },
    })

    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)

    await user.click(await screen.findAllByText('System').then((items) => items[0]))

    expect(await screen.findAllByRole('link', { name: 'MQTT' })).not.toHaveLength(0)
  })

  it('auto-expands the matching settings group for the current route', async () => {
    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />, {
      initialRoute: '/settings/appearance',
    })

    expect(await screen.findAllByRole('link', { name: /appearance/i })).not.toHaveLength(0)
  })

  it('renders disabled tabs without navigation links when the tab is unavailable', async () => {
    mockTabEnablement.repositories = false
    mockGetTabDisabledReason.mockReturnValue('Requires upgrade')

    renderWithProviders(<AppSidebar mobileOpen={false} onClose={vi.fn()} />)

    await waitFor(() => {
      expect(screen.queryAllByRole('link', { name: /repositories/i })).toHaveLength(0)
      expect(screen.getAllByText('Repositories').length).toBeGreaterThan(0)
    })
  })
})
