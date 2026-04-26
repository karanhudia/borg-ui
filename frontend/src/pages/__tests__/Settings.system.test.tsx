import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../context/ThemeContext'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import Settings from '../Settings'
import * as apiModule from '../../services/api'

const trackSettings = vi.fn()
const trackSystem = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      username: 'admin',
      email: 'admin@example.com',
      role: 'admin',
      global_permissions: ['settings.system.manage'],
    },
    hasGlobalPermission: (permission: string) => permission === 'settings.system.manage',
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSettings,
    trackSystem,
    EventAction: {
      VIEW: 'View',
      CREATE: 'Create',
      EDIT: 'Edit',
      DELETE: 'Delete',
    },
  }),
}))

vi.mock('../../components/AccountTab', () => ({ default: () => null }))
vi.mock('../../components/AppearanceTab', () => ({ default: () => null }))
vi.mock('../../components/NotificationsTab', () => ({ default: () => null }))
vi.mock('../../components/PreferencesTab', () => ({ default: () => null }))
vi.mock('../../components/PackagesTab', () => ({ default: () => null }))
vi.mock('../../components/ExportImportTab', () => ({ default: () => null }))
vi.mock('../../components/LogManagementTab', () => ({ default: () => null }))
vi.mock('../../components/CacheManagementTab', () => ({ default: () => null }))
vi.mock('../../components/MountsManagementTab', () => ({ default: () => null }))
vi.mock('../../components/LicensingTab', () => ({ default: () => null }))
vi.mock('../../components/BetaFeaturesTab', () => ({ default: () => null }))
vi.mock('../../components/MqttSettingsTab', () => ({ default: () => null }))
vi.mock('../../components/UsersTab', () => ({ default: () => null }))
vi.mock('../Scripts', () => ({ default: () => null }))
vi.mock('../Activity', () => ({ default: () => null }))

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn(),
    getCacheStats: vi.fn(),
    updateCacheSettings: vi.fn(),
    updateSystemSettings: vi.fn(),
    refreshAllStats: vi.fn(),
  },
  authAPI: {
    getAuthConfig: vi.fn(),
  },
  authAPIAdmin: {
    listEvents: vi.fn(),
  },
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ tab: 'system' }),
  }
})

describe('Settings system auth admin UX', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiModule.settingsAPI.getSystemSettings).mockResolvedValue({
      data: {
        settings: {
          oidc_client_secret_set: true,
          oidc_enabled: true,
          oidc_provider_name: 'Authentik',
        },
      },
    } as never)
    vi.mocked(apiModule.settingsAPI.getCacheStats).mockResolvedValue({
      data: {
        browse_max_items: 1000000,
        browse_max_memory_mb: 1024,
      },
    } as never)
    vi.mocked(apiModule.settingsAPI.updateCacheSettings).mockResolvedValue({ data: {} } as never)
    vi.mocked(apiModule.settingsAPI.updateSystemSettings).mockResolvedValue({ data: {} } as never)
    vi.mocked(apiModule.settingsAPI.refreshAllStats).mockResolvedValue({ data: {} } as never)
    vi.mocked(apiModule.authAPI.getAuthConfig).mockResolvedValue({
      data: {
        proxy_auth_enabled: false,
        insecure_no_auth_enabled: false,
        authentication_required: true,
      },
    } as never)
    vi.mocked(apiModule.authAPIAdmin.listEvents).mockResolvedValue({
      data: [
        {
          id: 1,
          event_type: 'oidc_user_pending',
          auth_source: 'oidc',
          username: 'alice',
          email: 'alice@example.com',
          success: false,
          detail: 'Awaiting admin approval',
          actor_user_id: null,
          created_at: '2026-04-25T10:00:00Z',
        },
        {
          id: 2,
          event_type: 'local_login_failed',
          auth_source: 'local',
          username: 'bob',
          email: 'bob@example.com',
          success: false,
          detail: 'Incorrect password',
          actor_user_id: null,
          created_at: '2026-04-25T11:00:00Z',
        },
        {
          id: 3,
          event_type: 'oidc_login_succeeded',
          auth_source: 'oidc',
          username: 'carol',
          email: 'carol@example.com',
          success: true,
          detail: null,
          actor_user_id: 1,
          created_at: '2026-04-25T12:00:00Z',
        },
      ],
    } as never)
  })

  it('shows readable auth events and client-side filters in the OIDC admin section', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('System Settings')

    await user.click(screen.getByRole('tab', { name: /single sign-on/i }))

    await waitFor(() => {
      expect(apiModule.authAPIAdmin.listEvents).toHaveBeenCalledWith(20)
    })

    await screen.findByText('OIDC user pending approval')
    expect(screen.getByText('Pending: 1')).toBeInTheDocument()
    expect(screen.getByText('Local login failed')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /pending approvals/i }))

    await screen.findByText('Awaiting admin approval')
    expect(screen.queryByText('Local login failed')).not.toBeInTheDocument()
    expect(screen.queryByText('OIDC login succeeded')).not.toBeInTheDocument()
  })
})
