import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import { ThemeProvider } from '../../context/ThemeContext'
import Settings from '../Settings'

const { authState, currentTab, authorization } = vi.hoisted(() => ({
  authState: {
    user: {
      id: 7,
      username: 'operator-user',
      full_name: 'Operator User',
      email: 'operator@example.com',
      role: 'viewer',
      global_permissions: [] as string[],
    },
  },
  currentTab: { value: 'users' },
  authorization: { isLoading: false },
}))

const trackSettings = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: authState.user,
    hasGlobalPermission: (permission: string) =>
      authState.user.global_permissions.includes(permission),
    refreshUser: vi.fn(),
  }),
}))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    isLoading: authorization.isLoading,
    globalRoleRank: authorization.isLoading
      ? new Map<string, number>()
      : new Map([
          ['viewer', 10],
          ['operator', 20],
          ['admin', 30],
        ]),
    currentGlobalRole: authState.user.role,
  }),
}))

vi.mock('../../components/BackgroundWorkTab', () => ({
  default: () => <div>Background Work Tab</div>,
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSettings,
    EventAction: {
      VIEW: 'View',
    },
  }),
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    can: () => true,
  }),
}))

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn().mockResolvedValue({ data: { settings: {} } }),
    getUsers: vi.fn().mockResolvedValue({ data: { users: [] } }),
    changePassword: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    resetUserPassword: vi.fn(),
  },
}))

vi.mock('../../components/AccountTab', () => ({
  default: () => <div>Account Tab</div>,
}))
vi.mock('../../components/AppearanceTab', () => ({
  default: () => <div>Appearance Tab</div>,
}))
vi.mock('../../components/NotificationsTab', () => ({
  default: () => <div>Notifications Tab</div>,
}))
vi.mock('../../components/PreferencesTab', () => ({
  default: () => <div>Preferences Tab</div>,
}))
vi.mock('../../components/PackagesTab', () => ({
  default: () => <div>Packages Tab</div>,
}))
vi.mock('../../components/ExportImportTab', () => ({
  default: () => <div>Export Tab</div>,
}))
vi.mock('../../components/LogManagementTab', () => ({
  default: () => <div>Logs Tab</div>,
}))
vi.mock('../../components/CacheManagementTab', () => ({
  default: () => <div>Cache Tab</div>,
}))
vi.mock('../../components/MountsManagementTab', () => ({
  default: () => <div>Mounts Tab</div>,
}))
vi.mock('../../components/SystemSettingsTab', () => ({
  default: () => <div>System Tab</div>,
}))
vi.mock('../../components/BetaFeaturesTab', () => ({
  default: () => <div>Beta Tab</div>,
}))
vi.mock('../../components/MqttSettingsTab', () => ({
  default: () => <div>MQTT Tab</div>,
}))
vi.mock('../../components/UsersTab', () => ({
  default: () => <div>User Management</div>,
}))
vi.mock('../Scripts', () => ({
  default: () => <div>Scripts Page</div>,
}))
vi.mock('../Activity', () => ({
  default: () => <div>Activity Page</div>,
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ tab: currentTab.value }),
  }
})

describe('Settings permission routing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    authorization.isLoading = false
    authState.user = {
      ...authState.user,
      role: 'viewer',
      global_permissions: [],
    }
  })

  it('does not flash the account tab while the authorization model is still loading', async () => {
    currentTab.value = 'background-work'
    authState.user = { ...authState.user, role: 'operator' }
    authorization.isLoading = true

    const { rerender } = renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )
    expect(screen.queryByText('Account Tab')).not.toBeInTheDocument()
    expect(screen.queryByText('Background Work Tab')).not.toBeInTheDocument()

    authorization.isLoading = false
    rerender(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )
    expect(await screen.findByText('Background Work Tab')).toBeInTheDocument()
  })

  it('renders the users tab when the user has users permission but not system permission', async () => {
    currentTab.value = 'users'
    authState.user = {
      ...authState.user,
      role: 'admin',
      global_permissions: ['settings.users.manage'],
    }

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    expect(await screen.findByText('User Management')).toBeInTheDocument()
  })

  it('renders the export tab when the user has export permission but not system permission', async () => {
    currentTab.value = 'export'
    authState.user = {
      ...authState.user,
      role: 'admin',
      global_permissions: ['settings.export_import.manage'],
    }

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    expect(await screen.findByText('Export Tab')).toBeInTheDocument()
  })
})
